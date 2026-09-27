from pathlib import Path

import genius_scraper.graph as graph_module
from genius_scraper.graph import build_graph, write_graph_html


def test_primary_artist_has_colored_arrow_to_song():
    artist = "https://genius.com/artists/source"
    graph = build_graph({1: {
        "title": "Start", "artist": "Source", "artist_url": artist,
        "referenced_artists": {artist: {
            "annotation_ids": [7], "most_popular_song": {"id": 2, "title": "Hit"},
        }},
    }}, 1)

    assert len([node for node in graph["nodes"]
               if node["id"] == f"artist:{artist}"]) == 1
    assert {"from": f"artist:{artist}", "to": "song:1",
            "color": "#27ae60", "title": "primary artist"} in graph["edges"]
    assert {"from": f"artist:{artist}", "to": "song:2", "dashes": True,
            "title": "most popular song"} in graph["edges"]


def test_graph_exposes_searchable_names_as_escaped_html(tmp_path):
    output = tmp_path / "graph.html"
    results = {
        1: {
            "title": "A & B <Demo>",
            "referenced_artists": {
                "https://genius.com/artists/some-artist": {
                    "annotation_ids": [7],
                    "most_popular_song": {"id": 2, "title": "Next & Song"},
                },
            },
        },
    }

    write_graph_html(results, 1, output)
    html = output.read_text(encoding="utf-8")

    assert "A &amp; B &lt;Demo&gt;</button>" in html
    assert 'Some Artist <span class="node-count">(1)</span></button>' in html
    assert "Next &amp; Song</button>" in html
    assert 'data-node-id="song:1"' in html
    assert 'data-node-id="artist:https://genius.com/artists/some-artist"' in html


def test_graph_retries_when_windows_temporarily_locks_output(tmp_path, monkeypatch):
    output = tmp_path / "graph.html"
    output.write_text("old", encoding="utf-8")
    original_replace = Path.replace
    attempts = 0

    def intermittently_locked(source, destination):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise PermissionError(5, "Access is denied", destination)
        return original_replace(source, destination)

    monkeypatch.setattr(Path, "replace", intermittently_locked)
    monkeypatch.setattr(graph_module, "sleep", lambda _: None)

    write_graph_html(
        {1: {"title": "Start", "referenced_artists": {}}}, 1, output)

    assert attempts == 3
    assert "Start" in output.read_text(encoding="utf-8")


def test_artist_count_includes_references_of_its_songs(tmp_path):
    output = tmp_path / "graph.html"
    artist = "https://genius.com/artists/some-artist"
    other = "https://genius.com/artists/other"
    results = {
        1: {"title": "Start", "referenced_artists": {
            artist: {"annotation_ids": [7, 8],
                     "most_popular_song": {"id": 2, "title": "Hit"}},
        }},
        2: {"title": "Hit", "referenced_artists": {
            other: {"annotation_ids": [9, 10, 11], "most_popular_song": None},
        }},
    }

    write_graph_html(results, 1, output)
    html = output.read_text(encoding="utf-8")

    assert 'Some Artist <span class="node-count">(5)</span></button>' in html
    assert 'Other <span class="node-count">(3)</span></button>' in html


def test_artist_circles_use_the_same_default_size():
    one = "https://genius.com/artists/one"
    four = "https://genius.com/artists/four"
    graph = build_graph({1: {"title": "Start", "referenced_artists": {
        one: {"annotation_ids": [1], "most_popular_song": None},
        four: {"annotation_ids": [2, 3, 4, 5], "most_popular_song": None},
    }}}, 1)
    artists = [node for node in graph["nodes"]
               if node["id"].startswith("artist:")]

    assert {node["count"] for node in artists} == {1, 4}
    assert all(node["shape"] ==
               "dot" and "size" not in node for node in artists)


def test_graph_uses_original_layout_with_bar_chart_and_pathfinder(tmp_path):
    output = tmp_path / "graph.html"
    write_graph_html(
        {1: {"title": "Start", "referenced_artists": {}}}, 1, output)

    html = output.read_text(encoding="utf-8")
    assert 'physics: { solver: "forceAtlas2Based", stabilization: { iterations: 200 } }' in html
    assert 'avoidOverlap' not in html
    assert 'id="barchart-rows"' in html
    assert 'id="pf-find"' in html
    assert 'if (saved.from && saved.to) network.once("stabilizationIterationsDone", findPath);' in html
