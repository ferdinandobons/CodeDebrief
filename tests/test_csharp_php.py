"""C# and PHP support via the profile-driven engine (Stage C)."""

from __future__ import annotations

from pathlib import Path

from logicchart.analysis.project import ProjectAnalyzer
from logicchart.model import NodeKind, ProjectModel

_CS = """namespace App {
  public class Svc {
    public int Handle(int s) {
      if (s == 1) { return 0; }
      switch (s) { case 1: return 1; case 2: return 2; }
      try { Risky(); } catch (Exception e) { Log(e); }
      return Persist(s);
    }
    private int Persist(int s) { return Store(s); }
  }
}
"""

_PHP = """<?php
class Svc {
  public function handle($s) {
    if ($s == "a") { return "ok"; }
    switch ($s) { case "a": return 1; case "b": return 2; }
    return $this->persist($s);
  }
  private function persist($s) { return store($s); }
}
"""


def _analyze(tmp_path: Path, name: str, content: str) -> ProjectModel:
    pkg = tmp_path / "app"
    pkg.mkdir()
    (pkg / name).write_text(content, encoding="utf-8")
    return ProjectAnalyzer(tmp_path).analyze(full=True).model


def _flow(model: ProjectModel, name: str):
    return next(f for f in model.flows if f.name == name)


def test_csharp_methods_switch_try_calls(tmp_path: Path) -> None:
    model = _analyze(tmp_path, "Svc.cs", _CS)
    by_name = {f.name: f for f in model.flows}
    assert by_name["Svc.Handle"].language == "csharp"
    assert by_name["Svc.Handle"].is_entrypoint and not by_name["Svc.Persist"].is_entrypoint
    handle = _flow(model, "Svc.Handle")
    switch = next(
        n for n in handle.nodes if n.kind is NodeKind.DECISION and n.label.startswith("Switch")
    )
    assert {"1", "2"} <= set(switch.metadata["values"])
    assert "missing_branch" in {f.kind for f in model.findings if f.flow_id == handle.id}
    # try/catch produces the error boundary decision
    assert any(n.metadata.get("domain") == "error" for n in handle.nodes)
    assert _flow(model, "Svc.Persist").id in handle.calls


def test_php_methods_switch_calls(tmp_path: Path) -> None:
    model = _analyze(tmp_path, "Svc.php", _PHP)
    by_name = {f.name: f for f in model.flows}
    assert by_name["Svc.handle"].language == "php"
    assert by_name["Svc.handle"].is_entrypoint and not by_name["Svc.persist"].is_entrypoint
    handle = _flow(model, "Svc.handle")
    switch = next(
        n for n in handle.nodes if n.kind is NodeKind.DECISION and n.label.startswith("Switch")
    )
    assert {'"a"', '"b"'} <= set(switch.metadata["values"])
    assert "missing_branch" in {f.kind for f in model.findings if f.flow_id == handle.id}
    assert _flow(model, "Svc.persist").id in handle.calls
