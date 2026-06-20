"""The language registry: dispatch by suffix and lazy analyzer construction."""

from __future__ import annotations

from pathlib import Path

import pytest

from logicchart.analysis.project import ProjectAnalyzer
from logicchart.analysis.registry import (
    language_capability_matrix,
    language_for,
    spec_for_language,
    spec_for_path,
    supported_suffixes,
)
from logicchart.model import NodeKind

_CAPABILITY_SMOKE_FIXTURES = {
    "python": (
        "service.py",
        """
def handle(status):
    if status == "active":
        return persist(status)
    match status:
        case "suspended":
            return block(status)
        case _:
            return persist(status)

def persist(status):
    return status

def block(status):
    return status
""",
        "handle",
    ),
    "typescript": (
        "service.ts",
        """
export function handle(status: string) {
  if (status === "active") {
    return persist(status);
  }
  switch (status) {
    case "suspended":
      return block(status);
    default:
      return persist(status);
  }
}

function persist(status: string) {
  return status;
}

function block(status: string) {
  return status;
}
""",
        "handle",
    ),
    "javascript": (
        "service.js",
        """
export function handle(status) {
  if (status === "active") {
    return persist(status);
  }
  switch (status) {
    case "suspended":
      return block(status);
    default:
      return persist(status);
  }
}

function persist(status) {
  return status;
}

function block(status) {
  return status;
}
""",
        "handle",
    ),
    "go": (
        "service.go",
        """
package svc

func Handle(status string) string {
    if status == "active" {
        return persist(status)
    }
    switch status {
    case "suspended":
        return block(status)
    default:
        return persist(status)
    }
}

func persist(status string) string {
    return status
}

func block(status string) string {
    return status
}
""",
        "Handle",
    ),
    "java": (
        "Svc.java",
        """
package app;

public class Svc {
  public String handle(String status) {
    if (status.equals("active")) {
      return persist(status);
    }
    switch (status) {
      case "suspended": return block(status);
      default: return persist(status);
    }
  }

  private String persist(String status) {
    return status;
  }

  private String block(String status) {
    return status;
  }
}
""",
        "Svc.handle",
    ),
    "csharp": (
        "Svc.cs",
        """
namespace App {
  public class Svc {
    public string Handle(string status) {
      if (status == "active") {
        return Persist(status);
      }
      switch (status) {
        case "suspended": return Block(status);
        default: return Persist(status);
      }
    }

    private string Persist(string status) {
      return status;
    }

    private string Block(string status) {
      return status;
    }
  }
}
""",
        "Svc.Handle",
    ),
    "php": (
        "Svc.php",
        """
<?php
class Svc {
  public function handle($status) {
    if ($status == "active") {
      return $this->persist($status);
    }
    switch ($status) {
      case "suspended": return $this->block($status);
      default: return $this->persist($status);
    }
  }

  private function persist($status) {
    return $status;
  }

  private function block($status) {
    return $status;
  }
}
""",
        "Svc.handle",
    ),
    "c": (
        "service.c",
        """
int persist(int status) {
  return status;
}

int block(int status) {
  return status;
}

int handle(int status) {
  if (status == 1) {
    return persist(status);
  }
  switch (status) {
    case 2: return block(status);
    default: return persist(status);
  }
}
""",
        "handle",
    ),
    "cpp": (
        "service.cpp",
        """
int persist(int status) {
  return status;
}

int block(int status) {
  return status;
}

int handle(int status) {
  if (status == 1) {
    return persist(status);
  }
  switch (status) {
    case 2: return block(status);
    default: return persist(status);
  }
}
""",
        "handle",
    ),
    "rust": (
        "service.rs",
        """
fn persist(status: i32) -> i32 {
  status
}

fn block(status: i32) -> i32 {
  status
}

pub fn handle(status: i32) -> i32 {
  if status == 1 {
    return persist(status);
  }
  match status {
    2 => block(status),
    _ => persist(status),
  }
}
""",
        "handle",
    ),
    "ruby": (
        "service.rb",
        """
class Svc
  def handle(status)
    if status == :active
      return persist(status)
    end
    case status
    when :suspended then block(status)
    else persist(status)
    end
  end

  def persist(status)
    status
  end

  def block(status)
    status
  end
end
""",
        "Svc.handle",
    ),
}


def test_known_suffixes_map_to_languages() -> None:
    assert language_for(Path("a/b.py")) == "python"
    assert language_for(Path("a/b.ts")) == "typescript"
    assert language_for(Path("a/b.tsx")) == "typescript"
    assert language_for(Path("a/b.cpp")) == "cpp"
    assert {".py", ".ts", ".tsx", ".cpp", ".hpp"} <= supported_suffixes()


