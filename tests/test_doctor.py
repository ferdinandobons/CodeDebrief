from __future__ import annotations

from pathlib import Path

from logicchart.doctor import doctor_report, render_doctor


def _missing_parser(monkeypatch, import_name: str) -> None:
    import logicchart.doctor as doctor_module

    real_find_spec = doctor_module.importlib.util.find_spec

    def fake_find_spec(name: str):
        if name == import_name:
            return None
        return real_find_spec(name)

    monkeypatch.setattr(doctor_module.importlib.util, "find_spec", fake_find_spec)


def test_doctor_reports_missing_lazy_parser_dependency(tmp_path: Path, monkeypatch) -> None:
    _missing_parser(monkeypatch, "tree_sitter_go")

    report = doctor_report(tmp_path)

    assert not report.ok
    assert [item.package for item in report.missing_dependencies] == ["tree-sitter-go"]
    assert "go" in report.language_capabilities.supported_languages
    assert report.language_capabilities.feature_count >= 10
    assert report.language_capabilities.limitation_note_count > 0
    assert "pip install" in report.repair_command
    rendered = render_doctor(report)
    assert "LogicChart doctor FAILED" in rendered
    assert "tree-sitter-go" in rendered
    assert "Language capabilities:" in rendered
    assert "Capability contract:" in rendered


def test_doctor_language_capabilities_do_not_import_missing_parser(
    tmp_path: Path, monkeypatch
) -> None:
    _missing_parser(monkeypatch, "tree_sitter_typescript")

    report = doctor_report(tmp_path)

    assert not report.ok
    assert [item.package for item in report.missing_dependencies] == ["tree-sitter-typescript"]
    assert {"javascript", "typescript"}.issubset(
        set(report.language_capabilities.supported_languages)
    )
    assert report.language_capabilities.contract.endswith("tests/test_registry.py")
