"""Rust language profile for the profile-driven tree-sitter analyzer."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import tree_sitter_rust

from codedebrief.analysis.languages._common import module_name, named, text
from codedebrief.analysis.treesitter import (
    LanguageProfile,
    TreeSitterAnalyzer,
    TSDefinition,
)
from codedebrief.config import CodeDebriefConfig


def _definitions(
    root: Any, source: bytes, relative: str, profile: LanguageProfile
) -> Iterable[TSDefinition]:
    yield from _walk(root, source, owner="")


def _walk(node: Any, source: bytes, owner: str) -> Iterable[TSDefinition]:
    if node.type == "impl_item":
        name = text(node.child_by_field_name("type"), source)
        for child in named(node.child_by_field_name("body")):
            yield from _walk(child, source, name)
        return
    if node.type in {"mod_item", "trait_item"}:
        body = node.child_by_field_name("body")
        for child in named(body if body is not None else node):
            yield from _walk(child, source, owner)
        return
    if node.type == "function_item":
        name = text(node.child_by_field_name("name"), source)
        body = node.child_by_field_name("body")
        if name and body is not None:
            yield TSDefinition(name=name, node=node, body=body, owner=owner)
        return
    for child in named(node):
        yield from _walk(child, source, owner)


def _classify(
    definition: TSDefinition, relative: str, source: str, config: CodeDebriefConfig
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
    # A Rust test is a `#[test]`/`#[cfg(test)]` item or a file under the `tests/`
    # integration directory - never a bare `test`-prefixed name (a real `test_render`
    # helper in `src/` must stay an analyzable function). The `(relative, name)` signature
    # can't see attributes, so anchor to the `tests/` path SEGMENT (the convention this
    # profile can detect); attribute-gated `#[test]` items are handled where they parse.
    segments = relative.lower().split("/")
    return "tests" in segments[:-1] or segments[-1] == "tests.rs"


RUST_PROFILE = LanguageProfile(
    language="rust",
    grammar_loader=tree_sitter_rust.language,
    function_types=frozenset({"function_item"}),
    definitions=_definitions,
    classify=_classify,
    is_test=_is_test,
    module_name=module_name,
    if_type="if_expression",
    return_type="return_expression",
    switch_types=frozenset({"match_expression"}),
    switch_value_field="value",
    switch_body_field="body",
    case_types=frozenset({"match_arm"}),
    case_value_field="pattern",
    wildcard_values=frozenset({"_"}),
    exhaustive_switch=True,
    loop_types=frozenset({"loop_expression", "while_expression", "for_expression"}),
    call_types=frozenset({"call_expression"}),
    assignment_types=frozenset({"let_declaration"}),
    nested_def_types=frozenset({"closure_expression"}),
    unwrap_types=frozenset({"expression_statement"}),
)


def build_analyzer(root: Path, config: CodeDebriefConfig) -> TreeSitterAnalyzer:
    return TreeSitterAnalyzer(root, config, RUST_PROFILE)
