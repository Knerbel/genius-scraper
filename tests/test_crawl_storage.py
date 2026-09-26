from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from genius_scraper.cli import crawl_song_references
from genius_scraper.db.models import Artist, Base, Reference, Song, SongScan
from genius_scraper.graph import write_graph_html
from genius_scraper.pipeline import scrape_artist


class FakeClient:
    def __init__(self):
        self.calls = []

    def get_song(self, song_id):
        self.calls.append(("get_song", song_id))
        return {
            "id": song_id,
            "title": "A song",
            "url": "https://genius.com/Source-a-song-lyrics",
            "primary_artist": {
                "id": 1, "name": "Source", "url": "https://genius.com/artists/Source"
            },
        }

    def iter_referents(self, song_id, text_format="dom"):
        self.calls.append(("iter_referents", song_id))
        yield {
            "fragment": "a nod to Target",
            "annotations": [{
                "id": 42,
                "body": {"dom": {"tag": "a", "attributes": {
                    "href": "https://genius.com/artists/Target",
                    "data-api_path": "/artists/2",
                }}},
            }],
        }

    def get_most_popular_song(self, artist_id):
        self.calls.append(("get_most_popular_song", artist_id))
        return None

    def find_artist_id_by_url(self, artist_url):
        self.calls.append(("find_artist_id_by_url", artist_url))
        return 2

    def search_artist(self, name):
        return {"id": 1, "name": "Source", "url": "https://genius.com/artists/Source"}

    def iter_artist_songs(self, artist_id):
        yield self.get_song(10)


def test_crawl_stores_connections_and_deduplicates_repeated_scans():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    client = FakeClient()

    results = crawl_song_references(client, 10, 1, factory)
    assert results[10]["referenced_artists"]["https://genius.com/artists/target"]["annotation_ids"] == [42]
    client.calls.clear()
    assert crawl_song_references(client, 10, 1, factory) == results
    assert client.calls == []

    with factory() as session:
        reference = session.scalar(select(Reference))
        assert reference is not None
        assert reference.annotation_id == 42
        assert reference.fragment == "a nod to Target"
        assert session.scalar(select(Song)).genius_id == 10
        assert session.scalar(select(Artist).where(
            Artist.id == reference.referenced_artist_id)).url == "https://genius.com/artists/target"
        assert len(session.scalars(select(Reference)).all()) == 1


def test_artist_scrape_skips_songs_already_scanned():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    client = FakeClient()

    scrape_artist(client, factory, "Source")
    client.calls.clear()
    scrape_artist(client, factory, "Source")

    assert ("iter_referents", 10) not in client.calls
    with factory() as session:
        assert session.scalar(select(SongScan)) is not None
        assert len(session.scalars(select(Reference)).all()) == 1


def test_crawl_reuses_artist_scrape_without_refetching_annotations():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    client = FakeClient()

    scrape_artist(client, factory, "Source")
    client.calls.clear()
    result = crawl_song_references(client, 10, 1, factory)

    assert ("iter_referents", 10) not in client.calls
    assert result[10]["referenced_artists"]["https://genius.com/artists/target"]["annotation_ids"] == [42]


def test_empty_song_is_cached_too():
    class EmptyClient(FakeClient):
        def iter_referents(self, song_id, text_format="dom"):
            self.calls.append(("iter_referents", song_id))
            return iter(())

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    client = EmptyClient()

    assert crawl_song_references(client, 10, 1, factory)[
        10]["referenced_artists"] == {}
    client.calls.clear()
    assert crawl_song_references(client, 10, 1, factory)[
        10]["referenced_artists"] == {}
    assert client.calls == []


def test_cached_graph_still_follows_next_song():
    class FollowingClient(FakeClient):
        def get_most_popular_song(self, artist_id):
            self.calls.append(("get_most_popular_song", artist_id))
            return {"id": 11, "title": "Next song"}

        def iter_referents(self, song_id, text_format="dom"):
            if song_id == 11:
                self.calls.append(("iter_referents", song_id))
                return iter(())
            return super().iter_referents(song_id, text_format)

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    client = FollowingClient()

    first = crawl_song_references(client, 10, 2, factory)
    assert set(first) == {10, 11}
    client.calls.clear()
    assert crawl_song_references(client, 10, 2, factory) == first
    assert client.calls == []


def test_graph_file_grows_after_each_new_artist(tmp_path):
    class TwoArtistClient(FakeClient):
        def iter_referents(self, song_id, text_format="dom"):
            yield from super().iter_referents(song_id, text_format)
            yield {
                "fragment": "another nod",
                "annotations": [{"id": 43, "body": {"dom": {"tag": "a", "attributes": {
                    "href": "https://genius.com/artists/Other",
                    "data-api_path": "/artists/3",
                }}}}],
            }

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    output = tmp_path / "graph.html"
    snapshots = []

    def update_graph(results):
        write_graph_html(results, 10, output, refresh=True)
        snapshots.append(output.read_text(encoding="utf-8"))

    crawl_song_references(TwoArtistClient(), 10, 1,
                          factory, on_update=update_graph)

    assert "Target</button>" not in snapshots[0]
    assert "Target</button>" in snapshots[1]
    assert "Other</button>" not in snapshots[1]
    assert "Target</button>" in snapshots[2]
    assert "Other</button>" in snapshots[2]
    assert all(
        '<meta http-equiv="refresh" content="5">' in snapshot for snapshot in snapshots)
    write_graph_html(
        {10: {"title": "A song", "referenced_artists": {}}}, 10, output)
    assert 'http-equiv="refresh"' not in output.read_text(encoding="utf-8")
