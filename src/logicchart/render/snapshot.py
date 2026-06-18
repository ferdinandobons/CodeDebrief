from __future__ import annotations

from html import escape
from typing import Any

from logicchart.model import Finding, Flow, FlowNode, NodeKind, ProjectModel

SNAPSHOT_FORMATS = ("svg",)
MAX_FLOW_NODES = 44


def unsupported_snapshot_format(requested: str) -> dict[str, Any]:
    return {
        "error": f"Unsupported snapshot format: {requested}",
        "supported_formats": list(SNAPSHOT_FORMATS),
    }


def render_flow_snapshot(
    model: ProjectModel,
    flow_id: str,
    *,
    highlight_node_ids: set[str] | None = None,
    title: str | None = None,
    max_nodes: int | None = None,
) -> dict[str, Any]:
    flow = next((item for item in model.flows if item.id == flow_id), None)
    if flow is None:
        return {"error": f"Unknown flow: {flow_id}"}
    findings = [item for item in model.findings if item.flow_id == flow.id]
    highlighted = highlight_node_ids or set()
    rendered_nodes = _select_flow_nodes(flow, highlighted, max_nodes)
    svg = _flow_svg(flow, findings, highlighted, rendered_nodes=rendered_nodes, title=title)
    return {
        "format": "svg",
        "flow_id": flow.id,
        "title": title or flow.name,
        "svg": svg,
        "highlighted_node_ids": sorted(highlight_node_ids or []),
        "node_count": len(flow.nodes),
        "rendered_node_count": len(rendered_nodes),
        "omitted_node_count": max(0, len(flow.nodes) - len(rendered_nodes)),
    }


def render_finding_snapshot(
    model: ProjectModel, finding_id: str, *, max_nodes: int | None = None
) -> dict[str, Any]:
    finding = next((item for item in model.findings if item.id == finding_id), None)
    if finding is None:
        return {"error": f"Unknown finding: {finding_id}"}
    result = render_flow_snapshot(
        model,
        finding.flow_id,
        highlight_node_ids={finding.node_id} if finding.node_id else set(),
        title=f"{finding.kind}: {finding.message}",
        max_nodes=max_nodes,
    )
    result["finding_id"] = finding.id
    return result


def render_impact_snapshot(
    *,
    changed_files: list[str],
    direct: list[Flow],
    transitive: list[Flow],
    findings: list[Finding],
    max_flows: int | None = None,
) -> dict[str, Any]:
    rendered_direct = _select_impact_flows(direct, max_flows)
    rendered_transitive = _select_impact_flows(transitive, max_flows)
    svg = _impact_svg(
        changed_files,
        direct,
        transitive,
        findings,
        rendered_direct=rendered_direct,
        rendered_transitive=rendered_transitive,
    )
    return {
        "format": "svg",
        "changed_files": changed_files,
        "direct_flow_ids": [flow.id for flow in direct],
        "transitive_flow_ids": [flow.id for flow in transitive],
        "rendered_direct_flow_ids": [flow.id for flow in rendered_direct],
        "rendered_transitive_flow_ids": [flow.id for flow in rendered_transitive],
        "omitted_direct_flow_count": max(0, len(direct) - len(rendered_direct)),
        "omitted_transitive_flow_count": max(0, len(transitive) - len(rendered_transitive)),
        "finding_ids": [finding.id for finding in findings],
        "svg": svg,
    }


def _flow_svg(
    flow: Flow,
    findings: list[Finding],
    highlight_node_ids: set[str],
    *,
    rendered_nodes: list[FlowNode],
    title: str | None,
) -> str:
    nodes = rendered_nodes
    omitted = max(0, len(flow.nodes) - len(nodes))
    width = 920
    header_height = 108
    row_gap = 34
    node_width = 340
    node_height = 76
    x = 290
    positions = {
        node.id: (x, header_height + index * (node_height + row_gap))
        for index, node in enumerate(nodes)
    }
    height = header_height + max(1, len(nodes)) * (node_height + row_gap) + 86
    parts = [
        _svg_open(width, height, title or flow.name),
        _style(),
        f'<rect class="background" x="0" y="0" width="{width}" height="{height}" />',
        _text(28, 34, title or flow.name, "title"),
        _text(
            28,
            58,
            f"{flow.entry_kind} - {flow.language} - "
            f"{flow.location.path}:{flow.location.start_line}",
            "subtitle",
        ),
        _text(
            28,
            82,
            f"{len(flow.nodes)} nodes - {len(flow.edges)} edges - {len(findings)} findings",
            "meta",
        ),
    ]
    for edge in flow.edges:
        if edge.source not in positions or edge.target not in positions:
            continue
        parts.append(
            _edge(edge.source, edge.target, positions, node_width, node_height, edge.label)
        )
    for node in nodes:
        node_findings = [finding for finding in findings if finding.node_id == node.id]
        parts.append(
            _flow_node(
                node,
                positions[node.id],
                node_width,
                node_height,
                highlighted=node.id in highlight_node_ids,
                finding_count=len(node_findings),
            )
        )
    if omitted:
        parts.append(
            _text(
                28,
                height - 34,
                f"{omitted} additional nodes omitted from this compact snapshot.",
                "meta",
            )
        )
    parts.append("</svg>")
    return "\n".join(parts)


