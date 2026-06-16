from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from logicchart.analysis import ProjectAnalyzer
from logicchart.artifacts import load_model, write_artifacts
from logicchart.model import ProjectModel
from logicchart.query import (
    explain_finding,
    find_decisions,
    impact_model,
    model_summary,
    query_model,
    where_is_state_handled,
)

# Rough tokens per returned list item, used to honor an agent's token_budget cap.
_TOKENS_PER_ITEM = 60

# Errors raised while loading the on-disk model (missing file, corrupt/garbled JSON,
# unexpected schema). Surfaced to the agent as a clean {"error": ...} instead of a raw
# traceback, so a stale or never-built model is recoverable advice, not a crash.
_LOAD_ERRORS = (OSError, ValueError, KeyError, TypeError)


def _cap(items: list[dict[str, Any]], token_budget: int) -> list[dict[str, Any]]:
    if token_budget <= 0:
        return items
    return items[: max(1, token_budget // _TOKENS_PER_ITEM)]


def _try_load(project_root: Path) -> tuple[ProjectModel | None, dict[str, Any] | None]:
    """Load the model, or return a clean error dict the tool can hand back.

    Every MCP tool reads the persisted model first; without this a missing or corrupt
    model would propagate a raw traceback to the calling agent.
    """
    try:
        return load_model(project_root), None
    except _LOAD_ERRORS as error:
        return None, {
            "error": f"Could not load the LogicChart model: {error}. "
            "Run `logicchart analyze --full` (or the update_logicchart tool) first."
        }


def run_mcp(root: Path) -> None:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as error:
        raise RuntimeError(
            "MCP support is not installed. Run `uv tool install '.[mcp]'` "
            "(or `uv sync --extra mcp` for development)."
        ) from error

    project_root = root.resolve()
    server = FastMCP("LogicChart", json_response=True)

    @server.tool()
    def list_flows(entrypoints_only: bool = True, token_budget: int = 0) -> list[dict[str, Any]]:
        """List known decision flows in the current project."""
        model, error = _try_load(project_root)
        if error is not None:
            return [error]
        assert model is not None
        return _cap(
            [
                {
                    "id": flow.id,
                    "name": flow.name,
                    "symbol": flow.symbol,
                    "entry_kind": flow.entry_kind,
                    "framework": flow.framework,
                    "source": f"{flow.location.path}:{flow.location.start_line}",
                    "findings": sum(item.flow_id == flow.id for item in model.findings),
                }
                for flow in model.flows
                if flow.is_entrypoint or not entrypoints_only
            ],
            token_budget,
        )

    @server.tool()
    def get_flow(flow_id: str, token_budget: int = 0) -> dict[str, Any]:
        """Return one complete flow, including nodes, edges, callers, and findings."""
        model, error = _try_load(project_root)
        if error is not None:
            return error
        assert model is not None
        flow = next((item for item in model.flows if item.id == flow_id), None)
        if flow is None:
            return {"error": f"Unknown flow: {flow_id}"}
        flow_dict = _flow_dict(flow)
        # Honor the budget by trimming the largest list-shaped fields of the graph, then
        # keep the subgraph internally consistent: drop any edge whose source or target
        # node was capped away, so the result is never a dangling-edge graph.
        flow_dict["nodes"] = _cap(flow_dict.get("nodes", []), token_budget)
        kept_node_ids = {node["id"] for node in flow_dict["nodes"]}
        flow_dict["edges"] = _cap(
            [
                edge
                for edge in flow_dict.get("edges", [])
                if edge["source"] in kept_node_ids and edge["target"] in kept_node_ids
            ],
            token_budget,
        )
        return {
            "flow": flow_dict,
            "findings": _cap(
                [_finding_dict(item) for item in model.findings if item.flow_id == flow.id],
                token_budget,
            ),
        }

    @server.tool()
    def query_logic(
        question: str,
        limit: int = 10,
        scope: str | None = None,
        token_budget: int = 0,
    ) -> list[dict[str, Any]]:
        """Find flows relevant to a behavior, decision, state, or codebase question.

        ``scope`` restricts to a named macro-part so the result matches the CLI's
        ``query --scope`` ranking. ``token_budget`` only ever shrinks the list below
        ``limit``; it never expands it (query_model has already truncated to ``limit``).
        """
        model, error = _try_load(project_root)
        if error is not None:
            return [error]
        assert model is not None
        matches = query_model(model, question, limit, scope)
        return _cap([match.to_dict() for match in matches], token_budget)

    @server.tool()
    def get_findings(flow_id: str | None = None, token_budget: int = 0) -> list[dict[str, Any]]:
        """List potential gaps and inconsistent case handling."""
        model, error = _try_load(project_root)
        if error is not None:
            return [error]
        assert model is not None
        return _cap(
            [
                _finding_dict(item)
                for item in model.findings
                if flow_id is None or item.flow_id == flow_id
            ],
            token_budget,
        )

    @server.tool()
    def logicchart_summary() -> dict[str, Any]:
        """An orientation snapshot: flow/entrypoint counts and findings by kind/severity."""
        model, error = _try_load(project_root)
        if error is not None:
            return error
        assert model is not None
        return model_summary(model)

    @server.tool()
    def explain_finding_chain(finding_id: str, token_budget: int = 0) -> dict[str, Any]:
        """The deterministic evidence chain behind one finding (decision, condition, branches).

        Returns one small record; token_budget is accepted only to match the uniform
        query/list tool contract.
        """
        model, error = _try_load(project_root)
        if error is not None:
            return error
        assert model is not None
        result = explain_finding(model, finding_id)
        return result if result is not None else {"error": f"Unknown finding: {finding_id}"}

    @server.tool()
    def where_state_handled(
        domain: str, value: str | None = None, token_budget: int = 0
    ) -> list[dict[str, Any]]:
        """Every flow that branches on a domain/value-namespace, with the values it covers."""
        model, error = _try_load(project_root)
        if error is not None:
            return [error]
        assert model is not None
        return _cap(where_is_state_handled(model, domain, value), token_budget)

    @server.tool()
    def find_decision_nodes(
        domain: str | None = None,
        subject: str | None = None,
        missing_fallback: bool = False,
        token_budget: int = 0,
    ) -> list[dict[str, Any]]:
        """Structured search over decision nodes (by domain/subject/missing-fallback)."""
        model, error = _try_load(project_root)
        if error is not None:
            return [error]
        assert model is not None
        decisions = find_decisions(
            model,
            domain=domain,
            subject=subject,
            missing_fallback=missing_fallback,
        )
        return _cap(decisions, token_budget)

    @server.tool()
    def analyze_impact(
        changed_files: list[str], scope: str | None = None, token_budget: int = 0
    ) -> dict[str, Any]:
        """Find direct and transitive decision flows affected by changed source files.

        ``scope`` restricts to a named macro-part, matching the CLI's ``impact --scope``.
        """
        model, error = _try_load(project_root)
        if error is not None:
            return error
        assert model is not None
        result = impact_model(model, changed_files, scope)
        direct = [_flow_summary(item) for item in result.directly_impacted]
        transitive = [_flow_summary(item) for item in result.transitively_impacted]
        return {
            "changed_files": result.changed_files,
            "direct": _cap(direct, token_budget),
            "transitive": _cap(transitive, token_budget),
            "findings": _cap([_finding_dict(item) for item in result.findings], token_budget),
        }

    @server.tool()
    def update_logicchart(full: bool = False) -> dict[str, Any]:
        """Refresh LogicChart after source changes and write JSON, Markdown, and HTML."""
        result = ProjectAnalyzer(project_root).analyze(full=full)
        json_path, markdown_path, html_path = write_artifacts(project_root, result.model)
        return {
            "changed_files": result.changed_files,
            "deleted_files": result.deleted_files,
            "cache_hits": result.cache_hits,
            "flows": len(result.model.flows),
            "findings": len(result.model.findings),
            "artifacts": [
                str(json_path),
                str(markdown_path),
                str(html_path) if html_path else "",
            ],
        }

    server.run(transport="stdio")


def _flow_summary(flow: Any) -> dict[str, Any]:
    return {
        "id": flow.id,
        "name": flow.name,
        "source": f"{flow.location.path}:{flow.location.start_line}",
        "entry_kind": flow.entry_kind,
    }


def _flow_dict(flow: Any) -> dict[str, Any]:
    return asdict(flow)


def _finding_dict(finding: Any) -> dict[str, Any]:
    return asdict(finding)
