from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from logicchart.annotations import ANNOTATIONS_SCHEMA_VERSION, annotations_path, model_hash
from logicchart.config import LogicChartConfig
from logicchart.llm_config import get_provider, logicchart_env_path, read_logicchart_env
from logicchart.model import Flow, FlowNode, ProjectModel
from logicchart.util import metadata_scope_names

_DEFAULT_MAX_FLOWS = 12
_DEFAULT_MAX_NODES_PER_FLOW = 18


@dataclass(frozen=True)
class EnrichmentOptions:
    scope: str | None = None
    flow_ids: tuple[str, ...] = ()
    max_flows: int = _DEFAULT_MAX_FLOWS
    max_nodes_per_flow: int = _DEFAULT_MAX_NODES_PER_FLOW


class EnrichmentError(RuntimeError):
    pass


def build_enrichment_preview(
    root: Path,
    model: ProjectModel,
    config: LogicChartConfig,
    options: EnrichmentOptions,
    env_file: str | None = None,
) -> dict[str, Any]:
    env_path = logicchart_env_path(root, env_file)
    llm_values = read_logicchart_env(env_path)
    llm_configured = bool(llm_values)
    provider_id = llm_values.get("LOGICCHART_LLM_PROVIDER")
    provider = get_provider(provider_id) if provider_id else None
    selected_flows = _select_flows(model, options)
    request = _build_llm_request(model, selected_flows, options)

    return {
        "provider_call_made": False,
        "send_required": True,
        "env_file": str(env_path),
        "llm_configured": llm_configured,
        "provider": provider.id if provider else None,
        "model": llm_values.get("LOGICCHART_LLM_MODEL"),
        "api_format": llm_values.get("LOGICCHART_LLM_API_FORMAT"),
        "model_hash": model_hash(model),
        "output": str(annotations_path(root, config)),
        "targets": {
            "scope": options.scope,
            "flow_ids": [flow.id for flow in selected_flows],
            "omitted_flow_count": max(
                0,
                len(_candidate_flows(model, options)) - len(selected_flows),
            ),
        },
        "request": request,
        "guardrails": [
            "Preview mode does not call a provider.",
            "Only the bounded request payload is sent when --send is used.",
            "Provider output must validate as logic-annotations.json before it is written.",
            (
                "Annotations can label or summarize existing ids only; "
                "they cannot change flow structure."
            ),
        ],
    }


def send_enrichment_request(preview: dict[str, Any], timeout: float = 60.0) -> dict[str, Any]:
    llm_values = read_logicchart_env(Path(str(preview["env_file"])))
    provider_id = llm_values.get("LOGICCHART_LLM_PROVIDER")
    if not provider_id:
        raise EnrichmentError("LLM config is missing for provider-managed enrichment.")
    provider = get_provider(provider_id)
    api_format = llm_values.get("LOGICCHART_LLM_API_FORMAT", provider.api_format)
    if api_format not in {"openai", "openai-compatible"}:
        raise EnrichmentError(
            f"provider {provider.id!r} uses api_format {api_format!r}; "
            "provider-managed enrichment currently supports openai-compatible chat APIs only."
        )
    api_key = llm_values.get("LOGICCHART_LLM_API_KEY")
    model = llm_values.get("LOGICCHART_LLM_MODEL")
    base_url = llm_values.get("LOGICCHART_LLM_BASE_URL") or provider.base_url
    if not api_key:
        raise EnrichmentError("LLM API key is missing for provider-managed enrichment.")
    if not model:
        raise EnrichmentError("LLM model is missing for provider-managed enrichment.")

    content = _call_openai_chat(
        base_url=base_url,
        api_key=api_key,
        model=model,
        request_payload=preview["request"],
        timeout=timeout,
    )
    annotations = _parse_annotations_json(content)
    return {
        **annotations,
        "generated_by": {
            "kind": "llm",
            "provider": provider.id,
            "model": model,
            "api_format": api_format,
            "logicchart_workflow": "provider_managed_enrichment",
        },
    }