def _impact_svg(
    changed_files: list[str],
    direct: list[Flow],
    transitive: list[Flow],
    findings: list[Finding],
    *,
    rendered_direct: list[Flow],
    rendered_transitive: list[Flow],
) -> str:
    width = 920
    row_height = 84
    row_gap = 22
    rows = max(1, max(len(rendered_direct), len(rendered_transitive)))
    height = 156 + rows * (row_height + row_gap) + 80
    omitted_direct = max(0, len(direct) - len(rendered_direct))
    omitted_transitive = max(0, len(transitive) - len(rendered_transitive))
    parts = [
        _svg_open(width, height, "LogicChart impact snapshot"),
        _style(),
        f'<rect class="background" x="0" y="0" width="{width}" height="{height}" />',
        _text(28, 34, "Impact snapshot", "title"),
        _text(
            28,
            58,
            f"{len(changed_files)} changed files - {len(direct)} direct - "
            f"{len(transitive)} caller impact - {len(findings)} findings",
            "subtitle",
        ),
        _text(28, 84, _compact(", ".join(changed_files), 125), "meta"),
        _text(80, 126, "Direct impact", "column"),
        _text(530, 126, "Caller impact", "column"),
    ]
    for index, flow in enumerate(rendered_direct):
        parts.append(_impact_box(flow, 52, 150 + index * (row_height + row_gap), row_height))
    for index, flow in enumerate(rendered_transitive):
        parts.append(_impact_box(flow, 502, 150 + index * (row_height + row_gap), row_height))
    if not direct and not transitive:
        parts.append(_text(52, 184, "No modeled flows are affected by these files.", "meta"))
    if omitted_direct or omitted_transitive:
        parts.append(
            _text(
                52,
                height - 34,
                f"{omitted_direct} direct and {omitted_transitive} caller flows omitted.",
                "meta",
            )
        )
    parts.append("</svg>")
    return "\n".join(parts)


def _select_flow_nodes(
    flow: Flow,
    highlight_node_ids: set[str],
    max_nodes: int | None,
) -> list[FlowNode]:
    limit = _effective_limit(max_nodes, MAX_FLOW_NODES)
    selected = flow.nodes[:limit]
    selected_ids = {node.id for node in selected}
    for node in flow.nodes:
        if node.id not in highlight_node_ids or node.id in selected_ids:
            continue
        if len(selected) < limit:
            selected.append(node)
        elif selected:
            selected[-1] = node
        selected_ids = {item.id for item in selected}
    return [node for node in flow.nodes if node.id in selected_ids]


def _select_impact_flows(flows: list[Flow], max_flows: int | None) -> list[Flow]:
    if max_flows is None:
        return flows
    return flows[: _effective_limit(max_flows, len(flows))]


def _effective_limit(value: int | None, default: int) -> int:
    if value is None:
        return default
    return max(1, min(default, value))


def _flow_node(
    node: FlowNode,
    position: tuple[int, int],
    width: int,
    height: int,
    *,
    highlighted: bool,
    finding_count: int,
) -> str:
    x, y = position
    classes = ["node", f"kind-{node.kind.value}"]
    if highlighted:
        classes.append("highlight")
    if finding_count:
        classes.append("has-finding")
    shape = _node_shape(node.kind, x, y, width, height, " ".join(classes))
    label_lines = _wrap(node.label, 34, 2)
    meta = f"{node.location.path}:{node.location.start_line}"
    if finding_count:
        meta += f" - {finding_count} finding{'s' if finding_count != 1 else ''}"
    text_lines = [
        _text(x + width / 2, y + 28, line, "node-label", anchor="middle") for line in label_lines
    ]
    text_lines.append(_text(x + width / 2, y + height - 18, meta, "node-meta", anchor="middle"))
    return "\n".join([shape, *text_lines])


