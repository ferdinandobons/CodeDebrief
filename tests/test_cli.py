import json
from pathlib import Path

import pytest

from codedebrief.cli import build_parser, main

REMOVED_AGENT_COMMAND_SNIPPETS = (
    "codedebrief query",
    "codedebrief impact",
    "codedebrief explain",
    "codedebrief navigate",
    "codedebrief snapshot",
    "codedebrief llm",
    "codedebrief enrich",
    "--api-key-stdin",
)


def _assert_current_agent_instructions(content: str) -> None:
    assert "Prefer the CodeDebrief MCP `agent_context` tool" in content
    assert "returned `workflow_slice`" in content
    assert "When the user asks to show a workflow, flusso, visual flow, canvas" in content
    assert "canonical Mermaid visual" in content
    assert "`snapshot.svg`" in content
    assert "`include_svg=false`" in content
    assert "`artifact.mermaid_path`" in content
    assert "`artifact.mermaid_markdown_path`" in content
    assert "`artifact.mermaid_open_command`" in content
    assert "Mermaid would appear as a raw code block" in content
    assert "Do not paste a long Mermaid code block as the primary visual" in content
    assert "raw or copyable Mermaid" in content
    assert "Do not render\n   `snapshot.svg` inline by default" in content
    assert "`workflow_slice.presentation.canonical_visual.diagram` exactly" in content
    assert "top-to-bottom" in content
    assert "vertical/top-to-bottom" in content
    assert "horizontal" in content
    assert "compact horizontal overview" in content
    assert "full returned `workflow_slice`" in content
    assert "clearest useful subset" in content
    assert "too large, saved externally, truncated" in content
    assert "smaller `token_budget`" in content
    assert "narrower `flow_id`, `symbol`,\n   `current_file`, or `scope`" in content
    assert "hand-building a\n   diagram" in content
    assert "bounded summary" in content
    assert "can be expanded" in content
    assert "short high-level written flow" in content
    assert "happy path first" in content
    assert "only the branches needed by the request" in content
    assert "language-friendly" in content
    assert "technical block labels and the high-level written flow" in content
    assert "language of the user's request" in content
    assert "simplify labels and\n   written flow" in content
    assert "omitted nodes/branches/adjacent flows" in content
    assert "related area" in content
    assert "synthesize a new Mermaid" in content
    assert "Do not read source\n   files to rebuild" in content
    assert "must not change displayed\n   nodes, edges, labels, or branches" in content
    assert "instead of creating\n   a replacement Mermaid diagram" in content
    assert "absent" in content
    assert "`workflow_slice` payload" in content
    assert "raw JSON" in content
    assert "YAML" in content
    assert "explicitly requested" in content
    assert "requested" in content
    assert "`expand_slice`, `workflow_path`, `snapshot_slice`" in content
    assert "codedebrief view ..." in content
    assert "codedebrief <command> --help" in content
    assert "provider keys" in content
    assert "`codedebrief setup <target>` updates only that target's files" in content
    assert "After code or workflow-relevant changes" in content
    assert "artifacts as part of done" in content
    assert "run `codedebrief update` before finalizing or\n   committing" in content
    assert "codedebrief validate --check-sync" in content
    for snippet in REMOVED_AGENT_COMMAND_SNIPPETS:
        assert snippet not in content


def _assert_codedebrief_skill(content: str) -> None:
    assert content.startswith("---\nname: codedebrief\n")
    assert "`agent_context`" in content
    assert "include_visual=true" in content
    assert "artifacts as part of done for workflow-relevant changes" in content
    assert "MCP `update_codedebrief`" in content
    assert "`codedebrief update`" in content
    assert "`codedebrief validate --check-sync`" in content
    assert "`snapshot_slice`" in content
    assert "`include_svg=false`" in content
    assert "`artifact.mermaid_path`" in content
    assert "`artifact.mermaid_markdown_path`" in content
    assert "`artifact.mermaid_open_command`" in content
    assert "Mermaid would appear as a raw code\n   block" in content
    assert "Do not paste a long\n   Mermaid code block as the primary visual" in content
    assert "raw or\n   copyable Mermaid" in content
    assert "Do not render `snapshot.svg` inline by default" in content
    assert "`workflow_slice.presentation.canonical_visual.diagram` exactly" in content
    assert "top-to-bottom" in content
    assert "vertical/top-to-bottom" in content
    assert "horizontal" in content
    assert "compact horizontal overview" in content
    assert "`diagram_hash`" in content
    assert "stable token" in content
    assert "full returned `workflow_slice`" in content
    assert "clearest useful subset" in content
    assert "too large, saved externally, truncated" in content
    assert "smaller\n   `token_budget`" in content
    assert "hand-building a diagram" in content
    assert "low-signal implementation node" in content
    assert "bounded summary" in content
    assert 'short "High-level flow" section' in content
    assert "compact\n   happy-path walkthrough" in content
    assert "human-friendly" in content
    assert "language-friendly" in content
    assert "block labels and the high-level written flow" in content
    assert "language of\n   the user's request" in content
    assert "simplify the labels and\n   written flow" in content
    assert "expand omitted" in content
    assert "related area or deeper path" in content
    assert "synthesize a new Mermaid" in content
    assert "Do not read source files to rebuild" in content
    assert "must not change the displayed nodes, edges, labels, or branches" in content
    assert "never create a replacement Mermaid diagram" in content
    assert "absent" in content
    assert "`workflow_slice` payload" in content
    assert "`viewer_targets` command" in content
    assert "`workflow_slice.presentation` as supporting context" in content
    assert "Do not answer\n   with raw JSON or YAML" in content


