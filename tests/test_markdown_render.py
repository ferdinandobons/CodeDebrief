"""Markdown report: injection escaping and the signal/noise split (review fixes)."""

from __future__ import annotations

from logicchart.model import (
    Evidence,
    Finding,
    FindingKind,
    Flow,
    ProjectModel,
    Severity,
    SourceLocation,
)
from logicchart.render.markdown import render_markdown


def _finding(
    kind: str | FindingKind, evidence: Evidence, message: str, path: str = "app.py"
) -> Finding:
    public_kind = kind.value if isinstance(kind, FindingKind) else kind
    return Finding(
        id=f"id-{public_kind}-{evidence.value}",
        kind=kind,
        severity=Severity.WARNING,
        message=message,
        evidence=evidence,
        flow_id="f",
        location=SourceLocation(path, 3, 3),
    )


def _model(findings: list[Finding]) -> ProjectModel:
    return ProjectModel(
        schema_version="1.1", generated_at="x", root=".", flows=[], findings=findings
    )


def test_finding_message_link_injection_is_neutralized() -> None:
    evil = "see [click](https://evil.example) and `code` and <b>x</b>"
    out = render_markdown(_model([_finding("dead_code", Evidence.INFERRED, evil)]))
    # The attacker substring must not survive as a live Markdown link / code / HTML.
    assert "[click](https://evil.example)" not in out
    assert r"\[click\]" in out
    assert "<b>x</b>" not in out


def test_potential_gap_is_grouped_under_collapsible_section() -> None:
    findings = [
        _finding("dead_code", Evidence.INFERRED, "an inferred fact"),
        _finding("missing_branch", Evidence.POTENTIAL_GAP, "a review candidate"),
    ]
    out = render_markdown(_model(findings))
    main, _, review = out.partition("<details>")
    # The verified/inferred finding is in the main section, the gap under <details>.
    assert "an inferred fact" in main
    assert "a review candidate" not in main
    assert "a review candidate" in review
    assert "POTENTIAL_GAP" in review


def test_include_gaps_expands_the_review_section() -> None:
    findings = [_finding("missing_branch", Evidence.POTENTIAL_GAP, "a review candidate")]
    folded = render_markdown(_model(findings), include_gaps=False)
    expanded = render_markdown(_model(findings), include_gaps=True)
    assert "<details>" in folded
    assert "<details open>" in expanded


def test_evidence_level_is_rendered_inline() -> None:
    out = render_markdown(_model([_finding("dead_code", Evidence.INFERRED, "x")]))
    assert "INFERRED" in out


def test_finding_id_and_explain_command_are_rendered_inline() -> None:
    finding = _finding("dead_code", Evidence.INFERRED, "x")
    out = render_markdown(_model([finding]))
    assert f"id `{finding.id}`" in out
    assert f"explain `logicchart explain {finding.id}`" in out


def test_diagnostic_review_prompt_is_rendered_when_present() -> None:
    finding = _finding("dead_code", Evidence.INFERRED, "x")
    finding.metadata["diagnostic"] = {"review_prompt": "Can this code be removed?"}
    out = render_markdown(_model([finding]))
    assert "Review: Can this code be removed?" in out


def test_finding_kind_enum_is_rendered_as_public_wire_value() -> None:
    out = render_markdown(
        _model([_finding(FindingKind.MISSING_BRANCH, Evidence.POTENTIAL_GAP, "x")])
    )
    assert "missing_branch" in out
    assert "FindingKind.MISSING_BRANCH" not in out


def test_source_path_with_metacharacters_cannot_break_the_reference() -> None:
    # A source-derived file path with a backtick, a `)`, and angle brackets must not be
    # able to close the inline code span or the link destination.
    evil_path = "a`b)c<d>e.py"
    out = render_markdown(_model([_finding("dead_code", Evidence.INFERRED, "msg", evil_path)]))
    reference = next(line for line in out.splitlines() if "e.py:3" in line)
    # The raw backtick never reaches the visible code span (swapped for a quote), so the
    # span cannot be closed early and the rest interpreted as live Markdown.
    assert "`a`b)" not in reference
    assert "a'b)c" in reference  # the backtick became a quote inside the code span
    # The link destination is percent-encoded, so a `)`, `<`, or `>` cannot terminate the
    # link early or smuggle markup into the (../...) target.
    assert "](../a`b)c" not in reference
    assert "%29" in reference  # the `)` survived as %29 inside the destination
    assert "%3C" in reference and "%3E" in reference  # `<` / `>` encoded in the target
    assert "](../a%60b%29c%3Cd%3Ee.py#L3)" in reference


def test_flow_name_with_metacharacters_is_escaped_in_the_heading() -> None:
    flow = Flow(
        id="f1",
        name="weird`name](http://evil)<b>",
        symbol="m:weird",
        language="python",
        framework="generic",
        entry_kind="function",
        is_entrypoint=True,
        location=SourceLocation("ok.py", 1, 1),
    )
    model = ProjectModel(
        schema_version="1.1", generated_at="x", root=".", flows=[flow], findings=[]
    )
    out = render_markdown(model)
    heading = next(line for line in out.splitlines() if line.startswith("### "))
    # The flow-name heading cannot smuggle a live link or raw HTML: every metacharacter
    # is backslash-escaped so it renders as literal text, not a link/emphasis/markup.
    assert "](http://evil)" not in heading
    assert "<b>" not in heading
    assert r"\]\(http://evil\)" in heading


def test_generated_at_and_root_cannot_break_the_header() -> None:
    flow_model = ProjectModel(
        schema_version="1.1",
        generated_at="x`echo pwned`",
        root="..`whoami`",
        flows=[],
        findings=[],
    )
    out = render_markdown(flow_model)
    # The backtick in generated_at/root is neutralized inside its code span.
    assert "`x`echo pwned`" not in out
