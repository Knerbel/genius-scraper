import argparse
import json
import logging
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from .config import load_settings
from .db.models import Reference, Song
from .db.repository import Repository
from .db.session import init_db, make_session_factory
from .graph import write_graph_html
from .pipeline import scrape_artist
from .scraper.client import GeniusClient
from .scraper.extractor import ARTIST_URL_RE, ArtistReference, extract_references, iter_link_attributes
from .server import serve

MIN_ARTIST_FOLLOWERS = 100


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

    p_serve = sub.add_parser(
        "serve",
        help="Serve the graph with a search box to start scrapes from the browser")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--max-songs", type=int, default=250,
                         help="Songs to scan per scrape (default: 250)")
    p_serve.add_argument("--output", type=Path, default=Path("graph.html"),
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
        init_db(settings.database_url)
        client = GeniusClient(settings.genius_access_token,
                              settings.request_delay)
        results = crawl_song_references(
            client, args.song_id, args.max_songs,
            make_session_factory(settings.database_url),
            on_update=lambda current: write_graph_html(
                current, args.song_id, args.output, refresh=True))
        write_graph_html(results, args.song_id, args.output)
        logging.getLogger(__name__).info(
            "Graph written to %s", args.output.resolve())
    elif args.command == "serve":
        serve(settings, args.output, args.max_songs, crawl_song_references,
              host=args.host, port=args.port)


def collect_referenced_artists(
    client: GeniusClient, song_id: int
) -> tuple[dict[str, dict[str, Any]], dict[str, str], list[ArtistReference]]:
    """Returns graph artists, known API paths, and annotation references."""
    log = logging.getLogger(__name__)
    artists: dict[str, dict[str, Any]] = {}
    api_paths: dict[str, str] = {}
    references: list[ArtistReference] = []
    annotation_count = 0
    for referent in client.iter_referents(song_id, text_format="dom"):
        references.extend(extract_references(referent))
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
    return artists, api_paths, references


def crawl_song_references(
    client: GeniusClient, start_song_id: int, max_songs: int,
    session_factory: sessionmaker | None = None,
    on_update: Callable[[dict[int, dict[str, Any]]], None] | None = None,
) -> dict[int, dict[str, Any]]:
    log = logging.getLogger(__name__)
    queue: deque[int] = deque([start_song_id])
    results: dict[int, dict[str, Any]] = {}
    # Artists recur across songs, so cache lookups to save API calls
    popular_songs: dict[str, dict[str, Any] | None] = {}
    eligible_artists: dict[str, bool] = {}

    def is_eligible_artist(url: str, artist_id: int | None) -> bool:
        if url not in eligible_artists:
            artist = client.get_artist(artist_id) if artist_id else None
            eligible_artists[url] = bool(
                artist and artist.get("followers_count", 0) >= MIN_ARTIST_FOLLOWERS)
        return eligible_artists[url]

    if on_update is not None:
        on_update(results)

    while queue and len(results) < max_songs:
        song_id = queue.popleft()
        if song_id in results:
            continue
        cached = None
        stored_artists = None
        stored_song_id = None
        stored_title = None
        stored_artist_name = None
        stored_artist_url = None
        if session_factory is not None:
            with session_factory() as session:
                scan = Repository(session).get_song_scan(song_id)
                if scan is not None:
                    cached = scan.graph_data
                    stored_song_id = scan.song_id
                    if cached is None:
                        stored_song = session.get(Song, scan.song_id)
                        stored_title = stored_song.title
                        stored_artist_name = stored_song.primary_artist.name
                        stored_artist_url = stored_song.primary_artist.url.lower()
                        stored_artists = {}
                        for ref in session.scalars(
                            select(Reference).where(
                                Reference.song_id == scan.song_id)
                        ):
                            url = ref.referenced_artist.url.lower()
                            entry = stored_artists.setdefault(
                                url, {"annotation_ids": []})
                            if ref.annotation_id not in entry["annotation_ids"]:
                                entry["annotation_ids"].append(
                                    ref.annotation_id)
        if cached is not None:
            log.info("[%d/%d] Reusing song %d %s", len(results) + 1,
                     max_songs, song_id, cached["title"])
            song_result = cached
            if "artist" not in song_result or "artist_url" not in song_result:
                with session_factory() as session, session.begin():
                    repo = Repository(session)
                    stored_song = session.get(Song, stored_song_id)
                    song_result = {**cached, "artist": stored_song.primary_artist.name,
                                   "artist_url": stored_song.primary_artist.url.lower()}
                    repo.save_song_scan(stored_song, song_result)
                if "artist" not in cached:
                    for url in list(cached["referenced_artists"]):
                        artist_id = client.find_artist_id_by_url(url)
                        if not is_eligible_artist(url, artist_id):
                            del cached["referenced_artists"][url]
                            continue
                        entry = cached["referenced_artists"][url]
                    popular_songs.setdefault(url, entry["most_popular_song"])
        else:
            song_data = client.get_song(
                song_id) if stored_artists is None else None
            title = song_data["title"] if song_data is not None else stored_title
            artist_name = (song_data["primary_artist"]["name"]
                           if song_data is not None else stored_artist_name)
            artist_url = (song_data["primary_artist"]["url"].lower()
                          if song_data is not None else stored_artist_url)
            log.info("[%d/%d] Scanning song %d %s", len(results) + 1,
                     max_songs, song_id, title)
            if stored_artists is None:
                artists, api_paths, references = collect_referenced_artists(
                    client, song_id)
            else:
                artists, api_paths = stored_artists, {}
                references = []

            resolved_artists: dict[str, dict[str, Any]] = {}
            for i, (url, entry) in enumerate(artists.items(), start=1):
                if url not in popular_songs:
                    log.info("    [%d/%d] Looking up most popular song for %s",
                             i, len(artists), url)
                    artist_id = (int(api_paths[url].rsplit("/", 1)[-1]) if url in api_paths
                                 else client.find_artist_id_by_url(url))
                    if not is_eligible_artist(url, artist_id):
                        log.info("    Skipping %s: fewer than %d followers",
                                 url, MIN_ARTIST_FOLLOWERS)
                        popular_songs[url] = None
                        continue
                    song = client.get_most_popular_song(
                        artist_id) if artist_id else None
                    popular_songs[url] = (
                        {"id": song["id"], "title": song["title"]} if song else None)
                entry["most_popular_song"] = popular_songs[url]
                resolved_artists[url] = entry
                if on_update is not None:
                    on_update({**results, song_id: {
                        "title": title, "artist": artist_name, "artist_url": artist_url,
                        "referenced_artists": resolved_artists.copy()}})

            song_result = {"title": title, "artist": artist_name, "artist_url": artist_url,
                           "referenced_artists": resolved_artists}
            if session_factory is not None:
                with session_factory() as session, session.begin():
                    repo = Repository(session)
                    if song_data is None:
                        stored_song = session.get(Song, stored_song_id)
                    else:
                        primary = song_data["primary_artist"]
                        source = repo.upsert_artist(
                            primary["url"].lower(), primary["id"], primary["name"])
                        stored_song = repo.upsert_song(
                            song_id, song_data["title"], song_data["url"], source)
                        for ref in references:
                            if ref.artist_url.lower() == source.url.lower():
                                continue
                            target = repo.upsert_artist(ref.artist_url.lower())
                            repo.add_reference(
                                stored_song, target, ref.annotation_id, ref.fragment)
                    repo.save_song_scan(stored_song, song_result)

        for entry in song_result["referenced_artists"].values():
            song = entry["most_popular_song"]
            if song and song["id"] not in results and song["id"] not in queue:
                queue.append(song["id"])

        results[song_id] = song_result
        if on_update is not None:
            on_update(results)

    log.info("Stopped after %d songs: %s", len(results),
             "limit reached" if queue else "no more songs to follow")
    # log.info("Results:\n%s", json.dumps(results, indent=2))
    return results


if __name__ == "__main__":
    main()
