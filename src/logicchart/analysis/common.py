from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from logicchart.model import (
    Evidence,
    Finding,
    Flow,
    FlowEdge,
    FlowNode,
    NodeKind,
    Severity,
    SourceLocation,
)
from logicchart.util import compact_text, stable_id

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

    def add_missing_branch_finding(
        self,
        node: FlowNode,
        condition: str,
        findings: list[Finding],
    ) -> None:
        findings.append(
            Finding(
                id=stable_id(self.flow.id, node.id, "missing-branch"),
                kind="missing_branch",
                severity=Severity.WARNING,
                message=f"Decision has no explicit fallback: {compact_text(condition, 80)}",
                evidence=Evidence.POTENTIAL_GAP,
                flow_id=self.flow.id,
                node_id=node.id,
                location=node.location,
                detail=(
                    "LogicChart found a state-like decision without an explicit else/default "
                    "path. This may be intentional, but it should be reviewed when adding cases."
                ),
            )
        )


def is_functional_condition(condition: str, branch_text: str = "") -> bool:
    lowered = f"{condition} {branch_text}".lower()
    tokens = set(re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", lowered))
    if tokens & FUNCTIONAL_TERMS:
        return True
    if any(term in lowered for term in ("return ", "raise ", "throw ", "redirect(")):
        return True
    return any(term in lowered for term in BOUNDARY_CALL_TERMS)


def decision_metadata(condition: str) -> dict[str, Any]:
    compact = compact_text(condition, 240)
    lowered = compact.lower()
    domain = ""
    for candidate in ("status", "state", "role", "type", "kind", "mode", "permission"):
        if re.search(rf"\b{candidate}\b", lowered):
            domain = candidate
            break

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
    return {"condition": compact, "domain": domain, "values": sorted(set(values))}


def call_is_boundary(name: str) -> bool:
    lowered = name.lower()
    return any(term in lowered for term in BOUNDARY_CALL_TERMS)
