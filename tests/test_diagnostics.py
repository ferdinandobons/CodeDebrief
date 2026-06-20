from __future__ import annotations

from pathlib import Path

from logicchart.analysis.project import ProjectAnalyzer
from logicchart.query import query_model

_FIXTURE = """
from enum import Enum


class Status(Enum):
    OPEN = "open"
    CLOSED = "closed"
    DELETED = "deleted"


def handle(status):
    match status:
        case Status.OPEN:
            return "open"
        case Status.CLOSED:
            return "closed"
"""


def test_project_analysis_does_not_emit_review_findings(tmp_path: Path) -> None:
    (tmp_path / "service.py").write_text(_FIXTURE, encoding="utf-8")

    model = ProjectAnalyzer(tmp_path).analyze(full=True).model

    assert model.findings == []
    assert "finding_rules" not in model.metadata
    assert "finding_count" not in model.metadata


def test_query_ignores_legacy_diagnostic_prose(tmp_path: Path) -> None:
    (tmp_path / "service.py").write_text(_FIXTURE, encoding="utf-8")
    model = ProjectAnalyzer(tmp_path).analyze(full=True).model

    matches = query_model(model, "suggested next actions", limit=10)

    assert matches == []
