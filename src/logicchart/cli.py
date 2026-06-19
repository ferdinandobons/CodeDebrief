from __future__ import annotations

import argparse
import getpass
import json
import sys
import webbrowser
from collections.abc import Sequence
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from textwrap import dedent
from typing import Any

from logicchart import __version__
from logicchart.analysis import ProjectAnalyzer
from logicchart.artifacts import load_model, output_paths, write_artifacts
from logicchart.config import BUILTIN_PROFILES, LogicChartConfig
from logicchart.doctor import doctor_report, render_doctor, render_doctor_json
from logicchart.install import install_all
from logicchart.llm_config import (
    PROVIDERS,
    config_to_json,
    get_provider,
    logicchart_env_path,
    render_current_config,
    render_providers_text,
    render_setup_text,
    write_logicchart_env,
)
from logicchart.llm_enrich import (
    EnrichmentOptions,
    build_enrichment_preview,
    render_enrichment_preview,
    send_enrichment_request,
    write_enrichment_annotations,
)
from logicchart.quality import render_quality
from logicchart.render.html import render_html
from logicchart.validation import validate_logicchart


class LogicChartHelpFormatter(argparse.RawDescriptionHelpFormatter):
    pass


class LogicChartArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("formatter_class", LogicChartHelpFormatter)
        super().__init__(*args, **kwargs)


