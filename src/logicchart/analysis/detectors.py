"""Single-flow detectors (Stage 2).

Each detector reasons about one built flow using the Stage 1 IR enrichment
(`branches` with per-branch `outcome`/`implicit`, decision identity, reachability)
and returns findings. Cross-flow detectors live in `project.py`; dead-code is
emitted by the analyzers' walkers (see `dead_code_finding`), which know exactly
where control terminates.
"""

from __future__ import annotations

from typing import Any

from logicchart.analysis.common import (
    DISPATCH_OPERATORS,
    EMPTY,
    FALLS_THROUGH,
    RAISES,
    RETURNS,
)
from logicchart.model import (
    Evidence,
    Finding,
    Flow,
    FlowNode,
    NodeKind,
    Severity,
    SourceLocation,
)
from logicchart.util import compact_text, stable_id

# A branch whose outcome is one of these exits the function early.
_EARLY_EXIT = frozenset({RETURNS, RAISES})
# Structural branch labels emitted by the walkers (see analysis.*._walk_*).
_SUCCESS = "Success"
_NO = "No"


def single_flow_findings(flow: Flow) -> list[Finding]:
    """All single-flow findings for one built flow (skips test flows)."""
    if flow.metadata.get("test"):
        return []
    findings: list[Finding] = []
    findings.extend(_missing_branch(flow))
    findings.extend(_broad_except_swallow(flow))
    findings.extend(_no_op_branch(flow))
    findings.extend(_asymmetric_return(flow))
    return findings


def dead_code_finding(flow: Flow, location: SourceLocation, detail: str) -> Finding:
    """Code that follows a point where every path has already returned/raised."""
    return Finding(
        id=stable_id(flow.id, "dead-code", str(location.start_line)),
        kind="dead_code",
        severity=Severity.WARNING,
        message=f"Unreachable code after all paths return or raise (line {location.start_line})",
        evidence=Evidence.INFERRED,
        flow_id=flow.id,
        location=location,
        detail=detail,
    )


# --- missing fallback (the flagship signal) --------------------------------


def _missing_branch(flow: Flow) -> list[Finding]:
    decisions = {node.id: node for node in flow.nodes if node.kind is NodeKind.DECISION}
    findings: list[Finding] = []
    # match/switch with no explicit default (preserves the established behavior).
    for node in decisions.values():
        if node.metadata.get("operator") in DISPATCH_OPERATORS and _has_implicit(node):
            condition = f"{node.metadata.get('operator', '')} {node.metadata.get('subject', '')}"
            findings.append(_missing_branch_finding(flow, node, condition.strip()))
    findings.extend(_missing_else_in_chain(flow, decisions))
    return findings


def _missing_else_in_chain(flow: Flow, decisions: dict[str, FlowNode]) -> list[Finding]:
    """An if/elif chain (>=2 comparisons of one state-like subject) with no else.

    Only true `elif` links are followed: a parent whose "No" branch is an explicit
    else-clause. Two sequential same-subject `if` guards each leave an *implicit*
    "No" that the walker happens to wire to the next decision — that is not an
    elif chain and must not be fused into one.
    """

    def links_via_else(node_id: str) -> bool:
        no_branch = _branch(decisions[node_id], _NO)
        return no_branch is not None and not no_branch["implicit"]

    no_target = {
        edge.source: edge.target
        for edge in flow.edges
        if edge.label == _NO
        and edge.source in decisions
        and edge.target in decisions
        and links_via_else(edge.source)
    }

    def same_subject(source: str, target: str) -> bool:
        subject = decisions[source].metadata.get("subject", "")
        return bool(subject) and subject == decisions[target].metadata.get("subject", "")

    no_children = {tgt for src, tgt in no_target.items() if same_subject(src, tgt)}
    findings: list[Finding] = []
    for node_id, head in decisions.items():
        if head.metadata.get("operator") in DISPATCH_OPERATORS or node_id in no_children:
            continue
        subject = str(head.metadata.get("subject", ""))
        if not subject or not _state_like(head):
            continue
        chain = [head]
        cursor = node_id
        while cursor in no_target and same_subject(cursor, no_target[cursor]):
            cursor = no_target[cursor]
            chain.append(decisions[cursor])
        if len(chain) < 2:
            continue
        tail_no = _branch(chain[-1], _NO)
        if tail_no is not None and tail_no["implicit"]:
            findings.append(_missing_branch_finding(flow, head, f"if/elif on {subject}"))
    return findings


def _missing_branch_finding(flow: Flow, node: FlowNode, condition: str) -> Finding:
    return _node_finding(
        flow,
        node,
        kind="missing_branch",
        severity=Severity.WARNING,
        evidence=Evidence.POTENTIAL_GAP,
        message=f"Decision has no explicit fallback: {compact_text(condition, 80)}",
        detail=(
            "LogicChart found a state-like decision without an explicit else/default "
            "path. This may be intentional, but it should be reviewed when adding cases."
        ),
        key=("missing-branch",),
    )


