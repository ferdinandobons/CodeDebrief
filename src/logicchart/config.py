from __future__ import annotations

import fnmatch
import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - Python 3.10
    import tomli as tomllib

DEFAULT_EXCLUDES = [
    ".git/**",
    ".venv/**",
    ".logicchart/**",
    "logicchart-out/**",
    "node_modules/**",
    ".next/**",
    "dist/**",
    "build/**",
    "coverage/**",
    "**/__pycache__/**",
    "**/*.min.js",
    "**/*.generated.*",
    "**/*.d.ts",
]


@dataclass(slots=True)
class LogicChartConfig:
    source_roots: list[str] = field(default_factory=lambda: ["."])
    exclude: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDES))
    include_public_functions: bool = True
    max_call_depth: int = 4
    output_dir: str = "logicchart-out"
    self_exclude: bool = True
    gated_detectors: bool = False
    entrypoint_include: list[str] = field(default_factory=list)
    entrypoint_exclude: list[str] = field(default_factory=list)
    # Named macro-parts of the codebase, e.g. {"backend": ["backend/**"], "infra": ["**/*.tf"]}.
    scopes: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def load(cls, root: Path) -> LogicChartConfig:
        config = cls()
        config_path = root / "logicchart.toml"
        if config_path.exists():
            payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
            section = payload.get("logicchart", {})
            config.source_roots = list(section.get("source_roots", config.source_roots))
            config.exclude.extend(section.get("exclude", []))
            config.include_public_functions = bool(
                section.get("include_public_functions", config.include_public_functions)
            )
            config.max_call_depth = int(section.get("max_call_depth", config.max_call_depth))
            config.output_dir = str(section.get("output_dir", config.output_dir))
            config.self_exclude = bool(section.get("self_exclude", config.self_exclude))
            config.gated_detectors = bool(section.get("gated_detectors", config.gated_detectors))
            entrypoints = section.get("entrypoints", {})
            config.entrypoint_include = list(entrypoints.get("include", []))
            config.entrypoint_exclude = list(entrypoints.get("exclude", []))
            config.scopes = {
                str(name): [str(pattern) for pattern in patterns]
                for name, patterns in section.get("scopes", {}).items()
            }

        ignore_path = root / ".logicchartignore"
        if ignore_path.exists():
            for raw_line in ignore_path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if line and not line.startswith("#"):
                    config.exclude.append(_normalize_pattern(line))
        return config

    def is_excluded(self, relative_path: str) -> bool:
        normalized = relative_path.replace("\\", "/")
        return any(
            fnmatch.fnmatch(normalized, pattern)
            or fnmatch.fnmatch("/" + normalized, pattern)
            or _directory_pattern_matches(normalized, pattern)
            for pattern in self.exclude
        )

    def entrypoint_override(self, symbol: str) -> bool | None:
        if any(fnmatch.fnmatch(symbol, item) for item in self.entrypoint_exclude):
            return False
        if any(fnmatch.fnmatch(symbol, item) for item in self.entrypoint_include):
            return True
        return None

    def scopes_for(self, relative_path: str) -> list[str]:
        """The macro-part(s) a file belongs to.

        With declared scopes, returns every named scope whose globs match. Otherwise the
        top-level directory is the inferred scope, splitting a codebase into
        backend/frontend/infra-style parts out of the box.
        """
        normalized = relative_path.replace("\\", "/")
        if self.scopes:
            return sorted(
                name
                for name, patterns in self.scopes.items()
                if any(_scope_match(normalized, pattern) for pattern in patterns)
            )
        head, sep, _ = normalized.partition("/")
        return [head] if sep else []


def _normalize_pattern(pattern: str) -> str:
    normalized = pattern.replace("\\", "/").lstrip("/")
    if normalized.endswith("/"):
        return normalized + "**"
    return normalized


def _directory_pattern_matches(path: str, pattern: str) -> bool:
    if pattern.endswith("/**"):
        directory = pattern[:-3].rstrip("/")
        return path == directory or path.startswith(directory + "/")
    return False


def _scope_match(path: str, pattern: str) -> bool:
    normalized = pattern.replace("\\", "/")
    return (
        fnmatch.fnmatch(path, normalized)
        or fnmatch.fnmatch(path, normalized.rstrip("/") + "/**")
        or _directory_pattern_matches(path, normalized)
    )
