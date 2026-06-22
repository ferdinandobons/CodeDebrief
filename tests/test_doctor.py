from __future__ import annotations

from pathlib import Path

from codedebrief.doctor import doctor_report, render_doctor


def _missing_parser(monkeypatch, import_name: str) -> None:
    import codedebrief.doctor as doctor_module

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
    assert "CodeDebrief doctor FAILED" in rendered
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


def test_doctor_reports_legacy_logicchart_mcp_config(tmp_path: Path) -> None:
    codex_config = tmp_path / ".codex" / "config.toml"
    codex_config.parent.mkdir(parents=True)
    codex_config.write_text(
        "# logicchart:mcp-config:start\n"
        "[mcp_servers.logicchart]\n"
        'command = "logicchart"\n'
        "# logicchart:mcp-config:end\n",
        encoding="utf-8",
    )

    report = doctor_report(tmp_path)

    assert not report.ok
    assert report.legacy_mcp_configs
    assert report.legacy_mcp_configs[0].server == "logicchart"
    rendered = render_doctor(report)
    assert "Legacy LogicChart MCP configs detected" in rendered
    assert "codedebrief setup" in rendered
