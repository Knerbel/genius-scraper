import logging

from sqlalchemy.orm import sessionmaker

from .db.repository import Repository
from .scraper.client import GeniusClient
from .scraper.extractor import extract_references

log = logging.getLogger(__name__)


def scrape_artist(client: GeniusClient, session_factory: sessionmaker, name: str, max_songs: int | None = None) -> None:
    artist_data = client.search_artist(name)
    if artist_data is None:
        raise LookupError(f"Artist not found: {name}")
    log.info("Scraping %s (id=%s)", artist_data["name"], artist_data["id"])

    for i, song_data in enumerate(client.iter_artist_songs(artist_data["id"])):
        if max_songs is not None and i >= max_songs:
            break
        # Only songs where the artist is the primary artist count as outgoing edges.
        if song_data["primary_artist"]["id"] != artist_data["id"]:
            continue

        with session_factory() as session, session.begin():
            repo = Repository(session)
            artist = repo.upsert_artist(
                artist_data["url"], artist_data["id"], artist_data["name"])
            song = repo.upsert_song(
                song_data["id"], song_data["title"], song_data["url"], artist)

            count = 0
            for referent in client.iter_referents(song_data["id"]):
                for ref in extract_references(referent):
                    if ref.artist_url == artist.url:
                        continue
                    target = repo.upsert_artist(ref.artist_url)
                    repo.add_reference(
                        song, target, ref.annotation_id, ref.fragment)
                    count += 1
            log.info("  %s: %d references", song_data["title"], count)
