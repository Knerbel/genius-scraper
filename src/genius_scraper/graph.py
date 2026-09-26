import json
from pathlib import Path
from typing import Any

_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Genius reference graph</title>
<script src="https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js"></script>
<style>
  html, body { margin: 0; height: 100%; font-family: sans-serif; }
  #graph { width: 100%; height: 100%; }
  #legend { position: absolute; top: 10px; left: 10px; background: #fff;
            padding: 8px 12px; border: 1px solid #ccc; border-radius: 4px; }
  .dot { display: inline-block; width: 12px; height: 12px; margin-right: 6px; }
</style>
</head>
<body>
<div id="legend">
  <div><span class="dot" style="background:#e74c3c"></span>Start song</div>
  <div><span class="dot" style="background:#3498db"></span>Scanned song</div>
  <div><span class="dot" style="background:#bdc3c7"></span>Not scanned (limit)</div>
  <div><span class="dot" style="background:#f39c12;border-radius:50%"></span>Artist</div>
</div>
<div id="graph"></div>
<script>
  const data = __DATA__;
  new vis.Network(document.getElementById("graph"),
    { nodes: new vis.DataSet(data.nodes), edges: new vis.DataSet(data.edges) },
    { edges: { arrows: "to", smooth: false },
      physics: { solver: "forceAtlas2Based", stabilization: { iterations: 200 } } });
</script>
</body>
</html>
"""


def _artist_label(url: str) -> str:
    return url.rsplit("/", 1)[-1].replace("-", " ").title()


def build_graph(results: dict[int, dict[str, Any]], start_song_id: int) -> dict[str, list]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    for song_id, song in results.items():
        nodes[f"song:{song_id}"] = {
            "id": f"song:{song_id}",
            "label": song["title"] or f"Song {song_id}",
            "shape": "box",
            "color": "#e74c3c" if song_id == start_song_id else "#3498db",
            "font": {"color": "#fff"},
        }

    for song_id, song in results.items():
        for url, artist in song["referenced_artists"].items():
            artist_node = f"artist:{url}"
            nodes.setdefault(artist_node, {
                "id": artist_node, "label": _artist_label(url), "title": url,
                "shape": "dot", "color": "#f39c12",
            })
            edges.append({"from": f"song:{song_id}", "to": artist_node,
                          "title": f"{len(artist['annotation_ids'])} annotation(s)"})

            popular = artist.get("most_popular_song")
            if not popular:
                continue
            song_node = f"song:{popular['id']}"
            nodes.setdefault(song_node, {
                "id": song_node, "label": popular["title"], "shape": "box",
                "color": "#bdc3c7",
            })
            edge = {"from": artist_node, "to": song_node, "dashes": True,
                    "title": "most popular song"}
            if edge not in edges:
                edges.append(edge)

    return {"nodes": list(nodes.values()), "edges": edges}


def write_graph_html(results: dict[int, dict[str, Any]], start_song_id: int, path: Path) -> None:
    # Escape "</" so song titles can't close the <script> tag
    data = json.dumps(build_graph(results, start_song_id)).replace("</", "<\\/")
    path.write_text(_TEMPLATE.replace("__DATA__", data), encoding="utf-8")
