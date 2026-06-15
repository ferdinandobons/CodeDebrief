"""C and Rust support via the profile-driven engine (Stage C)."""

from __future__ import annotations

from pathlib import Path

from logicchart.analysis.project import ProjectAnalyzer
from logicchart.model import NodeKind, ProjectModel

_C = """int handle(int s) {
  if (s == 1) { return 0; }
  switch (s) { case 1: return 1; case 2: return 2; }
  return persist(s);
}
static int persist(int s) { return store(s); }
"""

_RUST = """pub fn handle(s: Status) -> i32 {
  if s == Status::Active { return 1; }
  match s {
    Status::Active => 1,
    Status::Suspended => 2,
  }
}
fn persist(s: Status) -> i32 { store(s) }
"""


def _analyze(tmp_path: Path, name: str, content: str) -> ProjectModel:
    src = tmp_path / "src"
    src.mkdir()
    (src / name).write_text(content, encoding="utf-8")
    return ProjectAnalyzer(tmp_path).analyze(full=True).model


def _flow(model: ProjectModel, name: str):
    return next(f for f in model.flows if f.name == name)


def test_c_if_switch_static_and_calls(tmp_path: Path) -> None:
    model = _analyze(tmp_path, "handler.c", _C)
    by_name = {f.name: f for f in model.flows}
    assert by_name["handle"].language == "c"
    # a static function is file-local, not an entry point
    assert by_name["handle"].is_entrypoint and not by_name["persist"].is_entrypoint
    handle = _flow(model, "handle")
    labels = {n.label for n in handle.nodes if n.kind is NodeKind.DECISION}
    assert "s == 1" in labels and "Switch on s" in labels
    assert "missing_branch" in {f.kind for f in model.findings if f.flow_id == handle.id}
    assert _flow(model, "persist").id in handle.calls


def test_rust_if_match_and_visibility(tmp_path: Path) -> None:
    model = _analyze(tmp_path, "lib.rs", _RUST)
    by_name = {f.name: f for f in model.flows}
    assert by_name["handle"].language == "rust"
    assert by_name["handle"].is_entrypoint  # pub
    assert not by_name["persist"].is_entrypoint  # private
    handle = _flow(model, "handle")
    match = next(
        n for n in handle.nodes if n.kind is NodeKind.DECISION and n.label.startswith("Switch")
    )
    assert {"Status::Active", "Status::Suspended"} <= set(match.metadata["values"])
    # no wildcard arm -> missing_branch
    assert "missing_branch" in {f.kind for f in model.findings if f.flow_id == handle.id}


def test_rust_wildcard_arm_is_default(tmp_path: Path) -> None:
    model = _analyze(
        tmp_path,
        "w.rs",
        "pub fn pick(s: Status) -> i32 {\n  match s {\n"
        "    Status::Active => 1,\n    _ => 0,\n  }\n}\n",
    )
    pick = _flow(model, "pick")
    # the `_` arm is the default, so the match is exhaustive: no missing_branch
    assert "missing_branch" not in {f.kind for f in model.findings if f.flow_id == pick.id}
