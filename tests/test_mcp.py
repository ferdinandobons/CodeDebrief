import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from logicchart.analysis.project import ProjectAnalyzer
from logicchart.artifacts import load_model, write_artifacts
from logicchart.cli import main as cli_main


def test_mcp_lists_and_queries_flows(tmp_path: Path) -> None:
    source = tmp_path / "app.py"
    source.write_text(
        """
def authorize(user):
    if user.role == "admin":
        return True
    return False
""",
        encoding="utf-8",
    )
    result = ProjectAnalyzer(tmp_path).analyze(full=True)
    write_artifacts(tmp_path, result.model)

    async def exercise_server() -> None:
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "logicchart.cli", "mcp", str(tmp_path)],
        )
        async with stdio_client(parameters) as streams:
            read_stream, write_stream = streams
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools = await session.list_tools()
                names = {tool.name for tool in tools.tools}
                assert {"list_flows", "get_flow", "query_logic", "update_logicchart"} <= names
                assert {
                    "logicchart_summary",
                    "explain_finding_chain",
                    "where_state_handled",
                    "find_decision_nodes",
                } <= names

                # Spec §5.2: every query/list tool exposes a token_budget cap.
                schema_by_name = {tool.name: tool.inputSchema for tool in tools.tools}
                for budget_tool in (
                    "get_flow",
                    "query_logic",
                    "explain_finding_chain",
                    "analyze_impact",
                ):
                    properties = schema_by_name[budget_tool].get("properties", {})
                    assert "token_budget" in properties, budget_tool

                response = await session.call_tool(
                    "query_logic",
                    {"question": "admin authorization", "limit": 5},
                )
                assert not response.isError
                assert "authorize" in str(response.content)

                summary = await session.call_tool("logicchart_summary", {})
                assert not summary.isError
                assert "flows" in str(summary.content)

                state = await session.call_tool("where_state_handled", {"domain": "role"})
                assert not state.isError
                assert "authorize" in str(state.content)

    asyncio.run(exercise_server())


def test_cli_json_and_mcp_query_logic_have_same_shape(tmp_path: Path, capsys: object) -> None:
    """The CLI `query --json` and the MCP `query_logic` tool share one serializer
    (QueryMatch.to_dict), so identical inputs yield identical JSON rows."""
    source = tmp_path / "app.py"
    source.write_text(
        "def authorize(user):\n"
        "    if user.role == 'admin':\n"
        "        return True\n"
        "    return False\n",
        encoding="utf-8",
    )
    result = ProjectAnalyzer(tmp_path).analyze(full=True)
    write_artifacts(tmp_path, result.model)

    assert cli_main(["query", "admin authorize", "--path", str(tmp_path), "--json"]) == 0
    cli_rows = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]

    mcp_rows: list[dict[str, object]] = []

    async def call_mcp() -> None:
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "logicchart.cli", "mcp", str(tmp_path)],
        )
        async with stdio_client(parameters) as streams:
            read_stream, write_stream = streams
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                response = await session.call_tool("query_logic", {"question": "admin authorize"})
                assert not response.isError
                # A list-returning tool puts the full list under structuredContent.result
                # (each content block is one item serialized on its own).
                payload = response.structuredContent["result"]  # type: ignore[index]
                mcp_rows.extend(payload)

    asyncio.run(call_mcp())

    assert cli_rows == mcp_rows
    assert cli_rows
    for row in cli_rows:
        assert set(row) == {"flow_id", "name", "score", "reasons", "source"}


def test_get_flow_subgraph_is_internally_consistent(tmp_path: Path) -> None:
    """Capping nodes by token_budget must also drop edges whose endpoints were removed,
    so get_flow never returns a dangling-edge subgraph."""
    source = tmp_path / "app.py"
    source.write_text(
        "def authorize(user):\n"
        "    if user.role == 'admin':\n"
        "        return allow()\n"
        "    elif user.role == 'staff':\n"
        "        return review()\n"
        "    return deny()\n",
        encoding="utf-8",
    )
    result = ProjectAnalyzer(tmp_path).analyze(full=True)
    write_artifacts(tmp_path, result.model)
    flow = next(f for f in load_model(tmp_path).flows if f.name == "authorize")

    captured: dict[str, object] = {}

    async def call_get_flow() -> None:
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "logicchart.cli", "mcp", str(tmp_path)],
        )
        async with stdio_client(parameters) as streams:
            read_stream, write_stream = streams
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                response = await session.call_tool(
                    "get_flow", {"flow_id": flow.id, "token_budget": 90}
                )
                assert not response.isError
                # A dict-returning tool exposes the object directly via structuredContent.
                captured.update(response.structuredContent)  # type: ignore[arg-type]

    asyncio.run(call_get_flow())

    flow_dict = captured["flow"]
    node_ids = {node["id"] for node in flow_dict["nodes"]}  # type: ignore[index]
    # Budget was small enough to drop some nodes...
    assert len(node_ids) < len(flow.nodes)
    # ...and every surviving edge still connects two surviving nodes.
    for edge in flow_dict["edges"]:  # type: ignore[index]
        assert edge["source"] in node_ids
        assert edge["target"] in node_ids