def test_top_level_help_prioritizes_flag_light_quickstart() -> None:
    help_text = build_parser().format_help()

    assert "Quick start:" in help_text
    assert "codedebrief setup codex" in help_text
    assert "codedebrief update\n  codedebrief view" in help_text
    assert "codedebrief doctor" in help_text
    assert "{setup,update,view,validate,doctor,mcp}" in help_text
    assert "setup-agent" not in help_text
    for removed in (
        "analyze",
        "install",
        "init",
        "llm",
        "enrich",
        "query",
        "impact",
        "explain",
        "navigate",
        "snapshot",
    ):
        assert f"    {removed} " not in help_text
    assert "Add --help after any command" in help_text


def test_command_help_documents_simple_examples(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        build_parser().parse_args(["setup", "--help"])

    assert exc_info.value.code == 0
    setup_help = capsys.readouterr().out
    assert "Examples:" in setup_help
    assert "codedebrief setup codex" in setup_help
    assert "codedebrief setup claude --source backend/ frontend/" in setup_help
    assert "codedebrief setup claude ../my-app --source backend-api frontend/src" in setup_help
    assert "ask your coding agent ordinary questions" in setup_help


def test_update_nonexistent_path_errors_clearly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "does-not-exist"
    # A missing path must fail with a clear message, not silently report 0 flows.
    assert main(["update", str(missing), "--full"]) == 1
    captured = capsys.readouterr()
    assert "does not exist" in captured.err
    assert "Analyzed 0 files" not in captured.out


def test_cli_catches_oserror_instead_of_leaking_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "main.py").write_text("def f():\n    return 1\n", encoding="utf-8")

    import codedebrief.cli as cli_module

    def boom(*_args: object, **_kwargs: object) -> int:
        raise PermissionError("Permission denied")

    monkeypatch.setattr(cli_module, "_analyze", boom)
    # A PermissionError (an OSError subclass) surfaces as a clean failure, not a traceback.
    assert main(["update", str(tmp_path), "--full"]) == 1
    output = capsys.readouterr().err
    assert "CodeDebrief command FAILED" in output
    assert "Error: Permission denied" in output
    assert "Next steps:" in output


def test_update_full_flag_dispatches_to_full_analysis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import codedebrief.cli as cli_module

    calls: list[dict[str, object]] = []

    def fake_analyze(root: Path, **kwargs: object) -> int:
        calls.append({"root": root, **kwargs})
        return 0

    monkeypatch.setattr(cli_module, "_analyze", fake_analyze)

    assert main(["update", str(tmp_path), "--full", "--no-html"]) == 0
    assert calls == [
        {
            "root": tmp_path,
            "full": True,
            "include_html": False,
            "profile": None,
        }
    ]


def test_cli_update_and_view(tmp_path: Path, capsys: object) -> None:
    source = tmp_path / "main.py"
    source.write_text(
        """
def authorize(user):
    if user.role == "admin":
        return True
    return False
""",
        encoding="utf-8",
    )

    assert main(["update", str(tmp_path), "--full"]) == 0
    assert (tmp_path / "codedebrief-out" / "codedebrief.json").exists()
    output = capsys.readouterr().out
    assert "CodeDebrief update" in output
    assert "Status: OK" in output
    assert "Summary:" in output
    assert "Artifacts:" in output
    assert "Next steps:" in output
    assert main(["update", str(tmp_path)]) == 0
    assert main(["view", str(tmp_path), "--render-only"]) == 0
    output = capsys.readouterr().out
    assert "CodeDebrief view" in output
    assert "Status: OK" in output
    assert "Next steps:" in output


@pytest.mark.parametrize(
    "command",
    [
        "setup-agent",
        "analyze",
        "install",
        "init",
        "llm",
        "enrich",
        "query",
        "impact",
        "explain",
        "navigate",
        "snapshot",
    ],
)
def test_removed_agent_commands_are_not_public_cli(command: str) -> None:
    with pytest.raises(SystemExit) as exc_info:
        build_parser().parse_args([command])

    assert exc_info.value.code == 2


