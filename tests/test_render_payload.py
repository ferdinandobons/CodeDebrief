"""Unit tests for the viewer payload builder.

``build_payload`` derives, from the analyzed model, the structures the navigable
viewer needs: a nested directory tree (dirs/files with flow ids on file leaves)
and a scope index (flow ids grouped by scope). Both are pure functions of the
model, so they are tested directly here, independent of the HTML shell.
"""

from __future__ import annotations

from pathlib import Path

from logicchart.analysis.project import ProjectAnalyzer
from logicchart.model import (
    Flow,
    ProjectModel,
    SourceLocation,
)
from logicchart.render.payload import build_payload, build_scope_edges, build_scope_index


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
    # Test flows are excluded from the scope index with the same predicate the tree,
    # language, and scope-edge builders use, so L0/L1 agree with the tree's non-test
    # universe. The `tests/` directory held only test flows, so no `tests` scope
    # surfaces (it would otherwise be a super-node the tree hides), and the test
    # flow's id appears under no scope at all.
    assert "tests" not in scopes
    assert test_flow.id not in {fid for ids in scopes.values() for fid in ids}
    # The scope index covers exactly the non-test flow ids in the model.
    indexed = {fid for ids in scopes.values() for fid in ids}
    assert indexed == {f.id for f in model.flows if not f.metadata.get("test")}

    # --- languages ----------------------------------------------------------
    # Distinct non-test flow languages, sorted. The polyglot fixture has python
    # (backend) and typescript (frontend); the test flow's language is excluded.
    languages = payload["languages"]
    assert languages == sorted(set(languages))
    assert "python" in languages
    assert "typescript" in languages

    # --- scope_edges --------------------------------------------------------
    # Present in the payload (the canvas L0 draws aggregated cross-scope calls).
    assert "scope_edges" in payload
    assert isinstance(payload["scope_edges"], list)


def _flow(flow_id: str, *, scope: list[str], path: str, calls: list[str]) -> Flow:
    """A minimal Flow carrying just the fields ``build_scope_edges`` reads."""
    return Flow(
        id=flow_id,
        name=flow_id,
        symbol=flow_id,
        language="python",
        framework="generic",
        entry_kind="function",
        is_entrypoint=False,
        location=SourceLocation(path=path, start_line=1, end_line=2),
        calls=list(calls),
        metadata={"scope": list(scope)},
    )


def test_build_scope_edges_counts_cross_scope_calls() -> None:
    # Two flows in two scopes, one calling the other -> a single from!=to edge.
    flows = [
        _flow("a", scope=["backend"], path="backend/a.py", calls=["b"]),
        _flow("b", scope=["frontend"], path="frontend/b.py", calls=[]),
    ]
    scope_index = build_scope_index(flows)
    edges = build_scope_edges(flows, scope_index)
    assert edges == [{"from": "backend", "to": "frontend", "count": 1}]


def test_build_scope_edges_excludes_self_scope_and_unresolved() -> None:
    # An intra-scope call and a call to an unknown id are both dropped at L0.
    flows = [
        _flow("a", scope=["backend"], path="backend/a.py", calls=["b", "ghost"]),
        _flow("b", scope=["backend"], path="backend/b.py", calls=[]),
    ]
    scope_index = build_scope_index(flows)
    assert build_scope_edges(flows, scope_index) == []


def test_build_scope_edges_attributes_multi_scope_membership() -> None:
    # A flow listed under two scopes attributes its cross-scope calls to each
    # membership (the documented double-count convention).
    flows = [
        _flow("a", scope=["backend", "shared"], path="backend/a.py", calls=["b"]),
        _flow("b", scope=["frontend"], path="frontend/b.py", calls=[]),
    ]
    scope_index = build_scope_index(flows)
    edges = build_scope_edges(flows, scope_index)
    pairs = {(e["from"], e["to"]): e["count"] for e in edges}
    assert pairs == {("backend", "frontend"): 1, ("shared", "frontend"): 1}


def test_build_scope_edges_excludes_test_flows() -> None:
    # Test flows are excluded from the L0 aggregate, like the tree/language indexes.
    caller = _flow("a", scope=["backend"], path="backend/a.py", calls=["b"])
    caller.metadata["test"] = True
    flows = [
        caller,
        _flow("b", scope=["frontend"], path="frontend/b.py", calls=[]),
    ]
    scope_index = build_scope_index(flows)
    assert build_scope_edges(flows, scope_index) == []


def test_build_scope_index_excludes_test_flows() -> None:
    # A test flow must not contribute its scope membership to the index, so the L0
    # scope counts and L1 nodes agree with the directory tree (which hides test
    # flows). A scope that would contain only test flows is dropped entirely.
    prod = _flow("a", scope=["backend"], path="backend/a.py", calls=[])
    test_only = _flow("t", scope=["tests"], path="tests/test_a.py", calls=[])
    test_only.metadata["test"] = True
    index = build_scope_index([prod, test_only])
    # The test flow's scope membership is absent from the index entirely.
    assert "tests" not in index
    assert "t" not in {fid for ids in index.values() for fid in ids}
    # The surviving non-test flow is still indexed under its scope.
    assert index == {"backend": ["a"]}
