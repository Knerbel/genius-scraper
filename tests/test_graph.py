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
