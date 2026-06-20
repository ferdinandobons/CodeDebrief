"""Stage 6: the richer query surface."""

from __future__ import annotations

from pathlib import Path

from logicchart.analysis.project import ProjectAnalyzer
from logicchart.model import Flow, ProjectModel, SourceLocation
from logicchart.query import (
    find_decisions,
    flow_navigation,
    model_summary,
    query_model,
    where_is_state_handled,
)

_CHAIN = (
    "def a(s):\n"
    "    if s.status == X.A:\n        return 1\n"
    "    elif s.status == X.B:\n        return 2\n"
)


def _model(tmp_path: Path, body: str) -> ProjectModel:
    (tmp_path / "m.py").write_text(body, encoding="utf-8")
    return ProjectAnalyzer(tmp_path).analyze(full=True).model


def _flow(flow_id: str, name: str, symbol: str) -> Flow:
    return Flow(
        id=flow_id,
        name=name,
        symbol=symbol,
        language="python",
        framework="generic",
        entry_kind="function",
        is_entrypoint=False,
        location=SourceLocation(path="app.py", start_line=1, end_line=1),
    )


def test_model_summary_focuses_on_flows_and_quality(tmp_path: Path) -> None:
    model = _model(tmp_path, _CHAIN)
    summary = model_summary(model)
    assert summary["flows"] >= 1
    assert "quality" in summary
    assert "findings" not in summary


def test_analysis_no_longer_generates_review_findings(tmp_path: Path) -> None:
    model = _model(tmp_path, _CHAIN)
    assert model.findings == []
    assert "finding_rules" not in model.metadata
    assert "finding_count" not in model.metadata


def test_flow_annotations_are_exposed_in_query_surfaces(tmp_path: Path) -> None:
    model = _model(tmp_path, _CHAIN)
    flow = model.flows[0]
    flow.metadata["scope"] = ["core"]
    annotations = {
        "flows": {
            flow.id: {
                "label": "Primary status handler",
                "summary": "Handles the status branch decisions.",
            }
        },
        "scopes": {"core": {"label": "Core flows", "summary": "Decision-heavy core paths."}},
    }

    navigation = flow_navigation(model, flow.id, annotations=annotations)
    assert navigation["annotations"]["flow"]["label"] == "Primary status handler"
    assert "findings" not in navigation["annotations"]
    assert navigation["annotations"]["scopes"]["core"]["label"] == "Core flows"


def test_flow_navigation_resolves_target_without_name_ambiguity_regression(
    tmp_path: Path,
) -> None:
    model = ProjectModel.empty(tmp_path)
    model.flows = [
        _flow("target-id", "shared name", "pkg:target"),
        _flow("symbol-flow", "shared name", "pkg:symbol"),
        _flow("name-flow", "unique name", "pkg:name"),
    ]

    assert flow_navigation(model, "target-id")["flow"]["id"] == "target-id"
    assert flow_navigation(model, "pkg:symbol")["flow"]["id"] == "symbol-flow"
    assert flow_navigation(model, "unique name")["flow"]["id"] == "name-flow"

    ambiguous = flow_navigation(model, "shared name")

    assert ambiguous["error_code"] == "flow_target_ambiguous"
    assert [item["id"] for item in ambiguous["matches"]] == ["target-id", "symbol-flow"]


def test_where_is_state_handled(tmp_path: Path) -> None:
    model = _model(tmp_path, "def a(s):\n    if s.status == Status.ACTIVE:\n        return 1\n")
    rows = where_is_state_handled(model, "Status")
    assert rows and rows[0]["flow"] == "a"


def test_find_decisions_missing_fallback(tmp_path: Path) -> None:
    gaps = find_decisions(_model(tmp_path, _CHAIN), missing_fallback=True)
    assert gaps and all(decision["has_implicit_fallback"] for decision in gaps)


def test_find_decisions_subject_is_equality_not_substring(tmp_path: Path) -> None:
    """Subject matching is exact equality, consistent with where_is_state_handled's
    exact domain/value matching (a substring 'status' must not match 'order_status')."""
    model = _model(
        tmp_path,
        "def a(s):\n    if s.status == X.A:\n        return 1\n    return 0\n",
    )
    subject = next(
        node.metadata.get("subject")
        for flow in model.flows
        for node in flow.nodes
        if node.metadata.get("subject")
    )
    assert subject  # the decision branches on some subject
    assert find_decisions(model, subject=subject), "exact subject must match"
    # A strict substring of that subject must NOT match.
    assert find_decisions(model, subject=subject[:-1]) == []


def test_query_matches_structure_and_metadata(tmp_path: Path) -> None:
    model = _model(
        tmp_path,
        "def get_profile(user):\n"
        "    user = repository.fetch(user.id)\n"
        "    if user.status == AccountStatus.ACTIVE:\n"
        "        return user\n"
        "    return None\n",
    )

    matches = query_model(model, "python accountstatus active profile", language="python")

    assert matches
    top = matches[0]
    assert top.flow.name == "get_profile"
    assert any("structure" in reason or "metadata" in reason for reason in top.reasons)
    payload = top.to_dict()
    assert payload["language"] == "python"
    assert payload["entry_kind"] == "function"
