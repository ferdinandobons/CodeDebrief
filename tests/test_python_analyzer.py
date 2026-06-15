from pathlib import Path

from logicchart.analysis.python import PythonAnalyzer
from logicchart.config import LogicChartConfig
from logicchart.model import NodeKind


def test_fastapi_route_builds_functional_decisions(tmp_path: Path) -> None:
    source = tmp_path / "api.py"
    source.write_text(
        """
from fastapi import FastAPI, HTTPException

app = FastAPI()

@app.get("/users/{user_id}")
async def get_user(user_id: str):
    user = await load_user(user_id)
    if user.status == UserStatus.SUSPENDED:
        raise HTTPException(403)
    if user is None:
        return {"error": "missing"}
    return user
""",
        encoding="utf-8",
    )

    analysis = PythonAnalyzer(tmp_path, LogicChartConfig()).analyze(source)

    assert len(analysis.flows) == 1
    flow = analysis.flows[0]
    assert flow.is_entrypoint
    assert flow.framework == "fastapi"
    assert flow.entry_kind == "route"
    assert any(node.kind is NodeKind.DECISION for node in flow.nodes)
    assert any(node.kind is NodeKind.ERROR for node in flow.nodes)
    assert not any(item.kind == "missing_branch" for item in analysis.findings)


def test_python_internal_call_is_recorded(tmp_path: Path) -> None:
    source = tmp_path / "service.py"
    source.write_text(
        """
def load_user(user_id: str):
    return repository.fetch(user_id)

def get_profile(user_id: str):
    user = load_user(user_id)
    return user.profile
""",
        encoding="utf-8",
    )

    analysis = PythonAnalyzer(tmp_path, LogicChartConfig()).analyze(source)
    profile = next(flow for flow in analysis.flows if flow.name == "get_profile")

    call_node = next(node for node in profile.nodes if node.kind is NodeKind.CALL)
    assert "load_user" in call_node.metadata["calls"]
