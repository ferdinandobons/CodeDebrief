from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import asdict, dataclass
from importlib import metadata
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class RuntimeDependency:
    package: str
    import_name: str
    purpose: str


@dataclass(frozen=True, slots=True)
class MissingDependency:
    package: str
    import_name: str
    purpose: str


@dataclass(frozen=True, slots=True)
class LanguageCapabilitySummary:
    supported_languages: list[str]
    feature_count: int
    limitation_note_count: int
    contract: str


@dataclass(frozen=True, slots=True)
class LegacyMcpConfig:
    path: str
    server: str
    reason: str
    repair_hint: str


@dataclass(frozen=True, slots=True)
class DoctorReport:
    ok: bool
    executable: str
    package_version: str
    package_location: str
    missing_dependencies: list[MissingDependency]
    repair_command: str
    language_capabilities: LanguageCapabilitySummary
    legacy_mcp_configs: list[LegacyMcpConfig]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["missing_dependencies"] = [asdict(item) for item in self.missing_dependencies]
        payload["legacy_mcp_configs"] = [asdict(item) for item in self.legacy_mcp_configs]
        return payload


RUNTIME_DEPENDENCIES = (
    RuntimeDependency("jsonschema", "jsonschema", "artifact validation"),
    RuntimeDependency("tree-sitter", "tree_sitter", "parser runtime"),
    RuntimeDependency("tree-sitter-typescript", "tree_sitter_typescript", "TypeScript/JavaScript"),
    RuntimeDependency("tree-sitter-c", "tree_sitter_c", "C"),
    RuntimeDependency("tree-sitter-c-sharp", "tree_sitter_c_sharp", "C#"),
    RuntimeDependency("tree-sitter-go", "tree_sitter_go", "Go"),
    RuntimeDependency("tree-sitter-java", "tree_sitter_java", "Java"),
    RuntimeDependency("tree-sitter-php", "tree_sitter_php", "PHP"),
    RuntimeDependency("tree-sitter-cpp", "tree_sitter_cpp", "C++"),
    RuntimeDependency("tree-sitter-ruby", "tree_sitter_ruby", "Ruby"),
    RuntimeDependency("tree-sitter-rust", "tree_sitter_rust", "Rust"),
)


def doctor_report(root: Path) -> DoctorReport:
    missing = [
        MissingDependency(item.package, item.import_name, item.purpose)
        for item in RUNTIME_DEPENDENCIES
        if importlib.util.find_spec(item.import_name) is None
    ]
    legacy_mcp_configs = _legacy_mcp_configs(root.resolve())
    return DoctorReport(
        ok=not missing and not legacy_mcp_configs,
        executable=sys.executable,
        package_version=_package_version(),
        package_location=_package_location(),
        missing_dependencies=missing,
        repair_command=_repair_command(root),
        language_capabilities=_language_capability_summary(),
        legacy_mcp_configs=legacy_mcp_configs,
    )


def render_doctor(report: DoctorReport) -> str:
    capabilities = report.language_capabilities
    lines = [
        f"CodeDebrief doctor {'OK' if report.ok else 'FAILED'}",
        f"Python: {report.executable}",
        f"Package: codedebrief {report.package_version}",
    ]
    if report.package_location:
        lines.append(f"Location: {report.package_location}")
    lines.append(
        "Language capabilities: "
        f"{len(capabilities.supported_languages)} language ids, "
        f"{capabilities.feature_count} feature flags, "
        f"{capabilities.limitation_note_count} limitation notes"
    )
    lines.append(f"Capability contract: {capabilities.contract}")
    if report.missing_dependencies:
        lines.append("")
        lines.append("Missing runtime dependencies:")
        lines.extend(
            f"- {item.package} (import {item.import_name}) for {item.purpose}"
            for item in report.missing_dependencies
        )
        lines.append("")
        lines.append("Repair this interpreter with:")
        lines.append(f"  {report.repair_command}")
    else:
        lines.append("All runtime parser dependencies are importable.")
    if report.legacy_mcp_configs:
        lines.append("")
        lines.append("Legacy LogicChart MCP configs detected:")
        lines.extend(
            f"- {item.path}: {item.server} ({item.reason})" for item in report.legacy_mcp_configs
        )
        lines.append("")
        lines.append("Repair:")
        lines.append("  Run `codedebrief setup-agent <target>` for the affected agent target.")
    return "\n".join(lines)


def render_doctor_json(report: DoctorReport) -> str:
    return json.dumps(report.to_dict(), indent=2)


def _package_version() -> str:
    try:
        return metadata.version("codedebrief")
    except metadata.PackageNotFoundError:
        return "not installed"


def _package_location() -> str:
    try:
        distribution = metadata.distribution("codedebrief")
    except metadata.PackageNotFoundError:
        return ""
    direct_url = distribution.read_text("direct_url.json")
    if direct_url:
        try:
            payload = json.loads(direct_url)
        except json.JSONDecodeError:
            return ""
        url = payload.get("url")
        if isinstance(url, str) and url.startswith("file://"):
            return url.removeprefix("file://")
    return ""


def _repair_command(root: Path) -> str:
    project_root = root.resolve()
    if _looks_like_codedebrief_checkout(project_root):
        return f"{sys.executable} -m pip install -e {project_root}"
    if _looks_like_codedebrief_checkout(Path.cwd()):
        return f"{sys.executable} -m pip install -e {Path.cwd().resolve()}"
    return (
        f"{sys.executable} -m pip install --force-reinstall "
        "git+https://github.com/ferdinandobons/CodeDebrief.git"
    )


def _looks_like_codedebrief_checkout(path: Path) -> bool:
    return (path / "pyproject.toml").exists() and (path / "src" / "codedebrief" / "cli.py").exists()


def _language_capability_summary() -> LanguageCapabilitySummary:
    from codedebrief.analysis.registry import language_capability_matrix

    matrix = language_capability_matrix()
    feature_names: set[str] = set()
    limitation_note_count = 0
    for payload in matrix.values():
        features = payload.get("features")
        if isinstance(features, dict):
            feature_names.update(str(name) for name in features)
        limitations = payload.get("limitations")
        if isinstance(limitations, dict):
            limitation_note_count += len(limitations)
    return LanguageCapabilitySummary(
        supported_languages=sorted(matrix),
        feature_count=len(feature_names),
        limitation_note_count=limitation_note_count,
        contract="metadata.language_capabilities; smoke-tested by tests/test_registry.py",
    )


def _legacy_mcp_configs(root: Path) -> list[LegacyMcpConfig]:
    configs: list[LegacyMcpConfig] = []
    codex_config = root / ".codex" / "config.toml"
    if codex_config.exists():
        try:
            text = codex_config.read_text(encoding="utf-8")
        except OSError:
            text = ""
        if "logicchart:mcp-config:start" in text or "[mcp_servers.logicchart]" in text:
            configs.append(
                LegacyMcpConfig(
                    path=str(codex_config),
                    server="logicchart",
                    reason="old MCP server name points agents at LogicChart artifacts",
                    repair_hint="codedebrief setup-agent codex",
                )
            )
    for path in (
        root / ".mcp.json",
        root / ".gemini" / "settings.json",
        root / ".cursor" / "mcp.json",
    ):
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        servers = payload.get("mcpServers") if isinstance(payload, dict) else None
        if isinstance(servers, dict) and "logicchart" in servers:
            configs.append(
                LegacyMcpConfig(
                    path=str(path),
                    server="logicchart",
                    reason="old MCP server name can shadow the CodeDebrief MCP server",
                    repair_hint="codedebrief setup-agent all",
                )
            )
    return configs
