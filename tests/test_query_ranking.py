"""Relevance/scoring correctness for query_model and the CLI <-> MCP JSON contract.

These tests pin the exact per-bucket weights and the deterministic ordering, lock the
no-match / empty-query behavior, and prove the substring/entry-kind false positives that
an adversarial review found are gone. The CORE relevance (real queries still surface the
right flows) is covered by the demo golden test; here we isolate the scoring mechanics.
"""

from __future__ import annotations

import json
from pathlib import Path

from logicchart.cli import main
from logicchart.model import (
    Evidence,
    Finding,
    Flow,
    FlowNode,
    NodeKind,
    ProjectModel,
    Severity,
    SourceLocation,
)
from logicchart.query import (
    ENTRYPOINT_BONUS,
    FINDING_WEIGHT,
    IDENTITY_WEIGHT,
    NODE_WEIGHT,
    QueryMatch,
    query_model,
)


def _loc(path: str = "app.py", line: int = 1) -> SourceLocation:
    return SourceLocation(path=path, start_line=line, end_line=line + 1)


def _flow(
    flow_id: str,
    name: str,
    *,
    symbol: str | None = None,
    node_labels: tuple[str, ...] = (),
    is_entrypoint: bool = False,
    entry_kind: str = "function",
    framework: str = "generic",
) -> Flow:
    nodes = [
        FlowNode(
            id=f"{flow_id}-n{index}",
            kind=NodeKind.ACTION,
            label=label,
            location=_loc(),
        )
        for index, label in enumerate(node_labels)
    ]
    return Flow(
        id=flow_id,
        name=name,
        symbol=symbol if symbol is not None else name,
        language="python",
        framework=framework,
        entry_kind=entry_kind,
        is_entrypoint=is_entrypoint,
        location=_loc(),
        nodes=nodes,
    )


def _finding(flow_id: str, message: str) -> Finding:
    return Finding(
        id=f"{flow_id}-find",
        kind="missing_branch",
        severity=Severity.WARNING,
        message=message,
        evidence=Evidence.POTENTIAL_GAP,
        flow_id=flow_id,
        location=_loc(),
    )


def _model(flows: list[Flow], findings: list[Finding] | None = None) -> ProjectModel:
    return ProjectModel(
        schema_version="1.1",
        generated_at="2026-06-16T00:00:00+00:00",
        root="/tmp/project",
        flows=flows,
        findings=findings or [],
    )


def test_bucket_weights_and_order_are_exact() -> None:
    """Three flows that hit the SAME term in different buckets rank identity > finding
    > node, with scores equal to the named per-bucket constants."""
    model = _model(
        flows=[
            _flow("f-id", "widget", symbol="widget"),  # identity hit
            _flow("f-node", "alpha", node_labels=("the widget toggles",)),  # node hit
            _flow("f-find", "beta"),  # finding hit
        ],
        findings=[_finding("f-find", "widget review gap")],
    )
    matches = query_model(model, "widget")

    assert [m.flow.id for m in matches] == ["f-id", "f-find", "f-node"]
    by_id = {m.flow.id: m.score for m in matches}
    assert by_id["f-id"] == IDENTITY_WEIGHT
    assert by_id["f-find"] == FINDING_WEIGHT
    assert by_id["f-node"] == NODE_WEIGHT


def test_entrypoint_bonus_only_breaks_ties_between_real_matches() -> None:
    """The entrypoint bonus is added only on top of a positive term score."""
    model = _model(
        flows=[
            _flow("plain", "widget", symbol="widget"),
            _flow("entry", "widget", symbol="widget", is_entrypoint=True),
        ]
    )
    matches = query_model(model, "widget")
    by_id = {m.flow.id: m.score for m in matches}
    assert by_id["entry"] == IDENTITY_WEIGHT + ENTRYPOINT_BONUS
    assert by_id["plain"] == IDENTITY_WEIGHT
    # The entrypoint sorts first on the bonus tie-break.
    assert matches[0].flow.id == "entry"


def test_entrypoint_with_zero_term_overlap_is_not_returned() -> None:
    """An entrypoint matching no query term must not appear as score=1 filler."""
    model = _model(
        flows=[
            _flow("hit", "widget", symbol="widget"),
            _flow("noise", "unrelated", symbol="unrelated", is_entrypoint=True),
        ]
    )
    matches = query_model(model, "widget")
    assert [m.flow.id for m in matches] == ["hit"]
    assert all(m.score > 0 and m.reasons for m in matches)


def test_deterministic_tie_break_by_id() -> None:
    """Equal score AND equal name -> stable order by unique flow id, regardless of
    insertion order."""
    forward = _model(
        flows=[
            _flow("z-id", "widget", symbol="widget"),
            _flow("a-id", "widget", symbol="widget"),
        ]
    )
    reverse = _model(
        flows=[
            _flow("a-id", "widget", symbol="widget"),
            _flow("z-id", "widget", symbol="widget"),
        ]
    )
    assert [m.flow.id for m in query_model(forward, "widget")] == ["a-id", "z-id"]
    assert [m.flow.id for m in query_model(reverse, "widget")] == ["a-id", "z-id"]


def test_no_match_returns_empty() -> None:
    model = _model(flows=[_flow("f", "widget", symbol="widget")])
    assert query_model(model, "nonexistent_term") == []


