"""Stage 6: the richer query surface."""

from __future__ import annotations

from pathlib import Path

from logicchart.analysis.project import ProjectAnalyzer
from logicchart.model import ProjectModel
from logicchart.query import (
    explain_finding,
    find_decisions,
    model_summary,
    where_is_state_handled,
)

_CHAIN = (
    "def a(s):\n"
    "    if s.status == X.A:\n        return 1\n"
    "    elif s.status == X.B:\n        return 2\n"
)


def _model(tmp_path: Path, body: str) -> ProjectModel:
    (tmp_path / "m.py").write_text(body, encoding="utf-8")
    return ProjectAnalyzer(tmp_path).analyze(full=True).model


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


def test_find_decisions_subject_is_equality_not_substring(tmp_path: Path) -> None:
    """Subject matching is exact equality, consistent with where_is_state_handled's
    exact domain/value matching (a substring 'status' must not match 'order_status')."""
    model = _model(
        tmp_path,
        "def a(s):\n    if s.status == X.A:\n        return 1\n    return 0\n",
    )
    subject = next(
        node.metadata.get("subject")
        for flow in model.flows
        for node in flow.nodes
        if node.metadata.get("subject")
    )
    assert subject  # the decision branches on some subject
    assert find_decisions(model, subject=subject), "exact subject must match"
    # A strict substring of that subject must NOT match.
    assert find_decisions(model, subject=subject[:-1]) == []
