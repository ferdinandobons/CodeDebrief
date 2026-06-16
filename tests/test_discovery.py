"""Discovery edge cases: a symlink whose target resolves outside the root is skipped,
not allowed to abort the whole walk (relpath/relative_to would otherwise raise)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from logicchart.analysis.discovery import discover_source_files
from logicchart.config import LogicChartConfig


@pytest.mark.skipif(
    sys.platform == "win32", reason="symlink creation often needs elevation on Windows"
)
def test_symlink_pointing_outside_root_is_skipped(tmp_path: Path) -> None:
    project = tmp_path / "project"
    outside = tmp_path / "outside"
    project.mkdir()
    outside.mkdir()

    # A real in-tree file plus a symlink whose resolved target is OUTSIDE the project.
    (project / "real.py").write_text("def handler(x):\n    return x\n", encoding="utf-8")
    (outside / "external.py").write_text("def external():\n    return 1\n", encoding="utf-8")
    link = project / "linked.py"
    try:
        link.symlink_to(outside / "external.py")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported in this environment")

    files = discover_source_files(project, LogicChartConfig())
    names = {path.name for path in files}

    # The in-tree file is found; the out-of-tree symlink is skipped without crashing.
    assert "real.py" in names
    assert "external.py" not in names
    # Every returned path has a valid project-relative path (no relpath would raise).
    for path in files:
        assert path.resolve().is_relative_to(project.resolve())
