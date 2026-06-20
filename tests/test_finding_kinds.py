"""Legacy finding types remain loadable but are no longer emitted by analysis."""

from __future__ import annotations

from pathlib import Path

from logicchart.analysis.project import ProjectAnalyzer
from logicchart.model import FindingKind

_FIXTURE = (
    "from enum import Enum\n\n\n"
    "class Status(Enum):\n"
    "    A = 'a'\n"
    "    B = 'b'\n"
    "    C = 'c'\n\n\n"
    "def handle(status):\n"
    "    match status:\n"
    "        case Status.A:\n"
    "            return 1\n"
    "        case Status.B:\n"
    "            return 2\n"
    "    return 0\n"
)


def test_finding_kind_enum_is_legacy_compatible_but_not_emitted(tmp_path: Path) -> None:
    assert FindingKind.MISSING_BRANCH.value == "missing_branch"

    (tmp_path / "mod.py").write_text(_FIXTURE, encoding="utf-8")
    model = ProjectAnalyzer(tmp_path).analyze(full=True).model

    assert model.findings == []