def write_enrichment_annotations(
    root: Path,
    model: ProjectModel,
    config: LogicChartConfig,
    annotations: dict[str, Any],
) -> Path:
    from logicchart.annotations import AnnotationLoadResult, validate_annotations_payload

    path = annotations_path(root, config)
    result = AnnotationLoadResult(path=str(path), expected_model_hash=model_hash(model))
    normalized = validate_annotations_payload(annotations, model, result)
    if normalized is None or not result.ok:
        joined = "; ".join(result.errors) or "unknown annotation validation error"
        raise EnrichmentError(f"provider output did not validate: {joined}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def render_enrichment_preview(preview: dict[str, Any]) -> str:
    targets = preview["targets"]
    lines = [
        "LogicChart enrichment preview",
        f"provider configured: {preview['provider'] or '(none)'}",
        f"model configured: {preview['model'] or '(none)'}",
        f"output: {preview['output']}",
        f"flows: {len(targets['flow_ids'])} selected, {targets['omitted_flow_count']} omitted",
        "provider call made: false",
        "Run with --send to call the configured provider.",
    ]
    return "\n".join(lines)


def _build_llm_request(
    model: ProjectModel,
    flows: list[Flow],
    options: EnrichmentOptions,
) -> dict[str, Any]:
    return {
        "task": "Return LogicChart annotation sidecar JSON only.",
        "schema": {
            "schema_version": ANNOTATIONS_SCHEMA_VERSION,
            "model_hash": model_hash(model),
            "allowed_buckets": {
                "flows": ["label", "description", "summary"],
                "nodes": ["label", "description"],
                "scopes": ["label", "description", "summary"],
            },
            "limits": {"label": 120, "text": 2000},
        },
        "instructions": [
            "Use only ids present in this request.",
            "Do not create, delete, or rename flow nodes.",
            "Keep labels short and specific to the code behavior.",
            "Use annotations to improve comprehension; do not frame them as defect reports.",
            "Return a JSON object matching logic-annotations schema_version 1.0.",
        ],
        "selection": {
            "scope": options.scope,
            "max_flows": options.max_flows,
            "max_nodes_per_flow": options.max_nodes_per_flow,
        },
        "scopes": _request_scopes(model, flows),
        "flows": [_flow_payload(flow, options.max_nodes_per_flow) for flow in flows],
    }


def _select_flows(model: ProjectModel, options: EnrichmentOptions) -> list[Flow]:
    return _candidate_flows(model, options)[: max(0, options.max_flows)]


def _candidate_flows(model: ProjectModel, options: EnrichmentOptions) -> list[Flow]:
    flows = model.flows
    if options.scope:
        flows = [flow for flow in flows if options.scope in _flow_scopes(flow)]
    if options.flow_ids:
        wanted = set(options.flow_ids)
        flows = [
            flow
            for flow in flows
            if flow.id in wanted or flow.symbol in wanted or flow.name in wanted
        ]
    return sorted(
        flows,
        key=lambda flow: (
            not flow.is_entrypoint,
            flow.location.path,
            flow.name,
            flow.id,
        ),
    )


def _request_scopes(model: ProjectModel, flows: list[Flow]) -> dict[str, Any]:
    requested = {scope for flow in flows for scope in _flow_scopes(flow)}
    scopes = model.metadata.get("scopes", {})
    if not isinstance(scopes, dict):
        return {}
    return {scope: scopes.get(scope, {}) for scope in sorted(requested)}


def _flow_payload(flow: Flow, max_nodes: int) -> dict[str, Any]:
    nodes = flow.nodes[: max(0, max_nodes)]
    return {
        "id": flow.id,
        "name": flow.name,
        "symbol": flow.symbol,
        "language": flow.language,
        "entry_kind": flow.entry_kind,
        "is_entrypoint": flow.is_entrypoint,
        "source": _source_payload(flow.location),
        "calls": flow.calls[:20],
        "called_by": flow.called_by[:20],
        "scopes": _flow_scopes(flow),
        "nodes": [_node_payload(node) for node in nodes],
        "omitted_node_count": max(0, len(flow.nodes) - len(nodes)),
    }


def _node_payload(node: FlowNode) -> dict[str, Any]:
    return {
        "id": node.id,
        "kind": node.kind.value,
        "label": node.label,
        "evidence": node.evidence.value,
        "source": _source_payload(node.location),
    }


def _source_payload(location: Any) -> dict[str, Any]:
    return {
        "path": location.path,
        "start_line": location.start_line,
        "end_line": location.end_line,
    }


def _flow_scopes(flow: Flow) -> list[str]:
    return sorted(metadata_scope_names(flow.metadata))


def _call_openai_chat(
    *,
    base_url: str,
    api_key: str,
    model: str,
    request_payload: dict[str, Any],
    timeout: float,
) -> str:
    endpoint = _chat_endpoint(base_url)
    body = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You enrich LogicChart static-analysis artifacts. "
                    "Return only valid JSON matching the requested annotation sidecar schema."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(request_payload, ensure_ascii=False),
            },
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.URLError as error:
        raise EnrichmentError(f"provider request failed: {error}") from error
    payload = json.loads(raw)
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise EnrichmentError(
            "provider response did not contain choices[0].message.content"
        ) from error
    if not isinstance(content, str) or not content.strip():
        raise EnrichmentError("provider returned an empty annotation response")
    return content


def _chat_endpoint(base_url: str) -> str:
    cleaned = base_url.rstrip("/")
    if cleaned.endswith("/chat/completions"):
        return cleaned
    return f"{cleaned}/chat/completions"


def _parse_annotations_json(content: str) -> dict[str, Any]:
    stripped = content.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, re.DOTALL)
    if fenced:
        stripped = fenced.group(1).strip()
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as error:
        raise EnrichmentError(f"provider did not return valid JSON: {error}") from error
    if not isinstance(payload, dict):
        raise EnrichmentError("provider annotation response must be a JSON object")
    return payload
