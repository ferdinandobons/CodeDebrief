"""Rust language profile for the profile-driven tree-sitter analyzer."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import tree_sitter_rust

from logicchart.analysis.treesitter import (
    LanguageProfile,
    TreeSitterAnalyzer,
    TSDefinition,
)
from logicchart.config import LogicChartConfig


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
    if node.type == "impl_item":
        name = _text(node.child_by_field_name("type"), source)
        for child in _named(node.child_by_field_name("body")):
            yield from _walk(child, source, name)
        return
    if node.type in {"mod_item", "trait_item"}:
        body = node.child_by_field_name("body")
        for child in _named(body if body is not None else node):
            yield from _walk(child, source, owner)
        return
    if node.type == "function_item":
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
    owner_prefix = f"{definition.owner}." if definition.owner else ""
    override = config.entrypoint_override(f"{relative}:{owner_prefix}{definition.name}")
    if definition.name == "main" and not definition.owner:
        return "rust", "main", override if override is not None else True
    is_pub = any(c.type == "visibility_modifier" for c in definition.node.children)
    entry_kind = "method" if definition.owner else "function"
    public = config.include_public_functions and is_pub
    return "generic", entry_kind, override if override is not None else public


def _is_test(relative: str, name: str) -> bool:
    return "test" in relative.lower() or name.startswith("test")


def _module_name(relative: str) -> str:
    return Path(relative).parent.as_posix().replace("/", ".").strip(".")


RUST_PROFILE = LanguageProfile(
    language="rust",
    grammar_loader=tree_sitter_rust.language,
    function_types=frozenset({"function_item"}),
    definitions=_definitions,
    classify=_classify,
    is_test=_is_test,
    module_name=_module_name,
    if_type="if_expression",
    return_type="return_expression",
    switch_types=frozenset({"match_expression"}),
    switch_value_field="value",
    switch_body_field="body",
    case_types=frozenset({"match_arm"}),
    case_value_field="pattern",
    wildcard_values=frozenset({"_"}),
    loop_types=frozenset({"loop_expression", "while_expression", "for_expression"}),
    call_types=frozenset({"call_expression"}),
    assignment_types=frozenset({"let_declaration"}),
    nested_def_types=frozenset({"closure_expression"}),
    unwrap_types=frozenset({"expression_statement"}),
)


def build_analyzer(root: Path, config: LogicChartConfig) -> TreeSitterAnalyzer:
    return TreeSitterAnalyzer(root, config, RUST_PROFILE)
