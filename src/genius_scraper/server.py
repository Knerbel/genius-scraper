import json
import logging
import threading
from collections.abc import Callable
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from time import sleep
from typing import Any

from .config import Settings
from .db.session import init_db, make_session_factory
from .graph import write_graph_html
from .scraper.client import GeniusClient

MAX_BODY_BYTES = 4096

log = logging.getLogger(__name__)

CrawlFunc = Callable[..., dict[int, dict[str, Any]]]


def resolve_query(client: GeniusClient, query: str) -> dict[str, Any] | None:
    """Maps a free-text song or artist name to a song to start crawling from."""
    hits = client.search(query)
    if not hits:
        return None
    wanted = query.strip().casefold()

    for hit in hits:
        artist = hit["result"]["primary_artist"]
        if artist["name"].casefold() != wanted:
            continue
        song = client.get_most_popular_song(artist["id"])
        if song:
            return {"song_id": song["id"], "title": song["title"],
                    "artist": artist["name"], "matched": "artist"}

    for hit in hits:
        result = hit["result"]
        if wanted in (result["title"].casefold(), result.get("full_title", "").casefold()):
            return {"song_id": result["id"], "title": result["title"],
                    "artist": result["primary_artist"]["name"], "matched": "song"}

    result = hits[0]["result"]
    return {"song_id": result["id"], "title": result["title"],
            "artist": result["primary_artist"]["name"], "matched": "song"}


class CrawlRunner:
    """Runs one crawl at a time in a background thread, rewriting the graph file."""

    def __init__(self, settings: Settings, output: Path, max_songs: int, crawl: CrawlFunc):
        self._settings = settings
        self._output = output
        self._max_songs = max_songs
        self._crawl = crawl
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._state: dict[str, Any] = {"state": "idle"}

    @property
    def busy(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def status(self) -> dict[str, Any]:
        return {**self._state, "max_songs": self._max_songs}

    def start(self, query: str) -> dict[str, Any]:
        with self._lock:
            if self.busy:
                raise RuntimeError("A scrape is already running.")
            client = GeniusClient(
                self._settings.genius_access_token, self._settings.request_delay)
            match = resolve_query(client, query)
            if match is None:
                raise LookupError(f"Nothing found on Genius for {query!r}.")
            self._state = {**match, "state": "running", "scanned": 0}
            self._thread = threading.Thread(
                target=self._run, args=(client, match["song_id"]), daemon=True)
            self._thread.start()
            return match

    def _run(self, client: GeniusClient, song_id: int) -> None:
        def on_update(current: dict[int, dict[str, Any]]) -> None:
            self._state["scanned"] = len(current)
            write_graph_html(current, song_id, self._output, refresh=True)

        try:
            session_factory = make_session_factory(self._settings.database_url)
            results = self._crawl(
                client, song_id, self._max_songs, session_factory, on_update=on_update)
            write_graph_html(results, song_id, self._output)
            self._state.update(state="done", scanned=len(results))
            log.info("Graph written to %s", self._output.resolve())
        except Exception as error:
            self._state.update(state="error", error=str(error))
            log.exception("Scrape for song %d failed", song_id)


class _Handler(BaseHTTPRequestHandler):
    server_version = "genius-scraper"

    def __init__(self, *args, runner: CrawlRunner, output: Path, **kwargs):
        self._runner = runner
        self._output = output
        super().__init__(*args, **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        log.debug("%s %s", self.address_string(), format % args)

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        self._send(status, json.dumps(payload).encode(), "application/json")

    def _read_graph(self, attempts: int = 20) -> bytes | None:
        # The file briefly disappears while a progress update replaces it
        for attempt in range(attempts):
            try:
                return self._output.read_bytes()
            except OSError:
                if attempt == attempts - 1:
                    return None
                sleep(0.05)
        return None

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        if path == "/status":
            self._send_json(200, self._runner.status())
            return
        if path not in ("/", "/index.html", f"/{self._output.name}"):
            self._send_json(404, {"error": "Not found"})
            return
        body = self._read_graph()
        if body is None:
            self._send_json(503, {"error": "Graph not readable right now"})
            return
        self._send(200, body, "text/html; charset=utf-8")

    def do_POST(self) -> None:
        if self.path.split("?")[0] != "/search":
            self._send_json(404, {"error": "Not found"})
            return
        # Requiring JSON blocks plain cross-site form posts to this local server
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            self._send_json(415, {"error": "Expected application/json"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY_BYTES:
            self._send_json(413, {"error": "Request too large"})
            return
        try:
            query = json.loads(self.rfile.read(
                length) or b"{}").get("query", "")
        except (ValueError, UnicodeDecodeError):
            self._send_json(400, {"error": "Invalid JSON"})
            return
        if not isinstance(query, str) or not query.strip():
            self._send_json(400, {"error": "Enter a song or artist name."})
            return
        try:
            match = self._runner.start(query)
        except RuntimeError as error:
            self._send_json(409, {"error": str(error)})
        except LookupError as error:
            self._send_json(404, {"error": str(error)})
        except Exception as error:
            log.exception("Search for %r failed", query)
            self._send_json(502, {"error": f"Genius lookup failed: {error}"})
        else:
            self._send_json(202, match)


def serve(settings: Settings, output: Path, max_songs: int, crawl: CrawlFunc,
          host: str = "127.0.0.1", port: int = 8000) -> None:
    init_db(settings.database_url)
    if not output.exists():
        write_graph_html({}, 0, output)
    runner = CrawlRunner(settings, output, max_songs, crawl)
    handler = partial(_Handler, runner=runner, output=output)
    with ThreadingHTTPServer((host, port), handler) as httpd:
        log.info("Serving graph on http://%s:%d/ (Ctrl+C to stop)", host, port)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            log.info("Stopping server")
