import time
from collections.abc import Iterator
from typing import Any

import requests

API_BASE = "https://api.genius.com"


class GeniusClient:
    """Minimal wrapper around the official Genius API."""

    def __init__(self, access_token: str, request_delay: float = 0.5, timeout: float = 15.0):
        if not access_token:
            raise ValueError("GENIUS_ACCESS_TOKEN is not set")
        self._session = requests.Session()
        self._session.headers["Authorization"] = f"Bearer {access_token}"
        self._delay = request_delay
        self._timeout = timeout

    def _get(self, path: str, **params: Any) -> dict[str, Any]:
        time.sleep(self._delay)
        resp = self._session.get(
            f"{API_BASE}{path}", params=params, timeout=self._timeout)
        resp.raise_for_status()
        return resp.json()["response"]

    def search_artist(self, name: str) -> dict[str, Any] | None:
        hits = self._get("/search", q=name)["hits"]
        for hit in hits:
            artist = hit["result"]["primary_artist"]
            if artist["name"].lower() == name.lower():
                return artist
        return hits[0]["result"]["primary_artist"] if hits else None

    def find_artist_id_by_url(self, artist_url: str) -> int | None:
        slug = artist_url.rstrip("/").rsplit("/", 1)[-1]
        for hit in self._get("/search", q=slug.replace("-", " "))["hits"]:
            artist = hit["result"]["primary_artist"]
            if artist["url"].lower() == artist_url.lower():
                return artist["id"]
        return None

    def get_song(self, song_id: int) -> dict[str, Any]:
        return self._get(f"/songs/{song_id}")["song"]

    def get_artist(self, artist_id: int) -> dict[str, Any]:
        return self._get(f"/artists/{artist_id}")["artist"]

    def get_most_popular_song(self, artist_id: int) -> dict[str, Any] | None:
        songs = self._get(
            f"/artists/{artist_id}/songs", sort="popularity", per_page=1)["songs"]
        return songs[0] if songs else None

    def iter_artist_songs(self, artist_id: int, per_page: int = 50) -> Iterator[dict[str, Any]]:
        page: int | None = 1
        while page:
            data = self._get(
                f"/artists/{artist_id}/songs", per_page=per_page, page=page)
            yield from data["songs"]
            page = data.get("next_page")

    def iter_referents(
        self, song_id: int, per_page: int = 50, text_format: str = "dom"
    ) -> Iterator[dict[str, Any]]:
        """Yields referents (annotated lyric fragments) including their annotations."""
        page = 1
        while True:
            data = self._get(
                "/referents", song_id=song_id, per_page=per_page, page=page, text_format=text_format
            )
            referents = data["referents"]
            if not referents:
                return
            yield from referents
            page += 1
