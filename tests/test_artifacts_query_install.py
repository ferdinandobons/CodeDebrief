from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from logicchart.analysis.project import ProjectAnalyzer
from logicchart.artifacts import load_model, output_paths, write_artifacts
from logicchart.config import LogicChartConfig
from logicchart.install import END, START, install_agent_instructions
from logicchart.query import impact_model, query_model
from logicchart.util import read_json


def test_artifacts_query_impact_and_agent_install(tmp_path: Path) -> None:
    source = tmp_path / "users.py"
    source.write_text(
        """
def get_user(user_id: str):
    user = repository.fetch(user_id)
    if user.status == "suspended":
        return None
    return user
""",
        encoding="utf-8",
    )
    result = ProjectAnalyzer(tmp_path).analyze(full=True)
    json_path, markdown_path, html_path = write_artifacts(tmp_path, result.model)

    assert json_path.exists()
    assert markdown_path.exists()
    assert html_path is not None and html_path.exists()
    assert "flowchart TD" in markdown_path.read_text(encoding="utf-8")
    assert "Decision flow index" in html_path.read_text(encoding="utf-8")
    assert load_model(tmp_path).flows
    schema = read_json(Path(__file__).parents[1] / "schema" / "logic-flow.schema.json")
    artifact = read_json(json_path)
    Draft202012Validator(schema).validate(artifact)
    assert artifact["root"] == "."
    assert str(tmp_path) not in markdown_path.read_text(encoding="utf-8")
    assert str(tmp_path) in html_path.read_text(encoding="utf-8")

    matches = query_model(result.model, "suspended user")
    assert matches and matches[0].flow.name == "get_user"

    impact = impact_model(result.model, ["users.py"])
    assert impact.directly_impacted

    changed = install_agent_instructions(tmp_path, "codex")
    assert changed == [tmp_path / "AGENTS.md"]
    install_agent_instructions(tmp_path, "codex")
    contents = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert contents.count(START) == 1
    assert contents.count(END) == 1


def test_output_directory_cannot_escape_project(tmp_path: Path) -> None:
    config = LogicChartConfig(output_dir="../outside")

    with pytest.raises(ValueError, match="must stay inside"):
        output_paths(tmp_path, config)
