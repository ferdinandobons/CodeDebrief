"""The finding-kind vocabulary and category axis are single-sourced and complete."""

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
    "    return 0\n    dead()\n"  # also yields a single-flow dead_code finding
)


def test_every_finding_kind_is_an_enum_member_with_a_category(tmp_path: Path) -> None:
    (tmp_path / "mod.py").write_text(_FIXTURE, encoding="utf-8")
    model = ProjectAnalyzer(tmp_path).analyze(full=True).model

    assert model.findings, "fixture should produce findings"
    valid_kinds = {kind.value for kind in FindingKind}
    for finding in model.findings:
        assert finding.kind in valid_kinds, finding.kind
        assert finding.metadata.get("category") in {"single_flow", "cross_flow"}

    kinds = {finding.kind for finding in model.findings}
    assert FindingKind.ENUM_EXHAUSTIVENESS.value in kinds  # cross-flow
    assert FindingKind.DEAD_CODE.value in kinds  # single-flow
