"""Shared helpers for the tree-sitter language profiles.

Every profile needs the same byte-slice text, named-children, and directory-as-module
helpers; the class/method profiles also share one definition walker. Keeping them here
avoids copy-paste drift across the language modules.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from logicchart.analysis.treesitter import LanguageProfile, TSDefinition


def text(node: Any | None, source: bytes) -> str:
    if node is None:
        return ""
    return source[node.start_byte : node.end_byte].decode("utf-8", "replace")


def named(node: Any | None) -> Iterable[Any]:
    return (child for child in node.children if child.is_named) if node is not None else ()


def module_name(relative: str) -> str:
    """The directory as a dotted module name, so files in one package share a namespace."""
    return Path(relative).parent.as_posix().replace("/", ".").strip(".")


def container_definitions(
    containers: frozenset[str],
    methods: frozenset[str],
    *,
    name_field: str = "name",
    body_field: str = "body",
) -> Callable[[Any, bytes, str, LanguageProfile], Iterable[TSDefinition]]:
    """A `definitions()` for languages whose functions live inside class/module containers.

    It recurses into each container, tagging the methods it finds with the container name
    as their owner, and also yields top-level functions of a matching type.
    """

    def definitions(
        root: Any, source: bytes, relative: str, profile: LanguageProfile
    ) -> Iterable[TSDefinition]:
        yield from _walk(root, source, "")

    def _walk(node: Any, source: bytes, owner: str) -> Iterable[TSDefinition]:
        if node.type in containers:
            name = text(node.child_by_field_name(name_field), source) or owner
            body = node.child_by_field_name(body_field) or node.child_by_field_name(
                "declaration_list"
            )
            for child in named(body if body is not None else node):
                yield from _walk(child, source, name)
            return
        if node.type in methods:
            name = text(node.child_by_field_name(name_field), source)
            body = node.child_by_field_name(body_field)
            if name and body is not None:
                yield TSDefinition(name=name, node=node, body=body, owner=owner)
            return
        for child in named(node):
            yield from _walk(child, source, owner)

    return definitions
