from pathlib import Path

import pytest

from logicchart.cli import main


def test_analyze_nonexistent_path_errors_clearly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "does-not-exist"
    # A missing path must fail with a clear message, not silently report 0 flows.
    assert main(["analyze", str(missing), "--full"]) == 1
    captured = capsys.readouterr()
    assert "does not exist" in captured.err
    assert "Analyzed 0 files" not in captured.out


def test_cli_catches_oserror_instead_of_leaking_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "main.py").write_text("def f():\n    return 1\n", encoding="utf-8")

    import logicchart.cli as cli_module

    def boom(*_args: object, **_kwargs: object) -> int:
        raise PermissionError("Permission denied")

    monkeypatch.setattr(cli_module, "_analyze", boom)
    # A PermissionError (an OSError subclass) surfaces as a clean `error:` line, rc 1.
    assert main(["analyze", str(tmp_path), "--full"]) == 1
    assert "error:" in capsys.readouterr().err


def test_cli_analyze_query_and_view(tmp_path: Path, capsys: object) -> None:
    source = tmp_path / "main.py"
    source.write_text(
        """
def authorize(user):
    if user.role == "admin":
        return True
    return False
""",
        encoding="utf-8",
    )

    assert main(["analyze", str(tmp_path), "--full"]) == 0
    assert (tmp_path / "logicchart-out" / "logic-flow.json").exists()
    assert main(["query", "admin authorization", "--path", str(tmp_path)]) == 0
    assert main(["view", str(tmp_path), "--render-only"]) == 0


def test_cli_validate_and_profiles(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "src" / "logicchart" / "main.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "def analyze_source(path):\n    if path:\n        return path\n    return None\n",
        encoding="utf-8",
    )

    assert main(["analyze", str(tmp_path), "--profile", "self", "--full", "--no-html"]) == 0
    assert (tmp_path / "logicchart-out" / "self" / "logic-flow.json").exists()

    assert main(["validate", str(tmp_path), "--profile", "self"]) == 0
    assert "validation OK" in capsys.readouterr().out

    assert (
        main(
            [
                "query",
                "logicchart analyze source",
                "--path",
                str(tmp_path),
                "--profile",
                "self",
                "--language",
                "python",
            ]
        )
        == 0
    )
    assert "analyze_source" in capsys.readouterr().out


def test_cli_install_can_write_mcp_config(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["install", str(tmp_path), "--platform", "codex", "--mcp-config", "codex"]) == 0
    assert (tmp_path / "AGENTS.md").exists()
    assert (tmp_path / ".codex" / "config.toml").exists()
    assert "Updated" in capsys.readouterr().out

    assert main(["install", str(tmp_path), "--platform", "codex", "--mcp-config", "codex"]) == 0
    assert "already up to date" in capsys.readouterr().out
