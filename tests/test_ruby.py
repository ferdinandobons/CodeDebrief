"""Ruby support via the profile-driven engine (Stage C)."""

from __future__ import annotations

from pathlib import Path

from logicchart.analysis.project import ProjectAnalyzer
from logicchart.model import NodeKind, ProjectModel

_SVC = """class Svc
  def handle(s)
    if s == :active
      return "ok"
    else
      log(s)
    end
    case s
    when :active then "a"
    when :suspended then "s"
    end
    persist(s)
  end

  def persist(s)
    store(s)
  end
end
"""


def _analyze(tmp_path: Path) -> ProjectModel:
    app = tmp_path / "app"
    app.mkdir()
    (app / "svc.rb").write_text(_SVC, encoding="utf-8")
    return ProjectAnalyzer(tmp_path).analyze(full=True).model


def _flow(model: ProjectModel, name: str):
    return next(f for f in model.flows if f.name == name)


def test_ruby_if_else_case_and_calls(tmp_path: Path) -> None:
    model = _analyze(tmp_path)
    by_name = {f.name: f for f in model.flows}
    assert {"Svc.handle", "Svc.persist"} <= set(by_name)
    assert all(f.language == "ruby" for f in model.flows)
    handle = _flow(model, "Svc.handle")
    labels = {n.label for n in handle.nodes if n.kind is NodeKind.DECISION}
    assert "s == :active" in labels and "Switch on s" in labels
    case = next(
        n for n in handle.nodes if n.kind is NodeKind.DECISION and n.label.startswith("Switch")
    )
    assert {":active", ":suspended"} <= set(case.metadata["values"])
    # case without an else -> missing_branch
    assert "missing_branch" in {f.kind for f in model.findings if f.flow_id == handle.id}
    assert _flow(model, "Svc.persist").id in handle.calls


def test_ruby_else_branch_is_walked(tmp_path: Path) -> None:
    handle = _flow(_analyze(tmp_path), "Svc.handle")
    guard = next(n for n in handle.nodes if n.kind is NodeKind.DECISION and "active" in n.label)
    branches = {b["label"]: b for b in guard.metadata["branches"]}
    # the explicit else makes the No branch non-implicit
    assert not branches["No"]["implicit"]
