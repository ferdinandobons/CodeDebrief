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


def test_same_language_cross_flow_still_fires(tmp_path: Path) -> None:
    (tmp_path / "service.py").write_text(
        """
def handle_full(account):
    if account.status == Status.ACTIVE:
        return ok()
    if account.status == Status.SUSPENDED:
        return blocked()
    if account.status == Status.DELETED:
        return gone()

def handle_partial(account):
    if account.status == Status.ACTIVE:
        return ok()
    if account.status == Status.SUSPENDED:
        return blocked()
""",
        encoding="utf-8",
    )

    model = ProjectAnalyzer(tmp_path).analyze(full=True).model
    partial = next(f for f in model.flows if f.name == "handle_partial")
    on_partial = [
        f
        for f in model.findings
        if f.kind == "inconsistent_case_handling" and f.flow_id == partial.id
    ]

    # Same-language siblings on the same domain are still compared: handle_partial
    # never mentions Status.DELETED that its sibling handles, so it is flagged for it.
    assert any("DELETED" in f.message for f in on_partial)