def test_cli_validate_and_profiles(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "src" / "codedebrief" / "main.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "def analyze_source(path):\n    if path:\n        return path\n    return None\n",
        encoding="utf-8",
    )

    assert main(["update", str(tmp_path), "--profile", "self", "--full", "--no-html"]) == 0
    assert (tmp_path / "codedebrief-out" / "self" / "codedebrief.json").exists()

    assert main(["validate", str(tmp_path), "--profile", "self"]) == 0
    assert "validation OK" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("agent", "instruction_path", "skill_path", "mcp_path", "display"),
    [
        (
            "codex",
            Path("AGENTS.md"),
            Path(".agents/skills/codedebrief/SKILL.md"),
            Path(".codex/config.toml"),
            "Codex",
        ),
        (
            "claude",
            Path("CLAUDE.md"),
            Path(".claude/skills/codedebrief/SKILL.md"),
            Path(".mcp.json"),
            "Claude",
        ),
        (
            "gemini",
            Path("GEMINI.md"),
            Path(".gemini/skills/codedebrief/SKILL.md"),
            Path(".gemini/settings.json"),
            "Gemini",
        ),
        (
            "cursor",
            Path(".cursor/rules/codedebrief.mdc"),
            None,
            Path(".cursor/mcp.json"),
            "Cursor",
        ),
    ],
)
def test_cli_setup_agent_can_write_config_instructions_mcp_and_artifacts(
    agent: str,
    instruction_path: Path,
    skill_path: Path | None,
    mcp_path: Path | None,
    display: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "main.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    instruction_paths = [
        Path("AGENTS.md"),
        Path("CLAUDE.md"),
        Path("GEMINI.md"),
        Path(".cursor/rules/codedebrief.mdc"),
    ]
    skill_paths = [
        Path(".agents/skills/codedebrief/SKILL.md"),
        Path(".claude/skills/codedebrief/SKILL.md"),
        Path(".gemini/skills/codedebrief/SKILL.md"),
    ]

    assert main(["setup", agent, str(tmp_path), "--no-html"]) == 0
    assert (tmp_path / "codedebrief.toml").exists()
    assert (tmp_path / instruction_path).exists()
    for path in instruction_paths:
        if path == instruction_path:
            assert (tmp_path / path).exists()
            _assert_current_agent_instructions((tmp_path / path).read_text(encoding="utf-8"))
        else:
            assert not (tmp_path / path).exists()
    for path in skill_paths:
        if path == skill_path:
            assert (tmp_path / path).exists()
            _assert_codedebrief_skill((tmp_path / path).read_text(encoding="utf-8"))
        else:
            assert not (tmp_path / path).exists()
    if mcp_path is not None:
        assert (tmp_path / mcp_path).exists()
    else:
        assert not (tmp_path / ".codex" / "config.toml").exists()
        assert not (tmp_path / ".mcp.json").exists()
        assert not (tmp_path / ".cursor" / "mcp.json").exists()
    assert (tmp_path / "codedebrief-out" / "codedebrief.json").exists()
    assert (tmp_path / "codedebrief-out" / "codedebrief.md").exists()
    agents_text = (tmp_path / instruction_path).read_text(encoding="utf-8")
    _assert_current_agent_instructions(agents_text)
    output = capsys.readouterr().out
    assert "Created" in output
    assert "Status: OK - CodeDebrief is ready for your coding agent." in output
    assert "Next steps:" in output
    assert "CodeDebrief doctor OK" in output
    assert "CodeDebrief validation OK" in output
    assert f"CodeDebrief agent setup complete for {display}" in output

    assert main(["setup", agent, str(tmp_path), "--no-html"]) == 0
    assert "already up to date" in capsys.readouterr().out


def test_cli_setup_source_roots_limit_initial_analysis(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    backend = tmp_path / "backend"
    frontend = tmp_path / "frontend"
    scratch = tmp_path / "scratch"
    backend.mkdir()
    frontend.mkdir()
    scratch.mkdir()
    (backend / "api.py").write_text("def api():\n    return 1\n", encoding="utf-8")
    (frontend / "app.ts").write_text("export function app() { return 1; }\n", encoding="utf-8")
    (scratch / "ignored.py").write_text("def ignored():\n    return 1\n", encoding="utf-8")

    assert (
        main(["setup", "claude", str(tmp_path), "--source", "backend", "frontend", "--no-html"])
        == 0
    )

    config_text = (tmp_path / "codedebrief.toml").read_text(encoding="utf-8")
    artifact = json.loads((tmp_path / "codedebrief-out" / "codedebrief.json").read_text())
    analyzed_paths = {item["path"] for item in artifact["files"]}
    output = capsys.readouterr().out

    assert 'source_roots = ["backend", "frontend"]' in config_text
    assert analyzed_paths == {"backend/api.py", "frontend/app.ts"}
    assert "- Source roots: backend, frontend" in output
    assert "Summary: 2 files" in output


def test_cli_doctor_reports_active_install(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["doctor", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["package_version"] != "not installed"
    assert payload["missing_dependencies"] == []
    assert "python" in payload["language_capabilities"]["supported_languages"]
    assert "typescript" in payload["language_capabilities"]["supported_languages"]
    assert payload["language_capabilities"]["feature_count"] >= 10
    assert payload["language_capabilities"]["limitation_note_count"] > 0
