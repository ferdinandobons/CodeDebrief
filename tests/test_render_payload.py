"""Unit tests for the viewer payload builder.

``build_payload`` derives, from the analyzed model, the structures the navigable
viewer needs: a nested directory tree (dirs/files with flow ids on file leaves)
and a scope index (flow ids grouped by scope). Both are pure functions of the
model, so they are tested directly here, independent of the HTML shell.
"""

from __future__ import annotations

from pathlib import Path

from logicchart.analysis.project import ProjectAnalyzer
from logicchart.model import ProjectModel
from logicchart.render.payload import build_payload


def _analyze(tmp_path: Path) -> ProjectModel:
    return ProjectAnalyzer(tmp_path).analyze(full=True).model


def _find(node: dict, path: str) -> dict | None:
    """Depth-first lookup of a tree node by its ``path``."""
    if node.get("path") == path:
        return node
    for child in node.get("children", []):
        hit = _find(child, path)
        if hit is not None:
            return hit
    return None


def test_payload_has_directory_tree_and_scopes(tmp_path: Path) -> None:
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "svc.py").write_text(
        "def handler(x):\n    if x:\n        return 1\n    return 0\n",
        encoding="utf-8",
    )
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "page.ts").write_text(
        "export function render(items: number[]) {\n  return items.length;\n}\n",
        encoding="utf-8",
    )
    # A test file: its flows are tagged metadata.test and must be excluded from the
    # tree (the old left rail hid them via !flow.metadata.test). Since this file holds
    # only test flows, its leaf must be dropped entirely.
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_svc.py").write_text(
        "def test_handler():\n    if True:\n        return 1\n    return 0\n",
        encoding="utf-8",
    )
    model = _analyze(tmp_path)
    payload = build_payload(model, tmp_path)

    # --- tree ---------------------------------------------------------------
    tree = payload["tree"]
    # Root is a directory with the exact node shape.
    assert set(tree.keys()) == {"name", "path", "type", "children", "flow_ids"}
    assert tree["type"] == "dir"
    assert tree["flow_ids"] == []
    names = {c["name"] for c in tree["children"]}
    assert "backend" in names
    assert "frontend" in names

    # Directories are ordered before files, both sorted by name (deterministic).
    backend = next(c for c in tree["children"] if c["name"] == "backend")
    assert backend["type"] == "dir"
    assert backend["path"] == "backend"
    assert backend["flow_ids"] == []  # dirs carry no flow ids

    # The file leaf carries the ids of the flows declared in that file.
    leaf = _find(tree, "backend/svc.py")
    assert leaf is not None
    assert leaf["type"] == "file"
    assert leaf["children"] == []
    handler = next(f for f in model.flows if f.name == "handler")
    assert handler.id in leaf["flow_ids"]

    # Test flows are excluded: the test file leaf is dropped, and since `tests/`
    # held only test flows the directory itself is pruned too. No test flow id may
    # appear anywhere in the tree.
    assert _find(tree, "tests/test_svc.py") is None
    assert _find(tree, "tests") is None
    test_flow = next(f for f in model.flows if f.metadata.get("test"))

    def _all_flow_ids(node: dict) -> set[str]:
        ids = set(node["flow_ids"])
        for child in node["children"]:
            ids |= _all_flow_ids(child)
        return ids

    assert test_flow.id not in _all_flow_ids(tree)

    # Every tree node has exactly the agreed shape.
    def _check_shape(node: dict) -> None:
        assert set(node.keys()) == {"name", "path", "type", "children", "flow_ids"}
        assert node["type"] in ("dir", "file")
        for child in node["children"]:
            _check_shape(child)

    _check_shape(tree)

    # --- scopes -------------------------------------------------------------
    scopes = payload["scopes"]
    assert isinstance(scopes, dict)
    # Inferred top-level directory scopes when none are declared.
    assert handler.id in scopes["backend"]
    render = next(f for f in model.flows if f.name == "render")
    assert render.id in scopes["frontend"]
    # The scope index covers exactly the flow ids in the model.
    indexed = {fid for ids in scopes.values() for fid in ids}
    assert indexed == {f.id for f in model.flows}

    # --- languages ----------------------------------------------------------
    # Distinct non-test flow languages, sorted. The polyglot fixture has python
    # (backend) and typescript (frontend); the test flow's language is excluded.
    languages = payload["languages"]
    assert languages == sorted(set(languages))
    assert "python" in languages
    assert "typescript" in languages
