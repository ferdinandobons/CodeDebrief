from __future__ import annotations

from pathlib import Path
from typing import Any

from logicchart.analysis import ProjectAnalyzer
from logicchart.artifacts import load_model, write_artifacts
from logicchart.query import impact_model, query_model


def run_mcp(root: Path) -> None:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as error:
        raise RuntimeError(
            "MCP support is not installed. Run `pip install 'logicchart[mcp]'`."
        ) from error

    project_root = root.resolve()
    server = FastMCP("LogicChart", json_response=True)

    @server.tool()
    def list_flows(entrypoints_only: bool = True) -> list[dict[str, Any]]:
        """List known decision flows in the current project."""
        model = load_model(project_root)
        return [
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
        ]

    @server.tool()
    def get_flow(flow_id: str) -> dict[str, Any]:
        """Return one complete flow, including nodes, edges, callers, and findings."""
        model = load_model(project_root)
        flow = next((item for item in model.flows if item.id == flow_id), None)
        if flow is None:
            return {"error": f"Unknown flow: {flow_id}"}
        return {
            "flow": flow.__dict__ if hasattr(flow, "__dict__") else _flow_dict(flow),
            "findings": [
                item.__dict__ if hasattr(item, "__dict__") else _finding_dict(item)
                for item in model.findings
                if item.flow_id == flow.id
            ],
        }

    @server.tool()
    def query_logic(question: str, limit: int = 10) -> list[dict[str, Any]]:
        """Find flows relevant to a behavior, decision, state, or codebase question."""
        model = load_model(project_root)
        return [
            {
                "flow_id": match.flow.id,
                "name": match.flow.name,
                "score": match.score,
                "reasons": match.reasons,
                "source": (f"{match.flow.location.path}:{match.flow.location.start_line}"),
            }
            for match in query_model(model, question, limit)
        ]

    @server.tool()
    def get_findings(flow_id: str | None = None) -> list[dict[str, Any]]:
        """List potential gaps and inconsistent case handling."""
        model = load_model(project_root)
        return [
            _finding_dict(item)
            for item in model.findings
            if flow_id is None or item.flow_id == flow_id
        ]

    @server.tool()
    def analyze_impact(changed_files: list[str]) -> dict[str, Any]:
        """Find direct and transitive decision flows affected by changed source files."""
        result = impact_model(load_model(project_root), changed_files)
        return {
            "changed_files": result.changed_files,
            "direct": [_flow_summary(item) for item in result.directly_impacted],
            "transitive": [_flow_summary(item) for item in result.transitively_impacted],
            "findings": [_finding_dict(item) for item in result.findings],
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
    from dataclasses import asdict

    return asdict(flow)


def _finding_dict(finding: Any) -> dict[str, Any]:
    from dataclasses import asdict

    return asdict(finding)
