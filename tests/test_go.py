"""Go support via the profile-driven tree-sitter engine (Stage B)."""

from __future__ import annotations

from pathlib import Path

from logicchart.analysis.project import ProjectAnalyzer
from logicchart.model import NodeKind, ProjectModel

_HANDLER = """package svc

type Status int

func Handle(status Status) string {
\tif status == Active {
\t\treturn "ok"
\t}
\tswitch status {
\tcase Active:
\t\treturn "a"
\tcase Suspended:
\t\treturn "s"
\t}
\treturn persist(status)
}

func persist(status Status) string {
\treturn "stored"
}

func (r *Repo) Fetch(id string) (string, error) {
\tfor i := 0; i < 3; i++ {
\t\tdata, err := query(id)
\t\tif err != nil {
\t\t\treturn "", err
\t\t}
\t\treturn data, nil
\t}
\treturn "", nil
}
"""


def _analyze(tmp_path: Path) -> ProjectModel:
    pkg = tmp_path / "svc"
    pkg.mkdir()
    (pkg / "handler.go").write_text(_HANDLER, encoding="utf-8")
    return ProjectAnalyzer(tmp_path).analyze(full=True).model


def _flow(model: ProjectModel, name: str):
    return next(f for f in model.flows if f.name == name)


def _reaches(flow, start_id: str) -> set[str]:
    out: dict[str, list[str]] = {}
    for edge in flow.edges:
        out.setdefault(edge.source, []).append(edge.target)
    seen: set[str] = set()
    stack = [start_id]
    while stack:
        cur = stack.pop()
        for nxt in out.get(cur, ()):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return seen


def test_go_flows_and_classification(tmp_path: Path) -> None:
    model = _analyze(tmp_path)
    by_name = {f.name: f for f in model.flows}
    assert {"Handle", "persist", "Repo.Fetch"} <= set(by_name)
    assert all(f.language == "go" for f in model.flows)
    # Exported function/method are entry points; an unexported one is not.
    assert by_name["Handle"].is_entrypoint
    assert by_name["Repo.Fetch"].is_entrypoint and by_name["Repo.Fetch"].entry_kind == "method"
    assert not by_name["persist"].is_entrypoint
    # Directory is the Go package, so symbols share the package module name.
    assert by_name["Handle"].symbol == "svc:Handle"
    assert by_name["persist"].symbol == "svc:persist"


def test_go_if_and_switch_decisions(tmp_path: Path) -> None:
    handle = _flow(_analyze(tmp_path), "Handle")
    decisions = [n for n in handle.nodes if n.kind is NodeKind.DECISION]
    labels = {n.label for n in decisions}
    assert "status == Active" in labels  # the if guard
    assert "Switch on status" in labels  # the value dispatch
    switch = next(n for n in decisions if n.label == "Switch on status")
    assert {"Active", "Suspended"} <= set(switch.metadata["values"])


def test_go_switch_without_default_is_flagged(tmp_path: Path) -> None:
    model = _analyze(tmp_path)
    handle = _flow(model, "Handle")
    kinds = {f.kind for f in model.findings if f.flow_id == handle.id}
    assert "missing_branch" in kinds


def test_go_same_package_call_resolves(tmp_path: Path) -> None:
    model = _analyze(tmp_path)
    handle = _flow(model, "Handle")
    persist = _flow(model, "persist")
    call = next(n for n in handle.nodes if n.kind is NodeKind.CALL)
    assert call.metadata["link_confidence"] == "high"
    assert call.metadata["target_flow"] == persist.id
    assert persist.id in handle.calls


def test_go_loop_body_is_modeled_before_post_loop(tmp_path: Path) -> None:
    fetch = _flow(_analyze(tmp_path), "Repo.Fetch")
    labels = [node.label for node in fetch.nodes]

    assert any(label.startswith("Repeat: for ") for label in labels)
    assert "Call query()" in labels
    assert "err != nil" in labels
    assert "Return data, nil" in labels
    assert 'Return "", nil' in labels

    loop = next(node for node in fetch.nodes if node.label.startswith("Repeat: for "))
    by_label = {node.label: node.id for node in fetch.nodes}
    assert any(
        edge.source == loop.id
        and edge.target == by_label["Call query()"]
        and edge.label == "Iteration"
        for edge in fetch.edges
    )
    assert any(
        edge.source == loop.id
        and edge.target == by_label['Return "", nil']
        and edge.label == "Done"
        for edge in fetch.edges
    )
    iteration_target = next(
        edge.target for edge in fetch.edges if edge.source == loop.id and edge.label == "Iteration"
    )
    reached = _reaches(fetch, iteration_target) | {iteration_target}
    assert by_label["err != nil"] in reached
    assert by_label["Return data, nil"] in reached
    assert by_label['Return "", nil'] not in reached


def test_go_multi_value_case_splits_into_individual_values(tmp_path: Path) -> None:
    # `case Active, Suspended:` groups two values under one label; each must appear as a
    # separate dispatched value (so enum coverage counts them individually).
    pkg = tmp_path / "svc"
    pkg.mkdir()
    (pkg / "multi.go").write_text(
        "package svc\n\n"
        "type Status int\n\n"
        "func Group(status Status) string {\n"
        "\tswitch status {\n"
        "\tcase Active, Suspended:\n"
        '\t\treturn "live"\n'
        "\tcase Deleted:\n"
        '\t\treturn "gone"\n'
        "\t}\n"
        '\treturn ""\n'
        "}\n",
        encoding="utf-8",
    )
    model = ProjectAnalyzer(tmp_path).analyze(full=True).model
    group = _flow(model, "Group")
    switch = next(
        n for n in group.nodes if n.kind is NodeKind.DECISION and n.label.startswith("Switch")
    )
    assert {"Active", "Suspended", "Deleted"} <= set(switch.metadata["values"])
    assert "Active, Suspended" not in switch.metadata["values"]


def test_go_test_functions_are_detected(tmp_path: Path) -> None:
    (tmp_path / "svc").mkdir()
    (tmp_path / "svc" / "handler.go").write_text(_HANDLER, encoding="utf-8")
    (tmp_path / "svc" / "handler_test.go").write_text(
        "package svc\n\nfunc TestHandle(t *T) {\n\tHandle(Active)\n}\n", encoding="utf-8"
    )
    model = ProjectAnalyzer(tmp_path).analyze(full=True).model
    test_flow = _flow(model, "TestHandle")
    assert test_flow.metadata["test"] is True
    assert not test_flow.is_entrypoint
