"""C# language profile for the profile-driven tree-sitter analyzer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import tree_sitter_c_sharp

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
    {
        "class_declaration",
        "struct_declaration",
        "record_declaration",
        "interface_declaration",
        "namespace_declaration",
        "file_scoped_namespace_declaration",
    }
)
_METHODS = frozenset({"method_declaration", "constructor_declaration", "local_function_statement"})
_ROUTE_TAGS = ("HttpGet", "HttpPost", "Route", "HttpPut", "HttpDelete")


def _modifiers(node: Any, source: bytes) -> str:
    kinds = {"modifier", "attribute_list"}
    return " ".join(text(c, source) for c in node.children if c.type in kinds)


def _classify(
    definition: TSDefinition, relative: str, source: str, config: LogicChartConfig
) -> tuple[str, str, bool]:
    override = config.entrypoint_override(f"{relative}:{definition.owner}.{definition.name}")
    modifiers = _modifiers(definition.node, source.encode("utf-8"))
    if definition.name == "Main":
        return "csharp", "main", override if override is not None else True
    if any(tag in modifiers for tag in _ROUTE_TAGS):
        return "aspnet", "route", override if override is not None else True
    public = config.include_public_functions and "public" in modifiers
    return "generic", "method", override if override is not None else public


def _is_test(relative: str, name: str) -> bool:
    # Anchor to path SEGMENTS and the C# *Test.cs / *Tests.cs class-file convention, not a
    # substring of the whole path or a bare `Test`-prefixed method name (`TestRunner`,
    # `TestData`...) - those are real methods. The file suffix is matched case-sensitively
    # so `Latest.cs` (a real class) does not look like a test.
    segments = relative.split("/")
    return any(segment.lower() in {"test", "tests"} for segment in segments[:-1]) or segments[
        -1
    ].endswith(("Test.cs", "Tests.cs"))


def _import_map(root: Any, source: bytes, relative: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for directive in root.children:
        if directive.type != "using_directive":
            continue
        specifier = _using_specifier(directive, source)
        if not specifier:
            continue
        alias = directive.child_by_field_name("name")
        is_static = any(child.type == "static" for child in directive.children)
        if alias is not None:
            mapping[text(alias, source)] = f"{specifier}:"
        elif is_static:
            mapping[f"__static_using__:{specifier}"] = f"{specifier}:"
        else:
            mapping[f"__namespace_using__:{specifier}"] = f"{specifier}:"
    return mapping


def _using_specifier(directive: Any, source: bytes) -> str:
    for child in directive.children:
        if child.type in {"qualified_name", "alias_qualified_name"}:
            return text(child, source)
    alias = directive.child_by_field_name("name")
    for child in directive.children:
        if child.type == "identifier" and child is not alias:
            value = text(child, source)
            if value != "static":
                return value
    return ""


def _switch_cases(switch_node: Any, source: bytes, profile: LanguageProfile) -> list[CaseInfo]:
    body = switch_node.child_by_field_name("body")
    cases: list[CaseInfo] = []
    for section in named(body):
        if section.type != "switch_section":
            continue
        labels = [c for c in named(section) if "pattern" in c.type or "switch_label" in c.type]
        statements = [c for c in named(section) if c not in labels]
        values = [text(label, source) for label in labels]
        if not values:
            cases.append(CaseInfo(DEFAULT_LABEL, True, [], statements))
        else:
            cases.append(CaseInfo(", ".join(values), False, values, statements))
    return cases


CSHARP_PROFILE = LanguageProfile(
    language="csharp",
    grammar_loader=tree_sitter_c_sharp.language,
    function_types=_METHODS,
    definitions=container_definitions(_CONTAINERS, _METHODS),
    classify=_classify,
    is_test=_is_test,
    module_name=module_name,
    import_map=_import_map,
    dependency_module_suffixes=(".cs",),
    dependency_package_directories=True,
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
