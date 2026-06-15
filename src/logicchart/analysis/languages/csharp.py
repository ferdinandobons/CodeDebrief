"""C# language profile for the profile-driven tree-sitter analyzer."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import tree_sitter_c_sharp

from logicchart.analysis.common import DEFAULT as DEFAULT_LABEL
from logicchart.analysis.treesitter import (
    CaseInfo,
    LanguageProfile,
    TreeSitterAnalyzer,
    TSDefinition,
)
from logicchart.config import LogicChartConfig

_CONTAINERS = {
    "class_declaration",
    "struct_declaration",
    "record_declaration",
    "interface_declaration",
    "namespace_declaration",
    "file_scoped_namespace_declaration",
}
_METHODS = {"method_declaration", "constructor_declaration", "local_function_statement"}


def _text(node: Any | None, source: bytes) -> str:
    if node is None:
        return ""
    return source[node.start_byte : node.end_byte].decode("utf-8", "replace")


def _named(node: Any | None) -> Iterable[Any]:
    return (child for child in node.children if child.is_named) if node is not None else ()


def _definitions(
    root: Any, source: bytes, relative: str, profile: LanguageProfile
) -> Iterable[TSDefinition]:
    yield from _walk(root, source, owner="")


def _walk(node: Any, source: bytes, owner: str) -> Iterable[TSDefinition]:
    if node.type in _CONTAINERS:
        name = _text(node.child_by_field_name("name"), source) or owner
        body = node.child_by_field_name("body") or node.child_by_field_name("declaration_list")
        for child in _named(body if body is not None else node):
            yield from _walk(child, source, name)
        return
    if node.type in _METHODS:
        name = _text(node.child_by_field_name("name"), source)
        body = node.child_by_field_name("body")
        if name and body is not None:
            yield TSDefinition(name=name, node=node, body=body, owner=owner)
        return
    for child in _named(node):
        yield from _walk(child, source, owner)


def _modifiers(node: Any, source: bytes) -> str:
    kinds = {"modifier", "attribute_list"}
    return " ".join(_text(c, source) for c in node.children if c.type in kinds)


def _classify(
    definition: TSDefinition, relative: str, source: str, config: LogicChartConfig
) -> tuple[str, str, bool]:
    override = config.entrypoint_override(f"{relative}:{definition.owner}.{definition.name}")
    modifiers = _modifiers(definition.node, source.encode("utf-8"))
    if definition.name == "Main":
        return "csharp", "main", override if override is not None else True
    if any(tag in modifiers for tag in ("HttpGet", "HttpPost", "Route", "HttpPut", "HttpDelete")):
        return "aspnet", "route", override if override is not None else True
    public = config.include_public_functions and "public" in modifiers
    return "generic", "method", override if override is not None else public


def _is_test(relative: str, name: str) -> bool:
    lowered = relative.lower()
    return "test" in lowered or name.startswith("Test")


def _module_name(relative: str) -> str:
    return Path(relative).parent.as_posix().replace("/", ".").strip(".")


def _switch_cases(switch_node: Any, source: bytes, profile: LanguageProfile) -> list[CaseInfo]:
    body = switch_node.child_by_field_name("body")
    cases: list[CaseInfo] = []
    for section in _named(body):
        if section.type != "switch_section":
            continue
        labels = [c for c in _named(section) if "pattern" in c.type or "switch_label" in c.type]
        statements = [c for c in _named(section) if c not in labels]
        values = [_text(label, source) for label in labels]
        if not values:
            cases.append(CaseInfo(DEFAULT_LABEL, True, [], statements))
        else:
            cases.append(CaseInfo(", ".join(values), False, values, statements))
    return cases


CSHARP_PROFILE = LanguageProfile(
    language="csharp",
    grammar_loader=tree_sitter_c_sharp.language,
    function_types=frozenset(_METHODS),
    definitions=_definitions,
    classify=_classify,
    is_test=_is_test,
    module_name=_module_name,
    switch_types=frozenset({"switch_statement"}),
    switch_value_field="value",
    switch_cases=_switch_cases,
    loop_types=frozenset({"for_statement", "foreach_statement", "while_statement", "do_statement"}),
    throw_types=frozenset({"throw_statement"}),
    call_types=frozenset({"invocation_expression"}),
    try_type="try_statement",
    catch_types=frozenset({"catch_clause"}),
    finally_types=frozenset({"finally_clause"}),
    assignment_types=frozenset({"local_declaration_statement", "assignment_expression"}),
    nested_def_types=frozenset({"lambda_expression", "anonymous_method_expression"}),
)


def build_analyzer(root: Path, config: LogicChartConfig) -> TreeSitterAnalyzer:
    return TreeSitterAnalyzer(root, config, CSHARP_PROFILE)
