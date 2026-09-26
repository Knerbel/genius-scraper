import argparse
import json
import logging

from .config import load_settings
from .db.session import init_db, make_session_factory
from .pipeline import scrape_artist
from .scraper.client import GeniusClient
from .scraper.extractor import ARTIST_URL_RE, iter_links


def main() -> None:
    parser = argparse.ArgumentParser(prog="genius-scraper")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="Create database tables")

    p_artist = sub.add_parser(
        "scrape-artist", help="Scrape songs and references of an artist")
    p_artist.add_argument("name")
    p_artist.add_argument("--max-songs", type=int, default=None)

    p_song = sub.add_parser(
        "song-annotations", help="Print all annotations of a song to the console")
    p_song.add_argument("song_id", type=int)

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
        log_song_annotations(client, args.song_id)


def log_song_annotations(client: GeniusClient, song_id: int) -> None:
    log = logging.getLogger(__name__)
    artists: dict[str, list[int]] = {}
    for referent in client.iter_referents(song_id, text_format="dom"):
        for annotation in referent.get("annotations", []):
            for href in iter_links(annotation.get("body", {}).get("dom")):
                match = ARTIST_URL_RE.match(href)
                if not match:
                    continue
                # Genius slugs are case-insensitive, so lowercase to merge duplicates
                ids = artists.setdefault(match.group(0).lower(), [])
                if annotation["id"] not in ids:
                    ids.append(annotation["id"])
    log.info("Artist links (artist URL -> annotation IDs):\n%s",
             json.dumps(artists, indent=2))


if __name__ == "__main__":
    main()
