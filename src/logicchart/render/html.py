from __future__ import annotations

import json
from pathlib import Path

from logicchart.model import ProjectModel
from logicchart.render.payload import build_payload


def _asset(name: str) -> str:
    return (Path(__file__).parent / "assets" / name).read_text(encoding="utf-8")


def render_html(model: ProjectModel, source_root: Path | None = None) -> str:
    payload = json.dumps(build_payload(model, source_root), ensure_ascii=False).replace(
        "</", "<\\/"
    )
    css = _asset("styles.css")
    js = _asset("shell.js")
    canvas_js = _asset("canvas.js")
    tree_js = _asset("tree.js")
    return (
        _HTML_TEMPLATE.replace("__STYLES__", css)
        .replace("__SHELL_JS__", js)
        .replace("__CANVAS_JS__", canvas_js)
        .replace("__TREE_JS__", tree_js)
        .replace("__LOGICCHART_DATA__", payload)
    )


_HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LogicChart</title>
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 26 40'%3E%3Ccircle cx='13' cy='7.5' r='5.5' fill='%232f63ef'/%3E%3Cline x1='13' y1='17.5' x2='13' y2='21' stroke='%237458dc' stroke-width='3' stroke-linecap='round'/%3E%3Cpolygon points='13,25 19.5,31 13,37 6.5,31' fill='%23df9a12'/%3E%3C/svg%3E">
  <style>__STYLES__</style>
</head>
<body>
  <div class="shell">
    <header>
      <div class="brand">
        <div class="brand-mark" aria-hidden="true">
          <svg viewBox="0 0 26 40" xmlns="http://www.w3.org/2000/svg">
            <circle class="logo-node" cx="13" cy="7.5" r="5.5"></circle>
            <line class="logo-link" x1="13" y1="17.5" x2="13" y2="21"></line>
            <polygon class="logo-decision" points="13,25 19.5,31 13,37 6.5,31"></polygon>
          </svg>
        </div>
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
      <button class="theme-toggle" id="themeToggle" title="Toggle theme" aria-label="Toggle light/dark theme">&#9789;</button>
    </header>

    <aside class="left-rail" id="leftRail">
      <div class="rail-inner">
        <div class="rail-head">
          <h2 class="rail-title">Codebase</h2>
          <select class="filter" id="langFilter" aria-label="Filter by language" style="display:none"></select>
        </div>
        <div class="tree" id="tree" role="tree" aria-label="Directory tree"></div>
        <div class="legend">
          <span>Action</span><span class="decision">Decision</span>
          <span class="call">Subflow</span><span class="outcome">Outcome</span>
          <span class="gap">Review</span>
        </div>
      </div>
    </aside>

    <main>
      <nav id="breadcrumb" class="breadcrumb" aria-label="Canvas level"></nav>
      <div class="canvas-toolbar" aria-label="Canvas controls">
        <button class="tool" id="menuButton" title="Toggle flow list">&#9776;</button>
        <button class="tool" id="zoomOut" title="Zoom out">&minus;</button>
        <button class="tool" id="resetView" title="Reset view &amp; layout">0</button>
        <button class="tool" id="zoomIn" title="Zoom in">+</button>
      </div>
      <svg id="canvas" role="img" aria-label="Codebase canvas" data-level="0"></svg>
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
  <script>__SHELL_JS__</script>
  <script>__CANVAS_JS__</script>
  <script>__TREE_JS__</script>
</body>
</html>
"""