def _node_shape(kind: NodeKind, x: int, y: int, width: int, height: int, classes: str) -> str:
    if kind is NodeKind.DECISION:
        points = [
            (x + width / 2, y),
            (x + width, y + height / 2),
            (x + width / 2, y + height),
            (x, y + height / 2),
        ]
        return '<polygon class="{}" points="{}" />'.format(
            classes,
            " ".join(f"{px},{py}" for px, py in points),
        )
    if kind in {NodeKind.ENTRY, NodeKind.TERMINAL}:
        return (
            f'<rect class="{classes}" x="{x}" y="{y}" width="{width}" height="{height}" '
            f'rx="{height / 2}" />'
        )
    return f'<rect class="{classes}" x="{x}" y="{y}" width="{width}" height="{height}" rx="10" />'


def _edge(
    source_id: str,
    target_id: str,
    positions: dict[str, tuple[int, int]],
    node_width: int,
    node_height: int,
    label: str,
) -> str:
    sx, sy = positions[source_id]
    tx, ty = positions[target_id]
    x1 = sx + node_width / 2
    y1 = sy + node_height
    x2 = tx + node_width / 2
    y2 = ty
    mid_y = (y1 + y2) / 2
    path = f'<path class="edge" d="M {x1} {y1} C {x1} {mid_y}, {x2} {mid_y}, {x2} {y2}" />'
    if not label:
        return path
    return "\n".join(
        [
            path,
            _text((x1 + x2) / 2 + 10, mid_y - 4, _compact(label, 28), "edge-label"),
        ]
    )


def _impact_box(flow: Flow, x: int, y: int, height: int) -> str:
    width = 366
    lines = [
        f'<rect class="impact-node" x="{x}" y="{y}" width="{width}" height="{height}" rx="10" />',
        _text(x + 16, y + 28, _compact(flow.name, 42), "node-label"),
        _text(
            x + 16,
            y + 52,
            f"{flow.entry_kind} - {flow.language}",
            "node-meta",
        ),
        _text(x + 16, y + 72, _compact(flow.location.path, 52), "node-meta"),
    ]
    return "\n".join(lines)


def _style() -> str:
    return """
<style>
  .background { fill: #f8fafc; }
  .title { fill: #0f172a; font: 700 20px system-ui, sans-serif; }
  .subtitle { fill: #334155; font: 13px system-ui, sans-serif; }
  .meta { fill: #64748b; font: 11px ui-monospace, SFMono-Regular, Menlo, monospace; }
  .column { fill: #334155; font: 700 13px system-ui, sans-serif; }
  .node, .impact-node { fill: #ffffff; stroke: #94a3b8; stroke-width: 1.4; }
  .kind-decision { fill: #fff7ed; stroke: #f97316; }
  .kind-call { fill: #ecfeff; stroke: #0891b2; }
  .kind-error { fill: #fef2f2; stroke: #ef4444; }
  .has-finding { stroke-width: 2; }
  .highlight { stroke: #2563eb; stroke-width: 3; filter: drop-shadow(0 2px 5px #bfdbfe); }
  .edge { fill: none; stroke: #64748b; stroke-width: 1.2; marker-end: url(#arrow); }
  .edge-label { fill: #475569; font: 10px ui-monospace, SFMono-Regular, Menlo, monospace; }
  .node-label { fill: #0f172a; font: 700 12px system-ui, sans-serif; }
  .node-meta { fill: #64748b; font: 10px ui-monospace, SFMono-Regular, Menlo, monospace; }
</style>
<defs>
  <marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="3.5" orient="auto">
    <polygon points="0 0, 8 3.5, 0 7" fill="#64748b" />
  </marker>
</defs>
""".strip()


def _svg_open(width: int, height: int, label: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{escape(label)}">'
    )


def _text(
    x: float,
    y: float,
    value: str,
    class_name: str,
    *,
    anchor: str = "start",
) -> str:
    return (
        f'<text class="{class_name}" x="{x}" y="{y}" text-anchor="{anchor}">{escape(value)}</text>'
    )


def _wrap(value: str, width: int, max_lines: int) -> list[str]:
    words = value.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= width:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = word
        if len(lines) == max_lines:
            break
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) == max_lines and len(" ".join(words)) > len(" ".join(lines)):
        lines[-1] = _compact(lines[-1], max(4, width - 1))
    return lines


def _compact(value: str, width: int) -> str:
    collapsed = " ".join(value.split())
    return collapsed if len(collapsed) <= width else collapsed[: max(0, width - 3)] + "..."
