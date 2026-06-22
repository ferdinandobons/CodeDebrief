"""Unit tests for the viewer payload builder.

``build_payload`` derives, from the analyzed model, the structures the navigable
viewer needs: a nested directory tree (dirs/files with flow ids on file leaves)
and a scope index (flow ids grouped by scope). Both are pure functions of the
model, so they are tested directly here, independent of the HTML shell.
"""

from __future__ import annotations

from pathlib import Path

from codedebrief.analysis.project import ProjectAnalyzer
from codedebrief.model import (
    FileRecord,
    Flow,
    ProjectModel,
    SourceLocation,
)
from codedebrief.render.payload import (
    attach_source_snippets,
    build_payload,
    build_scope_edges,
    build_scope_index,
    build_tree,
)


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


def test_build_tree_dedupes_duplicate_file_flow_ids() -> None:
    flow = _flow("handler", scope=["backend"], path="backend/svc.py", calls=[])
    files = [
        FileRecord(
            path="backend/svc.py",
            language="python",
            sha256="sha",
            flow_ids=["handler", "handler"],
        )
    ]

    tree = build_tree(files, [flow])
    leaf = _find(tree, "backend/svc.py")

    assert leaf is not None
    assert leaf["flow_ids"] == ["handler"]


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


def _resolve_flow_lines(payload: dict, flow: dict) -> list[str]:
    """Resolve a flow's embedded source the way the viewer does: slice its window out of
    the shared ``source_files`` store (the file is embedded once, the flow holds a ref)."""
    ref = flow["source"]
    file = payload["source_files"][ref["path"]]
    ranges = file.get("ranges")
    if ranges is None:
        ranges = [{"start_line": file["start_line"], "lines": file["lines"]}]
    for range_ in ranges:
        offset = ref["start_line"] - range_["start_line"]
        if offset < 0:
            continue
        lines = range_["lines"][offset : offset + (ref["end_line"] - ref["start_line"] + 1)]
        if lines:
            return lines
    return []


def test_payload_embeds_source_via_file_store(tmp_path: Path) -> None:
    # A flow carries a lightweight reference into the shared source_files store, not its
    # own copy of the lines; resolving the reference yields exactly the flow's line range.
    (tmp_path / "a.py").write_text(
        "def f(x):\n    if x:\n        return 1\n    return 0\n",
        encoding="utf-8",
    )
    model = _analyze(tmp_path)
    payload = build_payload(model, tmp_path)
    flow = payload["flows"][0]
    ref = flow["source"]
    assert ref["path"] == flow["location"]["path"]
    # The clamped start (lo=max(1,start)) is stored, so gutter line numbers are correct.
    assert ref["start_line"] == max(1, flow["location"]["start_line"])
    lines = _resolve_flow_lines(payload, flow)
    expected = ref["end_line"] - ref["start_line"] + 1
    assert len(lines) == expected
    assert any("if x" in line for line in lines)
    # Lines are stored verbatim (no trailing newline kept, plain text).
    assert all("\n" not in line for line in lines)


def test_attach_source_snippets_tolerates_missing_file(tmp_path: Path) -> None:
    # A flow whose file is absent under source_root gets source=None, never crashes,
    # while a sibling flow with a real file still gets its reference + embedded lines.
    (tmp_path / "real.py").write_text("def g():\n    return 1\n", encoding="utf-8")
    flow_dicts: list[dict] = [
        {"location": {"path": "real.py", "start_line": 1, "end_line": 2}},
        {"location": {"path": "ghost.py", "start_line": 1, "end_line": 3}},
    ]
    source_files = attach_source_snippets(flow_dicts, tmp_path)
    assert flow_dicts[0]["source"] == {"path": "real.py", "start_line": 1, "end_line": 2}
    assert source_files["real.py"] == {
        "ranges": [{"start_line": 1, "lines": ["def g():", "    return 1"]}]
    }
    assert flow_dicts[1]["source"] is None
    assert "ghost.py" not in source_files


def test_attach_source_snippets_tolerates_binary_file(tmp_path: Path) -> None:
    # A binary/undecodable file yields source=None, not a crash.
    (tmp_path / "blob.py").write_bytes(b"\x00\x01\x02\xff\xfe\n")
    flow_dicts: list[dict] = [
        {"location": {"path": "blob.py", "start_line": 1, "end_line": 1}},
    ]
    source_files = attach_source_snippets(flow_dicts, tmp_path)
    assert flow_dicts[0]["source"] is None
    assert source_files == {}


def test_attach_source_snippets_caps_long_flow(tmp_path: Path) -> None:
    # A flow over a function longer than MAX_SNIPPET_LINES embeds only the head lines and
    # marks the tail elided -- the embedded span is bounded regardless of function size.
    from codedebrief.render.payload import MAX_SNIPPET_LINES

    total = MAX_SNIPPET_LINES + 120
    big = "def f():\n" + "".join(f"    x{i} = {i}\n" for i in range(total))
    (tmp_path / "big.py").write_text(big, encoding="utf-8")
    flow_dicts: list[dict] = [
        {"location": {"path": "big.py", "start_line": 1, "end_line": total + 1}},
    ]
    source_files = attach_source_snippets(flow_dicts, tmp_path)
    ref = flow_dicts[0]["source"]
    assert ref["elided"] is True
    # The reference keeps the full (uncapped) end so the panel can show "N more lines".
    assert ref["end_line"] == total + 1
    # The file store only embeds the capped head window, never the whole function.
    assert len(source_files["big.py"]["ranges"][0]["lines"]) == MAX_SNIPPET_LINES


def test_attach_source_snippets_dedupes_file_across_flows(tmp_path: Path) -> None:
    # Two flows in the same file embed that file once but preserve disjoint ranges, so
    # unrelated gap lines are not copied into the HTML payload.
    (tmp_path / "two.py").write_text(
        "def a():\n    return 1\n\n\ndef b():\n    return 2\n",
        encoding="utf-8",
    )
    flow_dicts: list[dict] = [
        {"location": {"path": "two.py", "start_line": 1, "end_line": 2}},
        {"location": {"path": "two.py", "start_line": 5, "end_line": 6}},
    ]
    source_files = attach_source_snippets(flow_dicts, tmp_path)
    # One file entry shared by both flows; both references point at the same path.
    assert list(source_files.keys()) == ["two.py"]
    assert flow_dicts[0]["source"]["path"] == "two.py"
    assert flow_dicts[1]["source"]["path"] == "two.py"
    entry = source_files["two.py"]
    assert entry["ranges"] == [
        {"start_line": 1, "lines": ["def a():", "    return 1"]},
        {"start_line": 5, "lines": ["def b():", "    return 2"]},
    ]


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


def test_build_scope_index_normalizes_legacy_string_scope() -> None:
    flow = _flow("a", scope=["frontend"], path="frontend/a.py", calls=[])
    flow.metadata["scope"] = "frontend"

    assert build_scope_index([flow]) == {"frontend": ["a"]}
