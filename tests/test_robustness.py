"""Robustness: one bad file never aborts the run; malformed JSON fails cleanly."""

from __future__ import annotations

from pathlib import Path

import pytest

from logicchart.analysis.project import ProjectAnalyzer
from logicchart.model import ProjectModel


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_one_unparseable_file_does_not_abort_the_run(tmp_path: Path) -> None:
    _write(tmp_path / "good.py", "def handler(x):\n    return x\n")
    _write(tmp_path / "broken.py", "def broken(:\n")  # SyntaxError
    (tmp_path / "py2.py").write_text('print "hello"\n', encoding="utf-8")  # Py2 SyntaxError
    (tmp_path / "latin1.py").write_bytes(b"x = '\xff'\n")  # UnicodeDecodeError
    (tmp_path / "bad.ts").write_bytes(b"export const x = '\xff'\n")  # TS decode error

    result = ProjectAnalyzer(tmp_path).analyze(full=True)

    # The clean file still produced a flow and the model was written.
    assert any(flow.name == "handler" for flow in result.model.flows)
    skipped = {relative for relative, _ in result.skipped_files}
    assert skipped == {"broken.py", "py2.py", "latin1.py", "bad.ts"}
    # Every file (good and degraded) is still recorded so callers see the full tree.
    recorded = {record.path for record in result.model.files}
    assert {"good.py", "broken.py", "latin1.py", "bad.ts"} <= recorded
    # Each skip carries a non-empty human-readable reason.
    assert all(reason for _, reason in result.skipped_files)


def test_incremental_run_skips_a_newly_broken_file(tmp_path: Path) -> None:
    _write(tmp_path / "good.py", "def handler(x):\n    return x\n")
    ProjectAnalyzer(tmp_path).analyze(full=True)
    _write(tmp_path / "broken.py", "def broken(:\n")

    result = ProjectAnalyzer(tmp_path).analyze(full=False)

    assert any(flow.name == "handler" for flow in result.model.flows)
    assert [relative for relative, _ in result.skipped_files] == ["broken.py"]


@pytest.mark.parametrize(
    "payload",
    [
        {"flows": "notalist", "findings": [], "files": [], "root": ".", "generated_at": "x"},
        {"root": ".", "generated_at": "x"},  # missing schema_version
        {
            "schema_version": "1.1",
            "generated_at": "x",
            "root": ".",
            "files": [{"path": "a", "language": "python", "sha256": "h", "bogus": 1}],
        },
        {
            "schema_version": "1.1",
            "generated_at": "x",
            "root": ".",
            "flows": [
                {
                    "id": "f",
                    "name": "n",
                    "symbol": "s",
                    "language": "python",
                    "framework": "g",
                    "entry_kind": "function",
                    "is_entrypoint": False,
                    "location": "not-a-dict",
                }
            ],
        },
    ],
)
def test_from_dict_rejects_malformed_models_cleanly(payload: dict) -> None:
    with pytest.raises(ValueError, match=r"malformed logic-flow\.json"):
        ProjectModel.from_dict(payload)
