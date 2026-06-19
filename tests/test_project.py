from pathlib import Path

from logicchart.analysis.project import ProjectAnalyzer


def test_project_links_calls_and_reuses_cache(tmp_path: Path) -> None:
    source = tmp_path / "app.py"
    source.write_text(
        """
def load_user(user_id: str):
    return repository.fetch(user_id)

def show_user(user_id: str):
    return load_user(user_id)
""",
        encoding="utf-8",
    )

    first = ProjectAnalyzer(tmp_path).analyze(full=True)
    second = ProjectAnalyzer(tmp_path).analyze()
    show = next(flow for flow in first.model.flows if flow.name == "show_user")
    load = next(flow for flow in first.model.flows if flow.name == "load_user")

    assert load.id in show.calls
    assert show.id in load.called_by
    assert second.cache_hits == 1
    assert second.changed_files == []
    assert second.model.generated_at == first.model.generated_at


def test_project_dedupes_repeated_call_edges(tmp_path: Path) -> None:
    source = tmp_path / "app.py"
    source.write_text(
        """
def load_user(user_id: str):
    return repository.fetch(user_id)

def show_user(user_id: str):
    load_user(user_id)
    return load_user(user_id)
""",
        encoding="utf-8",
    )

    model = ProjectAnalyzer(tmp_path).analyze(full=True).model
    show = next(flow for flow in model.flows if flow.name == "show_user")
    load = next(flow for flow in model.flows if flow.name == "load_user")

    assert show.calls == [load.id]
    assert load.called_by == [show.id]


def test_project_detects_deleted_files(tmp_path: Path) -> None:
    source = tmp_path / "app.py"
    source.write_text("def run():\n    return True\n", encoding="utf-8")
    ProjectAnalyzer(tmp_path).analyze(full=True)
    source.unlink()

    result = ProjectAnalyzer(tmp_path).analyze()

    assert result.deleted_files == ["app.py"]
    assert result.model.flows == []