def test_language_capability_matrix_tracks_registry() -> None:
    matrix = language_capability_matrix()

    assert {"python", "typescript", "javascript", "cpp", "rust"} <= set(matrix)
    assert matrix["python"]["suffixes"] == [".py"]
    assert matrix["typescript"]["suffixes"] == [".ts", ".tsx"]
    assert matrix["javascript"]["suffixes"] == [".js", ".jsx", ".mjs", ".cjs"]
    assert matrix["python"]["features"]["enum_harvest"] == "supported"
    assert matrix["python"]["features"]["expression_bodied_functions"] == "not_supported"
    assert matrix["typescript"]["features"]["expression_bodied_functions"] == "supported"
    assert matrix["javascript"]["features"]["expression_bodied_functions"] == "supported"
    assert matrix["go"]["features"]["import_dependencies"] == "supported"
    assert matrix["java"]["features"]["qualified_call_links"] == "partial"
    assert matrix["java"]["features"]["import_dependencies"] == "supported"
    assert matrix["c"]["features"]["try_catch"] == "not_supported"
    assert matrix["c"]["features"]["import_dependencies"] == "not_supported"
    assert matrix["rust"]["features"]["returns_throws"] == "partial"
    assert matrix["java"]["limitations"]["qualified_call_links"].startswith("Common")
    assert "import_dependencies" not in matrix["java"]["limitations"]
    assert matrix["c"]["limitations"]["try_catch"].startswith("Error-boundary")
    assert matrix["rust"]["limitations"]["returns_throws"].startswith("Return flow")

    for capability in matrix.values():
        features = capability["features"]
        limitations = capability["limitations"]
        assert set(limitations) <= {
            feature for feature, status in features.items() if status != "supported"
        }
        assert all(note.endswith(".") for note in limitations.values())


@pytest.mark.parametrize("language", sorted(_CAPABILITY_SMOKE_FIXTURES))
def test_language_capability_matrix_matches_smoke_analysis(tmp_path: Path, language: str) -> None:
    filename, source, flow_name = _CAPABILITY_SMOKE_FIXTURES[language]
    source_path = tmp_path / filename
    source_path.write_text(source, encoding="utf-8")

    model = ProjectAnalyzer(tmp_path).analyze(full=True).model
    matrix = language_capability_matrix()
    features = matrix[language]["features"]
    language_flows = [flow for flow in model.flows if flow.language == language]

    assert language in model.metadata["language_capabilities"]
    assert language_flows, f"{language} declared supported but produced no flows"
    flow = next(flow for flow in language_flows if flow.name == flow_name)

    if features["functions_methods"] == "supported":
        assert flow.nodes
    if features["decisions"] == "supported":
        assert any(node.kind is NodeKind.DECISION for node in flow.nodes)
    if features["switch_match"] == "supported":
        assert any(
            node.kind is NodeKind.DECISION
            and (node.label.startswith("Switch") or node.label.startswith("Match"))
            for node in flow.nodes
        )
    if features["calls"] == "supported":
        assert any(node.kind is NodeKind.CALL for node in flow.nodes)
    if features["returns_throws"] in {"supported", "partial"}:
        assert any(
            node.kind is NodeKind.TERMINAL and node.label.startswith("Return")
            for node in flow.nodes
        )


def test_unknown_suffix_is_rejected() -> None:
    assert spec_for_path(Path("a/b.unknown")) is None
    with pytest.raises(ValueError, match="Unsupported source file"):
        language_for(Path("a/b.unknown"))


def test_spec_factory_builds_an_analyzer(tmp_path: Path) -> None:
    spec = spec_for_language("python")
    analyzer = spec.factory(tmp_path, _config(tmp_path))
    assert hasattr(analyzer, "analyze")


def test_project_analyzer_dispatches_and_caches(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def f(x):\n    return x\n", encoding="utf-8")
    (tmp_path / "b.ts").write_text(
        "export function g(x: number) {\n  return x;\n}\n", encoding="utf-8"
    )
    (tmp_path / "c.cpp").write_text("int h(int x) { return x; }\n", encoding="utf-8")
    analyzer = ProjectAnalyzer(tmp_path)
    model = analyzer.analyze(full=True).model
    languages = {flow.language for flow in model.flows}
    assert {"python", "typescript", "cpp"} <= languages
    assert "language_capabilities" in model.metadata
    assert "javascript" in model.metadata["language_capabilities"]
    # Analyzers are cached lazily, one per language actually seen.
    assert set(analyzer._analyzers) == {"python", "typescript", "cpp"}


def _config(root: Path):
    from logicchart.config import LogicChartConfig

    return LogicChartConfig.load(root)
