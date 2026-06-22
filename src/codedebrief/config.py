from __future__ import annotations

import fnmatch
import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - Python 3.10
    import tomli as tomllib

CONFIG_FILENAME = "codedebrief.toml"
DEFAULT_OUTPUT_DIR = "codedebrief-out"

DEFAULT_EXCLUDES = [
    "**/.DS_Store",
    "**/.coverage*",
    "**/__generated__/**",
    "**/*.class",
    "**/*.dll",
    "**/*.dylib",
    "**/*.min.js",
    "**/*.o",
    "**/*.pyc",
    "**/*.pyo",
    "**/*.so",
    "**/*.gen.*",
    "**/*.generated.*",
    "**/*.pb.*",
    "**/*.d.ts",
]

DEFAULT_EXCLUDE_DIRS = [
    ".angular",
    ".aws-sam",
    ".bundle",
    ".cache",
    ".expo",
    ".git",
    ".gradle",
    ".hg",
    ".codedebrief",
    ".dart_tool",
    ".devenv",
    ".direnv",
    ".eggs",
    ".mypy_cache",
    ".next",
    ".nox",
    ".nuxt",
    ".nx",
    ".parcel-cache",
    ".pnpm-store",
    ".pytest_cache",
    ".pyre",
    ".pytype",
    ".ruff_cache",
    ".sass-cache",
    ".serverless",
    ".storybook-static",
    ".svn",
    ".svelte-kit",
    ".terraform",
    ".temp",
    ".tox",
    ".turbo",
    ".tmp",
    ".venv",
    ".venv-*",
    ".vite",
    ".vs",
    ".vscode",
    ".yarn",
    "__generated__",
    "__pycache__",
    ".build",
    "bower_components",
    "build",
    "cdk.out",
    "coverage",
    "DerivedData",
    "dist",
    "env",
    "graphify-out",
    "htmlcov",
    "jspm_packages",
    "codedebrief-out",
    "logs",
    "node_modules",
    "obj",
    "out",
    "Pods",
    "target",
    "temp",
    "tmp",
    "vendor",
    "venv",
    "*.egg-info",
]

BUILTIN_PROFILES = ("self", "project")


