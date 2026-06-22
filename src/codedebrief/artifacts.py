from __future__ import annotations

import hashlib
import json
from pathlib import Path

from codedebrief.config import CodeDebriefConfig
from codedebrief.model import ProjectModel
from codedebrief.render.html import render_html
from codedebrief.render.markdown import render_markdown
from codedebrief.util import atomic_write_text, atomic_write_text_batch, read_json

HASH_SIDECAR_SCHEMA_VERSION = "codedebrief_model_hash.v1"


def output_paths(root: Path, config: CodeDebriefConfig | None = None) -> tuple[Path, Path, Path]:
    active_config = config or CodeDebriefConfig.load(root)
    project_root = root.resolve()
    output = (project_root / active_config.output_dir).resolve()
    try:
        output.relative_to(project_root)
    except ValueError as error:
        raise ValueError("CodeDebrief output_dir must stay inside the analyzed project") from error
    return (
        output / "codedebrief.json",
        output / "codedebrief.md",
        output / "codedebrief.html",
    )


def model_hash_path(root: Path, config: CodeDebriefConfig | None = None) -> Path:
    json_path, _, _ = output_paths(root, config)
    return _model_hash_path_for_json(json_path)


def write_artifacts(
    root: Path,
    model: ProjectModel,
    *,
    include_html: bool = True,
    config: CodeDebriefConfig | None = None,
) -> tuple[Path, Path, Path | None]:
    json_path, markdown_path, html_path = output_paths(root, config)
    model_payload = model.to_dict()
    payloads = {
        json_path: json.dumps(model_payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
        markdown_path: render_markdown(model),
    }
    if include_html:
        payloads[html_path] = render_html(model, source_root=root.resolve())
    atomic_write_text_batch(payloads, encoding="utf-8")
    _write_model_hash_sidecar(json_path, model_payload)
    if include_html:
        return json_path, markdown_path, html_path
    return json_path, markdown_path, None


def load_model(root: Path, config: CodeDebriefConfig | None = None) -> ProjectModel:
    return ProjectModel.from_dict(_read_model_payload(root, config))


def load_model_with_hash(
    root: Path, config: CodeDebriefConfig | None = None
) -> tuple[ProjectModel, str]:
    json_path, _, _ = output_paths(root, config)
    payload = _read_model_payload_from_path(json_path)
    return ProjectModel.from_dict(payload), _model_hash_for_payload(json_path, payload)


def _read_model_payload(root: Path, config: CodeDebriefConfig | None = None) -> dict[str, object]:
    json_path, _, _ = output_paths(root, config)
    return _read_model_payload_from_path(json_path)


def _read_model_payload_from_path(json_path: Path) -> dict[str, object]:
    if not json_path.exists():
        raise FileNotFoundError(
            f"No CodeDebrief model found at {json_path}. Run `codedebrief update` first."
        )
    return read_json(json_path)


def artifact_model_hash(payload: dict[str, object]) -> str:
    normalized = dict(payload)
    normalized.pop("generated_at", None)
    raw = json.dumps(normalized, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _model_hash_for_payload(json_path: Path, payload: dict[str, object]) -> str:
    sidecar_hash = _read_model_hash_sidecar(json_path)
    if sidecar_hash is not None:
        return sidecar_hash
    return artifact_model_hash(payload)


def _model_hash_path_for_json(json_path: Path) -> Path:
    return json_path.with_name("codedebrief.hash.json")


def _write_model_hash_sidecar(json_path: Path, model_payload: dict[str, object]) -> None:
    stat = json_path.stat()
    payload = {
        "schema_version": HASH_SIDECAR_SCHEMA_VERSION,
        "artifact": json_path.name,
        "artifact_mtime_ns": stat.st_mtime_ns,
        "artifact_size": stat.st_size,
        "model_hash": artifact_model_hash(model_payload),
    }
    atomic_write_text(
        _model_hash_path_for_json(json_path),
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_model_hash_sidecar(json_path: Path) -> str | None:
    hash_path = _model_hash_path_for_json(json_path)
    if not hash_path.exists():
        return None
    try:
        payload = read_json(hash_path)
        stat = json_path.stat()
        if payload.get("schema_version") != HASH_SIDECAR_SCHEMA_VERSION:
            return None
        if payload.get("artifact") != json_path.name:
            return None
        if int(payload.get("artifact_mtime_ns", -1)) != stat.st_mtime_ns:
            return None
        if int(payload.get("artifact_size", -1)) != stat.st_size:
            return None
        model_hash = payload.get("model_hash")
        return str(model_hash) if model_hash else None
    except (OSError, TypeError, ValueError):
        return None
