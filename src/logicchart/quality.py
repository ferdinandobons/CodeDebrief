from __future__ import annotations

from collections import Counter
from typing import Any

from logicchart.model import Flow, FlowNode, NodeKind, ProjectModel

GENERIC_LABELS = {
    "call",
    "return",
    "raise",
    "action",
    "branch",
    "condition",
    "unknown",
}
LOW_CONFIDENCE = {"low", "none"}
HUGE_FLOW_NODE_THRESHOLD = 60
DENSE_EDGE_RATIO_THRESHOLD = 2.6


def model_quality(model: ProjectModel) -> dict[str, Any]:
    """Deterministic analyzer-quality metrics derived from one persisted model."""
    non_test_flows = [flow for flow in model.flows if not flow.metadata.get("test")]
    call_nodes = [node for flow in model.flows for node in flow.nodes if node.kind is NodeKind.CALL]
    resolved = [node for node in call_nodes if node.metadata.get("target_flow")]
    ambiguous = [node for node in call_nodes if len(node.metadata.get("call_candidates", [])) > 1]
    unresolved = [
        node
        for node in call_nodes
        if not node.metadata.get("target_flow") and not node.metadata.get("call_candidates")
    ]
    low_confidence = [
        node
        for node in call_nodes
        if str(node.metadata.get("link_confidence", "")).lower() in LOW_CONFIDENCE
    ]
    node_count = sum(len(flow.nodes) for flow in model.flows)
    edge_count = sum(len(flow.edges) for flow in model.flows)
    generic_labels = _generic_label_nodes(model.flows)
    source_locations = _source_location_nodes(model.flows)
    skipped_files = _skipped_files(model)
    parse_error_files = _parse_error_files(model.flows)
    huge_flows = [
        {
            "flow_id": flow.id,
            "name": flow.name,
            "nodes": len(flow.nodes),
            "source": f"{flow.location.path}:{flow.location.start_line}",
        }
        for flow in non_test_flows
        if len(flow.nodes) >= HUGE_FLOW_NODE_THRESHOLD
    ]
    edge_ratio = round(edge_count / node_count, 2) if node_count else 0.0
    return {
        "files": {
            "total": len(model.files),
            "by_language": dict(Counter(record.language for record in model.files)),
            "empty": sum(1 for record in model.files if not record.flow_ids),
            "skipped": {
                "total": len(skipped_files),
                "by_reason": dict(Counter(item["reason"] for item in skipped_files)),
                "sample": skipped_files[:20],
            },
            "parse_errors": {
                "total": len(parse_error_files),
                "by_language": dict(Counter(item["language"] for item in parse_error_files)),
                "sample": parse_error_files[:20],
            },
        },
        "flows": {
            "total": len(model.flows),
            "non_test": len(non_test_flows),
            "entrypoints": sum(flow.is_entrypoint for flow in non_test_flows),
            "by_language": dict(Counter(flow.language for flow in non_test_flows)),
            "by_entry_kind": dict(Counter(flow.entry_kind for flow in non_test_flows)),
            "per_file": _flow_distribution(model.flows),
            "huge": huge_flows[:20],
        },
        "calls": {
            "total": len(call_nodes),
            "resolved": len(resolved),
            "unresolved": len(unresolved),
            "ambiguous": len(ambiguous),
            "low_confidence": len(low_confidence),
            "resolution_rate": _ratio(len(resolved), len(call_nodes)),
        },
        "languages": _language_depth(
            model,
            non_test_flows=non_test_flows,
            resolved_calls=resolved,
            unresolved_calls=unresolved,
            generic_labels=generic_labels,
            skipped_files=skipped_files,
            parse_error_files=parse_error_files,
        ),
        "labels": {
            "generic_nodes": len(generic_labels),
            "generic_ratio": _ratio(len(generic_labels), node_count),
            "sample": generic_labels[:20],
        },
        "source_locations": {
            "nodes_with_source": len(source_locations),
            "coverage": _ratio(len(source_locations), node_count),
        },
        "graph": {
            "nodes": node_count,
            "edges": edge_count,
            "edge_to_node_ratio": edge_ratio,
            "dense_graph_warning": edge_ratio >= DENSE_EDGE_RATIO_THRESHOLD,
        },
    }


