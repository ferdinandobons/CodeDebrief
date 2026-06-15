"""Consumption-surface fixes from the whole-project review."""

from __future__ import annotations

from pathlib import Path

from logicchart.analysis.project import ProjectAnalyzer
from logicchart.diff import ModelDiff, render_sarif
from logicchart.model import Evidence, Finding, ProjectModel, Severity, SourceLocation
from logicchart.query import impact_model, where_is_state_handled


def test_normalize_path_preserves_dot_prefixed_paths() -> None:
    model = ProjectModel(schema_version="1.1", generated_at="x", root=".")
    result = impact_model(model, [".github/workflows/ci.yml", "./src/app.py", "../x/y.py"])
    assert ".github/workflows/ci.yml" in result.changed_files
    assert "src/app.py" in result.changed_files  # only the leading "./" is stripped
    assert "../x/y.py" in result.changed_files


def test_where_state_handled_empty_domain_is_not_a_wildcard(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text(
        "def auth(user):\n    if user.role == 'admin':\n        return 1\n    return 0\n",
        encoding="utf-8",
    )
    model = ProjectAnalyzer(tmp_path).analyze(full=True).model
    assert where_is_state_handled(model, "") == []
    assert where_is_state_handled(model, "role")  # a real domain still matches


def test_sarif_start_line_is_clamped_to_one() -> None:
    finding = Finding(
        id="x",
        kind="dead_code",
        severity=Severity.WARNING,
        message="m",
        evidence=Evidence.INFERRED,
        flow_id="f",
        location=SourceLocation("a.py", 0, 0),
    )
    sarif = render_sarif(ModelDiff(introduced=[finding], resolved=[], persisting=[]))
    region = sarif["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["region"]
    assert region["startLine"] == 1
