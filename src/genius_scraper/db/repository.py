from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Artist, Reference, Song, SongScan


class Repository:
    def __init__(self, session: Session):
        self.session = session

    def upsert_artist(self, url: str, genius_id: int | None = None, name: str | None = None) -> Artist:
        artist = self.session.scalar(select(Artist).where(
            func.lower(Artist.url) == url.lower()))
        if artist is None:
            artist = Artist(url=url)
            self.session.add(artist)
        if genius_id is not None:
            artist.genius_id = genius_id
        if name is not None:
            artist.name = name
        self.session.flush()
        return artist

    def upsert_song(self, genius_id: int, title: str, url: str, primary_artist: Artist) -> Song:
        song = self.session.scalar(
            select(Song).where(Song.genius_id == genius_id))
        if song is None:
            song = Song(genius_id=genius_id, title=title,
                        url=url, primary_artist=primary_artist)
            self.session.add(song)
            self.session.flush()
        return song

    def get_song_scan(self, genius_id: int) -> SongScan | None:
        return self.session.scalar(
            select(SongScan).join(Song).where(Song.genius_id == genius_id))

    def save_song_scan(self, song: Song, graph_data: dict[str, Any] | None = None) -> None:
        scan = self.session.get(SongScan, song.id)
        if scan is None:
            self.session.add(SongScan(song_id=song.id, graph_data=graph_data))
        elif graph_data is not None:
            scan.graph_data = graph_data

    def add_reference(self, song: Song, artist: Artist, annotation_id: int, fragment: str) -> None:
        exists = self.session.scalar(
            select(Reference.id).where(
                Reference.song_id == song.id,
                Reference.referenced_artist_id == artist.id,
                Reference.annotation_id == annotation_id,
            )
        )
        if exists is None:
            self.session.add(
                Reference(song=song, referenced_artist=artist,
                          annotation_id=annotation_id, fragment=fragment)
            )
