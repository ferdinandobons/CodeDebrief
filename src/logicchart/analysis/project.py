from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from logicchart.analysis.discovery import discover_source_files, language_for
from logicchart.analysis.python import PythonAnalyzer
from logicchart.analysis.typescript import TypeScriptAnalyzer
from logicchart.config import LogicChartConfig
from logicchart.model import (
    Evidence,
    FileAnalysis,
    FileRecord,
    Finding,
    Flow,
    FlowNode,
    NodeKind,
    ProjectModel,
    Severity,
)
from logicchart.util import file_sha256, read_json, relpath, stable_id, write_json

CACHE_VERSION = "1"


@dataclass(slots=True)
class AnalysisResult:
    model: ProjectModel
    changed_files: list[str]
    deleted_files: list[str]
    cache_hits: int


class ProjectAnalyzer:
    def __init__(self, root: Path, config: LogicChartConfig | None = None) -> None:
        self.root = root.resolve()
        self.config = config or LogicChartConfig.load(self.root)
        self.cache_dir = self.root / ".logicchart" / "cache"
        self.index_path = self.cache_dir / "index.json"
        self.previous_generated_at: str | None = None
        self.python = PythonAnalyzer(self.root, self.config)
        self.typescript = TypeScriptAnalyzer(self.root, self.config)

    def analyze(self, *, full: bool = False) -> AnalysisResult:
        files = discover_source_files(self.root, self.config)
        previous_index = {} if full else self._load_index()
        current_paths = {relpath(path, self.root) for path in files}
        deleted_files = sorted(set(previous_index) - current_paths)
        analyses: list[FileAnalysis] = []
        changed_files: list[str] = []
        cache_hits = 0
        new_index: dict[str, dict[str, str]] = {}

        for path in files:
            relative = relpath(path, self.root)
            digest = file_sha256(path)
            cache_file = self.cache_dir / f"{stable_id(relative, length=24)}.json"
            cached = previous_index.get(relative)
            if not full and cached and cached.get("sha256") == digest and cache_file.exists():
                analysis = FileAnalysis.from_dict(read_json(cache_file))
                cache_hits += 1
            else:
                analysis = self._analyze_file(path)
                write_json(cache_file, analysis.to_dict())
                changed_files.append(relative)
            analyses.append(analysis)
            new_index[relative] = {"sha256": digest, "cache": cache_file.name}

        model = self._combine(analyses)
        if not full and not changed_files and not deleted_files and self.previous_generated_at:
            model.generated_at = self.previous_generated_at
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        write_json(
            self.index_path,
            {
                "cache_version": CACHE_VERSION,
                "generated_at": model.generated_at,
                "files": new_index,
            },
        )
        return AnalysisResult(
            model=model,
            changed_files=changed_files,
            deleted_files=deleted_files,
            cache_hits=cache_hits,
        )

    def _analyze_file(self, path: Path) -> FileAnalysis:
        language = language_for(path)
        if language == "python":
            return self.python.analyze(path)
        return self.typescript.analyze(path)

    def _load_index(self) -> dict[str, dict[str, str]]:
        if not self.index_path.exists():
            return {}
        data = read_json(self.index_path)
        if data.get("cache_version") != CACHE_VERSION:
            return {}
        generated_at = data.get("generated_at")
        self.previous_generated_at = str(generated_at) if generated_at else None
        file_data = data.get("files", {})
        return {
            str(path): {"sha256": str(item["sha256"]), "cache": str(item["cache"])}
            for path, item in file_data.items()
        }

    def _combine(self, analyses: list[FileAnalysis]) -> ProjectModel:
        flows = [flow for analysis in analyses for flow in analysis.flows]
        findings = [finding for analysis in analyses for finding in analysis.findings]
        self._link_calls(flows)
        self._link_tests(flows)
        findings.extend(self._find_inconsistent_decisions(flows))
        findings = _deduplicate_findings(findings)
        files = [
            FileRecord(
                path=analysis.path,
                language=analysis.language,
                sha256=analysis.sha256,
                flow_ids=[flow.id for flow in analysis.flows],
            )
            for analysis in analyses
        ]
        return ProjectModel(
            schema_version="1.0",
            generated_at=datetime.now(timezone.utc).isoformat(),
            root=".",
            flows=sorted(flows, key=lambda item: (not item.is_entrypoint, item.symbol)),
            findings=sorted(findings, key=lambda item: (item.severity.value, item.message)),
            files=files,
            metadata={
                "languages": sorted({item.language for item in analyses}),
                "entrypoint_count": sum(flow.is_entrypoint for flow in flows),
                "flow_count": len(flows),
                "finding_count": len(findings),
            },
        )

    def _link_calls(self, flows: list[Flow]) -> None:
        by_name: dict[str, list[Flow]] = {}
        for flow in flows:
            short = flow.symbol.split(":", 1)[-1].split(".")[-1]
            by_name.setdefault(short, []).append(flow)

        for flow in flows:
            for node in flow.nodes:
                if node.kind is not NodeKind.CALL:
                    continue
                candidates: list[Flow] = []
                for raw_call in node.metadata.get("calls", []):
                    short = str(raw_call).split(".")[-1]
                    candidates.extend(by_name.get(short, []))
                unique = {item.id: item for item in candidates if item.id != flow.id}
                if len(unique) != 1:
                    continue
                target = next(iter(unique.values()))
                node.metadata["target_flow"] = target.id
                node.metadata["target_symbol"] = target.symbol
                if target.id not in flow.calls:
                    flow.calls.append(target.id)
                if flow.id not in target.called_by:
                    target.called_by.append(flow.id)

    def _link_tests(self, flows: list[Flow]) -> None:
        by_id = {flow.id: flow for flow in flows}
        for flow in flows:
            if not flow.metadata.get("test"):
                continue
            for target_id in flow.calls:
                target = by_id.get(target_id)
                if target and flow.symbol not in target.tests:
                    target.tests.append(flow.symbol)

    def _find_inconsistent_decisions(self, flows: list[Flow]) -> list[Finding]:
        # Bucket comparable decisions by (language, domain). Language scoping keeps
        # cross-language closed sets apart (e.g. a Python `status` enum is never
        # compared against a TS `status` union), which removes the cross-language
        # false positive without changing same-language behavior.
        buckets: dict[tuple[str, str], list[tuple[Flow, FlowNode, set[str]]]] = {}
        for flow in flows:
            if flow.metadata.get("test"):
                continue
            for node in flow.nodes:
                if node.kind is not NodeKind.DECISION:
                    continue
                domain = str(node.metadata.get("domain", ""))
                values = {str(item) for item in node.metadata.get("values", []) if str(item)}
                if domain and values:
                    buckets.setdefault((flow.language, domain), []).append((flow, node, values))

        findings: list[Finding] = []
        for (_language, domain), decisions in buckets.items():
            all_values = set().union(*(values for _, _, values in decisions))
            if len(all_values) < 2:
                continue
            for flow, node, values in decisions:
                missing = sorted(all_values - values)
                if not missing:
                    continue
                findings.append(
                    Finding(
                        id=stable_id(flow.id, node.id, domain, ",".join(missing)),
                        kind="inconsistent_case_handling",
                        severity=Severity.WARNING,
                        message=(
                            f"Related flows explicitly mention additional {domain} cases; "
                            f"review fallback handling for: {', '.join(missing)}"
                        ),
                        evidence=Evidence.POTENTIAL_GAP,
                        flow_id=flow.id,
                        node_id=node.id,
                        location=node.location,
                        detail=(
                            "The comparison is heuristic and based on values used by other "
                            f"{domain} decisions in this project."
                        ),
                    )
                )
        return findings


def _deduplicate_findings(findings: list[Finding]) -> list[Finding]:
    return list({item.id: item for item in findings}.values())
