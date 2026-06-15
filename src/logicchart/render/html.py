from __future__ import annotations

import json
from pathlib import Path

from logicchart.model import ProjectModel


def render_html(model: ProjectModel, source_root: Path | None = None) -> str:
    data = model.to_dict()
    if source_root is not None:
        data["root"] = str(source_root)
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return _HTML_TEMPLATE.replace("__LOGICCHART_DATA__", payload)


_HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LogicChart</title>
  <style>
    :root {
      --paper: #f5f7fb;
      --panel: #ffffff;
      --ink: #18243a;
      --muted: #65718a;
      --line: #c8d1e2;
      --blue: #2457d6;
      --cyan: #04a6c2;
      --amber: #e5a11a;
      --coral: #d84f4f;
      --violet: #7457d9;
      --shadow: 0 18px 50px rgba(30, 46, 78, 0.12);
    }
    * { box-sizing: border-box; }
    html, body { height: 100%; margin: 0; }
    body {
      color: var(--ink);
      background:
        linear-gradient(rgba(36, 87, 214, 0.045) 1px, transparent 1px),
        linear-gradient(90deg, rgba(36, 87, 214, 0.045) 1px, transparent 1px),
        var(--paper);
      background-size: 24px 24px;
      font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      overflow: hidden;
    }
    button, input { font: inherit; }
    button { color: inherit; }
    .shell {
      display: grid;
      grid-template-columns: 310px minmax(0, 1fr) 330px;
      grid-template-rows: 76px minmax(0, 1fr);
      height: 100%;
    }
    header {
      grid-column: 1 / -1;
      display: flex;
      align-items: center;
      gap: 24px;
      padding: 0 24px;
      background: rgba(255, 255, 255, 0.9);
      border-bottom: 1px solid var(--line);
      backdrop-filter: blur(14px);
      z-index: 3;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 13px;
      min-width: 286px;
    }
    .brand-mark {
      width: 34px;
      height: 44px;
      position: relative;
    }
    .brand-mark::before {
      content: "";
      position: absolute;
      left: 15px;
      top: 0;
      bottom: 0;
      width: 4px;
      border-radius: 2px;
      background: var(--cyan);
    }
    .brand-mark span {
      position: absolute;
      left: 7px;
      top: 15px;
      width: 20px;
      height: 20px;
      transform: rotate(45deg);
      background: var(--panel);
      border: 3px solid var(--blue);
    }
    .brand h1 {
      font-family: Georgia, "Times New Roman", serif;
      font-size: 24px;
      letter-spacing: -0.5px;
      margin: 0;
    }
    .brand small {
      display: block;
      color: var(--muted);
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 10px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }
    .flow-heading { min-width: 0; flex: 1; }
    .flow-heading .eyebrow {
      color: var(--blue);
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.1em;
      text-transform: uppercase;
    }
    .flow-heading h2 {
      margin: 4px 0 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: 20px;
    }
    .metrics { display: flex; gap: 8px; }
    .metric {
      padding: 8px 11px;
      border: 1px solid var(--line);
      background: var(--panel);
      min-width: 72px;
    }
    .metric strong { display: block; font-size: 16px; }
    .metric span {
      color: var(--muted);
      font-size: 10px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }
    aside {
      min-height: 0;
      background: rgba(255, 255, 255, 0.88);
      backdrop-filter: blur(12px);
    }
    .left-rail { border-right: 1px solid var(--line); }
    .right-rail { border-left: 1px solid var(--line); }
    .rail-inner {
      height: 100%;
      display: flex;
      flex-direction: column;
      min-height: 0;
    }
    .rail-head { padding: 20px; border-bottom: 1px solid var(--line); }
    .rail-title {
      margin: 0 0 12px;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 11px;
      letter-spacing: 0.1em;
      text-transform: uppercase;
    }
    .search {
      width: 100%;
      border: 1px solid var(--line);
      background: var(--paper);
      padding: 10px 12px;
      outline: none;
    }
    .search:focus { border-color: var(--blue); box-shadow: 0 0 0 3px rgba(36, 87, 214, .12); }
    .flow-list, .detail-scroll { overflow: auto; min-height: 0; }
    .flow-list { padding: 10px; }
    .flow-item {
      width: 100%;
      display: grid;
      grid-template-columns: 6px 1fr;
      gap: 11px;
      text-align: left;
      border: 0;
      background: transparent;
      padding: 11px 10px;
      cursor: pointer;
    }
    .flow-item:hover, .flow-item:focus-visible { background: #edf2fd; outline: none; }
    .flow-item.active { background: #e7eefc; }
    .flow-item .bar { background: var(--line); min-height: 42px; }
    .flow-item.active .bar { background: var(--blue); }
    .flow-item strong { display: block; font-size: 13px; line-height: 1.25; }
    .flow-item span {
      display: block;
      color: var(--muted);
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 10px;
      margin-top: 5px;
    }
    main { position: relative; min-width: 0; min-height: 0; overflow: hidden; }
    .canvas-toolbar {
      position: absolute;
      top: 16px;
      right: 16px;
      z-index: 2;
      display: flex;
      gap: 6px;
    }
    .tool {
      border: 1px solid var(--line);
      background: rgba(255,255,255,.94);
      min-width: 38px;
      height: 38px;
      cursor: pointer;
      box-shadow: 0 8px 18px rgba(30,46,78,.08);
    }
    .tool:hover, .tool:focus-visible { border-color: var(--blue); outline: none; }
    #canvas { width: 100%; height: 100%; cursor: grab; }
    #canvas.dragging { cursor: grabbing; }
    .empty {
      position: absolute;
      inset: 0;
      display: none;
      place-items: center;
      text-align: center;
      color: var(--muted);
    }
    .detail-scroll { padding: 20px; }
    .detail-kind {
      display: inline-block;
      padding: 5px 7px;
      color: var(--blue);
      background: #e9effe;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 10px;
      font-weight: 700;
      letter-spacing: .08em;
      text-transform: uppercase;
    }
    .detail-scroll h3 {
      margin: 16px 0 8px;
      font-family: Georgia, "Times New Roman", serif;
      font-size: 22px;
      line-height: 1.15;
    }
    .detail-scroll p { color: var(--muted); line-height: 1.55; font-size: 13px; }
    .source-link, .subflow-link {
      display: block;
      width: 100%;
      margin: 14px 0;
      padding: 11px 12px;
      border: 1px solid var(--line);
      background: var(--paper);
      color: var(--ink);
      text-decoration: none;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 11px;
      overflow-wrap: anywhere;
      cursor: pointer;
    }
    .source-link:hover, .subflow-link:hover { border-color: var(--blue); }
    .section-label {
      margin: 24px 0 10px;
      color: var(--muted);
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 10px;
      letter-spacing: .1em;
      text-transform: uppercase;
    }
    .finding {
      border-left: 4px solid var(--amber);
      background: #fff8e8;
      padding: 11px 12px;
      margin-bottom: 9px;
      font-size: 12px;
      line-height: 1.45;
    }
    .finding.error { border-color: var(--coral); background: #fff0f0; }
    .legend {
      margin-top: auto;
      border-top: 1px solid var(--line);
      padding: 14px 20px;
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      color: var(--muted);
      font-size: 10px;
    }
    .legend span::before {
      content: "";
      width: 8px;
      height: 8px;
      display: inline-block;
      margin-right: 7px;
      background: var(--blue);
    }
    .legend .decision::before { background: var(--amber); transform: rotate(45deg); }
    .legend .call::before { background: var(--violet); }
    .legend .gap::before { background: var(--coral); }
    .node { cursor: grab; }
    .node.dragging { cursor: grabbing; }
    .node.dragging .shape { filter: url(#nodeLift); }
    .node .shape { fill: #fff; stroke: var(--blue); stroke-width: 2; filter: url(#nodeShadow); transition: filter .12s ease; }
    .node.entry .shape { fill: #e9effe; stroke: var(--blue); }
    .node.decision .shape { fill: #fff7e2; stroke: var(--amber); }
    .node.call .shape { fill: #f1edff; stroke: var(--violet); }
    .node.terminal .shape { fill: #e7f8f4; stroke: var(--cyan); }
    .node.error .shape { fill: #fff0f0; stroke: var(--coral); }
    .node.has-finding .shape { stroke: var(--coral); stroke-width: 3; }
    .node text {
      fill: var(--ink);
      font-size: 13px;
      font-weight: 650;
      pointer-events: none;
    }
    .node .meta {
      fill: var(--muted);
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 9px;
      font-weight: 500;
      letter-spacing: .05em;
      text-transform: uppercase;
    }
    .edge { fill: none; stroke: #9ba8bf; stroke-width: 2; marker-end: url(#arrow); }
    .edge-label {
      fill: var(--muted);
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 10px;
      font-weight: 700;
      paint-order: stroke;
      stroke: var(--paper);
      stroke-width: 6px;
    }
    .decision-spine { stroke: rgba(4,166,194,.22); stroke-width: 5; stroke-dasharray: 3 10; }
    @media (max-width: 1050px) {
      .shell { grid-template-columns: 260px minmax(0,1fr); }
      .right-rail {
        position: fixed;
        right: 0;
        top: 76px;
        bottom: 0;
        width: 320px;
        z-index: 5;
        box-shadow: var(--shadow);
        transform: translateX(100%);
        transition: transform .2s ease;
      }
      .right-rail.open { transform: translateX(0); }
      .metrics { display: none; }
    }
    @media (max-width: 700px) {
      .shell { grid-template-columns: 1fr; }
      header { padding: 0 14px; }
      .brand { min-width: 0; }
      .brand small, .flow-heading { display: none; }
      .left-rail {
        position: fixed;
        left: 0;
        top: 76px;
        bottom: 0;
        width: 285px;
        z-index: 5;
        box-shadow: var(--shadow);
        transform: translateX(-100%);
      }
      .left-rail.open { transform: translateX(0); }
    }
    @media (prefers-reduced-motion: reduce) {
      *, *::before, *::after { scroll-behavior: auto !important; transition: none !important; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <header>
      <div class="brand">
        <div class="brand-mark" aria-hidden="true"><span></span></div>
        <div><h1>LogicChart</h1><small>Decision flow index</small></div>
      </div>
      <div class="flow-heading">
        <div class="eyebrow" id="flowKind">No flow selected</div>
        <h2 id="flowTitle">Analyze a project to begin</h2>
      </div>
      <div class="metrics">
        <div class="metric"><strong id="flowCount">0</strong><span>flows</span></div>
        <div class="metric"><strong id="entryCount">0</strong><span>entries</span></div>
        <div class="metric"><strong id="findingCount">0</strong><span>review</span></div>
      </div>
    </header>

    <aside class="left-rail" id="leftRail">
      <div class="rail-inner">
        <div class="rail-head">
          <h2 class="rail-title">Entry points and subflows</h2>
          <input class="search" id="flowSearch" type="search" placeholder="Filter flows..." aria-label="Filter flows">
        </div>
        <div class="flow-list" id="flowList"></div>
        <div class="legend">
          <span>Action</span><span class="decision">Decision</span>
          <span class="call">Subflow</span><span class="gap">Review</span>
        </div>
      </div>
    </aside>

    <main>
      <div class="canvas-toolbar" aria-label="Canvas controls">
        <button class="tool" id="menuButton" title="Toggle flow list">&#9776;</button>
        <button class="tool" id="zoomOut" title="Zoom out">&minus;</button>
        <button class="tool" id="resetView" title="Reset view &amp; layout">0</button>
        <button class="tool" id="zoomIn" title="Zoom in">+</button>
      </div>
      <svg id="canvas" role="img" aria-label="Decision flowchart"></svg>
      <div class="empty" id="emptyState"><p>No matching flow was found.</p></div>
    </main>

    <aside class="right-rail" id="rightRail">
      <div class="rail-inner">
        <div class="rail-head"><h2 class="rail-title">Inspector</h2></div>
        <div class="detail-scroll" id="details">
          <p>Select a node to inspect its source, evidence, and related findings.</p>
          <p>Tip: drag any block to rearrange the diagram by hand. Reset (0) restores the
          automatic layout.</p>
        </div>
      </div>
    </aside>
  </div>

  <script id="logicchart-data" type="application/json">__LOGICCHART_DATA__</script>
  <script>
    const model = JSON.parse(document.getElementById("logicchart-data").textContent);
    const flows = model.flows || [];
    const findings = model.findings || [];
    const byId = new Map(flows.map(flow => [flow.id, flow]));
    const findingsByNode = new Map();
    findings.forEach(item => {
      if (!item.node_id) return;
      const list = findingsByNode.get(item.node_id) || [];
      list.push(item);
      findingsByNode.set(item.node_id, list);
    });

    const svg = document.getElementById("canvas");
    const listEl = document.getElementById("flowList");
    const searchEl = document.getElementById("flowSearch");
    const detailsEl = document.getElementById("details");
    const rightRail = document.getElementById("rightRail");
    const leftRail = document.getElementById("leftRail");
    let activeFlow = null;
    let view = { x: 0, y: 0, width: 1000, height: 800 };
    let drag = null;
    // Per-flow manual node positions: flowId -> Map(nodeId -> {x, y}). Lets the user
    // hand-arrange blocks; survives navigating away and back within the session.
    const manualPositions = new Map();

    document.getElementById("flowCount").textContent = flows.length;
    document.getElementById("entryCount").textContent = flows.filter(item => item.is_entrypoint).length;
    document.getElementById("findingCount").textContent = findings.length;

    function sortedFlows() {
      return [...flows].sort((a, b) =>
        Number(b.is_entrypoint) - Number(a.is_entrypoint) || a.name.localeCompare(b.name)
      );
    }

    function renderList(filter = "") {
      const needle = filter.trim().toLowerCase();
      listEl.replaceChildren();
      sortedFlows()
        .filter(flow => !flow.metadata.test)
        .filter(flow => `${flow.name} ${flow.symbol} ${flow.entry_kind}`.toLowerCase().includes(needle))
        .forEach(flow => {
          const button = document.createElement("button");
          button.className = "flow-item" + (activeFlow?.id === flow.id ? " active" : "");
          button.innerHTML = `<span class="bar"></span><span><strong></strong><span></span></span>`;
          button.querySelector("strong").textContent = flow.name;
          button.querySelector("span span").textContent =
            `${flow.is_entrypoint ? "ENTRY" : "SUBFLOW"} · ${flow.entry_kind}`;
          button.addEventListener("click", () => selectFlow(flow.id));
          listEl.appendChild(button);
        });
    }

    function selectFlow(flowId) {
      const flow = byId.get(flowId);
      if (!flow) return;
      activeFlow = flow;
      location.hash = encodeURIComponent(flow.id);
      document.getElementById("flowTitle").textContent = flow.name;
      document.getElementById("flowKind").textContent =
        `${flow.entry_kind} · ${flow.language} · ${flow.framework}`;
      renderList(searchEl.value);
      renderFlow(flow);
      inspectFlow(flow);
      leftRail.classList.remove("open");
    }

    function layoutFlow(flow) {
      const order = new Map(flow.nodes.map((node, index) => [node.id, index]));
      const incoming = new Map(flow.nodes.map(node => [node.id, []]));
      flow.edges.forEach(edge => incoming.get(edge.target)?.push(edge));
      const positions = new Map();
      const layerCounts = new Map();

      flow.nodes.forEach((node, index) => {
        const parents = incoming.get(node.id) || [];
        let layer = 0;
        let x = 0;
        if (parents.length) {
          layer = Math.max(...parents.map(edge => (positions.get(edge.source)?.layer || 0) + 1));
          const parentXs = parents.map(edge => positions.get(edge.source)?.x || 0);
          x = parentXs.reduce((sum, value) => sum + value, 0) / parentXs.length;
          const branch = parents[0]?.label?.toLowerCase();
          if (["yes", "success"].includes(branch)) x -= 165;
          if (["no", "error"].includes(branch)) x += 165;
        }
        const occupied = layerCounts.get(layer) || [];
        while (occupied.some(value => Math.abs(value - x) < 210)) x += 230;
        occupied.push(x);
        layerCounts.set(layer, occupied);
        positions.set(node.id, { x, y: layer * 150, layer, order: index });
      });

      // Apply any hand-placed overrides for this flow before measuring bounds.
      const overrides = manualPositions.get(flow.id);
      if (overrides) {
        overrides.forEach((point, nodeId) => {
          const position = positions.get(nodeId);
          if (position) { position.x = point.x; position.y = point.y; position.moved = true; }
        });
      }

      const values = [...positions.values()];
      const minX = Math.min(...values.map(item => item.x), 0);
      const maxX = Math.max(...values.map(item => item.x), 0);
      const minY = Math.min(...values.map(item => item.y), 0);
      const maxY = Math.max(...values.map(item => item.y), 0);
      return { positions, bounds: { minX, maxX, minY, maxY } };
    }

    // One source for an edge's curved path + label anchor, reused on first render and
    // live while a node is dragged so connected edges follow.
    function edgeGeometry(start, end) {
      const startY = start.y + 43;
      const endY = end.y - 43;
      const middleY = (startY + endY) / 2;
      return {
        d: `M ${start.x} ${startY} C ${start.x} ${middleY}, ${end.x} ${middleY}, ${end.x} ${endY}`,
        labelX: (start.x + end.x) / 2 + 7,
        labelY: middleY - 6,
      };
    }

    function renderFlow(flow) {
      svg.replaceChildren();
      if (!flow.nodes.length) {
        document.getElementById("emptyState").style.display = "grid";
        return;
      }
      document.getElementById("emptyState").style.display = "none";
      const { positions, bounds } = layoutFlow(flow);
      const padding = 170;
      const top = Math.min(-90, bounds.minY - 70);
      view = {
        x: bounds.minX - padding,
        y: top,
        width: Math.max(760, bounds.maxX - bounds.minX + padding * 2),
        height: Math.max(600, bounds.maxY - top + 250)
      };
      updateViewBox();

      const defs = svgEl("defs");
      defs.innerHTML = `
        <filter id="nodeShadow" x="-30%" y="-30%" width="160%" height="180%">
          <feDropShadow dx="0" dy="8" stdDeviation="8" flood-color="#1e2e4e" flood-opacity=".10"/>
        </filter>
        <filter id="nodeLift" x="-45%" y="-45%" width="190%" height="210%">
          <feDropShadow dx="0" dy="16" stdDeviation="14" flood-color="#1e2e4e" flood-opacity=".24"/>
        </filter>
        <marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
          <path d="M0,0 L8,4 L0,8 z" fill="#9ba8bf"></path>
        </marker>`;
      svg.appendChild(defs);

      const spine = svgEl("line");
      spine.setAttribute("class", "decision-spine");
      spine.setAttribute("x1", "0");
      spine.setAttribute("y1", "-20");
      spine.setAttribute("x2", "0");
      spine.setAttribute("y2", String(bounds.maxY + 100));
      svg.appendChild(spine);

      // Keep edge element references per node so dragging a block re-routes its edges live.
      const nodeEdges = new Map(flow.nodes.map(node => [node.id, []]));
      const edgeLayer = svgEl("g");
      flow.edges.forEach(edge => {
        const start = positions.get(edge.source);
        const end = positions.get(edge.target);
        if (!start || !end) return;
        const geometry = edgeGeometry(start, end);
        const path = svgEl("path");
        path.setAttribute("class", "edge");
        path.setAttribute("d", geometry.d);
        edgeLayer.appendChild(path);
        let label = null;
        if (edge.label) {
          label = svgEl("text");
          label.setAttribute("class", "edge-label");
          label.setAttribute("x", String(geometry.labelX));
          label.setAttribute("y", String(geometry.labelY));
          label.textContent = edge.label;
          edgeLayer.appendChild(label);
        }
        const record = { edge, path, label };
        nodeEdges.get(edge.source)?.push(record);
        nodeEdges.get(edge.target)?.push(record);
      });
      svg.appendChild(edgeLayer);

      function rerouteFrom(nodeId) {
        (nodeEdges.get(nodeId) || []).forEach(({ edge, path, label }) => {
          const start = positions.get(edge.source);
          const end = positions.get(edge.target);
          if (!start || !end) return;
          const geometry = edgeGeometry(start, end);
          path.setAttribute("d", geometry.d);
          if (label) {
            label.setAttribute("x", String(geometry.labelX));
            label.setAttribute("y", String(geometry.labelY));
          }
        });
      }

      const nodeLayer = svgEl("g");
      flow.nodes.forEach(node => {
        const position = positions.get(node.id);
        const group = svgEl("g");
        group.setAttribute("class", `node ${node.kind}${findingsByNode.has(node.id) ? " has-finding" : ""}`);
        group.setAttribute("transform", `translate(${position.x} ${position.y})`);
        group.setAttribute("tabindex", "0");
        group.setAttribute("role", "button");
        group.setAttribute("aria-label", `${node.kind}: ${node.label}`);
        // Drag to rearrange the block; a plain click (no real movement) opens the inspector.
        let nodeDrag = null;
        group.addEventListener("pointerdown", event => {
          if (event.button !== 0) return;
          event.stopPropagation();
          nodeDrag = {
            x: event.clientX,
            y: event.clientY,
            ox: position.x,
            oy: position.y,
            scaleX: view.width / svg.clientWidth,
            scaleY: view.height / svg.clientHeight,
            moved: 0
          };
          group.classList.add("dragging");
          group.setPointerCapture(event.pointerId);
        });
        group.addEventListener("pointermove", event => {
          if (!nodeDrag) return;
          const dx = (event.clientX - nodeDrag.x) * nodeDrag.scaleX;
          const dy = (event.clientY - nodeDrag.y) * nodeDrag.scaleY;
          nodeDrag.moved = Math.max(nodeDrag.moved, Math.abs(dx) + Math.abs(dy));
          position.x = nodeDrag.ox + dx;
          position.y = nodeDrag.oy + dy;
          group.setAttribute("transform", `translate(${position.x} ${position.y})`);
          rerouteFrom(node.id);
        });
        const endNodeDrag = event => {
          if (!nodeDrag) return;
          group.classList.remove("dragging");
          try { group.releasePointerCapture(event.pointerId); } catch (_) {}
          if (nodeDrag.moved < 4) {
            inspectNode(flow, node);
          } else {
            const store = manualPositions.get(flow.id) || new Map();
            store.set(node.id, { x: position.x, y: position.y });
            manualPositions.set(flow.id, store);
          }
          nodeDrag = null;
        };
        group.addEventListener("pointerup", endNodeDrag);
        group.addEventListener("pointercancel", endNodeDrag);
        group.addEventListener("keydown", event => {
          if (event.key === "Enter" || event.key === " ") { event.preventDefault(); inspectNode(flow, node); }
        });
        const shape = nodeShape(node.kind);
        shape.setAttribute("class", "shape");
        group.appendChild(shape);
        const lines = wrapLabel(node.label, node.kind === "decision" ? 25 : 31);
        lines.forEach((line, index) => {
          const text = svgEl("text");
          text.setAttribute("text-anchor", "middle");
          text.setAttribute("y", String((index - (lines.length - 1) / 2) * 17 + 1));
          text.textContent = line;
          group.appendChild(text);
        });
        const meta = svgEl("text");
        meta.setAttribute("class", "meta");
        meta.setAttribute("text-anchor", "middle");
        meta.setAttribute("y", "62");
        meta.textContent = `${node.location.path}:${node.location.start_line}`;
        group.appendChild(meta);
        nodeLayer.appendChild(group);
      });
      svg.appendChild(nodeLayer);
    }

    function nodeShape(kind) {
      if (kind === "decision") {
        const polygon = svgEl("polygon");
        polygon.setAttribute("points", "0,-58 145,0 0,58 -145,0");
        return polygon;
      }
      const rect = svgEl("rect");
      rect.setAttribute("x", "-145");
      rect.setAttribute("y", "-43");
      rect.setAttribute("width", "290");
      rect.setAttribute("height", "86");
      rect.setAttribute("rx", kind === "entry" || kind === "terminal" ? "43" : kind === "call" ? "5" : "12");
      return rect;
    }

    function inspectFlow(flow) {
      detailsEl.replaceChildren();
      const badge = element("span", "detail-kind", flow.is_entrypoint ? "Entry point" : "Subflow");
      const title = element("h3", "", flow.name);
      const description = element("p", "", `${flow.symbol} · ${flow.nodes.length} nodes · ${flow.edges.length} paths`);
      detailsEl.append(badge, title, description, sourceLink(flow.location));
      const related = findings.filter(item => item.flow_id === flow.id);
      if (related.length) {
        detailsEl.append(element("div", "section-label", "Review points"));
        related.forEach(item => detailsEl.append(findingCard(item)));
      }
      if (flow.tests?.length) {
        detailsEl.append(element("div", "section-label", "Referenced by tests"));
        flow.tests.forEach(test => detailsEl.append(element("p", "", test)));
      }
    }

    function inspectNode(flow, node) {
      rightRail.classList.add("open");
      detailsEl.replaceChildren();
      detailsEl.append(
        element("span", "detail-kind", `${node.kind} · ${node.evidence}`),
        element("h3", "", node.label)
      );
      if (node.detail) detailsEl.append(element("p", "", node.detail));
      detailsEl.append(sourceLink(node.location));
      const nodeFindings = findingsByNode.get(node.id) || [];
      if (nodeFindings.length) {
        detailsEl.append(element("div", "section-label", "Review points"));
        nodeFindings.forEach(item => detailsEl.append(findingCard(item)));
      }
      if (node.metadata?.target_flow && byId.has(node.metadata.target_flow)) {
        const target = byId.get(node.metadata.target_flow);
        const link = element("button", "subflow-link", `Open subflow → ${target.name}`);
        link.addEventListener("click", () => selectFlow(target.id));
        detailsEl.append(element("div", "section-label", "Internal call"), link);
      }
      if (node.metadata?.condition) {
        detailsEl.append(element("div", "section-label", "Decision evidence"));
        detailsEl.append(element("p", "", node.metadata.condition));
      }
    }

    function findingCard(item) {
      const card = element("div", `finding ${item.severity}`, item.message);
      if (item.detail) card.title = item.detail;
      return card;
    }

    function sourceLink(location) {
      const link = element("a", "source-link", `${location.path}:${location.start_line}`);
      const absolute = `${model.root}/${location.path}`.replaceAll("//", "/");
      link.href = `vscode://file/${absolute}:${location.start_line}`;
      link.title = "Open source in VS Code";
      return link;
    }

    function element(tag, className, text) {
      const item = document.createElement(tag);
      if (className) item.className = className;
      item.textContent = text;
      return item;
    }

    function svgEl(tag) {
      return document.createElementNS("http://www.w3.org/2000/svg", tag);
    }

    function wrapLabel(value, width) {
      const words = value.split(/\s+/);
      const lines = [];
      let current = "";
      words.forEach(word => {
        if (!current || `${current} ${word}`.length <= width) current = current ? `${current} ${word}` : word;
        else { lines.push(current); current = word; }
      });
      if (current) lines.push(current);
      return lines.slice(0, 3);
    }

    function updateViewBox() {
      svg.setAttribute("viewBox", `${view.x} ${view.y} ${view.width} ${view.height}`);
    }

    function zoom(factor) {
      const nextWidth = view.width * factor;
      const nextHeight = view.height * factor;
      view.x += (view.width - nextWidth) / 2;
      view.y += (view.height - nextHeight) / 2;
      view.width = nextWidth;
      view.height = nextHeight;
      updateViewBox();
    }

    searchEl.addEventListener("input", event => renderList(event.target.value));
    document.getElementById("zoomIn").addEventListener("click", () => zoom(.82));
    document.getElementById("zoomOut").addEventListener("click", () => zoom(1.22));
    document.getElementById("resetView").addEventListener("click", () => {
      if (!activeFlow) return;
      manualPositions.delete(activeFlow.id);  // discard hand-placed positions, re-layout
      renderFlow(activeFlow);
    });
    document.getElementById("menuButton").addEventListener("click", () => leftRail.classList.toggle("open"));

    svg.addEventListener("wheel", event => {
      event.preventDefault();
      zoom(event.deltaY > 0 ? 1.08 : .92);
    }, { passive: false });
    svg.addEventListener("pointerdown", event => {
      drag = { x: event.clientX, y: event.clientY, vx: view.x, vy: view.y };
      svg.classList.add("dragging");
      svg.setPointerCapture(event.pointerId);
    });
    svg.addEventListener("pointermove", event => {
      if (!drag) return;
      const scaleX = view.width / svg.clientWidth;
      const scaleY = view.height / svg.clientHeight;
      view.x = drag.vx - (event.clientX - drag.x) * scaleX;
      view.y = drag.vy - (event.clientY - drag.y) * scaleY;
      updateViewBox();
    });
    svg.addEventListener("pointerup", () => { drag = null; svg.classList.remove("dragging"); });

    renderList();
    const requested = decodeURIComponent(location.hash.slice(1));
    const initial = byId.get(requested) || flows.find(item => item.is_entrypoint) || flows[0];
    if (initial) selectFlow(initial.id);
  </script>
</body>
</html>
"""
