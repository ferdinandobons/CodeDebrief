from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from logicchart.model import Finding, Flow, ProjectModel


@dataclass(slots=True)
class QueryMatch:
    flow: Flow
    score: int
    reasons: list[str]


@dataclass(slots=True)
class ImpactResult:
    changed_files: list[str]
    directly_impacted: list[Flow]
    transitively_impacted: list[Flow]
    findings: list[Finding]

    @property
    def all_flows(self) -> list[Flow]:
        seen: dict[str, Flow] = {}
        for flow in self.directly_impacted + self.transitively_impacted:
            seen[flow.id] = flow
        return list(seen.values())


def query_model(model: ProjectModel, question: str, limit: int = 10) -> list[QueryMatch]:
    terms = _terms(question)
    matches: list[QueryMatch] = []
    findings_by_flow: dict[str, list[Finding]] = {}
    for finding in model.findings:
        findings_by_flow.setdefault(finding.flow_id, []).append(finding)

    for flow in model.flows:
        score = 0
        reasons: list[str] = []
        name_text = f"{flow.name} {flow.symbol} {flow.entry_kind} {flow.framework}".lower()
        node_text = " ".join(node.label for node in flow.nodes).lower()
        finding_text = " ".join(
            finding.message for finding in findings_by_flow.get(flow.id, [])
        ).lower()
        for term in terms:
            if term in name_text:
                score += 6
                reasons.append(f"`{term}` matches the flow identity")
            if term in node_text:
                score += 3
                reasons.append(f"`{term}` appears in a decision or action")
            if term in finding_text:
                score += 4
                reasons.append(f"`{term}` appears in a review finding")
        if flow.is_entrypoint:
            score += 1
        if score:
            matches.append(QueryMatch(flow, score, list(dict.fromkeys(reasons))))
    return sorted(matches, key=lambda item: (-item.score, item.flow.name))[:limit]


def impact_model(model: ProjectModel, changed_files: list[str]) -> ImpactResult:
    normalized = {_normalize_path(item) for item in changed_files}
    direct = [
        flow
        for flow in model.flows
        if _normalize_path(flow.location.path) in normalized
        or any(_normalize_path(path) == _normalize_path(flow.location.path) for path in normalized)
    ]
    by_id = {flow.id: flow for flow in model.flows}
    impacted_ids = {flow.id for flow in direct}
    queue = list(impacted_ids)
    transitive: list[Flow] = []
    while queue:
        current = by_id.get(queue.pop(0))
        if current is None:
            continue
        for caller_id in current.called_by:
            if caller_id in impacted_ids:
                continue
            impacted_ids.add(caller_id)
            queue.append(caller_id)
            caller = by_id.get(caller_id)
            if caller:
                transitive.append(caller)

    findings = [item for item in model.findings if item.flow_id in impacted_ids]
    return ImpactResult(
        changed_files=sorted(normalized),
        directly_impacted=sorted(direct, key=lambda item: item.name),
        transitively_impacted=sorted(transitive, key=lambda item: item.name),
        findings=findings,
    )


def render_query(matches: list[QueryMatch]) -> str:
    if not matches:
        return "No matching logic flows found."
    lines = []
    for index, match in enumerate(matches, 1):
        flow = match.flow
        lines.append(
            f"{index}. {flow.name} [{flow.entry_kind}] "
            f"{flow.location.path}:{flow.location.start_line}"
        )
        lines.append(f"   score={match.score} · " + "; ".join(match.reasons[:3]))
    return "\n".join(lines)


def render_impact(result: ImpactResult) -> str:
    lines = [
        f"Changed files: {len(result.changed_files)}",
        f"Directly impacted flows: {len(result.directly_impacted)}",
        f"Transitively impacted flows: {len(result.transitively_impacted)}",
        f"Related review findings: {len(result.findings)}",
    ]
    if result.directly_impacted:
        lines.append("\nDirect impact:")
        lines.extend(
            f"- {flow.name} ({flow.location.path}:{flow.location.start_line})"
            for flow in result.directly_impacted
        )
    if result.transitively_impacted:
        lines.append("\nCaller impact:")
        lines.extend(
            f"- {flow.name} ({flow.location.path}:{flow.location.start_line})"
            for flow in result.transitively_impacted
        )
    if result.findings:
        lines.append("\nReview before changing:")
        lines.extend(f"- {finding.message}" for finding in result.findings)
    return "\n".join(lines)


def git_changed_files(root: Path) -> list[str]:
    import subprocess

    commands = [
        ["git", "diff", "--name-only", "HEAD"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ]
    files: set[str] = set()
    for command in commands:
        result = subprocess.run(
            command,
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            files.update(line.strip() for line in result.stdout.splitlines() if line.strip())
    return sorted(files)


def _terms(question: str) -> list[str]:
    stopwords = {
        "a",
        "an",
        "and",
        "are",
        "does",
        "flow",
        "for",
        "from",
        "how",
        "in",
        "is",
        "of",
        "the",
        "to",
        "what",
        "where",
        "which",
    }
    return [
        token
        for token in re.findall(r"[a-zA-Z0-9_]+", question.lower())
        if len(token) > 1 and token not in stopwords
    ]


def _normalize_path(value: str) -> str:
    return value.replace("\\", "/").lstrip("./")
