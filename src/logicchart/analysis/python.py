from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path

from logicchart.analysis.common import (
    FlowBuilder,
    PendingEdge,
    call_is_boundary,
    decision_metadata,
    is_functional_condition,
)
from logicchart.config import LogicChartConfig
from logicchart.model import (
    Evidence,
    FileAnalysis,
    Finding,
    Flow,
    NodeKind,
    SourceLocation,
)
from logicchart.util import compact_text, file_sha256, relpath, stable_id

FASTAPI_METHODS = {"get", "post", "put", "patch", "delete", "options", "head", "websocket"}
CLI_DECORATORS = {"command", "callback"}
HANDLER_PREFIXES = ("handle_", "on_", "process_")


class PythonAnalyzer:
    def __init__(self, root: Path, config: LogicChartConfig) -> None:
        self.root = root
        self.config = config

    def analyze(self, path: Path) -> FileAnalysis:
        source = path.read_text(encoding="utf-8")
        relative = relpath(path, self.root)
        tree = ast.parse(source, filename=relative)
        module_name = _module_name(relative)
        flows: list[Flow] = []
        findings: list[Finding] = []

        for definition, owner in _definitions(tree):
            flow = self._analyze_definition(
                definition=definition,
                owner=owner,
                source=source,
                relative=relative,
                module_name=module_name,
                findings=findings,
            )
            flows.append(flow)

        return FileAnalysis(
            path=relative,
            language="python",
            sha256=file_sha256(path),
            flows=flows,
            findings=findings,
        )

    def _analyze_definition(
        self,
        definition: ast.FunctionDef | ast.AsyncFunctionDef,
        owner: str,
        source: str,
        relative: str,
        module_name: str,
        findings: list[Finding],
    ) -> Flow:
        qualified_name = f"{owner}.{definition.name}" if owner else definition.name
        symbol = f"{module_name}:{qualified_name}"
        framework, entry_kind, is_entrypoint = _classify_entrypoint(
            definition, relative, owner, self.config
        )
        is_test = _is_test(relative, definition.name)
        if is_test:
            is_entrypoint = False
            entry_kind = "test"

        location = _location(relative, definition)
        flow = Flow(
            id=f"flow-{stable_id(symbol)}",
            name=qualified_name,
            symbol=symbol,
            language="python",
            framework=framework,
            entry_kind=entry_kind,
            is_entrypoint=is_entrypoint,
            location=location,
            metadata={
                "async": isinstance(definition, ast.AsyncFunctionDef),
                "test": is_test,
                "decorators": [_safe_unparse(item) for item in definition.decorator_list],
            },
        )
        builder = FlowBuilder(flow)
        entry = builder.add_node(
            NodeKind.ENTRY,
            _entry_label(flow),
            location,
            [],
            metadata={"symbol": symbol},
        )
        outgoing = self._walk_statements(
            definition.body,
            [PendingEdge(entry.id)],
            builder,
            findings,
            source,
            relative,
        )
        if outgoing:
            builder.add_node(
                NodeKind.TERMINAL,
                "Complete",
                location,
                outgoing,
                evidence=Evidence.INFERRED,
            )
        return flow

    def _walk_statements(
        self,
        statements: list[ast.stmt],
        incoming: list[PendingEdge],
        builder: FlowBuilder,
        findings: list[Finding],
        source: str,
        relative: str,
    ) -> list[PendingEdge]:
        endpoints = incoming
        for statement in statements:
            if not endpoints:
                break
            if isinstance(statement, ast.If):
                endpoints = self._walk_if(statement, endpoints, builder, findings, source, relative)
            elif isinstance(statement, ast.Match):
                endpoints = self._walk_match(
                    statement, endpoints, builder, findings, source, relative
                )
            elif isinstance(statement, ast.Try):
                endpoints = self._walk_try(
                    statement, endpoints, builder, findings, source, relative
                )
            elif isinstance(statement, (ast.For, ast.AsyncFor, ast.While)):
                label = _loop_label(statement)
                node = builder.add_node(
                    NodeKind.ACTION,
                    label,
                    _location(relative, statement),
                    endpoints,
                    detail=_source_segment(source, statement),
                    evidence=Evidence.INFERRED,
                )
                endpoints = [PendingEdge(node.id)]
            elif isinstance(statement, ast.Return):
                value = _safe_unparse(statement.value) if statement.value else ""
                calls = [
                    _call_name(item.func)
                    for item in ast.walk(statement)
                    if isinstance(item, ast.Call)
                ]
                calls = [item for item in calls if item]
                if calls:
                    call_node = builder.add_node(
                        NodeKind.CALL,
                        f"Call {calls[0]}()",
                        _location(relative, statement),
                        endpoints,
                        detail=_source_segment(source, statement),
                        metadata={"calls": calls},
                    )
                    endpoints = [PendingEdge(call_node.id)]
                node = builder.add_node(
                    NodeKind.TERMINAL,
                    f"Return {value}".strip(),
                    _location(relative, statement),
                    endpoints,
                    detail=_source_segment(source, statement),
                )
                endpoints = []
            elif isinstance(statement, ast.Raise):
                value = _safe_unparse(statement.exc) if statement.exc else "error"
                builder.add_node(
                    NodeKind.ERROR,
                    f"Raise {value}",
                    _location(relative, statement),
                    endpoints,
                    detail=_source_segment(source, statement),
                )
                endpoints = []
            else:
                kind, label, calls = _statement_summary(statement)
                node = builder.add_node(
                    kind,
                    label,
                    _location(relative, statement),
                    endpoints,
                    detail=_source_segment(source, statement),
                    metadata={"calls": calls} if calls else {},
                )
                endpoints = [PendingEdge(node.id)]
        return endpoints

    def _walk_if(
        self,
        statement: ast.If,
        incoming: list[PendingEdge],
        builder: FlowBuilder,
        findings: list[Finding],
        source: str,
        relative: str,
    ) -> list[PendingEdge]:
        condition = _safe_unparse(statement.test)
        branch_source = " ".join(_source_segment(source, item) for item in statement.body)
        functional = is_functional_condition(condition, branch_source)
        if not functional:
            node = builder.add_node(
                NodeKind.ACTION,
                f"Handle internal condition: {condition}",
                _location(relative, statement),
                incoming,
                evidence=Evidence.INFERRED,
                detail=_source_segment(source, statement),
            )
            return [PendingEdge(node.id)]

        node = builder.add_node(
            NodeKind.DECISION,
            condition,
            _location(relative, statement.test),
            incoming,
            detail=_source_segment(source, statement.test),
            metadata=decision_metadata(condition),
        )
        yes_endpoints = self._walk_statements(
            statement.body,
            [PendingEdge(node.id, "Yes")],
            builder,
            findings,
            source,
            relative,
        )
        if statement.orelse:
            no_endpoints = self._walk_statements(
                statement.orelse,
                [PendingEdge(node.id, "No")],
                builder,
                findings,
                source,
                relative,
            )
        else:
            no_endpoints = [PendingEdge(node.id, "No")]
        return yes_endpoints + no_endpoints

    def _walk_match(
        self,
        statement: ast.Match,
        incoming: list[PendingEdge],
        builder: FlowBuilder,
        findings: list[Finding],
        source: str,
        relative: str,
    ) -> list[PendingEdge]:
        subject = _safe_unparse(statement.subject)
        node = builder.add_node(
            NodeKind.DECISION,
            f"Match {subject}",
            _location(relative, statement),
            incoming,
            metadata={"condition": subject, "domain": _domain_from_subject(subject), "values": []},
        )
        endpoints: list[PendingEdge] = []
        has_default = False
        values: list[str] = []
        for case in statement.cases:
            pattern = _safe_unparse(case.pattern)
            has_default = has_default or pattern == "_"
            values.append(pattern)
            endpoints.extend(
                self._walk_statements(
                    case.body,
                    [PendingEdge(node.id, pattern)],
                    builder,
                    findings,
                    source,
                    relative,
                )
            )
        node.metadata["values"] = sorted(set(values))
        if not has_default:
            builder.add_missing_branch_finding(node, f"match {subject}", findings)
        return endpoints

    def _walk_try(
        self,
        statement: ast.Try,
        incoming: list[PendingEdge],
        builder: FlowBuilder,
        findings: list[Finding],
        source: str,
        relative: str,
    ) -> list[PendingEdge]:
        node = builder.add_node(
            NodeKind.DECISION,
            "Operation succeeds?",
            _location(relative, statement),
            incoming,
            evidence=Evidence.INFERRED,
            detail=_source_segment(source, statement),
            metadata={"condition": "exception boundary", "domain": "error", "values": []},
        )
        endpoints = self._walk_statements(
            statement.body,
            [PendingEdge(node.id, "Success")],
            builder,
            findings,
            source,
            relative,
        )
        for handler in statement.handlers:
            error_name = _safe_unparse(handler.type) if handler.type else "Any error"
            endpoints.extend(
                self._walk_statements(
                    handler.body,
                    [PendingEdge(node.id, error_name)],
                    builder,
                    findings,
                    source,
                    relative,
                )
            )
        if statement.finalbody:
            endpoints = self._walk_statements(
                statement.finalbody, endpoints, builder, findings, source, relative
            )
        return endpoints


