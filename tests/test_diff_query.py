"""Stage 6: model diffing (CI gate) and the richer query surface."""

from __future__ import annotations

from pathlib import Path

from logicchart.analysis.project import ProjectAnalyzer
from logicchart.cli import main
from logicchart.diff import diff_models, render_sarif
from logicchart.model import ProjectModel
from logicchart.query import (
    explain_finding,
    find_decisions,
    model_summary,
    where_is_state_handled,
)
from logicchart.util import write_json

_CHAIN = (
    "def a(s):\n"
    "    if s.status == X.A:\n        return 1\n"
    "    elif s.status == X.B:\n        return 2\n"
)


def _model(tmp_path: Path, body: str) -> ProjectModel:
    (tmp_path / "m.py").write_text(body, encoding="utf-8")
    return ProjectAnalyzer(tmp_path).analyze(full=True).model


def test_diff_reports_introduced_and_resolved(tmp_path: Path) -> None:
    base = _model(tmp_path, "def a(x):\n    return x\n")
    head = _model(tmp_path, "def a(x):\n    return x\n    dead()\n")

    forward = diff_models(base, head)
    assert any(f.kind == "dead_code" for f in forward.introduced)
    assert forward.has_regressions

    reverse = diff_models(head, base)
    assert any(f.kind == "dead_code" for f in reverse.resolved)
    assert not reverse.has_regressions


def test_render_sarif_is_well_formed(tmp_path: Path) -> None:
    base = _model(tmp_path, "def a(x):\n    return x\n")
    head = _model(tmp_path, "def a(x):\n    return x\n    dead()\n")
    sarif = render_sarif(diff_models(base, head))

    assert sarif["version"] == "2.1.0"
    results = sarif["runs"][0]["results"]  # type: ignore[index]
    assert results and results[0]["ruleId"] == "dead_code"


def test_diff_cli_fails_on_introduced(tmp_path: Path) -> None:
    base = _model(tmp_path, "def a(x):\n    return x\n")
    head = _model(tmp_path, "def a(x):\n    return x\n    dead()\n")
    base_path = tmp_path / "base.json"
    head_path = tmp_path / "head.json"
    write_json(base_path, base.to_dict())
    write_json(head_path, head.to_dict())

    assert main(["diff", str(base_path), str(head_path), "--fail-on-introduced"]) == 1
    assert main(["diff", str(base_path), str(base_path), "--fail-on-introduced"]) == 0


def test_model_summary_counts_by_kind(tmp_path: Path) -> None:
    summary = model_summary(_model(tmp_path, _CHAIN))
    assert summary["flows"] >= 1
    assert "missing_branch" in summary["findings"]["by_kind"]


def test_explain_finding_returns_chain(tmp_path: Path) -> None:
    model = _model(tmp_path, _CHAIN)
    finding = next(f for f in model.findings if f.kind == "missing_branch")
    chain = explain_finding(model, finding.id)
    assert chain is not None
    assert chain["kind"] == "missing_branch"
    assert chain["decision"] is not None
    assert explain_finding(model, "does-not-exist") is None


def test_where_is_state_handled(tmp_path: Path) -> None:
    model = _model(tmp_path, "def a(s):\n    if s.status == Status.ACTIVE:\n        return 1\n")
    rows = where_is_state_handled(model, "Status")
    assert rows and rows[0]["flow"] == "a"


def test_find_decisions_missing_fallback(tmp_path: Path) -> None:
    gaps = find_decisions(_model(tmp_path, _CHAIN), missing_fallback=True)
    assert gaps and all(decision["has_gap"] for decision in gaps)
