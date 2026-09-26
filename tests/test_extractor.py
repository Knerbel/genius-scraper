from genius_scraper.scraper.extractor import extract_references


def test_extracts_linked_artist():
    referent = {
        "fragment": "I'm the new Nas",
        "annotations": [
            {
                "id": 1,
                "body": {
                    "dom": {
                        "tag": "root",
                        "children": [
                            {"tag": "a", "attributes": {
                                "href": "https://genius.com/artists/Nas"}, "children": ["Nas"]},
                            {"tag": "a", "attributes": {
                                "href": "https://genius.com/Nas-ny-state-of-mind-lyrics"}},
                        ],
                    }
                },
            }
        ],
    }
    refs = extract_references(referent)
    assert len(refs) == 1
    assert refs[0].artist_slug == "Nas"
    assert refs[0].fragment == "I'm the new Nas"
