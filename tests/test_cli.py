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
