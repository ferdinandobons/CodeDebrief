from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from logicchart.model import (
    Evidence,
    Flow,
    FlowEdge,
    FlowNode,
    NodeKind,
    SourceLocation,
)
from logicchart.util import compact_text

FUNCTIONAL_TERMS = {
    "active",
    "admin",
    "allow",
    "auth",
    "authorized",
    "blocked",
    "cancel",
    "complete",
    "deleted",
    "deny",
    "disabled",
    "enabled",
    "error",
    "exists",
    "failed",
    "invalid",
    "missing",
    "mode",
    "none",
    "owner",
    "paid",
    "permission",
    "ready",
    "role",
    "state",
    "status",
    "suspended",
    "type",
    "valid",
}

BOUNDARY_CALL_TERMS = {
    "authorize",
    "commit",
    "create",
    "delete",
    "dispatch",
    "execute",
    "fetch",
    "insert",
    "publish",
    "redirect",
    "request",
    "save",
    "send",
    "update",
    "validate",
    "write",
}


@dataclass(slots=True)
class PendingEdge:
    node_id: str
    label: str = ""


class FlowBuilder:
    def __init__(self, flow: Flow) -> None:
        self.flow = flow
        self._node_number = 0
        self._edge_number = 0

    def add_node(
        self,
        kind: NodeKind,
        label: str,
        location: SourceLocation,
        incoming: list[PendingEdge],
        *,
        evidence: Evidence = Evidence.VERIFIED,
        detail: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> FlowNode:
        self._node_number += 1
        node = FlowNode(
            id=f"{self.flow.id}:n{self._node_number}",
            kind=kind,
            label=compact_text(label, 120),
            location=location,
            evidence=evidence,
            detail=compact_text(detail, 500),
            metadata=metadata or {},
        )
        self.flow.nodes.append(node)
        for endpoint in incoming:
            self.add_edge(endpoint.node_id, node.id, endpoint.label)
        return node

    def add_edge(
        self,
        source: str,
        target: str,
        label: str = "",
        evidence: Evidence = Evidence.VERIFIED,
    ) -> FlowEdge:
        self._edge_number += 1
        edge = FlowEdge(
            id=f"{self.flow.id}:e{self._edge_number}",
            source=source,
            target=target,
            label=label,
            evidence=evidence,
        )
        self.flow.edges.append(edge)
        return edge


def is_functional_condition(condition: str, branch_text: str = "") -> bool:
    lowered = f"{condition} {branch_text}".lower()
    tokens = set(re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", lowered))
    if tokens & FUNCTIONAL_TERMS:
        return True
    if any(term in lowered for term in ("return ", "raise ", "throw ", "redirect(")):
        return True
    return any(term in lowered for term in BOUNDARY_CALL_TERMS)


# Canonical per-branch terminal behavior, recorded on a decision node's
# `branches` metadata and validated by branch(). Detectors compare against these
# names, so they are single-sourced here to keep producers and consumers aligned.
RETURNS = "returns"
RAISES = "raises"
FALLS_THROUGH = "falls_through"
EMPTY = "empty"
CONTINUES = "continues"
BRANCH_OUTCOMES = frozenset({RETURNS, RAISES, FALLS_THROUGH, EMPTY, CONTINUES})

# Value-dispatch decision constructs, stored in a decision node's `operator`.
MATCH = "match"
SWITCH = "switch"
DISPATCH_OPERATORS = frozenset({MATCH, SWITCH})

DOMAIN_TERMS = ("status", "state", "role", "type", "kind", "mode", "permission")
_IDENTITY_OPERATORS = r"==|!=|\bis not\b|\bnot in\b|\bis\b|\bin\b"


def domain_from_subject(subject: str) -> str:
    """The functional domain a decision subject touches (status/role/...), or ""."""
    lowered = subject.lower()
    return next((term for term in DOMAIN_TERMS if term in lowered), "")


def branch(label: str, outcome: str, *, implicit: bool = False) -> dict[str, Any]:
    """One decision-branch record for a node's `branches` metadata."""
    assert outcome in BRANCH_OUTCOMES, f"unknown branch outcome: {outcome!r}"
    return {"label": label, "outcome": outcome, "implicit": implicit}


def decision_identity(
    *,
    condition: str,
    subject: str,
    operator: str,
    domain: str = "",
    values: list[str] | None = None,
    negation: bool = False,
    namespace: str | None = None,
) -> dict[str, Any]:
    """Assemble the canonical decision-node metadata key set.

    Single constructor so every decision node — if/elif, match, switch, try —
    carries the same shape (condition/domain/values plus the identity fields).
    """
    sorted_values = sorted(set(values or []))
    resolved_namespace = namespace if namespace is not None else value_namespace(sorted_values)
    return {
        "condition": condition,
        "domain": domain,
        "values": sorted_values,
        "subject": subject,
        "operator": operator,
        "negation": negation,
        "value_namespace": resolved_namespace,
    }


def decision_metadata(condition: str) -> dict[str, Any]:
    compact = compact_text(condition, 240)
    lowered = compact.lower()
    domain = next((term for term in DOMAIN_TERMS if re.search(rf"\b{term}\b", lowered)), "")

    values: list[str] = []
    for value in re.findall(
        r"(?:==|!=|\bin\b|\bis\b)\s*(?:\([^)]*\)|\[[^\]]*\]|[A-Za-z_][\w.]*|['\"][^'\"]+['\"])",
        compact,
    ):
        values.extend(
            token.strip(" '\"[]()")
            for token in re.split(r"[,|]", re.sub(r"^(==|!=|\bin\b|\bis\b)\s*", "", value))
            if token.strip(" '\"[]()")
        )
    subject, operator, negation = parse_subject_operator(compact)
    return decision_identity(
        condition=compact,
        subject=subject,
        operator=operator,
        domain=domain,
        values=values,
        negation=negation,
    )


def parse_subject_operator(condition: str) -> tuple[str, str, bool]:
    """Decompose a decision condition into (subject, operator, negation).

    Comparison conditions yield the normalized dotted left-hand side and one of
    ==/!=/is/is not/in/not in. Bare truthiness checks (``not user.active``,
    ``!ctx.ok``) yield an empty operator with the negation flag set.
    """
    text = condition.strip()
    match = re.match(
        rf"^\s*(?P<neg>not\s+|!)?\s*(?P<lhs>.+?)\s*(?P<op>{_IDENTITY_OPERATORS})\s*(?P<rhs>.+)$",
        text,
    )
    if match:
        operator = re.sub(r"\s+", " ", match.group("op").strip())
        return match.group("lhs").strip(), operator, bool(match.group("neg"))

    negation = bool(re.match(r"\s*(not\s+|!)", text))
    subject = re.sub(r"^\s*(not\s+|!)\s*", "", text)
    return subject.strip(), "", negation


def value_namespace(values: list[str]) -> str:
    """The shared dotted enum prefix of compared values (``Foo.BAR`` -> ``Foo``).

    Returns the single common namespace when every dotted value agrees, else "".
    """
    prefixes = {value.rsplit(".", 1)[0] for value in values if "." in value}
    return next(iter(prefixes)) if len(prefixes) == 1 else ""


def annotate_reachability(flow: Flow) -> None:
    """Record `reachable_from_entry` / `reaches_terminal` on every node.

    Deterministic graph reachability: a forward walk from entry nodes and a
    reverse walk from terminal/error nodes. Used by single-flow detectors (dead
    code, dead joins) and surfaced for navigation.
    """
    outgoing: dict[str, list[str]] = {node.id: [] for node in flow.nodes}
    incoming: dict[str, list[str]] = {node.id: [] for node in flow.nodes}
    for edge in flow.edges:
        if edge.source in outgoing and edge.target in incoming:
            outgoing[edge.source].append(edge.target)
            incoming[edge.target].append(edge.source)

    entries = [node.id for node in flow.nodes if node.kind is NodeKind.ENTRY]
    exits = [node.id for node in flow.nodes if node.kind in (NodeKind.TERMINAL, NodeKind.ERROR)]
    from_entry = _reach(entries, outgoing)
    to_terminal = _reach(exits, incoming)
    for node in flow.nodes:
        node.metadata["reachable_from_entry"] = node.id in from_entry
        node.metadata["reaches_terminal"] = node.id in to_terminal


def _reach(seeds: list[str], adjacency: dict[str, list[str]]) -> set[str]:
    seen: set[str] = set(seeds)
    stack = list(seeds)
    while stack:
        current = stack.pop()
        for neighbor in adjacency.get(current, ()):
            if neighbor not in seen:
                seen.add(neighbor)
                stack.append(neighbor)
    return seen


def call_is_boundary(name: str) -> bool:
    lowered = name.lower()
    return any(term in lowered for term in BOUNDARY_CALL_TERMS)
