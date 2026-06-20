# Agent-Authored Annotations

LogicChart is deterministic, local-first, and does not require provider keys. The primary
agent workflow is MCP-driven:

1. The user asks a coding agent a code-logic question.
2. The agent calls MCP `agent_context`.
3. LogicChart returns a deterministic `workflow_slice`.
4. The agent answers from the slice presentation contract, ordered steps, decisions,
   calls, source ranges, and visual handles.
5. Optional agent-authored labels or summaries are written as validated annotations.

Generated annotation text must be treated as `agent_generated`. It can improve readability,
but it must not replace source-backed flow data or deterministic graph structure.

## Agent Skills

`logicchart setup-agent codex` installs `.agents/skills/logicchart/SKILL.md`.
`logicchart setup-agent claude` installs `.claude/skills/logicchart/SKILL.md`.

These provider-native skills route implicit code-logic questions to MCP `agent_context`
and route visual workflow requests to `snapshot_slice` first. `viewer_targets` are manual
follow-up targets for `logicchart view`.

When a user asks for a workflow visual:

1. Render `snapshot.svg` through the client's SVG/HTML visualization widget when one is
   available.
2. If inline SVG is unavailable, call `snapshot_slice` with `include_svg=false` and use
   the returned local artifact path.
3. If a text fallback is needed, render
   `workflow_slice.presentation.canonical_visual.diagram` exactly as returned.

Snapshot SVGs and Mermaid fallbacks are vertical/top-to-bottom. The agent should not
redraw them as horizontal summaries or hand-build a replacement diagram from source reads.
If a result is too large, truncated, or missing the exact canonical visual, retry with a
smaller `token_budget` and a narrower `flow_id`, `symbol`, `current_file`, or `scope`.

The agent may choose how much detail to show first, but visible nodes, edges, branches,
values, and source anchors must stay grounded in returned LogicChart payloads. Visual
answers should say the diagram is a bounded summary that can be expanded, then offer to:

- simplify labels in the user's language;
- expand omitted nodes, branches, or adjacent flows;
- explore a related area or path.

Language-friendly wording is a separate presentation layer, not a new source of facts.

## Annotation Workflow

`preview_annotation_targets` is the preferred local-only MCP helper. It selects bounded
candidate flows, nodes, and scopes, returns the context an agent may want to annotate, and
always reports `provider_call_made: false`.

Use it to inspect annotation targets and payload size. Then use:

- `write_annotations` to merge validated `agent_generated` labels, summaries, and
  descriptions into `logicchart-out/logic-annotations.json`;
- `validate_annotations` to check the sidecar against the current model hash and ids;
- `annotation_status` to inspect sidecar status, counts, and optional contents;
- `clear_annotations` with `confirm=true` to remove optional generated annotation text.

`write_annotations` rejects non-`agent_generated` provenance. Provider-managed enrichment
support remains in internal modules for compatibility and tests, but it is not the primary
product path and is not part of the public CLI. No setup flow should ask users for API
keys during normal LogicChart use.

## Viewer And MCP Display

When a valid annotation sidecar is present, LogicChart may display flow labels, node
labels, flow summaries, and scope descriptions in MCP responses, snapshots, and the
viewer. These annotations remain optional. Flow structure, source anchors, decisions, and
validation must remain correct without them.