@dataclass(slots=True)
class CodeDebriefConfig:
    source_roots: list[str] = field(default_factory=lambda: ["."])
    exclude: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDES))
    exclude_dirs: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDE_DIRS))
    include_public_functions: bool = True
    max_call_depth: int = 4
    output_dir: str = DEFAULT_OUTPUT_DIR
    self_exclude: bool = True
    entrypoint_include: list[str] = field(default_factory=list)
    entrypoint_exclude: list[str] = field(default_factory=list)
    # Named macro-parts of the codebase, e.g. {"backend": ["backend/**"], "edge": ["edge/**"]}.
    scopes: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def load(cls, root: Path, profile: str | None = None) -> CodeDebriefConfig:
        config = cls()
        config_path = find_config_path(root)
        if config_path is not None:
            payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
            section = payload.get("codedebrief", {})
            if not isinstance(section, dict):
                raise ValueError(f"{config_path} [codedebrief] must be a table")
            config.source_roots = _string_list(
                section.get("source_roots", config.source_roots),
                "codedebrief.source_roots",
                non_empty=True,
            )
            config.exclude.extend(_string_list(section.get("exclude", []), "codedebrief.exclude"))
            config.exclude_dirs.extend(
                _string_list(section.get("exclude_dirs", []), "codedebrief.exclude_dirs")
            )
            config.include_public_functions = _bool_value(
                section.get("include_public_functions", config.include_public_functions),
                "codedebrief.include_public_functions",
            )
            config.max_call_depth = _int_value(
                section.get("max_call_depth", config.max_call_depth),
                "codedebrief.max_call_depth",
                minimum=0,
            )
            config.output_dir = _string_value(
                section.get("output_dir", config.output_dir),
                "codedebrief.output_dir",
                non_empty=True,
            )
            config.self_exclude = _bool_value(
                section.get("self_exclude", config.self_exclude),
                "codedebrief.self_exclude",
            )
            entrypoints = _table(section.get("entrypoints", {}), "codedebrief.entrypoints")
            config.entrypoint_include = _string_list(
                entrypoints.get("include", []),
                "codedebrief.entrypoints.include",
            )
            config.entrypoint_exclude = _string_list(
                entrypoints.get("exclude", []),
                "codedebrief.entrypoints.exclude",
            )
            config.scopes = _scope_table(section.get("scopes", {}), "codedebrief.scopes")

        if profile is not None:
            config = _apply_profile(config, profile)

        ignore_path = root / ".codedebriefignore"
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

    def is_excluded_dir(self, relative_path: str) -> bool:
        normalized = relative_path.replace("\\", "/").strip("/")
        if not normalized:
            return False
        name = normalized.rsplit("/", 1)[-1]
        return any(
            _directory_name_or_path_matches(normalized, name, pattern)
            for pattern in self.exclude_dirs
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
        parts = [part for part in normalized.split("/") if part and part not in {".", ".."}]
        return [parts[0]] if len(parts) > 1 else []


def _apply_profile(config: CodeDebriefConfig, profile: str) -> CodeDebriefConfig:
    """Apply one built-in analysis profile on top of the project config.

    Profiles keep the normal config/ignore semantics, but give agents explicit choices:
    self artifacts for CodeDebrief internals and project artifacts for the whole checkout.
    Each non-default profile writes to its own output dir so focused dogfood models do not
    overwrite one another.
    """
    if profile not in BUILTIN_PROFILES:
        known = ", ".join(BUILTIN_PROFILES)
        raise ValueError(f"unknown CodeDebrief profile {profile!r}; known profiles: {known}")
    if profile == "self":
        config.source_roots = ["src/codedebrief"]
        config.self_exclude = False
        config.output_dir = "codedebrief-out/self"
    elif profile == "project":
        config.source_roots = ["src", "tests"]
        config.self_exclude = False
        config.output_dir = "codedebrief-out/project"
    return config


def legacy_config_path(root: Path) -> Path:
    return root / CONFIG_FILENAME


def default_config_path(root: Path) -> Path:
    return root / DEFAULT_OUTPUT_DIR / CONFIG_FILENAME


def config_path_candidates(root: Path) -> tuple[Path, Path]:
    return legacy_config_path(root), default_config_path(root)


def find_config_path(root: Path) -> Path | None:
    for candidate in config_path_candidates(root):
        if candidate.exists():
            return candidate
    return None


def _table(value: object, field_name: str) -> dict[object, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a table")
    return value


def _string_value(value: object, field_name: str, *, non_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    if non_empty and not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    return value


def _string_list(
    value: object,
    field_name: str,
    *,
    non_empty: bool = False,
) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list of strings")
    if non_empty and not value:
        raise ValueError(f"{field_name} must not be empty")
    result = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise ValueError(f"{field_name}[{index}] must be a string")
        result.append(item)
    return result


def _bool_value(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a boolean")
    return value


def _int_value(value: object, field_name: str, *, minimum: int | None = None) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{field_name} must be >= {minimum}")
    return value


def _scope_table(value: object, field_name: str) -> dict[str, list[str]]:
    table = _table(value, field_name)
    return {
        _string_value(name, f"{field_name} key", non_empty=True): _string_list(
            patterns,
            f"{field_name}.{name}",
        )
        for name, patterns in table.items()
    }


def _normalize_pattern(pattern: str) -> str:
    normalized = pattern.replace("\\", "/").lstrip("/")
    if normalized.endswith("/"):
        return normalized + "**"
    return normalized


def _directory_name_or_path_matches(path: str, name: str, pattern: str) -> bool:
    normalized = pattern.replace("\\", "/").strip("/")
    if not normalized:
        return False
    if "/" not in normalized:
        return any(fnmatch.fnmatch(part, normalized) for part in path.split("/") if part)
    return fnmatch.fnmatch(path, normalized) or _directory_pattern_matches(
        path, normalized.rstrip("/") + "/**"
    )


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
