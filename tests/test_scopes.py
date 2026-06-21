"""Scope / macro-parts: tag flows by backend/frontend/edge and filter by scope."""

from __future__ import annotations

from pathlib import Path

from codedebrief.analysis.project import ProjectAnalyzer
from codedebrief.config import CodeDebriefConfig
from codedebrief.model import ProjectModel
from codedebrief.query import impact_model, query_model


def _project(tmp_path: Path, toml: str = "") -> None:
    (tmp_path / "backend").mkdir()
    (tmp_path / "frontend").mkdir()
    (tmp_path / "backend" / "svc.py").write_text(
        "def handle(user):\n    if user.active:\n        return 1\n    return 0\n", encoding="utf-8"
    )
    (tmp_path / "frontend" / "page.ts").write_text(
        "export function render(items: number[]) {\n  return items.length;\n}\n", encoding="utf-8"
    )
    if toml:
        (tmp_path / "codedebrief.toml").write_text(toml, encoding="utf-8")


def _analyze(tmp_path: Path) -> ProjectModel:
    return ProjectAnalyzer(tmp_path).analyze(full=True).model


def test_scope_inferred_from_top_level_directory(tmp_path: Path) -> None:
    _project(tmp_path)
    model = _analyze(tmp_path)
    by_name = {f.name: f for f in model.flows}
    assert by_name["handle"].metadata["scope"] == ["backend"]
    assert by_name["render"].metadata["scope"] == ["frontend"]
    assert model.metadata["scopes"] == {"backend": 1, "frontend": 1}


def test_named_scopes_from_config(tmp_path: Path) -> None:
    _project(
        tmp_path,
        '[codedebrief]\nsource_roots = ["."]\n\n'
        '[codedebrief.scopes]\napi = ["backend/**"]\nweb = ["frontend/**"]\n',
    )
    model = _analyze(tmp_path)
    by_name = {f.name: f for f in model.flows}
    assert by_name["handle"].metadata["scope"] == ["api"]
    assert by_name["render"].metadata["scope"] == ["web"]


def test_query_and_impact_respect_scope(tmp_path: Path) -> None:
    _project(tmp_path)
    model = _analyze(tmp_path)
    # query restricted to backend never returns the frontend flow
    matches = query_model(model, "user active render items", scope="backend")
    assert matches and all("frontend" not in m.flow.location.path for m in matches)
    # impact restricted to frontend ignores a backend change
    result = impact_model(model, ["backend/svc.py"], scope="frontend")
    assert result.directly_impacted == []


def test_config_scopes_for_helper() -> None:
    config = CodeDebriefConfig(scopes={"edge": ["edge/**"], "api": ["backend/**"]})
    assert config.scopes_for("backend/app.py") == ["api"]
    assert config.scopes_for("edge/router.go") == ["edge"]
    assert config.scopes_for("other/x.py") == []
