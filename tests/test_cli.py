from pathlib import Path

from logicchart.cli import main


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
