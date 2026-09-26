import argparse
import logging

from .config import load_settings
from .db.session import init_db, make_session_factory
from .pipeline import scrape_artist
from .scraper.client import GeniusClient
from .scraper.extractor import ARTIST_URL_RE, SONG_URL_RE, iter_links


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
    count = 0
    total = 0
    for referent in client.iter_referents(song_id, text_format="plain,dom"):
        for annotation in referent.get("annotations", []):
            total += 1
            body = annotation.get("body", {})
            links = []
            for href in dict.fromkeys(iter_links(body.get("dom"))):
                if ARTIST_URL_RE.match(href):
                    links.append(f"[ARTIST] {href}")
                elif SONG_URL_RE.match(href):
                    links.append(f"[SONG]   {href}")
            if not links:
                continue
            count += 1
            authors = ", ".join(
                a["user"]["name"] for a in annotation.get("authors", []) if a.get("user"))
            log.info(
                "\n[%s] Annotation %s (votes: %s, by: %s)\n  Fragment: %s\n  %s\n  %s\n  Links:%s",
                count,
                annotation["id"],
                annotation.get("votes_total"),
                authors or "-",
                referent.get("fragment"),
                body.get("plain", "").replace("\n", "\n  "),
                annotation.get("url"),
                "".join(f"\n    - {link}" for link in links),
            )
    log.info("Found %d of %d annotations referencing artists or songs for song %d",
             count, total, song_id)


if __name__ == "__main__":
    main()