def render_quality(quality: dict[str, Any]) -> str:
    files = quality["files"]
    flows = quality["flows"]
    calls = quality["calls"]
    labels = quality["labels"]
    source = quality["source_locations"]
    graph = quality["graph"]
    languages = quality.get("languages", {})
    language_depth = languages.get("depth", {}) if isinstance(languages, dict) else {}
    attention = languages.get("attention", []) if isinstance(languages, dict) else []
    lines = [
        "Analysis quality:",
        f"- Files: {files['total']} ({_format_counts(files['by_language'])})",
        f"- Skipped files: {files['skipped']['total']}",
        f"- Parse warnings: {files.get('parse_errors', {}).get('total', 0)}",
        f"- Flows: {flows['total']} total, {flows['entrypoints']} entrypoints "
        f"({_format_counts(flows['by_language'])})",
        f"- Calls: {calls['resolved']}/{calls['total']} resolved "
        f"({calls['resolution_rate']:.0%}); {calls['unresolved']} unresolved, "
        f"{calls['ambiguous']} ambiguous, {calls['low_confidence']} low-confidence",
        f"- Labels: {labels['generic_nodes']} generic nodes ({labels['generic_ratio']:.0%})",
        f"- Source coverage: {source['nodes_with_source']} nodes ({source['coverage']:.0%})",
        f"- Graph density: {graph['edges']} edges / {graph['nodes']} nodes "
        f"({graph['edge_to_node_ratio']})",
    ]
    if language_depth:
        lines.append(f"- Language depth: {len(language_depth)} observed language(s)")
        lines.extend(
            _format_language_depth(language, metrics)
            for language, metrics in sorted(language_depth.items())[:5]
        )
    if attention:
        lines.append("- Language attention signals:")
        lines.extend(
            f"  - {item['language']}: {', '.join(item['signals'])}" for item in attention[:5]
        )
    if flows["huge"]:
        lines.append("- Huge flows:")
        lines.extend(
            f"  - {item['name']} ({item['nodes']} nodes, {item['source']})"
            for item in flows["huge"][:5]
        )
    if files["skipped"]["sample"]:
        lines.append("- Skipped file samples:")
        lines.extend(
            f"  - {item['path']} ({item['reason']})" for item in files["skipped"]["sample"][:5]
        )
    parse_errors = files.get("parse_errors", {})
    if isinstance(parse_errors, dict) and parse_errors.get("sample"):
        lines.append("- Parse warning samples:")
        lines.extend(
            f"  - {item['path']}:{item['line']} ({item['reason']})"
            for item in parse_errors["sample"][:5]
        )
    if labels["sample"]:
        lines.append("- Generic label samples:")
        lines.extend(f"  - {item['label']} ({item['source']})" for item in labels["sample"][:5])
    if graph["dense_graph_warning"]:
        lines.append("- Warning: graph edge density is high; inspect layout and call resolution.")
    return "\n".join(lines)


def _flow_distribution(flows: list[Flow]) -> dict[str, Any]:
    counts = Counter(flow.location.path for flow in flows)
    values = sorted(counts.values())
    if not values:
        return {"min": 0, "max": 0, "avg": 0.0}
    return {
        "min": values[0],
        "max": values[-1],
        "avg": round(sum(values) / len(values), 2),
    }


def _language_depth(
    model: ProjectModel,
    *,
    non_test_flows: list[Flow],
    resolved_calls: list[FlowNode],
    unresolved_calls: list[FlowNode],
    generic_labels: list[dict[str, Any]],
    skipped_files: list[dict[str, str]],
    parse_error_files: list[dict[str, Any]],
) -> dict[str, Any]:
    file_counts = Counter(record.language for record in model.files)
    files_with_flows = Counter(
        record.language for record in model.files if getattr(record, "flow_ids", [])
    )
    flow_counts = Counter(flow.language for flow in non_test_flows)
    entrypoint_counts = Counter(flow.language for flow in non_test_flows if flow.is_entrypoint)
    decision_counts = Counter(
        flow.language
        for flow in non_test_flows
        for node in flow.nodes
        if node.kind is NodeKind.DECISION
    )
    resolved_ids = {id(node) for node in resolved_calls}
    unresolved_ids = {id(node) for node in unresolved_calls}
    call_counts: Counter[str] = Counter()
    resolved_counts: Counter[str] = Counter()
    unresolved_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    for flow in non_test_flows:
        for node in flow.nodes:
            if node.kind is NodeKind.CALL:
                call_counts[flow.language] += 1
                if id(node) in resolved_ids:
                    resolved_counts[flow.language] += 1
                if id(node) in unresolved_ids:
                    unresolved_counts[flow.language] += 1
            if node.location.path and node.location.start_line > 0 and node.location.end_line > 0:
                source_counts[flow.language] += 1
    generic_counts = Counter(_sample_language(item) for item in generic_labels)
    node_counts = Counter(flow.language for flow in non_test_flows for _node in flow.nodes)
    skipped_counts = Counter(item.get("language", "") for item in skipped_files)
    parse_error_counts = Counter(item.get("language", "") for item in parse_error_files)
    capabilities = model.metadata.get("language_capabilities", {})
    languages = sorted(
        {
            *file_counts.keys(),
            *flow_counts.keys(),
            *skipped_counts.keys(),
            *parse_error_counts.keys(),
        }
        - {""}
    )
    depth: dict[str, dict[str, Any]] = {}
    attention: list[dict[str, Any]] = []
    for language in languages:
        files = file_counts[language]
        flows = flow_counts[language]
        calls = call_counts[language]
        resolved = resolved_counts[language]
        skipped = skipped_counts[language]
        parse_errors = parse_error_counts[language]
        nodes = node_counts[language]
        metrics = {
            "files": files,
            "files_with_flows": files_with_flows[language],
            "flow_file_coverage": _ratio(files_with_flows[language], files),
            "flows": flows,
            "entrypoints": entrypoint_counts[language],
            "decisions": decision_counts[language],
            "calls": calls,
            "resolved_calls": resolved,
            "unresolved_calls": unresolved_counts[language],
            "call_resolution_rate": _ratio(resolved, calls),
            "generic_nodes": generic_counts[language],
            "generic_ratio": _ratio(generic_counts[language], nodes),
            "source_coverage": _ratio(source_counts[language], nodes),
            "skipped_files": skipped,
            "parse_error_files": parse_errors,
            "capability": capabilities.get(language, {}),
        }
        signals = _language_attention_signals(metrics)
        if signals:
            attention.append({"language": language, "signals": signals})
        depth[language] = metrics
    return {"depth": depth, "attention": attention}


