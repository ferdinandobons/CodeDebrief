"""Worked-corpus golden master for examples/shop (Stage 5 positive fixture)."""

from __future__ import annotations

import shutil
from pathlib import Path

from logicchart.analysis.project import ProjectAnalyzer
from logicchart.model import ProjectModel

SHOP = Path(__file__).resolve().parent.parent / "examples" / "shop"


def _analyze_shop_copy(tmp_path: Path) -> ProjectModel:
    for item in ("backend", "frontend", "tests", "logicchart.toml"):
        src = SHOP / item
        dst = tmp_path / item
        if src.is_dir():
            shutil.copytree(src, dst)
        elif src.is_file():
            shutil.copy2(src, dst)
    return ProjectAnalyzer(tmp_path).analyze(full=True).model


def _by_flow(model: ProjectModel) -> dict[str, set[str]]:
    names = {flow.id: flow.name for flow in model.flows}
    grouped: dict[str, set[str]] = {}
    for finding in model.findings:
        grouped.setdefault(names.get(finding.flow_id, ""), set()).add(finding.kind)
    return grouped


def test_shop_planted_defects_fire(tmp_path: Path) -> None:
    by_flow = _by_flow(_analyze_shop_copy(tmp_path))
    assert "dead_code" in by_flow.get("load_profile", set())
    assert "no_op_branch" in by_flow.get("summarize", set())
    assert "broad_except_swallow" in by_flow.get("charge", set())
    assert "broad_except_swallow" in by_flow.get("processCheckout", set())
    assert "enum_exhaustiveness" in by_flow.get("change_email", set())
    assert "enum_exhaustiveness" in by_flow.get("handle_result", set())
    assert "enum_exhaustiveness" in by_flow.get("transition", set())
    assert "logging_asymmetry" in by_flow.get("capture_payment", set())
    assert "missing_branch" in by_flow.get("OrdersPage", set())


def test_shop_controls_stay_silent(tmp_path: Path) -> None:
    by_flow = _by_flow(_analyze_shop_copy(tmp_path))
    for control in (
        "authenticate",
        "GET",
        "AccountPage",
        "middleware",
        "reset_password",
        "get_profile",
        "cancel",
        "request_refund",
    ):
        assert control not in by_flow, (
            f"{control} should be a silent control, got {by_flow[control]}"
        )
