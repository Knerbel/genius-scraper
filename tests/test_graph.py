from genius_scraper.graph import write_graph_html


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
    assert "Some Artist</button>" in html
    assert "Next &amp; Song</button>" in html
    assert 'data-node-id="song:1"' in html
    assert 'data-node-id="artist:https://genius.com/artists/some-artist"' in html