def build_parser() -> argparse.ArgumentParser:
    parser = LogicChartArgumentParser(
        prog="logicchart",
        description="Turn a polyglot codebase into navigable decision flowcharts.",
        epilog=dedent(
            """\
            Quick start:
              logicchart update
              logicchart view
              logicchart validate
              logicchart doctor

            Optional setup:
              logicchart install

            Add --help after any command for focused examples and advanced options.
            """
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
        parser_class=LogicChartArgumentParser,
    )

    analyze = subparsers.add_parser(
        "analyze",
        help="Analyze a source folder.",
        description="Analyze the current project and write JSON, Markdown, and HTML artifacts.",
        epilog=dedent(
            """\
            Examples:
              logicchart analyze
              logicchart analyze ../my-app
              logicchart analyze --full

            The simple command is enough for first use. Use --full when you intentionally
            want to bypass the incremental cache.
            """
        ),
    )
    analyze.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project folder to analyze. Defaults to the current directory.",
    )
    analyze.add_argument("--full", action="store_true", help="Ignore the incremental cache.")
    analyze.add_argument("--no-html", action="store_true", help="Skip the local HTML artifact.")
    _add_profile_argument(analyze)
    analyze.add_argument(
        "--include-gaps",
        action="store_true",
        help="Expand the review-only (POTENTIAL_GAP) findings section in the Markdown report.",
    )

    update = subparsers.add_parser(
        "update",
        help="Incrementally refresh changed source files.",
        description="Refresh existing LogicChart artifacts after source changes.",
        epilog=dedent(
            """\
            Examples:
              logicchart update
              logicchart update ../my-app
              logicchart update --full

            Use update during normal development. Use --full after analyzer upgrades or
            when cached file models should be ignored.
            """
        ),
    )
    update.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project folder to refresh. Defaults to the current directory.",
    )
    update.add_argument("--full", action="store_true", help="Ignore the incremental cache.")
    update.add_argument("--no-html", action="store_true", help="Skip the local HTML artifact.")
    update.add_argument(
        "--include-gaps",
        action="store_true",
        help="Expand review-only (POTENTIAL_GAP) findings in Markdown.",
    )
    _add_profile_argument(update)

    view = subparsers.add_parser(
        "view",
        help="Generate and serve the interactive flowchart.",
        description="Open the local interactive decision-flowchart viewer.",
        epilog=dedent(
            """\
            Examples:
              logicchart view
              logicchart view ../my-app
              logicchart view --port 8771

            The viewer is local-only. Use --render-only for CI or artifact generation.
            """
        ),
    )
    view.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project folder to view. Defaults to the current directory.",
    )
    view.add_argument("--port", type=int, default=8765, help="Local server port.")
    view.add_argument("--no-open", action="store_true", help="Serve without opening a browser.")
    view.add_argument(
        "--render-only",
        action="store_true",
        help="Write logic-flow.html without starting a server.",
    )
    _add_profile_argument(view)

    install = subparsers.add_parser(
        "install",
        help="Install persistent LogicChart instructions for coding agents.",
        description="Write agent instructions that teach coding agents how to use LogicChart.",
        epilog=dedent(
            """\
            Examples:
              logicchart install
              logicchart install --platform codex
              logicchart install --mcp-config codex

            The simple command installs instruction blocks only. Add --mcp-config when
            you also want project-scoped MCP configuration.
            """
        ),
    )
    install.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project folder to update. Defaults to the current directory.",
    )
    install.add_argument(
        "--platform",
        choices=["all", "codex", "claude", "cursor", "gemini"],
        default="all",
        help="Instruction target to update.",
    )
    install.add_argument(
        "--mcp-config",
        choices=["none", "all", "codex", "claude", "cursor"],
        default="none",
        nargs="?",
        const="all",
        help="Also install project-scoped MCP config for Codex, Claude Code, or Cursor.",
    )

    llm = subparsers.add_parser(
        "llm",
        help="Configure optional local LLM enrichment settings.",
        description="Configure optional local credentials for annotation enrichment.",
        epilog=dedent(
            """\
            Examples:
              logicchart llm providers
              logicchart llm setup
              logicchart llm show

            Setup only writes .env.logicchart. It never calls a provider.
            """
        ),
    )
    llm_subparsers = llm.add_subparsers(
        dest="llm_command",
        required=True,
        parser_class=LogicChartArgumentParser,
    )
    llm_providers = llm_subparsers.add_parser(
        "providers", help="List curated provider/model presets."
    )
    llm_providers.add_argument(
        "--json", action="store_true", dest="json_output", help="Emit JSON output."
    )

    llm_setup = llm_subparsers.add_parser(
        "setup",
        help="Write a local .env.logicchart provider configuration.",
        description="Choose a provider/model and store the API key in .env.logicchart.",
        epilog=dedent(
            """\
            Examples:
              logicchart llm setup
              logicchart llm setup --provider qwen --model qwen3-coder-plus
              printf '%s' "$DEEPSEEK_API_KEY" | logicchart llm setup --api-key-stdin

            The default provider is DeepSeek v4. Interactive setup is the simplest path;
            --api-key-stdin is safer for scripts and shared shell history.
            """
        ),
    )
    llm_setup.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project folder that will receive .env.logicchart.",
    )
    llm_setup.add_argument(
        "--provider",
        choices=[provider.id for provider in PROVIDERS],
        default="deepseek",
        help="LLM provider preset to configure. Defaults to DeepSeek v4.",
    )
    llm_setup.add_argument(
        "--model",
        default=None,
        help="Provider model id. Defaults to the provider's recommended preset.",
    )
    llm_setup.add_argument(
        "--base-url",
        default=None,
        help="Override the provider base URL when using a region-specific endpoint.",
    )
    llm_setup.add_argument(
        "--api-key",
        default=None,
        help="API key to write. Prefer --api-key-stdin for shell-history safety.",
    )
    llm_setup.add_argument(
        "--api-key-stdin",
        action="store_true",
        help="Read the API key from stdin.",
    )
    llm_setup.add_argument(
        "--env-file",
        default=None,
        help="Path to the dedicated env file. Defaults to .env.logicchart under PATH.",
    )
    llm_setup.add_argument(
        "--json", action="store_true", dest="json_output", help="Emit JSON output."
    )

    llm_show = llm_subparsers.add_parser(
        "show", help="Show the current local LLM configuration with secrets masked."
    )
    llm_show.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project folder containing .env.logicchart.",
    )
    llm_show.add_argument(
        "--env-file",
        default=None,
        help="Path to the dedicated env file. Defaults to .env.logicchart under PATH.",
    )
    llm_show.add_argument(
        "--json", action="store_true", dest="json_output", help="Emit JSON output."
    )

    enrich = subparsers.add_parser(
        "enrich",
        help="Preview or run optional LLM annotation enrichment.",
        description="Preview the bounded enrichment payload locally, or explicitly send it.",
        epilog=dedent(
            """\
            Examples:
              logicchart enrich
              logicchart enrich --scope backend
              logicchart enrich --send

            Without --send this is a local preview and no provider call is made.
            """
        ),
    )
    enrich.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project folder containing logicchart-out/logic-flow.json.",
    )
    enrich.add_argument("--scope", default=None, help="Restrict enrichment to one scope.")
    enrich.add_argument(
        "--flow",
        action="append",
        default=[],
        help="Restrict enrichment to a flow id, symbol, or name.",
    )
    enrich.add_argument(
        "--finding",
        action="append",
        default=[],
        help="Restrict enrichment to a finding id.",
    )
    enrich.add_argument(
        "--max-flows",
        type=int,
        default=12,
        help="Maximum selected flows to include in the provider payload.",
    )
    enrich.add_argument(
        "--max-nodes-per-flow",
        type=int,
        default=18,
        help="Maximum nodes per selected flow to include in the provider payload.",
    )
    enrich.add_argument(
        "--max-findings",
        type=int,
        default=20,
        help="Maximum selected findings to include in the provider payload.",
    )
    enrich.add_argument(
        "--env-file",
        default=None,
        help="Path to the dedicated env file. Defaults to .env.logicchart under PATH.",
    )
    enrich.add_argument(
        "--send",
        action="store_true",
        help="Call the configured provider and write validated logic-annotations.json.",
    )
    enrich.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the bounded enrichment payload locally without calling a provider.",
    )
    enrich.add_argument(
        "--preview",
        action="store_true",
        help="Alias for --dry-run. This is also the default when --send is omitted.",
    )
    enrich.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Provider request timeout in seconds when --send is used.",
    )
    _add_profile_argument(enrich)
    enrich.add_argument("--json", action="store_true", dest="json_output", help="Emit JSON output.")

    init = subparsers.add_parser("init", help="Create a starter LogicChart configuration.")
    init.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project folder where logicchart.toml should be created.",
    )

    validate = subparsers.add_parser(
        "validate",
        help="Validate the generated LogicChart model.",
        description="Validate generated artifacts and optional quality/annotation checks.",
        epilog=dedent(
            """\
            Examples:
              logicchart validate
              logicchart validate --check-sync
              logicchart validate --quality
            """
        ),
    )
    validate.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project folder containing generated LogicChart artifacts.",
    )
    validate.add_argument(
        "--check-sync",
        action="store_true",
        help="Re-analyze sources and fail if logic-flow.json is stale.",
    )
    validate.add_argument(
        "--json", action="store_true", dest="json_output", help="Emit JSON output."
    )
    validate.add_argument(
        "--quality",
        action="store_true",
        help="Include deterministic analysis-quality metrics in the report.",
    )
    validate.add_argument(
        "--annotations",
        action="store_true",
        help="Include optional logic-annotations.json sidecar validation status.",
    )
    validate.add_argument(
        "--max-skipped-files",
        type=int,
        help="Fail validation when skipped-file count exceeds this value.",
    )
    validate.add_argument(
        "--max-parse-warnings",
        type=int,
        help="Fail validation when parse-warning count exceeds this value.",
    )
    validate.add_argument(
        "--min-call-resolution",
        type=float,
        help="Fail validation when call-resolution rate is below this 0..1 value.",
    )
    validate.add_argument(
        "--max-generic-label-ratio",
        type=float,
        help="Fail validation when generic-label ratio exceeds this 0..1 value.",
    )
    _add_profile_argument(validate)

    doctor = subparsers.add_parser("doctor", help="Check the active LogicChart installation.")
    doctor.add_argument("path", nargs="?", default=".", help="Project folder to inspect.")
    doctor.add_argument("--json", action="store_true", dest="json_output", help="Emit JSON output.")

    mcp = subparsers.add_parser("mcp", help="Start the LogicChart MCP server over stdio.")
    mcp.add_argument("path", nargs="?", default=".", help="Project folder served over MCP.")
    _add_profile_argument(mcp)
    return parser


