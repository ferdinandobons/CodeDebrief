from __future__ import annotations

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - py310 fallback
    import tomli as tomllib


def test_mcp_is_default_runtime_dependency() -> None:
    pyproject = tomllib.loads(
        (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    )
    dependencies = pyproject["project"]["dependencies"]
    optional_dependencies = pyproject["project"]["optional-dependencies"]

    assert any(item.startswith("mcp>=") for item in dependencies)
    assert optional_dependencies["mcp"] == []
