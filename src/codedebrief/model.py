from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class Evidence(str, Enum):
    VERIFIED = "VERIFIED"
    INFERRED = "INFERRED"


LEGACY_REVIEW_GAP_EVIDENCE = "POTENTIAL" + "_GAP"


class NodeKind(str, Enum):
    ENTRY = "entry"
    ACTION = "action"
    DECISION = "decision"
    CALL = "call"
    TERMINAL = "terminal"
    ERROR = "error"


_NODE_KIND_BY_VALUE = {item.value: item for item in NodeKind}
_EVIDENCE_BY_VALUE = {item.value: item for item in Evidence}


@dataclass(slots=True)
class SourceLocation:
    path: str
    start_line: int
    end_line: int


@dataclass(slots=True)
class FlowNode:
    id: str
    kind: NodeKind
    label: str
    location: SourceLocation
    evidence: Evidence = Evidence.VERIFIED
    detail: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FlowEdge:
    id: str
    source: str
    target: str
    label: str = ""
    evidence: Evidence = Evidence.VERIFIED


@dataclass(slots=True)
class Flow:
    id: str
    name: str
    symbol: str
    language: str
    framework: str
    entry_kind: str
    is_entrypoint: bool
    location: SourceLocation
    nodes: list[FlowNode] = field(default_factory=list)
    edges: list[FlowEdge] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    called_by: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FileRecord:
    path: str
    language: str
    sha256: str
    flow_ids: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)


@dataclass(slots=True)
class FileAnalysis:
    path: str
    language: str
    sha256: str
    flows: list[Flow] = field(default_factory=list)
    enums: dict[str, list[str]] = field(default_factory=dict)
    constants: dict[str, bool] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "language": self.language,
            "sha256": self.sha256,
            "flows": [_flow_to_dict(flow) for flow in self.flows],
            "enums": self.enums,
            "constants": self.constants,
            "dependencies": self.dependencies,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FileAnalysis:
        return cls(
            path=data["path"],
            language=data["language"],
            sha256=data["sha256"],
            flows=[_flow_from_dict(item) for item in data.get("flows", [])],
            enums=data.get("enums", {}),
            constants=data.get("constants", {}),
            dependencies=data.get("dependencies", []),
        )


