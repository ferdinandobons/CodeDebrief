"""Viewer-shell smoke tests.

The HTML viewer is assembled from a template plus extracted assets
(``render/assets/styles.css`` and ``render/assets/shell.js``) and a JSON payload
built by :func:`build_payload`. These tests pin the seams so a future split of
the assets cannot silently drop the style block, the data hook, or the canvas.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from logicchart.analysis.project import ProjectAnalyzer
from logicchart.render.html import render_html
from logicchart.render.payload import build_payload


def _model(tmp_path: Path):
    (tmp_path / "service.py").write_text(
        "def handle(account):\n    if account.active:\n        return ok()\n    return denied()\n",
        encoding="utf-8",
    )
    return ProjectAnalyzer(tmp_path).analyze(full=True).model


def test_render_html_emits_shell(tmp_path: Path) -> None:
    html = render_html(_model(tmp_path), tmp_path)
    # Style block survived the asset extraction.
    assert "<style>" in html
    # The JSON payload hook the shell script reads from is present.
    assert "logicchart-data" in html
    # The main canvas the viewer draws into is wired up.
    assert 'id="canvas"' in html


def test_build_payload_has_flows(tmp_path: Path) -> None:
    payload = build_payload(_model(tmp_path), tmp_path)
    assert isinstance(payload, dict)
    assert payload["flows"]


def test_render_html_emits_directory_tree(tmp_path: Path) -> None:
    html = render_html(_model(tmp_path), tmp_path)
    # The directory tree container the left rail renders into is wired up.
    assert 'id="tree"' in html
    # The language dropdown above the tree is present (hidden until >1 language).
    assert 'id="langFilter"' in html
    # tree.js is actually inlined into the page (a function unique to it). Asserting a
    # runtime-only DOM attribute like data-flow-id would pass vacuously just because the
    # script source mentions it, so we pin a structural marker instead.
    assert "refreshRovingTarget" in html

    # The embedded JSON payload carries a non-empty directory tree (file leaves with
    # flow ids), not just the literal key. Parse the data <script> and check it.
    match = re.search(
        r'<script id="logicchart-data" type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    )
    assert match is not None
    payload = json.loads(match.group(1).replace("<\\/", "</"))
    tree = payload["tree"]
    assert tree["type"] == "dir"
    assert tree["children"], "expected at least one file/dir node in the tree"

    def _has_flow_leaf(node: dict) -> bool:
        if node["type"] == "file" and node["flow_ids"]:
            return True
        return any(_has_flow_leaf(child) for child in node["children"])

    assert _has_flow_leaf(tree), "expected a file leaf carrying flow ids"


def test_render_html_has_no_leftover_placeholders(tmp_path: Path) -> None:
    html = render_html(_model(tmp_path), tmp_path)
    for placeholder in (
        "__STYLES__",
        "__SHELL_JS__",
        "__CANVAS_JS__",
        "__TREE_JS__",
        "__LOGICCHART_DATA__",
    ):
        assert placeholder not in html


def test_render_html_emits_codebase_canvas(tmp_path: Path) -> None:
    html = render_html(_model(tmp_path), tmp_path)
    # The canvas carries a level attribute (L0 by default); the Phase-2 smoke test
    # asserts the level seam exists so the two-level canvas cannot silently regress.
    assert "data-level" in html
    # The breadcrumb container the canvas level path renders into is wired up.
    assert 'id="breadcrumb"' in html
    # canvas.js is actually inlined: a structural marker unique to it (the renderL0
    # entry) plus the data-scope attribute literal it stamps on every super-node.
    assert "renderL0" in html
    assert "data-scope" in html
    # The payload carries the aggregated cross-scope edge list the L0 view draws.
    match = re.search(
        r'<script id="logicchart-data" type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    )
    assert match is not None
    payload = json.loads(match.group(1).replace("<\\/", "</"))
    assert isinstance(payload["scope_edges"], list)
