"""A profile-driven tree-sitter analyzer.

Most languages share the same control-flow shape (functions, ``if``, ``switch``/
``match``, loops, ``return``, ``throw``/``raise``, ``try``/``catch``, calls). This module
runs that common walk once, parameterized by a :class:`LanguageProfile` that names the
grammar node types and supplies small per-language extractors. A new control-flow
language becomes a profile (see ``analysis/languages/``), not a bespoke analyzer.

It produces exactly the same IR (flows, nodes, edges, ``branches``, decision identity,
effects, qualified calls) as the dedicated Python/TypeScript analyzers, so detectors,
linking, and rendering are unchanged.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tree_sitter import Language, Parser

from logicchart.analysis.common import (
    CONTINUES,
    EMPTY,
    FALLS_THROUGH,
    RAISES,
    RETURNS,
    SWITCH,
    YES,
    FlowBuilder,
    PendingEdge,
    annotate_reachability,
    attach_qualified_calls,
    branch,
    call_is_boundary,
    decision_identity,
    decision_metadata,
    domain_from_subject,
    is_functional_condition,
    tag_call_effects,
    value_namespace,
)
from logicchart.analysis.common import DEFAULT as DEFAULT_LABEL
from logicchart.analysis.common import NO as NO_LABEL
from logicchart.analysis.detectors import dead_code_finding, single_flow_findings
from logicchart.config import LogicChartConfig
from logicchart.model import Evidence, FileAnalysis, Finding, Flow, NodeKind, SourceLocation
from logicchart.util import compact_text, file_sha256, relpath, stable_id


@dataclass(slots=True)
class TSDefinition:
    """One function/method to turn into a flow."""

    name: str
    node: Any
    body: Any
    owner: str = ""


@dataclass(frozen=True, slots=True)
class LanguageProfile:
    """The grammar vocabulary + extractors that make a language analyzable.

    The defaults describe a typical C-family grammar; a profile overrides only what
    differs. Callables keep the genuinely per-language bits (which functions are entry
    points, what a test file looks like, how imports resolve) out of the generic walk.
    """

    language: str
    grammar_loader: Callable[[], Any]
    function_types: frozenset[str]
    definitions: Callable[[Any, bytes, str, LanguageProfile], Iterable[TSDefinition]]
    classify: Callable[[TSDefinition, str, str, LogicChartConfig], tuple[str, str, bool]]
    is_test: Callable[[str, str], bool]
    module_name: Callable[[str], str]
    import_map: Callable[[Any, bytes, str], dict[str, str]] = lambda root, src, rel: {}
    entry_label: Callable[[Flow], str] | None = None
    harvest_enums: Callable[[Any, bytes], dict[str, list[str]]] | None = None
    # Node-type vocabulary (C-family defaults).
    block_types: frozenset[str] = frozenset({"block"})
    name_field: str = "name"
    body_field: str = "body"
    if_type: str = "if_statement"
    condition_field: str = "condition"
    consequence_field: str = "consequence"
    alternative_field: str = "alternative"
    switch_types: frozenset[str] = frozenset()
    switch_value_field: str = "value"
    switch_body_field: str | None = "body"
    case_types: frozenset[str] = frozenset()
    case_value_field: str = "value"
    default_types: frozenset[str] = frozenset()
    loop_types: frozenset[str] = frozenset()
    return_type: str = "return_statement"
    return_keyword: str = "return"
    throw_types: frozenset[str] = frozenset()
    throw_keyword: str = "throw"
    continue_types: frozenset[str] = frozenset({"continue_statement"})
    break_types: frozenset[str] = frozenset({"break_statement"})
    call_types: frozenset[str] = frozenset({"call_expression"})
    call_function_field: str = "function"
    assignment_types: frozenset[str] = frozenset()
    assignment_target_field: str = "left"
    nested_def_types: frozenset[str] = field(default_factory=frozenset)
    inert_types: frozenset[str] = frozenset({"comment"})


class TreeSitterAnalyzer:
    def __init__(self, root: Path, config: LogicChartConfig, profile: LanguageProfile) -> None:
        self.root = root
        self.config = config
        self.profile = profile
        self.parser = Parser(Language(profile.grammar_loader()))

    def analyze(self, path: Path) -> FileAnalysis:
        source = path.read_bytes()
        relative = relpath(path, self.root)
        tree = self.parser.parse(source)
        findings: list[Finding] = []
        flows = [
            self._analyze_definition(item, source, relative, findings)
            for item in self.profile.definitions(tree.root_node, source, relative, self.profile)
        ]
        import_map = self.profile.import_map(tree.root_node, source, relative)
        module_name = self.profile.module_name(relative)
        for flow in flows:
            attach_qualified_calls(flow, import_map, module_name)
            tag_call_effects(flow)
        harvest = self.profile.harvest_enums
        enums = harvest(tree.root_node, source) if harvest else {}
        return FileAnalysis(
            path=relative,
            language=self.profile.language,
            sha256=file_sha256(path),
            enums=enums,
            flows=flows,
            findings=findings,
        )

    def _analyze_definition(
        self, definition: TSDefinition, source: bytes, relative: str, findings: list[Finding]
    ) -> Flow:
        owner_prefix = f"{definition.owner}." if definition.owner else ""
        qualified_name = f"{owner_prefix}{definition.name}"
        symbol = f"{self.profile.module_name(relative)}:{qualified_name}"
        framework, entry_kind, is_entrypoint = self.profile.classify(
            definition, relative, source.decode("utf-8", "replace"), self.config
        )
        is_test = self.profile.is_test(relative, definition.name)
        if is_test:
            is_entrypoint = False
            entry_kind = "test"

        location = _location(relative, definition.node)
        flow = Flow(
            id=f"flow-{stable_id(symbol)}",
            name=qualified_name,
            symbol=symbol,
            language=self.profile.language,
            framework=framework,
            entry_kind=entry_kind,
            is_entrypoint=is_entrypoint,
            location=location,
            metadata={"test": is_test},
        )
        builder = FlowBuilder(flow)
        entry = builder.add_node(
            NodeKind.ENTRY, self._entry_label(flow), location, [], metadata={"symbol": symbol}
        )
        outgoing = self._walk_statements(
            self._statement_children(definition.body),
            [PendingEdge(entry.id)],
            builder,
            findings,
            source,
            relative,
        )
        if outgoing:
            builder.add_node(
                NodeKind.TERMINAL, "Complete", location, outgoing, evidence=Evidence.INFERRED
            )
        annotate_reachability(flow)
        tag_call_effects(flow)
        findings.extend(single_flow_findings(flow))
        return flow

    def _entry_label(self, flow: Flow) -> str:
        if self.profile.entry_label is not None:
            return self.profile.entry_label(flow)
        return flow.name

    def _walk_statements(
        self,
        statements: list[Any],
        incoming: list[PendingEdge],
        builder: FlowBuilder,
        findings: list[Finding],
        source: bytes,
        relative: str,
    ) -> list[PendingEdge]:
        profile = self.profile
        endpoints = incoming
        for statement in statements:
            if not endpoints:
                findings.append(
                    dead_code_finding(
                        builder.flow, _location(relative, statement), _text(statement, source)
                    )
                )
                break
            node_type = statement.type
            if node_type == profile.if_type:
                endpoints = self._walk_if(statement, endpoints, builder, findings, source, relative)
            elif node_type in profile.switch_types:
                endpoints = self._walk_switch(
                    statement, endpoints, builder, findings, source, relative
                )
            elif node_type in profile.loop_types:
                node = builder.add_node(
                    NodeKind.ACTION,
                    _loop_label(statement, source),
                    _location(relative, statement),
                    endpoints,
                    detail=_text(statement, source),
                    evidence=Evidence.INFERRED,
                )
                endpoints = [PendingEdge(node.id)]
            elif node_type == profile.return_type:
                endpoints = self._walk_return(statement, endpoints, builder, source, relative)
            elif node_type in profile.throw_types:
                value = _text(statement, source).removeprefix(profile.throw_keyword).strip(" ;")
                builder.add_node(
                    NodeKind.ERROR,
                    f"Raise {value}".strip(),
                    _location(relative, statement),
                    endpoints,
                    detail=_text(statement, source),
                )
                endpoints = []
            elif node_type in profile.function_types or node_type in profile.nested_def_types:
                continue
            else:
                kind, label, calls = self._statement_summary(statement, source)
                node = builder.add_node(
                    kind,
                    label,
                    _location(relative, statement),
                    endpoints,
                    detail=_text(statement, source),
                    metadata={"calls": calls} if calls else {},
                )
                endpoints = [PendingEdge(node.id)]
        return endpoints

    def _walk_return(
        self,
        statement: Any,
        incoming: list[PendingEdge],
        builder: FlowBuilder,
        source: bytes,
        relative: str,
    ) -> list[PendingEdge]:
        value = _text(statement, source).removeprefix(self.profile.return_keyword).strip(" ;")
        calls = self._calls_in(statement, source)
        endpoints = incoming
        if calls:
            call_node = builder.add_node(
                NodeKind.CALL,
                f"Call {calls[0]}()",
                _location(relative, statement),
                endpoints,
                detail=_text(statement, source),
                metadata={"calls": calls},
            )
            endpoints = [PendingEdge(call_node.id)]
        builder.add_node(
            NodeKind.TERMINAL,
            f"Return {value}".strip(),
            _location(relative, statement),
            endpoints,
            detail=_text(statement, source),
        )
        return []

    def _walk_if(
        self,
        statement: Any,
        incoming: list[PendingEdge],
        builder: FlowBuilder,
        findings: list[Finding],
        source: bytes,
        relative: str,
    ) -> list[PendingEdge]:
        profile = self.profile
        condition_node = statement.child_by_field_name(profile.condition_field)
        consequence = statement.child_by_field_name(profile.consequence_field)
        alternative = statement.child_by_field_name(profile.alternative_field)
        condition = _strip_parentheses(_text(condition_node, source))
        branch_text = _text(consequence, source)

        if not is_functional_condition(condition, branch_text):
            node = builder.add_node(
                NodeKind.ACTION,
                f"Handle internal condition: {condition}",
                _location(relative, statement),
                incoming,
                evidence=Evidence.INFERRED,
                detail=_text(statement, source),
            )
            return [PendingEdge(node.id)]

        node = builder.add_node(
            NodeKind.DECISION,
            condition,
            _location(relative, condition_node or statement),
            incoming,
            detail=condition,
            metadata=decision_metadata(condition),
        )
        node.metadata["branches"] = [
            branch(YES, self._branch_outcome(self._statement_children(consequence))),
            branch(
                NO_LABEL,
                self._branch_outcome(self._statement_children(alternative))
                if alternative is not None
                else FALLS_THROUGH,
                implicit=alternative is None,
            ),
        ]
        yes_endpoints = self._walk_statements(
            self._statement_children(consequence),
            [PendingEdge(node.id, YES)],
            builder,
            findings,
            source,
            relative,
        )
        if alternative is not None:
            no_endpoints = self._walk_statements(
                self._statement_children(alternative),
                [PendingEdge(node.id, NO_LABEL)],
                builder,
                findings,
                source,
                relative,
            )
        else:
            no_endpoints = [PendingEdge(node.id, NO_LABEL)]
        return yes_endpoints + no_endpoints

    def _walk_switch(
        self,
        statement: Any,
        incoming: list[PendingEdge],
        builder: FlowBuilder,
        findings: list[Finding],
        source: bytes,
        relative: str,
    ) -> list[PendingEdge]:
        profile = self.profile
        value_node = statement.child_by_field_name(profile.switch_value_field)
        subject = _strip_parentheses(_text(value_node, source)) or "value"
        node = builder.add_node(
            NodeKind.DECISION,
            f"Switch on {subject}",
            _location(relative, statement),
            incoming,
            metadata=decision_identity(
                condition=subject,
                subject=subject,
                operator=SWITCH,
                domain=domain_from_subject(subject),
                namespace="",
            ),
        )
        container = (
            statement.child_by_field_name(profile.switch_body_field)
            if profile.switch_body_field
            else statement
        )
        endpoints: list[PendingEdge] = []
        values: list[str] = []
        has_default = False
        branches: list[dict[str, Any]] = []
        for case in _named_children(container):
            case_value = case.child_by_field_name(profile.case_value_field)
            if case.type in profile.default_types:
                label = DEFAULT_LABEL
                has_default = True
            elif case.type in profile.case_types:
                label = _text(case_value, source) or "case"
                values.append(label)
            else:
                continue
            children = [
                child
                for child in _named_children(case)
                if case_value is None
                or child.start_byte != case_value.start_byte
                or child.end_byte != case_value.end_byte
            ]
            branches.append(branch(label, self._branch_outcome(children)))
            endpoints.extend(
                self._walk_statements(
                    children, [PendingEdge(node.id, label)], builder, findings, source, relative
                )
            )
        node.metadata["values"] = sorted(set(values))
        node.metadata["value_namespace"] = value_namespace(sorted(set(values)))
        if not has_default:
            branches.append(branch(DEFAULT_LABEL, FALLS_THROUGH, implicit=True))
            endpoints.append(PendingEdge(node.id, DEFAULT_LABEL))
        node.metadata["branches"] = branches
        return endpoints

    def _branch_outcome(self, statements: list[Any]) -> str:
        profile = self.profile
        meaningful = [s for s in statements if s.type not in profile.inert_types]
        if not meaningful:
            return EMPTY
        for statement in meaningful:
            if statement.type == profile.return_type:
                return RETURNS
            if statement.type in profile.throw_types:
                return RAISES
            if statement.type in profile.continue_types:
                return CONTINUES
            if statement.type in profile.break_types:
                return FALLS_THROUGH
            if statement.type == profile.if_type:
                alternative = statement.child_by_field_name(profile.alternative_field)
                if alternative is not None:
                    then_outcome = self._branch_outcome(
                        self._statement_children(
                            statement.child_by_field_name(profile.consequence_field)
                        )
                    )
                    else_outcome = self._branch_outcome(self._statement_children(alternative))
                    if _terminates(then_outcome) and _terminates(else_outcome):
                        return then_outcome if then_outcome == else_outcome else RETURNS
        return FALLS_THROUGH

    def _statement_summary(self, statement: Any, source: bytes) -> tuple[NodeKind, str, list[str]]:
        calls = self._calls_in(statement, source)
        boundary = next((item for item in calls if call_is_boundary(item)), "")
        if boundary:
            return NodeKind.CALL, f"Call {boundary}()", calls
        if calls:
            return NodeKind.CALL, f"Call {calls[0]}()", calls
        if statement.type in self.profile.assignment_types:
            target = _text(
                statement.child_by_field_name(self.profile.assignment_target_field), source
            )
            if target:
                return NodeKind.ACTION, f"Set {target}", []
        return NodeKind.ACTION, compact_text(_text(statement, source).rstrip(";"), 90), []

    def _calls_in(self, statement: Any, source: bytes) -> list[str]:
        names = [
            _call_name(item, source, self.profile.call_function_field)
            for item in self._descendants(statement)
            if item.type in self.profile.call_types
        ]
        return [name for name in names if name]

    def _descendants(self, node: Any) -> Iterable[Any]:
        breakers = self.profile.function_types | self.profile.nested_def_types
        stack = [node]
        while stack:
            current = stack.pop()
            yield current
            if current is not node and current.type in breakers:
                continue
            stack.extend(reversed(current.children))

    def _statement_children(self, node: Any | None) -> list[Any]:
        if node is None:
            return []
        if node.type in self.profile.block_types:
            return list(_named_children(node))
        return [node]


def _named_children(node: Any | None) -> Iterable[Any]:
    if node is None:
        return []
    return (child for child in node.children if child.is_named)


def _text(node: Any | None, source: bytes) -> str:
    if node is None:
        return ""
    return compact_text(source[node.start_byte : node.end_byte].decode("utf-8", "replace"), 500)


def _location(relative: str, node: Any) -> SourceLocation:
    return SourceLocation(relative, int(node.start_point.row) + 1, int(node.end_point.row) + 1)


def _loop_label(statement: Any, source: bytes) -> str:
    header = _text(statement, source).split("{", 1)[0].strip()
    return compact_text(f"Repeat: {header}", 100)


def _call_name(call: Any, source: bytes, function_field: str) -> str:
    return _text(call.child_by_field_name(function_field), source)


def _strip_parentheses(value: str) -> str:
    value = value.strip()
    while value.startswith("(") and value.endswith(")"):
        value = value[1:-1].strip()
    return value


def _terminates(outcome: str) -> bool:
    return outcome in {RETURNS, RAISES, CONTINUES}
