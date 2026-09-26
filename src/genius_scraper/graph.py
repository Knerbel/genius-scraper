import json
from html import escape
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
__REFRESH__
<title>Genius reference graph</title>
<script src="https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js"></script>
<style>
    * { box-sizing: border-box; }
    html, body { margin: 0; height: 100%; font-family: sans-serif; }
    #layout { display: flex; width: 100%; height: 100vh; height: 100dvh; }
    #sidebar { width: clamp(210px, 22vw, 300px); flex: none; display: flex;
                         flex-direction: column; border-right: 1px solid #d8dfe5; background: #fff; }
    #legend { padding: 12px 16px; border-bottom: 1px solid #d8dfe5;
                        font-size: 13px; line-height: 1.7; }
    #node-index { overflow-y: auto; flex: 1; padding: 8px 0 16px; }
    #node-index h2 { margin: 12px 16px 4px; color: #53616a; font-size: 12px; }
    .node-link { display: block; width: 100%; padding: 7px 16px; border: 0;
                             background: transparent; text-align: left; font: inherit;
                             font-size: 13px; line-height: 1.4; cursor: pointer;
                             overflow-wrap: anywhere; }
    .node-link:hover, .node-link:focus-visible { background: #eaf4f8; }
    .node-link:focus-visible { outline: 2px solid #207ca6; outline-offset: -2px; }
    .node-count { color: #7a8a93; }
    #graph { flex: 1; min-width: 0; }
  .dot { display: inline-block; width: 12px; height: 12px; margin-right: 6px; }
    @media (max-width: 640px) {
        #layout { flex-direction: column-reverse; }
        #sidebar { width: 100%; height: 36%; border-right: 0;
                             border-top: 1px solid #d8dfe5; }
        #legend { display: flex; flex-wrap: wrap; gap: 0 12px; padding: 6px 12px; }
        #graph { min-height: 0; }
    }
</style>
</head>
<body>
<div id="layout">
<aside id="sidebar">
<div id="legend">
  <div><span class="dot" style="background:#e74c3c"></span>Start song</div>
  <div><span class="dot" style="background:#3498db"></span>Scanned song</div>
  <div><span class="dot" style="background:#bdc3c7"></span>Not scanned (limit)</div>
  <div><span class="dot" style="background:#f39c12;border-radius:50%"></span>Artist</div>
</div>
<nav id="node-index" aria-label="Graph nodes">
__INDEX__
</nav>
</aside>
<div id="graph"></div>
</div>
<script>
  const data = __DATA__;
    const network = new vis.Network(document.getElementById("graph"),
    { nodes: new vis.DataSet(data.nodes), edges: new vis.DataSet(data.edges) },
    { edges: { arrows: "to", smooth: false },
      physics: { solver: "forceAtlas2Based", stabilization: { iterations: 200 } } });
    document.querySelectorAll(".node-link").forEach(button => {
        button.addEventListener("click", () => {
            const id = button.dataset.nodeId;
            network.selectNodes([id]);
            network.focus(id, { scale: 1.1, animation: { duration: 400 } });
        });
    });
</script>
</body>
</html>
"""


def _artist_label(url: str) -> str:
    return url.rsplit("/", 1)[-1].replace("-", " ").title()


def build_graph(results: dict[int, dict[str, Any]], start_song_id: int) -> dict[str, list]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    reference_counts: dict[str, int] = {}
    song_counts: dict[str, int] = {}
    artist_songs: dict[str, set[str]] = {}

    for song_id, song in results.items():
        label = song["title"] or f"Song {song_id}"
        count = sum(len(artist["annotation_ids"])
                    for artist in song["referenced_artists"].values())
        song_counts[f"song:{song_id}"] = count
        annotations = "annotation" if count == 1 else "annotations"
        title = f"{label} - {count} {annotations}"
        if song.get("artist"):
            title = f"{label} by {song['artist']} - {count} {annotations}"
        nodes[f"song:{song_id}"] = {
            "id": f"song:{song_id}",
            "label": label,
            "title": title,
            "shape": "box",
            "color": "#e74c3c" if song_id == start_song_id else "#3498db",
            "font": {"color": "#fff"},
        }

    for song_id, song in results.items():
        for url, artist in song["referenced_artists"].items():
            artist_node = f"artist:{url}"
            reference_counts[artist_node] = reference_counts.get(
                artist_node, 0) + len(artist["annotation_ids"])
            nodes.setdefault(artist_node, {
                "id": artist_node, "label": _artist_label(url),
                "shape": "dot", "color": "#f39c12",
            })
            edges.append({"from": f"song:{song_id}", "to": artist_node,
                          "title": f"{len(artist['annotation_ids'])} annotation(s)"})

            popular = artist.get("most_popular_song")
            if not popular:
                continue
            song_node = f"song:{popular['id']}"
            artist_songs.setdefault(artist_node, set()).add(song_node)
            nodes.setdefault(song_node, {
                "id": song_node, "label": popular["title"], "shape": "box",
                "color": "#bdc3c7",
            })
            edge = {"from": artist_node, "to": song_node, "dashes": True,
                    "title": "most popular song"}
            if edge not in edges:
                edges.append(edge)

    for artist_node, count in reference_counts.items():
        count += sum(song_counts.get(song_node, 0)
                     for song_node in artist_songs.get(artist_node, ()))
        annotations = "annotation" if count == 1 else "annotations"
        nodes[artist_node]["title"] = f"{nodes[artist_node]['label']} - {count} {annotations}"
        nodes[artist_node]["count"] = count

    return {"nodes": list(nodes.values()), "edges": edges}


def write_graph_html(results: dict[int, dict[str, Any]], start_song_id: int, path: Path,
                     refresh: bool = False) -> None:
    graph = build_graph(results, start_song_id)
    songs = [node for node in graph["nodes"] if node["id"].startswith("song:")]
    artists = [node for node in graph["nodes"]
               if node["id"].startswith("artist:")]
    index = "".join(
        f"<h2>{heading}</h2>\n" + "".join(
            f'<button type="button" class="node-link" data-node-id="{escape(node["id"], quote=True)}">'
            f'{escape(node["label"] or "")}'
            + (f' <span class="node-count">({node["count"]})</span>' if "count" in node else "")
            + '</button>\n'
            for node in sorted(group, key=lambda node: (node["label"] or "").casefold())
        ) for heading, group in (("Songs", songs), ("Artists", artists))
    )
    data = json.dumps(graph).replace("</", "<\\/")
    refresh_tag = '<meta http-equiv="refresh" content="5">' if refresh else ""
    html = _TEMPLATE.replace("__REFRESH__", refresh_tag).replace(
        "__INDEX__", index).replace("__DATA__", data)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                            prefix=f".{path.name}.", suffix=".tmp", delete=False) as output:
        output.write(html)
    temporary = Path(output.name)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
