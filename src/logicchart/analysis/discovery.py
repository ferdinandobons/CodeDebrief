from __future__ import annotations

from pathlib import Path

from logicchart.config import LogicChartConfig
from logicchart.util import relpath

SUPPORTED_SUFFIXES = {".py", ".ts", ".tsx"}


def discover_source_files(root: Path, config: LogicChartConfig) -> list[Path]:
    files: set[Path] = set()
    for source_root in config.source_roots:
        base = (root / source_root).resolve()
        if not base.exists():
            continue
        candidates = [base] if base.is_file() else base.rglob("*")
        for candidate in candidates:
            if not candidate.is_file() or candidate.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            relative = relpath(candidate, root)
            if not config.is_excluded(relative):
                files.add(candidate)
    return sorted(files, key=lambda item: relpath(item, root))


def language_for(path: Path) -> str:
    if path.suffix == ".py":
        return "python"
    if path.suffix in {".ts", ".tsx"}:
        return "typescript"
    raise ValueError(f"Unsupported source file: {path}")
