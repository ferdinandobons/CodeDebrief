from __future__ import annotations

from pathlib import Path

import pytest

from logicchart.analysis.project import ProjectAnalyzer
from logicchart.config import LogicChartConfig


def test_certifexp_real_project_local_smoke() -> None:
    """Analyze the private Certifexp fixture when it exists locally.

    The fixture is intentionally ignored by Git and absent in CI. This test gives local
    development a real-project regression gate without publishing the project or making
    public CI depend on private source code.
    """

    root = Path("examples/Certifexp")
    if not root.exists():
        pytest.skip("examples/Certifexp is a private local fixture and is not in Git")

    config = LogicChartConfig(
        source_roots=[
            "backend-api/app",
            "frontend/frontend-app/src",
            "frontend/frontend-app/tests",
            "frontend/landing/src",
            "infrastructure/lambdas",
            "infrastructure/modules/lambda_api/bootstrap",
        ],
        output_dir="logicchart-out/certifexp-local",
        self_exclude=False,
        scopes={
            "backend": ["backend-api/app/**", "infrastructure/lambdas/**"],
            "frontend": ["frontend/**"],
            "infrastructure": ["infrastructure/modules/lambda_api/bootstrap/**"],
        },
    )

    result = ProjectAnalyzer(root, config).analyze(full=True)
    model = result.model
    languages = set(model.metadata.get("languages", []))

    assert result.skipped_files == []
    assert len(model.files) >= 25
    assert len(model.flows) >= 25
    assert "python" in languages
    assert "typescript" in languages or "javascript" in languages
    assert any(flow.is_entrypoint for flow in model.flows)
