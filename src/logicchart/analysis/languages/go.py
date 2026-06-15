"""Go language profile for the profile-driven tree-sitter analyzer."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import tree_sitter_go

from logicchart.analysis.treesitter import (
    LanguageProfile,
    TreeSitterAnalyzer,
    TSDefinition,
)
from logicchart.config import LogicChartConfig
from logicchart.model import Flow

_TEST_PREFIXES = ("Test", "Benchmark", "Example", "Fuzz")


def _text(node: Any | None, source: bytes) -> str:
    if node is None:
        return ""
    return source[node.start_byte : node.end_byte].decode("utf-8", "replace")


def _definitions(
    root: Any, source: bytes, relative: str, profile: LanguageProfile
) -> Iterable[TSDefinition]:
    for node in root.children:
        if node.type == "function_declaration":
            name = _text(node.child_by_field_name("name"), source)
            body = node.child_by_field_name("body")
            if name and body is not None:
                yield TSDefinition(name=name, node=node, body=body, owner="")
        elif node.type == "method_declaration":
            name = _text(node.child_by_field_name("name"), source)
            body = node.child_by_field_name("body")
            owner = _receiver_type(node.child_by_field_name("receiver"), source)
            if name and body is not None:
                yield TSDefinition(name=name, node=node, body=body, owner=owner)


def _receiver_type(receiver: Any | None, source: bytes) -> str:
    if receiver is None:
        return ""
    stack = [receiver]
    while stack:
        current = stack.pop()
        if current.type == "type_identifier":
            return _text(current, source)
        stack.extend(current.children)
    return ""


def _classify(
    definition: TSDefinition, relative: str, source: str, config: LogicChartConfig
) -> tuple[str, str, bool]:
    owner_prefix = f"{definition.owner}." if definition.owner else ""
    override = config.entrypoint_override(f"{relative}:{owner_prefix}{definition.name}")
    exported = definition.name[:1].isupper()
    if definition.name == "main" and not definition.owner:
        return "go", "main", override if override is not None else True
    entry_kind = "method" if definition.owner else "function"
    public = config.include_public_functions and exported
    return "generic", entry_kind, override if override is not None else public


def _is_test(relative: str, name: str) -> bool:
    return relative.endswith("_test.go") or name.startswith(_TEST_PREFIXES)


def _module_name(relative: str) -> str:
    # A Go package is a directory, so files in the same directory share a module name
    # and same-package calls resolve against one another.
    return Path(relative).parent.as_posix().replace("/", ".").strip(".")


def _entry_label(flow: Flow) -> str:
    prefix = {"main": "Main", "test": "Test"}.get(flow.entry_kind)
    return f"{prefix}: {flow.name}" if prefix else flow.name


GO_PROFILE = LanguageProfile(
    language="go",
    grammar_loader=tree_sitter_go.language,
    function_types=frozenset({"function_declaration", "method_declaration"}),
    definitions=_definitions,
    classify=_classify,
    is_test=_is_test,
    module_name=_module_name,
    entry_label=_entry_label,
    switch_types=frozenset({"expression_switch_statement", "type_switch_statement"}),
    switch_body_field=None,
    case_types=frozenset({"expression_case", "type_case"}),
    default_types=frozenset({"default_case", "communication_case"}),
    case_value_field="value",
    loop_types=frozenset({"for_statement"}),
    throw_types=frozenset(),
    assignment_types=frozenset({"short_var_declaration", "assignment_statement"}),
    assignment_target_field="left",
    nested_def_types=frozenset({"func_literal"}),
)


def build_analyzer(root: Path, config: LogicChartConfig) -> TreeSitterAnalyzer:
    return TreeSitterAnalyzer(root, config, GO_PROFILE)
