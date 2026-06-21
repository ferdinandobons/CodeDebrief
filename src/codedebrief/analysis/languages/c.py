"""C language profile for the profile-driven tree-sitter analyzer."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import tree_sitter_c

from codedebrief.analysis.languages._common import module_name, text
from codedebrief.analysis.treesitter import (
    LanguageProfile,
    TreeSitterAnalyzer,
    TSDefinition,
)
from codedebrief.config import CodeDebriefConfig


def _definitions(
    root: Any, source: bytes, relative: str, profile: LanguageProfile
) -> Iterable[TSDefinition]:
    for node in root.children:
        if node.type != "function_definition":
            continue
        name = _function_name(node.child_by_field_name("declarator"), source)
        body = node.child_by_field_name("body")
        if name and body is not None:
            yield TSDefinition(name=name, node=node, body=body, owner="")


def _function_name(declarator: Any | None, source: bytes) -> str:
    """The identifier inside a (possibly pointer-wrapped) function_declarator."""
    node = declarator
    while node is not None:
        if node.type == "identifier":
            return text(node, source)
        inner = node.child_by_field_name("declarator")
        if inner is None:
            break
        node = inner
    if node is not None:
        ident = next((c for c in node.children if c.type == "identifier"), None)
        return text(ident, source)
    return ""


def _classify(
    definition: TSDefinition, relative: str, source: str, config: CodeDebriefConfig
) -> tuple[str, str, bool]:
    override = config.entrypoint_override(f"{relative}:{definition.name}")
    if definition.name == "main":
        return "c", "main", override if override is not None else True
    is_static = any(
        c.type == "storage_class_specifier" and c.text.decode() == "static"
        for c in definition.node.children
    )
    public = config.include_public_functions and not is_static
    return "generic", "function", override if override is not None else public


def _is_test(relative: str, name: str) -> bool:
    # Anchor to path SEGMENTS (a `test`/`tests` directory or a test_*.c / *_test.c file),
    # not a substring of the whole path: `latest/` or `contest.c` must not count, and a
    # real function named `test_harness` outside a test file must not be misclassified.
    lowered = relative.lower()
    segments = lowered.split("/")
    filename = segments[-1]
    return (
        any(segment in {"test", "tests"} for segment in segments[:-1])
        or filename.startswith("test_")
        or filename.endswith(("_test.c", "_test.h"))
    )


C_PROFILE = LanguageProfile(
    language="c",
    grammar_loader=tree_sitter_c.language,
    function_types=frozenset({"function_definition"}),
    definitions=_definitions,
    classify=_classify,
    is_test=_is_test,
    module_name=module_name,
    block_types=frozenset({"compound_statement"}),
    switch_types=frozenset({"switch_statement"}),
    switch_value_field="condition",
    case_types=frozenset({"case_statement"}),
    default_when_no_value=True,
    case_fall_through=True,
    loop_types=frozenset({"for_statement", "while_statement", "do_statement"}),
    assignment_types=frozenset({"declaration"}),
)


def build_analyzer(root: Path, config: CodeDebriefConfig) -> TreeSitterAnalyzer:
    return TreeSitterAnalyzer(root, config, C_PROFILE)