def _definitions(
    tree: ast.Module,
) -> Iterable[tuple[ast.FunctionDef | ast.AsyncFunctionDef, str]]:
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node, ""
        elif isinstance(node, ast.ClassDef):
            for member in node.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    yield member, node.name


def _classify_entrypoint(
    definition: ast.FunctionDef | ast.AsyncFunctionDef,
    relative: str,
    owner: str,
    config: LogicChartConfig,
) -> tuple[str, str, bool]:
    decorators = [_safe_unparse(item) for item in definition.decorator_list]
    symbol_hint = f"{relative}:{owner + '.' if owner else ''}{definition.name}"
    override = config.entrypoint_override(symbol_hint)

    for decorator in decorators:
        parts = decorator.split("(", 1)[0].split(".")
        method = parts[-1]
        if method in FASTAPI_METHODS:
            return "fastapi", "route", override if override is not None else True
        if method in CLI_DECORATORS:
            return "python-cli", "command", override if override is not None else True

    if definition.name.startswith(HANDLER_PREFIXES):
        return "generic", "event_handler", override if override is not None else True
    if owner:
        return "generic", "method", override if override is not None else False
    public = config.include_public_functions and not definition.name.startswith("_")
    return "generic", "function", override if override is not None else public


def _statement_summary(statement: ast.stmt) -> tuple[NodeKind, str, list[str]]:
    calls = [_call_name(item.func) for item in ast.walk(statement) if isinstance(item, ast.Call)]
    calls = [item for item in calls if item]
    boundary = next((item for item in calls if call_is_boundary(item)), "")
    if boundary:
        return NodeKind.CALL, f"Call {boundary}()", calls
    if calls:
        return NodeKind.CALL, f"Call {calls[0]}()", calls
    if isinstance(statement, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
        targets: list[str] = []
        if isinstance(statement, ast.Assign):
            targets = [_safe_unparse(item) for item in statement.targets]
        else:
            targets = [_safe_unparse(statement.target)]
        return NodeKind.ACTION, f"Set {', '.join(targets)}", []
    if isinstance(statement, ast.Assert):
        return NodeKind.ACTION, f"Assert {_safe_unparse(statement.test)}", []
    if isinstance(statement, (ast.Import, ast.ImportFrom)):
        return NodeKind.ACTION, "Load dependencies", []
    return NodeKind.ACTION, compact_text(_safe_unparse(statement), 90), []


def _entry_label(flow: Flow) -> str:
    if flow.entry_kind == "route":
        return f"Route: {flow.name}"
    if flow.entry_kind == "command":
        return f"Command: {flow.name}"
    if flow.entry_kind == "test":
        return f"Test: {flow.name}"
    return flow.name


def _location(relative: str, node: ast.AST) -> SourceLocation:
    start = int(getattr(node, "lineno", 1))
    end = int(getattr(node, "end_lineno", start))
    return SourceLocation(relative, start, end)


def _source_segment(source: str, node: ast.AST) -> str:
    return compact_text(ast.get_source_segment(source, node) or _safe_unparse(node), 500)


def _safe_unparse(node: ast.AST | None) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except (ValueError, TypeError):
        return node.__class__.__name__


def _call_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _loop_label(statement: ast.For | ast.AsyncFor | ast.While) -> str:
    if isinstance(statement, ast.While):
        return f"Repeat while {_safe_unparse(statement.test)}"
    return f"Process each {_safe_unparse(statement.target)}"


def _module_name(relative: str) -> str:
    path = relative.removesuffix(".py").replace("/", ".")
    return path.removesuffix(".__init__")


def _is_test(relative: str, name: str) -> bool:
    parts = Path(relative).parts
    return name.startswith("test_") or "tests" in parts or Path(relative).name.startswith("test_")


def _domain_from_subject(subject: str) -> str:
    lowered = subject.lower()
    for candidate in ("status", "state", "role", "type", "kind", "mode", "permission"):
        if candidate in lowered:
            return candidate
    return ""
