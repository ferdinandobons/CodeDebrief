from __future__ import annotations

from codedebrief.model import Flow, FlowNode, NodeKind, ProjectModel, SourceLocation
from codedebrief.render.snapshot import (
    render_subgraph_snapshot,
    unsupported_snapshot_format,
)


def test_subgraph_snapshot_layout_quality_reports_compaction() -> None:
    flows = [
        Flow(
            id=f"flow-{index}",
            name=f"flow {index}",
            symbol=f"flow_{index}",
            language="python",
            framework="generic",
            entry_kind="function",
            is_entrypoint=True,
            location=SourceLocation(path=f"app{index}.py", start_line=1, end_line=1),
            nodes=[
                FlowNode(
                    id=f"flow-{index}-node-{node_index}",
                    kind=NodeKind.ACTION,
                    label=f"node {node_index}",
                    location=SourceLocation(
                        path=f"app{index}.py",
                        start_line=node_index + 1,
                        end_line=node_index + 1,
                    ),
                )
                for node_index in range(3)
            ],
        )
        for index in range(3)
    ]
    model = ProjectModel(
        schema_version="2.0",
        generated_at="2026-06-18T00:00:00+00:00",
        root=".",
        flows=flows,
    )

    snapshot = render_subgraph_snapshot(
        model,
        flow_ids=[flow.id for flow in flows],
        max_flows=2,
        max_nodes=2,
    )

    assert snapshot["layout"]["compact"] is True
    assert snapshot["layout"]["direction"] == "top_to_bottom_stacked_flows"
    assert snapshot["layout"]["orientation"] == "vertical"
    assert snapshot["layout"]["canvas"]["width"] == 720
    assert snapshot["layout_quality"]["status"] == "compact"
    assert snapshot["layout_quality"]["counts"]["flow_count"] == 3
    assert snapshot["layout_quality"]["counts"]["rendered_flow_count"] == 2
    assert snapshot["layout_quality"]["counts"]["omitted_flow_count"] == 1
    assert snapshot["layout_quality"]["counts"]["omitted_node_count"] == 2
    assert snapshot["layout_quality"]["clarity"]["counts"]["box_overlap_count"] == 0


def test_subgraph_snapshot_reports_unresolved_targets() -> None:
    model = ProjectModel(
        schema_version="2.0",
        generated_at="2026-06-18T00:00:00+00:00",
        root=".",
    )

    snapshot = render_subgraph_snapshot(model, flow_ids=["missing-flow"])

    assert snapshot["requested_flow_ids"] == ["missing-flow"]
    assert snapshot["flow_ids"] == []
    assert snapshot["unresolved_targets"] == [
        {"type": "flow", "value": "missing-flow", "reason": "not_found"}
    ]
    assert snapshot["layout_quality"]["counts"]["unresolved_target_count"] == 1
    assert "Unresolved targets: flow:missing-flow" in snapshot["svg"]
    assert "No valid flows matched the requested subgraph." in snapshot["svg"]


def test_subgraph_snapshot_compacts_long_node_text() -> None:
    long_token = "VeryLongUnbrokenIdentifierThatWouldOverflowTheSnapshotNodeWithoutCompaction"
    long_path = "backend/api/modules/very/deep/path/with/a/long/source/file/name/service.py"
    flow = Flow(
        id="flow-long",
        name="long",
        symbol="long",
        language="python",
        framework="generic",
        entry_kind="function",
        is_entrypoint=True,
        location=SourceLocation(path=long_path, start_line=1, end_line=1),
        nodes=[
            FlowNode(
                id="node-long",
                kind=NodeKind.ACTION,
                label=long_token,
                location=SourceLocation(path=long_path, start_line=42, end_line=42),
            )
        ],
    )
    model = ProjectModel(
        schema_version="2.0",
        generated_at="2026-06-18T00:00:00+00:00",
        root=".",
        flows=[flow],
    )

    snapshot = render_subgraph_snapshot(model, flow_ids=[flow.id])

    assert long_token not in snapshot["svg"]
    assert long_path not in snapshot["svg"]
    assert "..." in snapshot["svg"]


def test_subgraph_snapshot_requires_flow_ids() -> None:
    model = ProjectModel(
        schema_version="2.0",
        generated_at="2026-06-18T00:00:00+00:00",
        root=".",
    )

    payload = render_subgraph_snapshot(model, flow_ids=[])

    assert payload["error"] == "Subgraph snapshot requires at least one flow_id."
    assert payload["error_code"] == "snapshot_subgraph_empty"
    assert payload["recoverable"] is True


def test_unsupported_snapshot_format_reports_supported_formats() -> None:
    payload = unsupported_snapshot_format("png")

    assert payload["error"] == "Unsupported snapshot format: png"
    assert payload["error_code"] == "unsupported_snapshot_format"
    assert payload["requested_format"] == "png"
    assert payload["supported_formats"] == ["svg"]
    assert payload["recoverable"] is True