def _add_profile_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--profile",
        choices=BUILTIN_PROFILES,
        default=None,
        help=(
            "Use a built-in analysis profile: demo keeps the public example artifact, "
            "self maps LogicChart internals, project maps the whole checkout."
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "analyze":
            return _analyze(
                Path(args.path),
                full=args.full,
                include_html=not args.no_html,
                include_gaps=args.include_gaps,
                profile=args.profile,
            )
        if args.command == "update":
            return _analyze(
                Path(args.path),
                full=args.full,
                include_html=not args.no_html,
                include_gaps=args.include_gaps,
                profile=args.profile,
            )
        if args.command == "view":
            return _view(
                Path(args.path),
                args.port,
                not args.no_open,
                args.render_only,
                args.profile,
            )
        if args.command == "install":
            return _install(Path(args.path), args.platform, args.mcp_config)
        if args.command == "llm":
            return _llm(args)
        if args.command == "enrich":
            return _enrich(args)
        if args.command == "init":
            return _init(Path(args.path))
        if args.command == "validate":
            return _validate(
                Path(args.path),
                args.check_sync,
                args.json_output,
                args.annotations,
                args.quality,
                _quality_thresholds(args),
                args.profile,
            )
        if args.command == "doctor":
            return _doctor(Path(args.path), args.json_output)
        if args.command == "mcp":
            from logicchart.mcp_server import run_mcp

            config = LogicChartConfig.load(Path(args.path).resolve(), profile=args.profile)
            run_mcp(Path(args.path), config)
            return 0
    except (OSError, RuntimeError, ValueError, SyntaxError) as error:
        # OSError subsumes FileNotFoundError/PermissionError, so a missing path or a
        # permission-denied write surfaces as a clean message instead of a raw traceback.
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


def _llm(args: argparse.Namespace) -> int:
    if args.llm_command == "providers":
        if args.json_output:
            print(
                json.dumps(
                    {
                        "preferred_provider": "deepseek",
                        "providers": [provider.to_dict() for provider in PROVIDERS],
                    },
                    indent=2,
                )
            )
        else:
            print(render_providers_text())
        return 0

    if args.llm_command == "show":
        env_path = logicchart_env_path(Path(args.path).resolve(), args.env_file)
        print(
            json.dumps(config_to_json(env_path), indent=2)
            if args.json_output
            else render_current_config(env_path)
        )
        return 0

    if args.llm_command == "setup":
        root = Path(args.path).resolve()
        provider = get_provider(args.provider)
        model = args.model or provider.default_model
        if not model.strip():
            raise ValueError("LLM model id cannot be empty.")
        api_key = _read_api_key(args)
        env_path = logicchart_env_path(root, args.env_file)
        values = write_logicchart_env(
            env_path,
            provider=provider,
            model=model.strip(),
            api_key=api_key,
            base_url=args.base_url,
        )
        if args.json_output:
            payload = {
                "env_file": str(env_path),
                "provider": values["LOGICCHART_LLM_PROVIDER"],
                "model": values["LOGICCHART_LLM_MODEL"],
                "base_url": values["LOGICCHART_LLM_BASE_URL"],
                "api_format": values["LOGICCHART_LLM_API_FORMAT"],
                "api_key": "<set>",
                "provider_call_made": False,
            }
            print(json.dumps(payload, indent=2))
        else:
            print(render_setup_text(env_path, values))
        return 0

    raise ValueError(f"unknown llm command: {args.llm_command}")


def _enrich(args: argparse.Namespace) -> int:
    root = Path(args.path).resolve()
    if args.send and (args.dry_run or args.preview):
        raise ValueError("pass either --send or --dry-run/--preview, not both.")
    config = LogicChartConfig.load(root, profile=args.profile)
    model = load_model(root, config)
    options = EnrichmentOptions(
        scope=args.scope,
        flow_ids=tuple(args.flow),
        finding_ids=tuple(args.finding),
        max_flows=args.max_flows,
        max_nodes_per_flow=args.max_nodes_per_flow,
        max_findings=args.max_findings,
    )
    preview = build_enrichment_preview(root, model, config, options, args.env_file)

    if not args.send:
        output = (
            json.dumps(preview, indent=2)
            if args.json_output
            else render_enrichment_preview(preview)
        )
        print(output)
        return 0

    annotations = send_enrichment_request(preview, timeout=args.timeout)
    output_path = write_enrichment_annotations(root, model, config, annotations)
    payload = {
        "provider_call_made": True,
        "provider": preview["provider"],
        "model": preview["model"],
        "output": str(output_path),
        "model_hash": preview["model_hash"],
        "annotation_counts": {
            "flows": len(annotations.get("flows", {})),
            "nodes": len(annotations.get("nodes", {})),
            "findings": len(annotations.get("findings", {})),
            "scopes": len(annotations.get("scopes", {})),
        },
    }
    if args.json_output:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Wrote {output_path}")
        print(f"provider call made: true ({preview['provider']} / {preview['model']})")
    return 0


def _read_api_key(args: argparse.Namespace) -> str:
    if args.api_key and args.api_key_stdin:
        raise ValueError("pass only one of --api-key or --api-key-stdin.")
    if args.api_key_stdin:
        api_key = sys.stdin.read().strip()
    elif args.api_key:
        api_key = args.api_key.strip()
    elif sys.stdin.isatty():
        api_key = getpass.getpass("LLM API key: ").strip()
    else:
        raise ValueError("provide an API key with --api-key or --api-key-stdin.")

    if not api_key:
        raise ValueError("LLM API key cannot be empty.")
    return api_key


def _analyze(
    root: Path,
    *,
    full: bool,
    include_html: bool,
    include_gaps: bool = False,
    profile: str | None = None,
) -> int:
    if not root.exists():
        raise FileNotFoundError(f"path does not exist: {root}")
    root = root.resolve()
    config = LogicChartConfig.load(root, profile=profile)
    result = ProjectAnalyzer(root, config).analyze(full=full)
    json_path, markdown_path, html_path = write_artifacts(
        root,
        result.model,
        include_html=include_html,
        include_gaps=include_gaps,
        config=config,
    )
    findings = len(result.model.findings)
    print(
        f"Analyzed {len(result.model.files)} files: {len(result.model.flows)} flows, "
        f"{findings} finding{'s' if findings != 1 else ''}."
    )
    print(
        f"Incremental cache: {result.cache_hits} hits, {len(result.changed_files)} changed, "
        f"{len(result.deleted_files)} deleted."
    )
    if result.skipped_files:
        print(f"Skipped {len(result.skipped_files)} unparseable file(s):", file=sys.stderr)
        for relative, reason in result.skipped_files:
            print(f"  - {relative}: {reason}", file=sys.stderr)
    print(f"Wrote {json_path}")
    print(f"Wrote {markdown_path}")
    if html_path:
        print(f"Wrote {html_path}")
    return 0


def _view(
    root: Path,
    port: int,
    should_open: bool,
    render_only: bool,
    profile: str | None = None,
) -> int:
    root = root.resolve()
    config = LogicChartConfig.load(root, profile=profile)
    _, _, html_path = output_paths(root, config)
    model = load_model(root, config)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(render_html(model, source_root=root), encoding="utf-8")
    print(f"Wrote {html_path}")
    if render_only:
        return 0

    handler = partial(SimpleHTTPRequestHandler, directory=str(html_path.parent))
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    url = f"http://127.0.0.1:{port}/{html_path.name}"
    print(f"Serving LogicChart at {url}. Press Ctrl+C to stop.")
    if should_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def _validate(
    root: Path,
    check_sync: bool,
    json_output: bool,
    include_annotations: bool,
    include_quality: bool,
    quality_thresholds: dict[str, float | int] | None,
    profile: str | None = None,
) -> int:
    root = root.resolve()
    config = LogicChartConfig.load(root, profile=profile)
    report = validate_logicchart(
        root,
        config=config,
        check_sync=check_sync,
        include_annotations=include_annotations,
        include_quality=include_quality,
        quality_thresholds=quality_thresholds,
    )
    if json_output:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        status = "OK" if report.ok else "FAILED"
        print(f"LogicChart validation {status}: {report.artifact}")
        for warning in report.warnings:
            print(f"warning: {warning}")
        for error in report.errors:
            print(f"error: {error}", file=sys.stderr)
        if report.annotations is not None:
            status_text = report.annotations.get("status", "unknown")
            print(f"Annotations: {status_text}")
        if report.quality is not None:
            print(render_quality(report.quality))
    return 0 if report.ok else 1


def _quality_thresholds(args: argparse.Namespace) -> dict[str, float | int]:
    thresholds: dict[str, float | int] = {}
    if args.max_skipped_files is not None:
        thresholds["max_skipped_files"] = args.max_skipped_files
    if args.max_parse_warnings is not None:
        thresholds["max_parse_warnings"] = args.max_parse_warnings
    if args.min_call_resolution is not None:
        thresholds["min_call_resolution"] = args.min_call_resolution
    if args.max_generic_label_ratio is not None:
        thresholds["max_generic_label_ratio"] = args.max_generic_label_ratio
    return thresholds


def _install(root: Path, platform: str, mcp_config: str = "none") -> int:
    changed = install_all(root.resolve(), platform, mcp_config)
    if not changed:
        print("LogicChart agent instructions and MCP config are already up to date.")
        return 0
    for path in changed:
        print(f"Updated {path}")
    return 0


def _doctor(root: Path, json_output: bool) -> int:
    report = doctor_report(root)
    print(render_doctor_json(report) if json_output else render_doctor(report))
    return 0 if report.ok else 1


def _init(root: Path) -> int:
    root = root.resolve()
    config_path = root / "logicchart.toml"
    if config_path.exists():
        print(f"{config_path} already exists.")
        return 0
    config_path.write_text(
        """[logicchart]
source_roots = ["."]
exclude = []
exclude_dirs = []
# Defaults always prune dependency, VCS, cache, temp, and generated directories such as
# .git, node_modules, venv/.venv, dist/build/out/target, coverage, .next, .turbo,
# .svelte-kit, vendor, and logicchart-out. Add project-specific directories above.
include_public_functions = true
max_call_depth = 4
output_dir = "logicchart-out"
self_exclude = true
gated_detectors = false

[logicchart.entrypoints]
include = []
exclude = []

# Named macro-parts of the codebase (otherwise the top-level directory is the scope):
# [logicchart.scopes]
# backend = ["backend/**", "services/**"]
# frontend = ["frontend/**", "web/**"]
# edge = ["edge/**", "workers/**"]
""",
        encoding="utf-8",
    )
    print(f"Created {config_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