@dataclass(slots=True)
class ProjectModel:
    schema_version: str
    generated_at: str
    root: str
    flows: list[Flow] = field(default_factory=list)
    files: list[FileRecord] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def empty(cls, root: Path) -> ProjectModel:
        return cls(
            schema_version="2.0",
            generated_at=datetime.now(timezone.utc).isoformat(),
            root=str(root.resolve()),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "root": self.root,
            "flows": [_flow_to_dict(flow) for flow in self.flows],
            "files": [_file_record_to_dict(file_record) for file_record in self.files],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProjectModel:
        # Loading a committed `codedebrief.json` deserializes untrusted JSON, so a malformed
        # shape must surface as a clean ValueError, not a raw KeyError / TypeError traceback
        # leaking to the CLI or the MCP transport.
        if not isinstance(data, dict):
            raise ValueError("malformed codedebrief.json: expected a JSON object at the top level")
        try:
            flows = [_flow_from_dict(item) for item in data.get("flows", [])]
            files = [_file_record_from_dict(item) for item in data.get("files", [])]
            return cls(
                schema_version=data["schema_version"],
                generated_at=data["generated_at"],
                root=data["root"],
                flows=flows,
                files=files,
                metadata=data.get("metadata", {}),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"malformed codedebrief.json: {error}") from error


def _location_from_dict(data: dict[str, Any]) -> SourceLocation:
    return SourceLocation(
        path=data["path"],
        start_line=data["start_line"],
        end_line=data["end_line"],
    )


def _node_from_dict(data: dict[str, Any]) -> FlowNode:
    return FlowNode(
        id=data["id"],
        kind=_node_kind_from_value(data["kind"]),
        label=data["label"],
        location=_location_from_dict(data["location"]),
        evidence=_evidence_from_value(data.get("evidence", Evidence.VERIFIED.value)),
        detail=data.get("detail", ""),
        metadata=data.get("metadata", {}),
    )


def _edge_from_dict(data: dict[str, Any]) -> FlowEdge:
    return FlowEdge(
        id=data["id"],
        source=data["source"],
        target=data["target"],
        label=data.get("label", ""),
        evidence=_evidence_from_value(data.get("evidence", Evidence.VERIFIED.value)),
    )


def _flow_from_dict(data: dict[str, Any]) -> Flow:
    return Flow(
        id=data["id"],
        name=data["name"],
        symbol=data["symbol"],
        language=data["language"],
        framework=data.get("framework", "generic"),
        entry_kind=data.get("entry_kind", "function"),
        is_entrypoint=data.get("is_entrypoint", False),
        location=_location_from_dict(data["location"]),
        nodes=[_node_from_dict(item) for item in data.get("nodes", [])],
        edges=[_edge_from_dict(item) for item in data.get("edges", [])],
        calls=data.get("calls", []),
        called_by=data.get("called_by", []),
        tests=data.get("tests", []),
        metadata=data.get("metadata", {}),
    )


def _evidence_from_value(value: Any) -> Evidence:
    # Backward compatibility for old LogicChart/early CodeDebrief artifacts. CodeDebrief is
    # now a comprehension tool, so old review-gap evidence is treated as an inferred fact.
    if isinstance(value, Evidence):
        return value
    if value == LEGACY_REVIEW_GAP_EVIDENCE:
        return Evidence.INFERRED
    if isinstance(value, str):
        known = _EVIDENCE_BY_VALUE.get(value)
        if known is not None:
            return known
    return Evidence(value)


def _node_kind_from_value(value: Any) -> NodeKind:
    if isinstance(value, NodeKind):
        return value
    if isinstance(value, str):
        known = _NODE_KIND_BY_VALUE.get(value)
        if known is not None:
            return known
    return NodeKind(value)


def _location_to_dict(location: SourceLocation) -> dict[str, Any]:
    return {
        "path": location.path,
        "start_line": location.start_line,
        "end_line": location.end_line,
    }


def _node_to_dict(node: FlowNode) -> dict[str, Any]:
    return {
        "id": node.id,
        "kind": node.kind.value,
        "label": node.label,
        "location": _location_to_dict(node.location),
        "evidence": node.evidence.value,
        "detail": node.detail,
        "metadata": node.metadata,
    }


def _edge_to_dict(edge: FlowEdge) -> dict[str, Any]:
    return {
        "id": edge.id,
        "source": edge.source,
        "target": edge.target,
        "label": edge.label,
        "evidence": edge.evidence.value,
    }


def _flow_to_dict(flow: Flow) -> dict[str, Any]:
    return {
        "id": flow.id,
        "name": flow.name,
        "symbol": flow.symbol,
        "language": flow.language,
        "framework": flow.framework,
        "entry_kind": flow.entry_kind,
        "is_entrypoint": flow.is_entrypoint,
        "location": _location_to_dict(flow.location),
        "nodes": [_node_to_dict(node) for node in flow.nodes],
        "edges": [_edge_to_dict(edge) for edge in flow.edges],
        "calls": flow.calls,
        "called_by": flow.called_by,
        "tests": flow.tests,
        "metadata": flow.metadata,
    }


def _file_record_to_dict(file_record: FileRecord) -> dict[str, Any]:
    return {
        "path": file_record.path,
        "language": file_record.language,
        "sha256": file_record.sha256,
        "flow_ids": file_record.flow_ids,
        "dependencies": file_record.dependencies,
    }


def _file_record_from_dict(data: dict[str, Any]) -> FileRecord:
    allowed = {"path", "language", "sha256", "flow_ids", "dependencies"}
    unexpected = set(data) - allowed
    if unexpected:
        raise TypeError(f"FileRecord.__init__() got unexpected keys: {sorted(unexpected)}")
    return FileRecord(
        path=data["path"],
        language=data["language"],
        sha256=data["sha256"],
        flow_ids=data.get("flow_ids", []),
        dependencies=data.get("dependencies", []),
    )
