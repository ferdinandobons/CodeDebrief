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


def test_try_else_body_is_modeled_on_success_path(tmp_path: Path) -> None:
    source = tmp_path / "service.py"
    source.write_text(
        """
def process(order):
    try:
        validate(order)
    except ValidationError:
        return reject(order)
    else:
        persist(order)
    return ok(order)
""",
        encoding="utf-8",
    )

    analysis = PythonAnalyzer(tmp_path, LogicChartConfig()).analyze(source)
    flow = next(item for item in analysis.flows if item.name == "process")
    labels = [node.label for node in flow.nodes]

    assert "Call validate()" in labels
    assert "Call persist()" in labels
    assert "Call ok()" in labels
    assert "Return ok(order)" in labels
    assert "Return reject(order)" in labels

    by_label = {node.label: node.id for node in flow.nodes}
    assert any(
        edge.source == by_label["Call validate()"] and edge.target == by_label["Call persist()"]
        for edge in flow.edges
    )
    assert any(
        edge.source == by_label["Call persist()"] and edge.target == by_label["Call ok()"]
        for edge in flow.edges
    )
    assert any(
        edge.source == by_label["Call ok()"] and edge.target == by_label["Return ok(order)"]
        for edge in flow.edges
    )


def test_try_else_is_skipped_when_body_returns(tmp_path: Path) -> None:
    source = tmp_path / "service.py"
    source.write_text(
        """
def process(order):
    try:
        return ok(order)
    except ValidationError:
        return reject(order)
    else:
        persist(order)
""",
        encoding="utf-8",
    )

    analysis = PythonAnalyzer(tmp_path, LogicChartConfig()).analyze(source)
    flow = next(item for item in analysis.flows if item.name == "process")

    assert "Call persist()" not in {node.label for node in flow.nodes}
