"""Golden-master precision SLA, measured on examples/demo.

Stage 0 of the build order pins the published-artifact noise budget: the
cross-language false positive must be gone, while the one true-positive review
signal (the TS switch without a default) survives. A second test proves the
language-scoping guard did not gut same-language cross-flow detection.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from logicchart.analysis.project import ProjectAnalyzer
from logicchart.model import Evidence

DEMO = Path(__file__).resolve().parent.parent / "examples" / "demo"


def _analyze_copy(source: Path, tmp_path: Path) -> ProjectAnalyzer:
    """Analyze a copy so the committed fixture's cache/output stay pristine."""
    for item in ("backend", "frontend", "logicchart.toml"):
        src = source / item
        dst = tmp_path / item
        if src.is_dir():
            shutil.copytree(src, dst)
        elif src.is_file():
            shutil.copy2(src, dst)
    return ProjectAnalyzer(tmp_path)


def test_demo_precision_sla(tmp_path: Path) -> None:
    model = _analyze_copy(DEMO, tmp_path).analyze(full=True).model
    findings = model.findings

    # The cross-language false positive must not survive language scoping.
    assert not any(f.kind == "inconsistent_case_handling" for f in findings)

    # The one true-positive review signal survives: the TS switch with no default.
    assert [f.kind for f in findings].count("missing_branch") == 1

    # Precision SLA: at most one POTENTIAL_GAP across the whole demo.
    gaps = [f for f in findings if f.evidence is Evidence.POTENTIAL_GAP]
    assert len(gaps) <= 1


def test_quorum_cross_flow_flags_the_minority_omission(tmp_path: Path) -> None:
    # Three sibling flows handle Status.DELETED; the fourth omits it. A strict
    # majority handling a value it lacks makes the minority flow a review candidate.
    full = """
def handle_{n}(account):
    if account.status == Status.ACTIVE:
        return ok()
    if account.status == Status.SUSPENDED:
        return blocked()
    if account.status == Status.DELETED:
        return gone()
"""
    body = full.format(n="a") + full.format(n="b") + full.format(n="c")
    body += """
def handle_partial(account):
    if account.status == Status.ACTIVE:
        return ok()
    if account.status == Status.SUSPENDED:
        return blocked()
"""
    (tmp_path / "service.py").write_text(body, encoding="utf-8")

    model = ProjectAnalyzer(tmp_path).analyze(full=True).model
    partial = next(f for f in model.flows if f.name == "handle_partial")
    flagged = [
        f
        for f in model.findings
        if f.kind == "inconsistent_case_handling" and f.flow_id == partial.id
    ]

    assert any("DELETED" in f.message for f in flagged)
    # The mutable detail lives in metadata; the id is structural and stable.
    finding = next(f for f in flagged if "DELETED" in f.message)
    assert finding.metadata["value_namespace"] == "Status"
    assert "Status.DELETED" in finding.metadata["missing"]
    assert finding.metadata["quorum"]["siblings"] == 4
    # The three complete siblings are not flagged.
    assert not any(
        f.kind == "inconsistent_case_handling" and f.flow_id != partial.id for f in model.findings
    )