def test_empty_and_punctuation_only_query_returns_empty() -> None:
    model = _model(flows=[_flow("f", "widget", symbol="widget", is_entrypoint=True)])
    assert query_model(model, "") == []
    assert query_model(model, "??? !!! ...") == []
    # Stopwords-only collapses to no terms, too.
    assert query_model(model, "what is the") == []


def test_substring_no_longer_matches() -> None:
    """'order' must NOT match inside 'reordering_queue' (token, not substring); it must
    still match a flow whose identity contains 'order' as a whole token."""
    model = _model(
        flows=[
            _flow("re", "reordering_queue", symbol="reordering_queue"),
            _flow("ok", "create order", symbol="createOrder", node_labels=("order ok",)),
        ]
    )
    matches = query_model(model, "order")
    assert [m.flow.id for m in matches] == ["ok"]


def test_entry_kind_and_framework_are_not_matchable() -> None:
    """Querying the internal vocabulary 'route'/'function' must not return everything."""
    model = _model(
        flows=[
            _flow("r1", "alpha", symbol="alpha", entry_kind="route", framework="next"),
            _flow("r2", "beta", symbol="beta", entry_kind="route", framework="next"),
        ]
    )
    assert query_model(model, "route") == []
    assert query_model(model, "function") == []
    assert query_model(model, "next") == []


def test_repeated_query_term_does_not_inflate_rank() -> None:
    model = _model(flows=[_flow("f", "widget", symbol="widget")])
    once = query_model(model, "widget")
    thrice = query_model(model, "widget widget widget")
    assert [m.score for m in once] == [m.score for m in thrice] == [IDENTITY_WEIGHT]


def test_unicode_terms_survive_tokenization() -> None:
    """Unicode \\w words (café, 日本語) must not be dropped or corrupted by the ASCII-only
    tokenizer they replaced; they tokenize to standalone matchable terms."""
    model = _model(
        flows=[
            _flow("c", "café handler", symbol="cafeHandler"),
            _flow("j", "日本語 flow", symbol="jpFlow"),
        ]
    )
    assert [m.flow.id for m in query_model(model, "café")] == ["c"]
    assert [m.flow.id for m in query_model(model, "日本語")] == ["j"]


def test_limit_is_respected_and_non_positive_means_no_limit() -> None:
    flows = [_flow(f"f{i}", "widget", symbol="widget") for i in range(5)]
    model = _model(flows=flows)
    assert len(query_model(model, "widget", limit=2)) == 2
    assert len(query_model(model, "widget", limit=0)) == 5
    # A negative limit must NOT silently drop results via slice semantics.
    assert len(query_model(model, "widget", limit=-1)) == 5


def test_query_match_to_dict_shape() -> None:
    match = QueryMatch(
        flow=_flow("f1", "widget", symbol="widget"),
        score=6,
        reasons=["`widget` matches the flow identity"],
    )
    payload = match.to_dict()
    assert payload == {
        "flow_id": "f1",
        "name": "widget",
        "score": 6,
        "reasons": ["`widget` matches the flow identity"],
        "source": "app.py:1",
    }
    assert "source" not in match.to_dict(include_source=False)


def _demo_source(tmp_path: Path) -> Path:
    source = tmp_path / "app.py"
    source.write_text(
        "def authorize(user):\n"
        "    if user.role == 'admin':\n"
        "        return True\n"
        "    return False\n",
        encoding="utf-8",
    )
    return tmp_path


def test_cli_no_match_prints_message(tmp_path: Path, capsys: object) -> None:
    root = _demo_source(tmp_path)
    assert main(["analyze", str(root), "--full"]) == 0
    capsys.readouterr()  # type: ignore[attr-defined]
    assert main(["query", "zzqqxx_nonsense", "--path", str(root)]) == 0
    out = capsys.readouterr()  # type: ignore[attr-defined]
    assert out.out.strip() == "No matching logic flows found."


def test_cli_negative_limit_warns_and_keeps_results(tmp_path: Path, capsys: object) -> None:
    root = _demo_source(tmp_path)
    assert main(["analyze", str(root), "--full"]) == 0
    capsys.readouterr()  # type: ignore[attr-defined]
    assert main(["query", "admin authorize", "--path", str(root), "--limit", "-1"]) == 0
    out = capsys.readouterr()  # type: ignore[attr-defined]
    assert "authorize" in out.out
    assert "negative --limit" in out.err


def test_cli_unknown_scope_warns_but_runs(tmp_path: Path, capsys: object) -> None:
    root = _demo_source(tmp_path)
    assert main(["analyze", str(root), "--full"]) == 0
    capsys.readouterr()  # type: ignore[attr-defined]
    assert main(["query", "admin authorize", "--path", str(root), "--scope", "nope"]) == 0
    out = capsys.readouterr()  # type: ignore[attr-defined]
    assert "unknown scope" in out.err


def test_cli_json_matches_query_match_to_dict(tmp_path: Path, capsys: object) -> None:
    """The CLI --json shape is exactly QueryMatch.to_dict() (the same serializer the MCP
    query_logic tool now uses), including the path:line `source` field."""
    root = _demo_source(tmp_path)
    assert main(["analyze", str(root), "--full"]) == 0
    capsys.readouterr()  # type: ignore[attr-defined]
    assert main(["query", "admin authorize", "--path", str(root), "--json"]) == 0
    out = capsys.readouterr()  # type: ignore[attr-defined]
    payload = json.loads(out.out)
    assert payload
    for row in payload:
        assert set(row) == {"flow_id", "name", "score", "reasons", "source"}
        assert ":" in row["source"]
