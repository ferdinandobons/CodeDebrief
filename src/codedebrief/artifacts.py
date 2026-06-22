from __future__ import annotations

import json
from pathlib import Path

from codedebrief.config import CodeDebriefConfig
from codedebrief.model import ProjectModel
from codedebrief.render.html import render_html
from codedebrief.render.markdown import render_markdown
from codedebrief.util import atomic_write_text_batch, read_json


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


def write_artifacts(
    root: Path,
    model: ProjectModel,
    *,
    include_html: bool = True,
    config: CodeDebriefConfig | None = None,
) -> tuple[Path, Path, Path | None]:
    json_path, markdown_path, html_path = output_paths(root, config)
    payloads = {
        json_path: json.dumps(model.to_dict(), indent=2, ensure_ascii=False, sort_keys=False)
        + "\n",
        markdown_path: render_markdown(model),
    }
    if include_html:
        payloads[html_path] = render_html(model, source_root=root.resolve())
    atomic_write_text_batch(payloads, encoding="utf-8")
    if include_html:
        return json_path, markdown_path, html_path
    return json_path, markdown_path, None


def load_model(root: Path, config: CodeDebriefConfig | None = None) -> ProjectModel:
    json_path, _, _ = output_paths(root, config)
    if not json_path.exists():
        raise FileNotFoundError(
            f"No CodeDebrief model found at {json_path}. Run `codedebrief update` first."
        )
    return ProjectModel.from_dict(read_json(json_path))
