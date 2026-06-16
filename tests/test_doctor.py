from __future__ import annotations

from pathlib import Path

from logicchart.doctor import doctor_report, render_doctor


def test_doctor_reports_missing_lazy_parser_dependency(tmp_path: Path, monkeypatch) -> None:
    import logicchart.doctor as doctor_module

    real_find_spec = doctor_module.importlib.util.find_spec

    def fake_find_spec(name: str):
        if name == "tree_sitter_go":
            return None
        return real_find_spec(name)

    monkeypatch.setattr(doctor_module.importlib.util, "find_spec", fake_find_spec)

    report = doctor_report(tmp_path)

    assert not report.ok
    assert [item.package for item in report.missing_dependencies] == ["tree-sitter-go"]
    assert "pip install" in report.repair_command
    rendered = render_doctor(report)
    assert "LogicChart doctor FAILED" in rendered
    assert "tree-sitter-go" in rendered
