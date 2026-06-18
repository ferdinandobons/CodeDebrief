"""The language registry: the single place that maps a language to its file suffixes
and an analyzer factory.

Adding a language is one `LanguageSpec` entry here plus its analyzer (a dedicated class
for Python, or a `LanguageProfile` for the profile-driven tree-sitter engine). Discovery
and the project loop dispatch through this registry, so neither needs to change.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from logicchart.analysis.python import PythonAnalyzer
from logicchart.analysis.typescript import TypeScriptAnalyzer
from logicchart.config import LogicChartConfig
from logicchart.model import FileAnalysis


class LanguageAnalyzer(Protocol):
    """Every language front-end turns one source file into a `FileAnalysis`."""

    def analyze(self, path: Path) -> FileAnalysis: ...


AnalyzerFactory = Callable[[Path, LogicChartConfig], LanguageAnalyzer]


@dataclass(frozen=True, slots=True)
class LanguageSpec:
    id: str
    suffixes: tuple[str, ...]
    factory: AnalyzerFactory


def _make_go(root: Path, config: LogicChartConfig) -> LanguageAnalyzer:
    # Lazy import so the Go grammar (.so) loads only when a .go file is analyzed.
    from logicchart.analysis.languages.go import build_analyzer

    return build_analyzer(root, config)


def _make_java(root: Path, config: LogicChartConfig) -> LanguageAnalyzer:
    from logicchart.analysis.languages.java import build_analyzer

    return build_analyzer(root, config)


def _make_csharp(root: Path, config: LogicChartConfig) -> LanguageAnalyzer:
    from logicchart.analysis.languages.csharp import build_analyzer

    return build_analyzer(root, config)


def _make_php(root: Path, config: LogicChartConfig) -> LanguageAnalyzer:
    from logicchart.analysis.languages.php import build_analyzer

    return build_analyzer(root, config)


def _make_c(root: Path, config: LogicChartConfig) -> LanguageAnalyzer:
    from logicchart.analysis.languages.c import build_analyzer

    return build_analyzer(root, config)


def _make_cpp(root: Path, config: LogicChartConfig) -> LanguageAnalyzer:
    from logicchart.analysis.languages.cpp import build_analyzer

    return build_analyzer(root, config)


def _make_rust(root: Path, config: LogicChartConfig) -> LanguageAnalyzer:
    from logicchart.analysis.languages.rust import build_analyzer

    return build_analyzer(root, config)


def _make_ruby(root: Path, config: LogicChartConfig) -> LanguageAnalyzer:
    from logicchart.analysis.languages.ruby import build_analyzer

    return build_analyzer(root, config)


# The order is the dispatch precedence when two specs claim the same suffix (none do today).
LANGUAGES: tuple[LanguageSpec, ...] = (
    LanguageSpec("python", (".py",), PythonAnalyzer),
    # JavaScript reuses the TypeScript analyzer (grammar superset) to keep the
    # Next.js / React entry-point detection; the IR labels it "javascript".
    LanguageSpec("typescript", (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"), TypeScriptAnalyzer),
    LanguageSpec("go", (".go",), _make_go),
    LanguageSpec("java", (".java",), _make_java),
    LanguageSpec("csharp", (".cs",), _make_csharp),
    LanguageSpec("php", (".php",), _make_php),
    LanguageSpec("c", (".c", ".h"), _make_c),
    LanguageSpec("cpp", (".cc", ".cpp", ".cxx", ".hh", ".hpp", ".hxx", ".ipp", ".tpp"), _make_cpp),
    LanguageSpec("rust", (".rs",), _make_rust),
    LanguageSpec("ruby", (".rb",), _make_ruby),
)

_BY_SUFFIX: dict[str, LanguageSpec] = {
    suffix: spec for spec in LANGUAGES for suffix in spec.suffixes
}
_BY_ID: dict[str, LanguageSpec] = {spec.id: spec for spec in LANGUAGES}

_FEATURES: tuple[str, ...] = (
    "functions_methods",
    "entrypoint_heuristics",
    "decisions",
    "switch_match",
    "loops",
    "calls",
    "returns_throws",
    "try_catch",
    "test_detection",
    "enum_harvest",
    "qualified_call_links",
)

_BASE_FEATURES: dict[str, str] = {
    "functions_methods": "supported",
    "entrypoint_heuristics": "supported",
    "decisions": "supported",
    "switch_match": "supported",
    "loops": "supported",
    "calls": "supported",
    "returns_throws": "supported",
    "try_catch": "supported",
    "test_detection": "supported",
    "enum_harvest": "not_supported",
    "qualified_call_links": "partial",
}

_LANGUAGE_OVERRIDES: dict[str, dict[str, str]] = {
    "javascript": {"enum_harvest": "not_supported"},
    "typescript": {"enum_harvest": "supported"},
    "python": {"enum_harvest": "supported", "qualified_call_links": "supported"},
    "c": {
        "entrypoint_heuristics": "partial",
        "try_catch": "not_supported",
        "qualified_call_links": "not_supported",
    },
    "cpp": {"entrypoint_heuristics": "partial", "qualified_call_links": "not_supported"},
    "csharp": {"entrypoint_heuristics": "partial", "qualified_call_links": "not_supported"},
    "go": {
        "entrypoint_heuristics": "partial",
        "try_catch": "not_supported",
        "qualified_call_links": "not_supported",
    },
    "java": {"entrypoint_heuristics": "partial", "qualified_call_links": "not_supported"},
    "php": {"entrypoint_heuristics": "partial", "qualified_call_links": "not_supported"},
    "ruby": {
        "entrypoint_heuristics": "partial",
        "try_catch": "not_supported",
        "qualified_call_links": "not_supported",
    },
    "rust": {
        "entrypoint_heuristics": "partial",
        "returns_throws": "partial",
        "try_catch": "not_supported",
        "qualified_call_links": "not_supported",
    },
}

_FRONTENDS: dict[str, str] = {
    "javascript": "typescript_tree_sitter",
    "typescript": "typescript_tree_sitter",
    "python": "python_ast",
    "c": "tree_sitter_profile",
    "cpp": "tree_sitter_profile",
    "csharp": "tree_sitter_profile",
    "go": "tree_sitter_profile",
    "java": "tree_sitter_profile",
    "php": "tree_sitter_profile",
    "ruby": "tree_sitter_profile",
    "rust": "tree_sitter_profile",
}

_STATUSES: dict[str, str] = {
    language: "supported"
    for language in (
        "javascript",
        "typescript",
        "python",
        "c",
        "cpp",
        "csharp",
        "go",
        "java",
        "php",
        "ruby",
        "rust",
    )
}


def supported_suffixes() -> frozenset[str]:
    return frozenset(_BY_SUFFIX)


def supported_language_ids() -> tuple[str, ...]:
    ids = []
    for spec in LANGUAGES:
        ids.append(spec.id)
        # JavaScript files are parsed by the TypeScript grammar, but the IR labels
        # plain JS files as "javascript" so consumers can distinguish them.
        if spec.id == "typescript":
            ids.append("javascript")
    return tuple(ids)


def language_capability_matrix() -> dict[str, dict[str, object]]:
    """Return a coarse, deterministic analyzer support matrix for agents and UI."""
    matrix: dict[str, dict[str, object]] = {}
    for language in supported_language_ids():
        features = dict(_BASE_FEATURES)
        features.update(_LANGUAGE_OVERRIDES.get(language, {}))
        matrix[language] = {
            "status": _STATUSES[language],
            "frontend": _FRONTENDS[language],
            "suffixes": list(_suffixes_for_language(language)),
            "features": {key: features[key] for key in _FEATURES},
        }
    return matrix


def spec_for_path(path: Path) -> LanguageSpec | None:
    return _BY_SUFFIX.get(path.suffix.lower())


def language_for(path: Path) -> str:
    spec = spec_for_path(path)
    if spec is None:
        raise ValueError(f"Unsupported source file: {path}")
    return spec.id


def _suffixes_for_language(language: str) -> tuple[str, ...]:
    if language == "javascript":
        return (".js", ".jsx", ".mjs", ".cjs")
    if language == "typescript":
        return (".ts", ".tsx")
    return spec_for_language(language).suffixes


def spec_for_language(language: str) -> LanguageSpec:
    spec = _BY_ID.get(language)
    if spec is None:
        raise ValueError(f"Unknown language: {language}")
    return spec
