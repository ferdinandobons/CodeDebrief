"""Go language profile for the profile-driven tree-sitter analyzer."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import tree_sitter_go

from logicchart.analysis.languages._common import module_name, text
from logicchart.analysis.treesitter import (
    LanguageProfile,
    TreeSitterAnalyzer,
    TSDefinition,
)
from logicchart.config import LogicChartConfig
from logicchart.model import Flow

_TEST_PREFIXES = ("Test", "Benchmark", "Example", "Fuzz")


def _definitions(
    root: Any, source: bytes, relative: str, profile: LanguageProfile
) -> Iterable[TSDefinition]:
    for node in root.children:
        if node.type == "function_declaration":
            name = text(node.child_by_field_name("name"), source)
            body = node.child_by_field_name("body")
            if name and body is not None:
                yield TSDefinition(name=name, node=node, body=body, owner="")
        elif node.type == "method_declaration":
            name = text(node.child_by_field_name("name"), source)
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
            return text(current, source)
        stack.extend(current.children)
    return ""


def _import_map(root: Any, source: bytes, relative: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for declaration in root.children:
        if declaration.type != "import_declaration":
            continue
        for spec in _import_specs(declaration):
            path = _import_path(spec, source)
            if not path:
                continue
            module = path.replace("/", ".").strip(".")
            if not module:
                continue
            alias = _import_alias(spec, source)
            if alias in {"_", "."}:
                mapping[f"__side_effect_import__:{module}"] = f"{module}:"
                continue
            binding = alias or path.rsplit("/", 1)[-1]
            if binding:
                mapping[binding] = f"{module}:"
    return mapping


def _import_specs(declaration: Any) -> Iterable[Any]:
    stack = list(declaration.children)
    while stack:
        current = stack.pop(0)
        if current.type == "import_spec":
            yield current
            continue
        stack[0:0] = list(current.children)


def _import_path(spec: Any, source: bytes) -> str:
    literal = next(
        (
            child
            for child in spec.children
            if child.type in {"interpreted_string_literal", "raw_string_literal"}
        ),
        None,
    )
    return text(literal, source).strip('"`')


def _import_alias(spec: Any, source: bytes) -> str:
    for child in spec.children:
        if child.type in {"package_identifier", "blank_identifier", "dot"}:
            return text(child, source)
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


def _dependency_path_filter(relative: str) -> bool:
    return not relative.endswith("_test.go")


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
    module_name=module_name,
    import_map=_import_map,
    dependency_module_suffixes=(".go",),
    dependency_package_directories=True,
    dependency_path_filter=_dependency_path_filter,
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