# --- error handling, no-op, asymmetry --------------------------------------


def _broad_except_swallow(flow: Flow) -> list[Finding]:
    """An exception handler with an empty body — the error is silently swallowed."""
    findings: list[Finding] = []
    for node in flow.nodes:
        if node.kind is not NodeKind.DECISION or node.metadata.get("domain") != "error":
            continue
        for entry in _explicit_branches(node):
            if entry["label"] != _SUCCESS and entry["outcome"] == EMPTY:
                findings.append(
                    _node_finding(
                        flow,
                        node,
                        kind="broad_except_swallow",
                        severity=Severity.WARNING,
                        evidence=Evidence.INFERRED,
                        message=f"Exception handler '{entry['label']}' swallows the error",
                        detail=(
                            "The handler body neither re-raises nor returns an error path, "
                            "so the failure is hidden from callers."
                        ),
                        key=("swallow", str(entry["label"])),
                    )
                )
    return findings


def _no_op_branch(flow: Flow) -> list[Finding]:
    """An explicit if-branch whose body does nothing.

    Dispatch (match/switch) cases are excluded: an empty case is usually an
    intentional fall-through to the next case, not a no-op.
    """
    findings: list[Finding] = []
    for node in flow.nodes:
        if node.kind is not NodeKind.DECISION or node.metadata.get("domain") == "error":
            continue
        if node.metadata.get("operator") in DISPATCH_OPERATORS:
            continue
        for entry in _explicit_branches(node):
            if entry["outcome"] == EMPTY:
                findings.append(
                    _node_finding(
                        flow,
                        node,
                        kind="no_op_branch",
                        severity=Severity.INFO,
                        evidence=Evidence.INFERRED,
                        message=f"Branch '{entry['label']}' has an empty body",
                        detail="The branch is taken but performs no work — likely unfinished.",
                        key=("no-op", str(entry["label"])),
                    )
                )
    return findings


def _asymmetric_return(flow: Flow) -> list[Finding]:
    """A value-dispatch where most cases return/raise but at least one falls through."""
    findings: list[Finding] = []
    for node in flow.nodes:
        if node.kind is not NodeKind.DECISION:
            continue
        if node.metadata.get("operator") not in DISPATCH_OPERATORS:
            continue
        explicit = _explicit_branches(node)
        if len(explicit) < 3:
            continue
        exiting = [b for b in explicit if b["outcome"] in _EARLY_EXIT]
        # Only count cases that do work but never exit — the "forgot to return"
        # shape. An empty case is usually an intentional fall-through.
        fallthrough = [b for b in explicit if b["outcome"] == FALLS_THROUGH]
        if fallthrough and len(exiting) > len(fallthrough):
            labels = compact_text(", ".join(str(b["label"]) for b in fallthrough), 80)
            findings.append(
                _node_finding(
                    flow,
                    node,
                    kind="asymmetric_return",
                    severity=Severity.WARNING,
                    evidence=Evidence.INFERRED,
                    message=f"Most cases return, but these fall through: {labels}",
                    detail=(
                        "In a dispatch where the majority of cases return or raise, a case "
                        "that falls through is often a missing return."
                    ),
                    key=("asymmetric-return",),
                )
            )
    return findings


# --- helpers ----------------------------------------------------------------


def _node_finding(
    flow: Flow,
    node: FlowNode,
    *,
    kind: str,
    severity: Severity,
    evidence: Evidence,
    message: str,
    detail: str,
    key: tuple[str, ...],
) -> Finding:
    """Build a finding anchored to one decision node, keyed by stable structural parts."""
    return Finding(
        id=stable_id(flow.id, node.id, *key),
        kind=kind,
        severity=severity,
        message=message,
        evidence=evidence,
        flow_id=flow.id,
        node_id=node.id,
        location=node.location,
        detail=detail,
    )


def _branches(node: FlowNode) -> list[dict[str, Any]]:
    branches = node.metadata.get("branches", [])
    return branches if isinstance(branches, list) else []


def _explicit_branches(node: FlowNode) -> list[dict[str, Any]]:
    return [entry for entry in _branches(node) if not entry.get("implicit")]


def _branch(node: FlowNode, label: str) -> dict[str, Any] | None:
    return next((entry for entry in _branches(node) if entry.get("label") == label), None)


def _has_implicit(node: FlowNode) -> bool:
    return any(entry.get("implicit") for entry in _branches(node))


def _state_like(node: FlowNode) -> bool:
    return bool(node.metadata.get("domain") or node.metadata.get("value_namespace"))
