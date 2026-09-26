import argparse
import json
import logging
from collections import deque
from pathlib import Path
from typing import Any

from .config import load_settings
from .db.session import init_db, make_session_factory
from .graph import write_graph_html
from .pipeline import scrape_artist
from .scraper.client import GeniusClient
from .scraper.extractor import ARTIST_URL_RE, iter_link_attributes


def main() -> None:
    parser = argparse.ArgumentParser(prog="genius-scraper")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="Create database tables")

    p_artist = sub.add_parser(
        "scrape-artist", help="Scrape songs and references of an artist")
    p_artist.add_argument("name")
    p_artist.add_argument("--max-songs", type=int, default=None)

    p_song = sub.add_parser(
        "song-annotations",
        help="Follow artist references starting from a song, up to --max-songs songs")
    p_song.add_argument("song_id", type=int)
    p_song.add_argument("--max-songs", type=int, default=10,
                        help="Stop after this many songs have been scanned (default: 10)")
    p_song.add_argument("--output", type=Path, default=Path("graph.html"),
                        help="Where to write the HTML graph (default: graph.html)")

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = load_settings()

    if args.command == "init-db":
        init_db(settings.database_url)
    elif args.command == "scrape-artist":
        init_db(settings.database_url)
        client = GeniusClient(settings.genius_access_token,
                              settings.request_delay)
        scrape_artist(client, make_session_factory(
            settings.database_url), args.name, args.max_songs)
    elif args.command == "song-annotations":
        client = GeniusClient(settings.genius_access_token,
                              settings.request_delay)
        results = crawl_song_references(
            client, args.song_id, args.max_songs)
        write_graph_html(results, args.song_id, args.output)
        logging.getLogger(__name__).info(
            "Graph written to %s", args.output.resolve())


def collect_referenced_artists(
    client: GeniusClient, song_id: int
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Returns artist URL -> annotation IDs, plus artist URL -> API path where known."""
    log = logging.getLogger(__name__)
    artists: dict[str, dict[str, Any]] = {}
    api_paths: dict[str, str] = {}
    annotation_count = 0
    for referent in client.iter_referents(song_id, text_format="dom"):
        for annotation in referent.get("annotations", []):
            annotation_count += 1
            log.info("    Scanning annotation %d (id %s)",
                     annotation_count, annotation["id"])
            for attrs in iter_link_attributes(annotation.get("body", {}).get("dom")):
                match = ARTIST_URL_RE.match(attrs.get("href", ""))
                if not match:
                    continue
                # Genius slugs are case-insensitive, so lowercase to merge duplicates
                url = match.group(0).lower()
                entry = artists.setdefault(url, {"annotation_ids": []})
                if annotation["id"] not in entry["annotation_ids"]:
                    entry["annotation_ids"].append(annotation["id"])
                if attrs.get("data-api_path", "").startswith("/artists/"):
                    api_paths.setdefault(url, attrs["data-api_path"])
    log.info("  Found %d referenced artists in %d annotations",
             len(artists), annotation_count)
    return artists, api_paths


def crawl_song_references(
    client: GeniusClient, start_song_id: int, max_songs: int
) -> dict[int, dict[str, Any]]:
    log = logging.getLogger(__name__)
    queue: deque[int] = deque([start_song_id])
    results: dict[int, dict[str, Any]] = {}
    titles: dict[int, str] = {
        start_song_id: client.get_song(start_song_id)["title"]}
    # Artists recur across songs, so cache lookups to save API calls
    popular_songs: dict[str, dict[str, Any] | None] = {}

    while queue and len(results) < max_songs:
        song_id = queue.popleft()
        if song_id in results:
            continue
        log.info("[%d/%d] Scanning song %d %s", len(results) + 1, max_songs,
                 song_id, titles.get(song_id, ""))
        artists, api_paths = collect_referenced_artists(client, song_id)

        for i, (url, entry) in enumerate(artists.items(), start=1):
            if url not in popular_songs:
                log.info("    [%d/%d] Looking up most popular song for %s",
                         i, len(artists), url)
                artist_id = (int(api_paths[url].rsplit("/", 1)[-1]) if url in api_paths
                             else client.find_artist_id_by_url(url))
                song = client.get_most_popular_song(
                    artist_id) if artist_id else None
                popular_songs[url] = (
                    {"id": song["id"], "title": song["title"]} if song else None)
            song = popular_songs[url]
            entry["most_popular_song"] = song
            if song and song["id"] not in results and song["id"] not in queue:
                titles[song["id"]] = song["title"]
                queue.append(song["id"])

        results[song_id] = {"title": titles.get(song_id),
                            "referenced_artists": artists}

    log.info("Stopped after %d songs: %s", len(results),
             "limit reached" if queue else "no more songs to follow")
    log.info("Results:\n%s", json.dumps(results, indent=2))
    return results


if __name__ == "__main__":
    main()
