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
    #graph-wrap { flex: 1; min-width: 0; position: relative; }
    #graph { position: absolute; inset: 0; }
  .dot { display: inline-block; width: 12px; height: 12px; margin-right: 6px; }
    #barchart { position: absolute; top: 12px; right: 12px; width: clamp(220px, 26vw, 320px);
                            background: rgba(255,255,255,0.92); border: 1px solid #d8dfe5;
                            border-radius: 6px; padding: 10px 14px; box-shadow: 0 1px 4px rgba(0,0,0,0.12); }
    #barchart h3 { margin: 0 0 8px; font-size: 12px; color: #53616a; }
    .bar-row { display: flex; align-items: center; gap: 8px; margin: 6px 0; font-size: 12px; }
    .bar-label { width: 35%; flex: none; overflow: hidden; text-overflow: ellipsis;
                             white-space: nowrap; }
    .bar-track { flex: 1; background: #eef1f3; border-radius: 3px; height: 14px; position: relative; }
    .bar-fill { display: block; background: #f39c12; height: 100%; border-radius: 3px; }
    .bar-value { flex: none; width: 28px; text-align: right; color: #53616a; }
    #pathfinder { flex: none; padding: 10px 16px 12px; border-bottom: 1px solid #d8dfe5;
                  font-size: 13px; }
    #pathfinder h2 { margin: 0 0 8px; color: #53616a; font-size: 12px; }
    .pf-row { display: flex; align-items: center; gap: 6px; margin: 6px 0; }
    .pf-row label { width: 34px; flex: none; color: #53616a; }
    .pf-row input { flex: 1; min-width: 0; padding: 5px 7px; border: 1px solid #c5cfd6;
                    border-radius: 4px; font: inherit; }
    .pf-pick { flex: none; width: 28px; height: 28px; padding: 0; border: 1px solid #c5cfd6;
               border-radius: 4px; background: #fff; cursor: pointer; }
    .pf-pick.active { background: #8e44ad; border-color: #8e44ad; color: #fff; }
    .pf-check { display: block; margin: 6px 0; color: #53616a; }
    .pf-actions { display: flex; gap: 6px; }
    .pf-actions button { padding: 5px 10px; border: 1px solid #c5cfd6; border-radius: 4px;
                         background: #fff; font: inherit; cursor: pointer; }
    .pf-actions #pf-find { background: #8e44ad; border-color: #8e44ad; color: #fff; }
    #pf-status { margin: 8px 0 0; color: #53616a; }
    #pf-steps { list-style: none; margin: 6px 0 0; padding: 0; max-height: 30vh; overflow-y: auto; }
    #pf-steps:empty { display: none; }
    .pf-node { display: flex; align-items: center; gap: 6px; width: 100%; padding: 4px 6px;
               border: 1px solid #e3d3ea; border-radius: 4px; background: #faf5fc;
               font: inherit; text-align: left; cursor: pointer; overflow-wrap: anywhere; }
    .pf-node:hover { background: #f1e4f7; }
    .pf-rel { padding: 3px 0 3px 14px; margin-left: 8px; border-left: 2px solid #8e44ad;
              color: #6c5a75; font-size: 12px; font-style: italic; }
    @media (max-width: 640px) {
        #layout { flex-direction: column-reverse; }
        #sidebar { width: 100%; height: 36%; border-right: 0;
                             border-top: 1px solid #d8dfe5; }
        #legend { display: flex; flex-wrap: wrap; gap: 0 12px; padding: 6px 12px; }
        #graph-wrap { min-height: 0; }
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
    <div><span class="dot" style="background:#27ae60;height:3px;vertical-align:middle"></span>Primary artist arrow</div>
</div>
<section id="pathfinder" aria-label="Find path">
  <h2>Find path</h2>
  <div class="pf-row"><label for="pf-from">From</label>
    <input id="pf-from" list="pf-options" placeholder="Song or artist" autocomplete="off">
    <button type="button" class="pf-pick" data-target="pf-from" title="Pick from graph" aria-label="Pick start from graph">&#9678;</button></div>
  <div class="pf-row"><label for="pf-to">To</label>
    <input id="pf-to" list="pf-options" placeholder="Song or artist" autocomplete="off">
    <button type="button" class="pf-pick" data-target="pf-to" title="Pick from graph" aria-label="Pick target from graph">&#9678;</button></div>
  <label class="pf-check"><input type="checkbox" id="pf-directed"> Follow arrow direction</label>
  <div class="pf-actions">
    <button type="button" id="pf-find">Find path</button>
    <button type="button" id="pf-swap" title="Swap from and to">&#8645;</button>
    <button type="button" id="pf-clear">Clear</button>
  </div>
  <div id="pf-status" role="status"></div>
  <ol id="pf-steps"></ol>
  <datalist id="pf-options"></datalist>
</section>
<nav id="node-index" aria-label="Graph nodes">
__INDEX__
</nav>
</aside>
<div id="graph-wrap">
<div id="graph"></div>
<div id="barchart">
    <h3>Top artists by references</h3>
    <div id="barchart-rows"></div>
</div>
</div>
</div>
<script>
  const data = __DATA__;
    const topArtists = data.nodes
        .filter(node => node.id.startsWith("artist:") && typeof node.count === "number")
        .sort((a, b) => b.count - a.count)
        .slice(0, 5);
    const maxCount = topArtists.length ? topArtists[0].count : 0;
    document.getElementById("barchart-rows").innerHTML = topArtists.map(node => `
        <div class="bar-row">
            <span class="bar-label" title="${node.label}">${node.label}</span>
            <span class="bar-track"><span class="bar-fill" style="width:${maxCount ? (node.count / maxCount) * 100 : 0}%"></span></span>
            <span class="bar-value">${node.count}</span>
        </div>
    `).join("");
    data.edges.forEach((edge, i) => { edge.id = i; });
    const nodeSet = new vis.DataSet(data.nodes);
    const edgeSet = new vis.DataSet(data.edges);
    const network = new vis.Network(document.getElementById("graph"),
    { nodes: nodeSet, edges: edgeSet },
    { edges: { arrows: "to", smooth: false },
            physics: { solver: "forceAtlas2Based", stabilization: { iterations: 200 } } });

    const PATH_COLOR = "#8e44ad";
    const $ = id => document.getElementById(id);
    const fromInput = $("pf-from"), toInput = $("pf-to"), directedBox = $("pf-directed");
    const statusEl = $("pf-status"), stepsEl = $("pf-steps");
    const nodeById = new Map(data.nodes.map(node => [node.id, node]));
    const nameToId = new Map(), idToName = new Map();
    const isArtist = id => id.startsWith("artist:");
    data.nodes.forEach(node => {
        const type = isArtist(node.id) ? "artist" : "song";
        let name = `${node.label || node.id} (${type})`;
        if (nameToId.has(name)) name = `${node.label || node.id} (${node.id})`;
        nameToId.set(name, node.id);
        idToName.set(node.id, name);
        const option = document.createElement("option");
        option.value = name;
        $("pf-options").append(option);
    });

    const adjacency = new Map(data.nodes.map(node => [node.id, []]));
    data.edges.forEach(edge => {
        adjacency.get(edge.from)?.push({ to: edge.to, edge, forward: true });
        adjacency.get(edge.to)?.push({ to: edge.from, edge, forward: false });
    });

    function resolve(value) {
        const text = value.trim();
        if (!text) return null;
        if (nameToId.has(text)) return nameToId.get(text);
        const lower = text.toLowerCase();
        const names = [...nameToId.keys()];
        const exact = names.filter(name => name.toLowerCase().startsWith(lower + " ("));
        const matches = exact.length ? exact : names.filter(name => name.toLowerCase().includes(lower));
        return matches.length === 1 ? nameToId.get(matches[0]) : null;
    }

    function shortestPath(start, goal, directed) {
        const previous = new Map([[start, null]]);
        const queue = [start];
        while (queue.length) {
            const current = queue.shift();
            if (current === goal) break;
            for (const step of adjacency.get(current) || []) {
                if ((directed && !step.forward) || previous.has(step.to)) continue;
                previous.set(step.to, { node: current, edge: step.edge, forward: step.forward });
                queue.push(step.to);
            }
        }
        if (!previous.has(goal)) return null;
        const path = [];
        for (let id = goal; id !== null; id = previous.get(id)?.node ?? null) {
            path.unshift({ id, via: previous.get(id) });
        }
        return path;
    }

    function relation(edge, forward) {
        if (edge.dashes) return forward ? "most popular song is" : "is the most popular song of";
        if (edge.title === "primary artist") return forward ? "is the primary artist of" : "is by";
        return (forward ? "references" : "is referenced by") + (edge.title ? ` (${edge.title})` : "");
    }

    function resetStyles() {
        nodeSet.update(data.nodes.map(node => ({ id: node.id, color: node.color, borderWidth: 1,
            font: node.font || { color: "#343434" } })));
        edgeSet.update(data.edges.map(edge => ({ id: edge.id, width: 1,
            color: { color: edge.color || "#848484", inherit: edge.color ? false : "from", opacity: 1 } })));
    }

    function highlight(path) {
        const onPath = new Set(path.map(step => step.id));
        const pathEdges = new Set(path.filter(step => step.via).map(step => step.via.edge.id));
        nodeSet.update(data.nodes.map(node => onPath.has(node.id)
            ? { id: node.id, borderWidth: 4, color: { background: node.color, border: PATH_COLOR },
                font: node.font || { color: "#343434" } }
            : { id: node.id, borderWidth: 1, color: { background: "#eef1f3", border: "#d8dfe5" },
                font: { color: "#b0b8bd" } }));
        edgeSet.update(data.edges.map(edge => pathEdges.has(edge.id)
            ? { id: edge.id, width: 4, color: { color: PATH_COLOR, inherit: false, opacity: 1 } }
            : { id: edge.id, width: 1, color: { color: "#d5dbdf", inherit: false, opacity: 0.4 } }));
        network.fit({ nodes: [...onPath], animation: { duration: 500 } });
    }

    function focusNode(id) {
        network.selectNodes([id]);
        network.focus(id, { scale: 1.1, animation: { duration: 400 } });
    }

    function renderSteps(path) {
        stepsEl.replaceChildren();
        path.forEach(step => {
            if (step.via) {
                const rel = document.createElement("li");
                rel.className = "pf-rel";
                rel.textContent = relation(step.via.edge, step.via.forward);
                stepsEl.append(rel);
            }
            const item = document.createElement("li");
            const button = document.createElement("button");
            button.type = "button";
            button.className = "pf-node";
            const dot = document.createElement("span");
            dot.className = "dot";
            dot.style.background = nodeById.get(step.id).color;
            if (isArtist(step.id)) dot.style.borderRadius = "50%";
            button.append(dot, nodeById.get(step.id).label || step.id);
            button.addEventListener("click", () => focusNode(step.id));
            item.append(button);
            stepsEl.append(item);
        });
    }

    function saveState() {
        try {
            sessionStorage.setItem("pathfinder", JSON.stringify(
                { from: fromInput.value, to: toInput.value, directed: directedBox.checked }));
        } catch (e) { /* storage unavailable */ }
    }

    function findPath() {
        saveState();
        const from = resolve(fromInput.value), to = resolve(toInput.value);
        stepsEl.replaceChildren();
        resetStyles();
        if (!from || !to) {
            statusEl.textContent = `Choose a ${!from ? "start" : "target"} from the suggestions.`;
            return;
        }
        fromInput.value = idToName.get(from);
        toInput.value = idToName.get(to);
        const path = shortestPath(from, to, directedBox.checked);
        if (!path) {
            statusEl.textContent = directedBox.checked
                ? "No path along arrow direction. Try unchecking 'Follow arrow direction'."
                : "These nodes are not connected.";
            return;
        }
        const hops = path.length - 1;
        statusEl.textContent = hops ? `${hops} step${hops === 1 ? "" : "s"}` : "Same node.";
        renderSteps(path);
        highlight(path);
    }

    let picking = null;
    function setPicking(target) {
        picking = target;
        document.querySelectorAll(".pf-pick").forEach(button =>
            button.classList.toggle("active", button.dataset.target === target));
        if (target) statusEl.textContent = "Click a node in the graph or the list below.";
    }
    function pick(id) {
        $(picking).value = idToName.get(id);
        setPicking(null);
        if (resolve(fromInput.value) && resolve(toInput.value)) findPath();
        else { statusEl.textContent = ""; saveState(); }
    }
    document.querySelectorAll(".pf-pick").forEach(button => button.addEventListener("click",
        () => setPicking(picking === button.dataset.target ? null : button.dataset.target)));
    network.on("click", params => { if (picking && params.nodes.length) pick(params.nodes[0]); });

    $("pf-find").addEventListener("click", findPath);
    [fromInput, toInput].forEach(input => input.addEventListener("keydown", event => {
        if (event.key === "Enter") findPath();
    }));
    directedBox.addEventListener("change", () => { if (stepsEl.children.length || statusEl.textContent) findPath(); });
    $("pf-swap").addEventListener("click", () => {
        [fromInput.value, toInput.value] = [toInput.value, fromInput.value];
        if (fromInput.value && toInput.value) findPath(); else saveState();
    });
    $("pf-clear").addEventListener("click", () => {
        fromInput.value = toInput.value = "";
        statusEl.textContent = "";
        stepsEl.replaceChildren();
        setPicking(null);
        resetStyles();
        saveState();
        network.fit({ animation: { duration: 400 } });
    });

    document.querySelectorAll(".node-link").forEach(button => {
        button.addEventListener("click", () => {
            const id = button.dataset.nodeId;
            if (picking) pick(id);
            else focusNode(id);
        });
    });

    try {
        const saved = JSON.parse(sessionStorage.getItem("pathfinder") || "null");
        if (saved) {
            fromInput.value = saved.from || "";
            toInput.value = saved.to || "";
            directedBox.checked = !!saved.directed;
            if (saved.from && saved.to) network.once("stabilizationIterationsDone", findPath);
        }
    } catch (e) { /* storage unavailable */ }
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
        artist_url = song.get("artist_url")
        if artist_url:
            artist_node = f"artist:{artist_url.lower()}"
            nodes.setdefault(artist_node, {
                "id": artist_node, "label": song.get("artist") or _artist_label(artist_url),
                "shape": "dot", "color": "#f39c12",
            })
            edges.append({"from": artist_node, "to": f"song:{song_id}",
                          "color": "#27ae60", "title": "primary artist"})
            artist_songs.setdefault(artist_node, set()).add(f"song:{song_id}")
        for url, artist in song["referenced_artists"].items():
            artist_node = f"artist:{url.lower()}"
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

    for artist_node in (node for node in nodes if node.startswith("artist:")):
        count = reference_counts.get(artist_node, 0)
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
