"""PHP language profile for the profile-driven tree-sitter analyzer."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import tree_sitter_php

from logicchart.analysis.treesitter import (
    LanguageProfile,
    TreeSitterAnalyzer,
    TSDefinition,
)
from logicchart.config import LogicChartConfig

_CONTAINERS = {
    "class_declaration",
    "interface_declaration",
    "trait_declaration",
    "enum_declaration",
}
_METHODS = {"method_declaration", "function_definition"}
_VISIBILITY = {"visibility_modifier", "static_modifier", "abstract_modifier"}


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
        for child in _named(node.child_by_field_name("body")):
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


def _classify(
    definition: TSDefinition, relative: str, source: str, config: LogicChartConfig
) -> tuple[str, str, bool]:
    override = config.entrypoint_override(f"{relative}:{definition.owner}.{definition.name}")
    visibility = " ".join(
        _text(c, source.encode("utf-8")) for c in definition.node.children if c.type in _VISIBILITY
    )
    is_private = "private" in visibility or "protected" in visibility
    entry_kind = "method" if definition.owner else "function"
    public = config.include_public_functions and not is_private
    return "generic", entry_kind, override if override is not None else public


def _is_test(relative: str, name: str) -> bool:
    lowered = relative.lower()
    return "/test" in lowered or lowered.endswith("test.php") or name.startswith("test")


def _module_name(relative: str) -> str:
    return Path(relative).parent.as_posix().replace("/", ".").strip(".")


def _call_name(call: Any, source: bytes) -> str:
    if call.type == "function_call_expression":
        return _text(call.child_by_field_name("function"), source)
    return _text(call.child_by_field_name("name"), source)


PHP_PROFILE = LanguageProfile(
    language="php",
    grammar_loader=tree_sitter_php.language_php,
    function_types=frozenset(_METHODS),
    definitions=_definitions,
    classify=_classify,
    is_test=_is_test,
    module_name=_module_name,
    block_types=frozenset({"compound_statement"}),
    consequence_field="body",
    switch_types=frozenset({"switch_statement"}),
    switch_value_field="condition",
    case_types=frozenset({"case_statement"}),
    default_types=frozenset({"default_statement"}),
    loop_types=frozenset({"for_statement", "while_statement", "foreach_statement", "do_statement"}),
    call_types=frozenset(
        {"function_call_expression", "member_call_expression", "scoped_call_expression"}
    ),
    call_name=_call_name,
    try_type="try_statement",
    catch_types=frozenset({"catch_clause"}),
    finally_types=frozenset({"finally_clause"}),
    assignment_types=frozenset({"assignment_expression"}),
    nested_def_types=frozenset({"anonymous_function_creation_expression", "arrow_function"}),
)


def build_analyzer(root: Path, config: LogicChartConfig) -> TreeSitterAnalyzer:
    return TreeSitterAnalyzer(root, config, PHP_PROFILE)
