import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

ARTIST_URL_RE = re.compile(r"^https?://genius\.com/artists/(?P<slug>[^/?#]+)")
SONG_URL_RE = re.compile(
    r"^https?://genius\.com/(?P<slug>[^/?#]+-lyrics)(?:[?#]|$)")


@dataclass(frozen=True)
class ArtistReference:
    artist_slug: str
    artist_url: str
    annotation_id: int
    fragment: str


def iter_link_attributes(node: Any) -> Iterator[dict[str, Any]]:
    """Walks a Genius 'dom' tree and yields the attributes of all <a> tags."""
    if isinstance(node, dict):
        if node.get("tag") == "a":
            yield node.get("attributes", {})
        for child in node.get("children", []):
            yield from iter_link_attributes(child)
    elif isinstance(node, list):
        for child in node:
            yield from iter_link_attributes(child)


def iter_links(node: Any) -> Iterator[str]:
    """Walks a Genius 'dom' tree and yields all href values."""
    for attrs in iter_link_attributes(node):
        if attrs.get("href"):
            yield attrs["href"]


def extract_references(referent: dict[str, Any]) -> list[ArtistReference]:
    """Returns all artist pages linked from the annotations of a referent."""
    fragment = referent.get("fragment", "")
    refs: dict[tuple[int, str], ArtistReference] = {}
    for annotation in referent.get("annotations", []):
        for href in iter_links(annotation.get("body", {}).get("dom")):
            match = ARTIST_URL_RE.match(href)
            if match:
                key = (annotation["id"], match["slug"])
                refs[key] = ArtistReference(
                    artist_slug=match["slug"],
                    artist_url=match.group(0),
                    annotation_id=annotation["id"],
                    fragment=fragment,
                )
    return list(refs.values())
