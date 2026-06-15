"""Ruby language profile for the profile-driven tree-sitter analyzer."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import tree_sitter_ruby

from logicchart.analysis.treesitter import (
    LanguageProfile,
    TreeSitterAnalyzer,
    TSDefinition,
)
from logicchart.config import LogicChartConfig

_CONTAINERS = {"class", "module", "singleton_class"}
_METHODS = {"method", "singleton_method"}


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
    owner_prefix = f"{definition.owner}." if definition.owner else ""
    override = config.entrypoint_override(f"{relative}:{owner_prefix}{definition.name}")
    entry_kind = "method" if definition.owner else "function"
    public = config.include_public_functions and not definition.name.startswith("_")
    return "generic", entry_kind, override if override is not None else public


def _is_test(relative: str, name: str) -> bool:
    lowered = relative.lower()
    return (
        "/spec/" in lowered
        or "/test/" in lowered
        or lowered.endswith(("_spec.rb", "_test.rb"))
        or name.startswith("test")
    )


def _module_name(relative: str) -> str:
    return Path(relative).parent.as_posix().replace("/", ".").strip(".")


def _call_name(call: Any, source: bytes) -> str:
    method = call.child_by_field_name("method")
    if method is not None:
        return _text(method, source)
    ident = next((c for c in call.children if c.type in {"identifier", "constant"}), None)
    return _text(ident, source)


RUBY_PROFILE = LanguageProfile(
    language="ruby",
    grammar_loader=tree_sitter_ruby.language,
    function_types=frozenset(_METHODS),
    definitions=_definitions,
    classify=_classify,
    is_test=_is_test,
    module_name=_module_name,
    block_types=frozenset({"body_statement", "then", "else", "do_block", "begin"}),
    if_type="if",
    alternative_types=frozenset({"else"}),
    switch_types=frozenset({"case"}),
    switch_value_field="value",
    switch_body_field=None,
    case_types=frozenset({"when"}),
    case_value_field="pattern",
    default_types=frozenset({"else"}),
    return_type="return",
    loop_types=frozenset({"while", "until", "for"}),
    call_types=frozenset({"call", "command_call", "method_call"}),
    call_name=_call_name,
)


def build_analyzer(root: Path, config: LogicChartConfig) -> TreeSitterAnalyzer:
    return TreeSitterAnalyzer(root, config, RUBY_PROFILE)
