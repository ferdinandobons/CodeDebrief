"""Java language profile for the profile-driven tree-sitter analyzer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import tree_sitter_java

from logicchart.analysis.common import DEFAULT as DEFAULT_LABEL
from logicchart.analysis.languages._common import container_definitions, module_name, named, text
from logicchart.analysis.treesitter import (
    CaseInfo,
    LanguageProfile,
    TreeSitterAnalyzer,
    TSDefinition,
)
from logicchart.config import LogicChartConfig

_CONTAINERS = frozenset(
    {"class_declaration", "interface_declaration", "enum_declaration", "record_declaration"}
)
_METHODS = frozenset({"method_declaration", "constructor_declaration"})
_ROUTE_ANNOTATIONS = (
    "@GetMapping",
    "@PostMapping",
    "@PutMapping",
    "@DeleteMapping",
    "@PatchMapping",
    "@RequestMapping",
)


def _modifiers(node: Any, source: bytes) -> str:
    for child in node.children:
        if child.type == "modifiers":
            return text(child, source)
    return ""


def _classify(
    definition: TSDefinition, relative: str, source: str, config: LogicChartConfig
) -> tuple[str, str, bool]:
    override = config.entrypoint_override(f"{relative}:{definition.owner}.{definition.name}")
    modifiers = _modifiers(definition.node, source.encode("utf-8"))
    if definition.name == "main" and "static" in modifiers:
        return "java", "main", override if override is not None else True
    if any(annotation in modifiers for annotation in _ROUTE_ANNOTATIONS):
        return "spring", "route", override if override is not None else True
    public = config.include_public_functions and "public" in modifiers
    return "generic", "method", override if override is not None else public


def _is_test(relative: str, name: str) -> bool:
    return (
        "/test/" in relative
        or relative.endswith(("Test.java", "Tests.java", "IT.java"))
        or name.startswith("test")
    )


def _switch_cases(switch_node: Any, source: bytes, profile: LanguageProfile) -> list[CaseInfo]:
    body = switch_node.child_by_field_name("body")
    cases: list[CaseInfo] = []
    for group in named(body):
        if group.type != "switch_block_statement_group":
            continue
        labels = [c for c in named(group) if c.type == "switch_label"]
        statements = [c for c in named(group) if c.type != "switch_label"]
        values: list[str] = []
        is_default = False
        for label in labels:
            value = next(iter(named(label)), None)
            if value is None:
                is_default = True
            else:
                values.append(text(value, source))
        if is_default and not values:
            cases.append(CaseInfo(DEFAULT_LABEL, True, [], statements))
        else:
            cases.append(CaseInfo(", ".join(values) or "case", False, values, statements))
    return cases


def _call_name(call: Any, source: bytes) -> str:
    if call.type == "method_invocation":
        return text(call.child_by_field_name("name"), source)
    if call.type == "object_creation_expression":
        return text(call.child_by_field_name("type"), source)
    return ""


JAVA_PROFILE = LanguageProfile(
    language="java",
    grammar_loader=tree_sitter_java.language,
    function_types=_METHODS,
    definitions=container_definitions(_CONTAINERS, _METHODS),
    classify=_classify,
    is_test=_is_test,
    module_name=module_name,
    switch_types=frozenset({"switch_expression"}),
    switch_value_field="condition",
    switch_cases=_switch_cases,
    loop_types=frozenset(
        {"for_statement", "enhanced_for_statement", "while_statement", "do_statement"}
    ),
    throw_types=frozenset({"throw_statement"}),
    call_types=frozenset({"method_invocation", "object_creation_expression"}),
    call_name=_call_name,
    try_type="try_statement",
    catch_types=frozenset({"catch_clause"}),
    finally_types=frozenset({"finally_clause"}),
    assignment_types=frozenset({"local_variable_declaration", "assignment_expression"}),
    nested_def_types=frozenset({"lambda_expression"}),
)


def build_analyzer(root: Path, config: LogicChartConfig) -> TreeSitterAnalyzer:
    return TreeSitterAnalyzer(root, config, JAVA_PROFILE)
