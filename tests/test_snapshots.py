from __future__ import annotations

from pathlib import Path

from logicchart.analysis.project import ProjectAnalyzer
from logicchart.render.snapshot import (
    render_finding_snapshot,
    render_flow_snapshot,
    render_impact_snapshot,
    unsupported_snapshot_format,
)


def test_flow_snapshot_renders_decision_flow_svg(tmp_path: Path) -> None:
    source = tmp_path / "app.py"
    source.write_text(
        "def handle(user):\n"
        "    if user.role == '<admin>':\n"
        "        return allow()\n"
        "    return deny()\n",
        encoding="utf-8",
    )
    model = ProjectAnalyzer(tmp_path).analyze(full=True).model
    flow = next(item for item in model.flows if item.name == "handle")
    decision = next(node for node in flow.nodes if node.kind.value == "decision")

    snapshot = render_flow_snapshot(model, flow.id, highlight_node_ids={decision.id})

    assert snapshot["format"] == "svg"
    assert snapshot["flow_id"] == flow.id
    assert decision.id in snapshot["highlighted_node_ids"]
    svg = snapshot["svg"]
    assert svg.startswith("<svg ")
    assert "kind-decision highlight" in svg
    assert "&lt;admin&gt;" in svg
    assert "<admin>" not in svg


def test_finding_snapshot_highlights_finding_node(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text(
        "def dispatch(order):\n"
        "    if order.status == Status.OPEN:\n"
        "        return 'open'\n"
        "    elif order.status == Status.CLOSED:\n"
        "        return 'closed'\n",
        encoding="utf-8",
    )
    model = ProjectAnalyzer(tmp_path).analyze(full=True).model
    finding = model.findings[0]

    snapshot = render_finding_snapshot(model, finding.id)

    assert snapshot["finding_id"] == finding.id
    assert snapshot["flow_id"] == finding.flow_id
    assert snapshot["highlighted_node_ids"] == [finding.node_id]
    assert "highlight" in snapshot["svg"]


def test_impact_snapshot_renders_empty_state() -> None:
    snapshot = render_impact_snapshot(
        changed_files=["docs/readme.md"],
        direct=[],
        transitive=[],
        findings=[],
    )

    assert snapshot["format"] == "svg"
    assert snapshot["direct_flow_ids"] == []
    assert "No modeled flows are affected" in snapshot["svg"]


def test_unsupported_snapshot_format_reports_supported_formats() -> None:
    assert unsupported_snapshot_format("png") == {
        "error": "Unsupported snapshot format: png",
        "supported_formats": ["svg"],
    }