def _language_attention_signals(metrics: dict[str, Any]) -> list[str]:
    signals = []
    if metrics["skipped_files"]:
        signals.append("skipped_files")
    if metrics.get("parse_error_files"):
        signals.append("parse_errors")
    if metrics["files"] and not metrics["files_with_flows"]:
        signals.append("no_flow_files")
    if metrics["calls"] and metrics["call_resolution_rate"] < 0.5:
        signals.append("low_call_resolution")
    if metrics["generic_ratio"] >= 0.2:
        signals.append("generic_labels")
    if metrics["flows"] and metrics["source_coverage"] < 0.9:
        signals.append("low_source_coverage")
    return signals


def _sample_language(item: dict[str, Any]) -> str:
    return str(item.get("language", ""))


def _format_language_depth(language: str, metrics: dict[str, Any]) -> str:
    return (
        f"  - {language}: {metrics['files']} files, {metrics['flows']} flows, "
        f"{metrics['decisions']} decisions, {metrics['resolved_calls']}/{metrics['calls']} "
        "calls resolved"
    )


def _generic_label_nodes(flows: list[Flow]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for flow in flows:
        for node in flow.nodes:
            if not _generic_label(node):
                continue
            rows.append(
                {
                    "flow_id": flow.id,
                    "node_id": node.id,
                    "label": node.label,
                    "language": flow.language,
                    "source": f"{node.location.path}:{node.location.start_line}",
                }
            )
    return rows


def _generic_label(node: FlowNode) -> bool:
    label = " ".join(node.label.lower().split())
    if label in GENERIC_LABELS:
        return True
    if node.kind is NodeKind.CALL and label.startswith("call "):
        return len(label.split()) <= 2
    return node.kind is NodeKind.ACTION and label in {"do work", "handle", "process"}


def _source_location_nodes(flows: list[Flow]) -> list[FlowNode]:
    return [
        node
        for flow in flows
        for node in flow.nodes
        if node.location.path and node.location.start_line > 0 and node.location.end_line > 0
    ]


def _parse_error_files(flows: list[Flow]) -> list[dict[str, Any]]:
    by_path: dict[str, dict[str, Any]] = {}
    for flow in flows:
        parse_error = flow.metadata.get("parse_error")
        if not isinstance(parse_error, dict):
            continue
        path = str(parse_error.get("path") or flow.location.path)
        if not path:
            continue
        by_path.setdefault(
            path,
            {
                "path": path,
                "language": str(parse_error.get("language") or flow.language),
                "line": int(parse_error.get("line") or flow.location.start_line),
                "kind": str(parse_error.get("kind") or "ERROR"),
                "reason": str(parse_error.get("reason") or "tree-sitter parse warning"),
            },
        )
    return [by_path[path] for path in sorted(by_path)]


def _skipped_files(model: ProjectModel) -> list[dict[str, str]]:
    rows = model.metadata.get("skipped_files", [])
    if not isinstance(rows, list):
        return []
    normalized = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        reason = item.get("reason")
        language = item.get("language")
        if isinstance(path, str) and isinstance(reason, str):
            normalized.append(
                {
                    "path": path,
                    "language": language if isinstance(language, str) else "",
                    "reason": reason,
                }
            )
    return normalized


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _format_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "none"
    return ", ".join(f"{key}={value}" for key, value in sorted(counts.items()))
