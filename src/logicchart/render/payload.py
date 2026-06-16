from __future__ import annotations

from pathlib import Path
from typing import Any

from logicchart.model import FileRecord, Flow, ProjectModel


def build_payload(model: ProjectModel, source_root: Path | None = None) -> dict[str, Any]:
    data = model.to_dict()
    if source_root is not None:
        data["root"] = str(source_root)
    data["tree"] = build_tree(model.files, model.flows)
    data["scopes"] = build_scope_index(model.flows)
    data["languages"] = build_language_index(model.flows)
    return data


def _is_test_flow(flow: Flow) -> bool:
    """Whether a flow is a test flow, mirroring the old left rail's ``!flow.metadata.test``."""
    return bool(flow.metadata.get("test"))


def build_tree(files: list[FileRecord], flows: list[Flow]) -> dict[str, Any]:
    """Fold file paths into a nested dir/file tree.

    Each node has the shape ``{name, path, type, children, flow_ids}``. ``flow_ids``
    is populated on file leaves with the ids of flows whose ``location.path`` is that
    file; directories always carry ``[]``. A flow whose file is missing from ``files``
    still gets a leaf so no flow is dropped from the tree. Children are ordered
    deterministically: directories before files, each group sorted by name.

    Test flows are excluded (the old left rail hid them via ``!flow.metadata.test``);
    a file with only test flows is dropped entirely, and a directory that ends up
    with no surviving descendants is dropped too, so counts are not inflated.
    """
    # Only non-test flows are eligible. Map each file path to the surviving flow ids.
    non_test = [flow for flow in flows if not _is_test_flow(flow)]
    by_id = {flow.id: flow for flow in non_test}

    flows_for_path: dict[str, list[str]] = {}
    for record in files:
        # Keep the file's flow ids, but only the non-test ones.
        kept = [fid for fid in record.flow_ids if fid in by_id]
        if kept:
            flows_for_path[record.path] = kept
    for flow in non_test:
        path = flow.location.path
        ids = flows_for_path.setdefault(path, [])
        if flow.id not in ids:
            ids.append(flow.id)

    root = _new_node("", "", "dir")
    for path in flows_for_path:
        _insert_path(root, path, flows_for_path[path])
    _prune_empty(root)
    _sort_children(root)
    return root


def build_language_index(flows: list[Flow]) -> list[str]:
    """Sorted list of distinct ``flow.language`` across non-test flows.

    Powers the viewer's language dropdown for polyglot repos. Test flows are excluded
    so a language that only appears in tests does not surface a filter option for it.
    """
    languages = {flow.language for flow in flows if not _is_test_flow(flow) and flow.language}
    return sorted(languages)


def build_scope_index(flows: list[Flow]) -> dict[str, list[str]]:
    """Group flow ids by scope.

    Uses ``flow.metadata["scope"]`` (a list) when present; otherwise infers the
    scope as the top-level directory segment of ``flow.location.path`` (so it works
    with no ``[logicchart.scopes]`` declared). Never hard-codes scope names.
    """
    index: dict[str, list[str]] = {}
    for flow in flows:
        scopes = flow.metadata.get("scope")
        if not scopes:
            scopes = [_top_level_segment(flow.location.path)]
        for scope in scopes:
            index.setdefault(scope, []).append(flow.id)
    return index


def _top_level_segment(path: str) -> str:
    """The first path segment, or the file's own name for a root-level file."""
    parts = [part for part in path.split("/") if part]
    return parts[0] if parts else path


def _new_node(name: str, path: str, node_type: str) -> dict[str, Any]:
    return {"name": name, "path": path, "type": node_type, "children": [], "flow_ids": []}


def _insert_path(root: dict[str, Any], path: str, flow_ids: list[str]) -> None:
    segments = [part for part in path.split("/") if part]
    if not segments:
        return
    node = root
    prefix = ""
    for index, segment in enumerate(segments):
        prefix = f"{prefix}/{segment}" if prefix else segment
        is_leaf = index == len(segments) - 1
        child = next((c for c in node["children"] if c["name"] == segment), None)
        if child is None:
            child = _new_node(segment, prefix, "file" if is_leaf else "dir")
            node["children"].append(child)
        node = child
    # `node` is now the leaf; attach flow ids without duplicating.
    for flow_id in flow_ids:
        if flow_id not in node["flow_ids"]:
            node["flow_ids"].append(flow_id)


def _prune_empty(node: dict[str, Any]) -> None:
    """Drop file leaves with no flow ids and directories with no surviving descendants.

    Recurses depth-first so a directory whose children all get pruned is itself dropped.
    The root is never removed by this (callers keep it), only its empty subtrees.
    """
    kept: list[dict[str, Any]] = []
    for child in node["children"]:
        if child["type"] == "dir":
            _prune_empty(child)
            if child["children"]:
                kept.append(child)
        elif child["flow_ids"]:
            kept.append(child)
    node["children"] = kept


def _sort_children(node: dict[str, Any]) -> None:
    node["children"].sort(key=lambda c: (c["type"] != "dir", c["name"]))
    for child in node["children"]:
        _sort_children(child)
