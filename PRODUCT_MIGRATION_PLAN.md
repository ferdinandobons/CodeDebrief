# LogicChart Product Vision and Migration Plan

This document is both the product vision and the execution plan for the agent-first
migration. It should guide implementation, README positioning, documentation language,
agent instructions, and release readiness.

## North Star

LogicChart is an agent-first workflow navigator for code logic.

Developers should be able to set it up once, then ask their coding agent simple questions
such as:

- How does this feature work?
- What logic is involved in this change?
- What could break if I edit this file?
- Where is this state handled?
- Why did the AI-generated code create this branch?
- Which decisions, callers, callees, and missing cases should I review?

LogicChart should give the agent a deterministic workflow slice: a focused, navigable piece
of the codebase flowchart that shows the logic involved in the user's question or change.
The agent should use that slice to answer with source-grounded explanation instead of
plausible narration.

## Product Positioning

LogicChart is not primarily a terminal tool, a generic knowledge graph, or a graph viewer.

It is a support system for coding agents. Its job is to make code logic inspectable,
queryable, and explainable for both humans and AI, especially in projects where modern
development is mediated by agents such as Codex, Claude, Cursor, or similar tools.

The product should stay focused on decision and workflow understanding. It can learn from
generic graph tools, but its core output must remain a code-logic flowchart: entrypoints,
decisions, branches, calls, outcomes, domain states, review signals, evidence, and source
ranges.

The distribution model should be hybrid, with one clear hierarchy:

1. MCP and agent workflows are the primary runtime surface.
2. CLI is the local executable substrate for setup, repair, CI, explicit refresh, and
   debugging.
3. Agent instructions and skills are the activation layer that teach each coding agent
   when and how to use LogicChart.
4. `logicchart view ...` remains the official manual command for opening the UI and
   visually exploring the decision flowchart.
5. Generated artifacts are the shared source of truth between humans, agents, CI, and UI.

MCP should remain the primary integration channel because it exposes structured tools and
resources directly to coding agents. The CLI should not compete with MCP; it should power
MCP, setup, validation, and fallback workflows. Skills or agent instruction files should
not replace MCP either; they should package the usage policy, examples, and decision rules
that make the agent reach for LogicChart automatically when the user asks about code logic.

The viewer is not the default daily workflow, but it is still a central product capability.
It should be the one explicit manual experience users can rely on when they want to inspect
the flowchart directly: run `logicchart view ...`, open the UI, and explore the decision
flows.

## Core Promise

After setup, users should not need to remember LogicChart commands.

They should ask their coding agent ordinary questions, and the agent should use
LogicChart automatically to build a workflow slice that lets it:

- retrieve the relevant flows;
- inspect decisions, calls, callers, callees, and outcomes;
- identify review signals and their evidence tier;
- understand impact from changed files, symbols, flows, review signals, and dependencies;
- request deterministic visual snapshots;
- distinguish verified facts from inferred review candidates;
- generate useful explanations without losing source-grounded traceability.

The user-facing result should be a clear answer, not raw graph data. A good answer should
include:

- a concise explanation of how the requested behavior works;
- the ordered workflow steps that matter;
- the relevant source files, symbols, and line ranges;
- important decisions, branches, states, outcomes, and cross-flow calls;
- what is certain, inferred, incomplete, or outside the slice budget;
- review signals as candidates, not confirmed defects;
- suggested tests or code areas to inspect next;
- a visual snapshot or viewer link when the flowchart adds clarity.

## Design Principles

### Agent-first

Every major capability should be usable through MCP and structured payloads. Human-facing
CLI commands should be limited to setup, maintenance, CI, diagnostics, MCP startup, and the
manual viewer. Cognitive tools such as query, impact, explain, navigate, and snapshots
belong behind MCP or inside the unified context workflow, not in the public CLI.

### Local-first and deterministic

The core model must work offline and must not require an LLM. Correctness comes from the
local analyzer, schema validation, source locations, evidence tiers, and deterministic
snapshots.

### Visual context for agents

Because the product is about flowcharts, agents need visual artifacts too. SVG snapshots
for flows, review signals, impact sets, and explicit subgraphs are first-class context, not a
secondary export feature.

### Workflow slices are the product unit

The main product unit is the `workflow_slice`: a bounded, source-grounded, visualizable
piece of the decision flowchart selected for a question, code selection, change, symbol,
flow, review signal, or dependency path.

A workflow slice is not a generic graph dump. It should preserve the semantics of a
decision flowchart:

- which entrypoints start the behavior;
- which flows are primary and which are supporting context;
- which decisions and handled values control the behavior;
- which calls connect one flow to another;
- which outcomes, returns, errors, terminal states, and unresolved calls matter;
- which domain states, roles, permissions, feature flags, or enum values are involved;
- which review signals are nearby and what evidence tier they have;
- which source ranges prove each important step;
- which nodes, flows, findings, or files were omitted because of budget or uncertainty.

The slice should be stable enough for an agent to cite ids, ask for expansion, request a
snapshot, or write annotations against it.

### One orchestration path

Agents should not have to manually stitch together many low-level tools for common tasks.
LogicChart should provide a unified context workflow that accepts a user question, changed
files, selected code, target flow, finding, or symbol, then returns a bounded workflow
slice.

The lower-level tools should remain available for expert or fallback use, but the expected
agent path should be:

```text
user question -> agent instruction/skill trigger -> MCP agent_context -> workflow_slice
-> agent explanation or code change
```

### Enrichment belongs to the coding agent

The coding agent already has a model. LogicChart should not require provider keys for the
main enrichment workflow.

Instead, LogicChart should:

- expose deterministic context to the agent;
- tell the agent which ids can be annotated;
- accept agent-authored annotations through a validated sidecar;
- keep annotations separate from deterministic facts;
- reject annotations that reference unknown flow, node, finding, or scope ids.

Provider-managed enrichment can remain an advanced optional path, but it should not be the
primary product story.

### Trust boundaries must be explicit

LogicChart should always make clear whether a statement is:

- `VERIFIED`: syntax-backed or source-backed;
- `INFERRED`: deterministic heuristic;
- `POTENTIAL_GAP`: review candidate;
- `agent_generated`: optional explanatory annotation from the coding agent.

Agents must not present inferred review signals or generated enrichment as confirmed defects.

## Target Setup Experience

The ideal setup is a single guided command:

```bash
logicchart setup-agent codex
```

Equivalent targets should exist for Claude, Cursor, and other supported agent surfaces.

The setup flow should:

- create or update `logicchart.toml` only when needed;
- install or refresh agent instructions and skills when that surface supports them;
- register the MCP server as the preferred agent integration;
- generate the initial `logicchart-out` model;
- run `logicchart doctor`;
- validate artifacts;
- explain what users can now ask their coding agent;
- avoid asking for LLM provider credentials unless the user explicitly chooses an advanced
  provider-managed enrichment flow.

Setup should optimize for a user who will not remember commands later. The success state is
not "the CLI is installed"; it is "the coding agent knows LogicChart is available, knows
when to call it, and can retrieve useful flow context without the user naming a command."

## Target Agent Experience

The primary MCP capability should become a unified workflow-slice tool, conceptually:

```text
agent_context(
  question,
  changed_files,
  selected_code,
  current_file,
  flow_id,
  symbol,
  finding_id,
  dependency_path,
  token_budget,
  include_visual
)
```

The response should include a `workflow_slice` object with:

- `intent`: the normalized user request and the detected task type, such as explain,
  review impact, trace behavior, inspect state handling, or prepare tests;
- `selection`: matched flows, symbols, files, findings, and the reasons they were selected;
- `primary_flows`: the main flows needed to answer the question;
- `supporting_flows`: callers, callees, tests, sibling flows, and domain-related flows that
  provide useful context;
- `ordered_steps`: an agent-readable path through the flowchart, including source anchors;
- `decisions`: decision nodes, handled values, missing or unresolved values when known, and
  branch outcomes;
- `calls`: direct and transitive call edges, with edge confidence and unresolved calls;
- `domain_logic`: statuses, roles, permissions, feature flags, enums, transitions, and
  lifecycle states touched by the slice;
- `review_signals`: related review candidates with evidence tier, confidence, scope, and
  remediation hints when available;
- `source_ranges`: compact source anchors for the evidence the agent should cite;
- `visuals`: deterministic SVG/PNG snapshot payloads or follow-up snapshot tool calls;
- `omissions`: what was excluded because of token budget, unsupported language capability,
  stale artifacts, parse errors, or ambiguous matches;
- `next_actions`: recommended follow-up tools, tests, files, or human review points.

This should be the default path for questions such as:

- "Explain how checkout works."
- "Review the logical impact of my change."
- "What logic touches this status?"
- "Show me the flow around this bug."
- "What should I test after this edit?"

The context tool should be opinionated enough that an agent can use it from natural
language, but transparent enough that advanced users can inspect which flows, review signals,
source files, snapshots, and omissions were included.

## Workflow Slice Lifecycle

The workflow-slice pipeline should be deterministic and explainable:

1. Normalize the request: identify whether the user is asking for explanation, impact,
   path tracing, review, testing, domain-state handling, or visual inspection.
2. Select seeds from the question, changed files, current file, selected code, flow id,
   symbol, finding id, dependency path, route, endpoint, component, or domain value.
3. Resolve seeds to flows, nodes, findings, files, and source ranges with ranked reasons.
4. Expand the slice through decision-flow semantics: entrypoint links, caller/callee links,
   route/API relationships, domain-state relationships, tests, and nearby review signals.
5. Rank and prune by task relevance, evidence quality, and token budget.
6. Order the selected material into a decision workflow rather than a generic neighbor list.
7. Attach evidence tiers, edge confidence, source anchors, analyzer capability notes, stale
   artifact state, and omissions.
8. Provide snapshot references and follow-up expansion handles for the agent.
9. Let the agent answer the user, then optionally write validated annotations back as
   `agent_generated` enrichment.

The slice should support progressive navigation:

- `expand_slice` should widen or deepen an existing slice without starting from scratch;
- `workflow_path` should connect two concepts, such as UI component to API endpoint or
  status value to backend handler;
- `explain_flow`, `explain_node`, and `explain_edge` should inspect focused entities;
- `snapshot_slice` should render the current slice as deterministic visual context;
- every expansion should preserve ids, reasons, trust tiers, and omission metadata.

## Channel Strategy

### MCP: primary runtime integration

MCP should expose a small set of high-value tools and resources that map to real agent
tasks:

- `agent_context` for question-driven workflow-slice generation;
- `expand_slice` for progressive exploration from an existing slice;
- `workflow_path` for tracing between components, routes, APIs, states, symbols, or flows;
- focused flow, node, edge, and review-signal inspection for fallback expert use;
- snapshot or slice rendering for visual context inside the MCP surface;
- annotation write/validate tools for agent-authored enrichment.

The MCP surface should avoid forcing agents to call many tiny tools before they can answer
ordinary user questions. Low-level tools are useful, but the default path should be one
workflow slice, then progressive expansion only when the first slice is not enough.

### CLI: kept public commands

The public CLI should be intentionally small. These are the commands that should remain:

- `logicchart setup-agent`: configure LogicChart once for a coding agent.
- `logicchart view`: open the official manual UI for the decision flowchart.
- `logicchart update`: refresh generated artifacts for setup, CI, and agent maintenance.
- `logicchart validate`: validate artifact/schema/sync state.
- `logicchart doctor`: diagnose install, config, artifact, and agent integration issues.
- `logicchart mcp`: start the MCP server.

The CLI should not mirror every agent capability. Most users are expected to interact
through their coding agent after setup, with `logicchart view` as the only central manual
experience.

### CLI: commands to remove from the public surface

These commands should be removed from the public CLI as part of the migration:

- `logicchart query`
- `logicchart impact`
- `logicchart explain`
- `logicchart navigate`
- `logicchart snapshot`

Their underlying functionality should remain available to MCP tools and internal
orchestration where useful. Removing these commands means removing the manual command
surface, not deleting the analyzer, ranking, impact, explanation, navigation, or snapshot
capabilities from the product.

Other current commands should be folded into the kept surface:

- `logicchart init` and `logicchart install` should become part of `logicchart
  setup-agent`.
- `logicchart analyze` should be folded into `logicchart update` or kept as an internal
  implementation detail if full reanalysis still needs a distinct operation.
- `logicchart llm` and `logicchart enrich` should be removed from the primary CLI, or
  moved to a clearly advanced/internal path, because agent-authored enrichment is the
  preferred product path.

### Skills and agent instructions: activation layer

Skills and instruction files are how LogicChart becomes discoverable inside the agent's
normal workflow. Their job is to encode behavior:

- when the agent should call LogicChart;
- which user questions imply code-flow analysis;
- when to request a workflow slice before grep/read/file-by-file exploration;
- how to respect trust tiers;
- when to refresh artifacts;
- how to cite source ranges and flow ids;
- how to avoid overstating inferred review signals;
- how to request visual snapshots only when they add value.

Skills should not contain the product's source of truth or duplicate large command
manuals. They should be compact routing policies that point the agent to MCP first and CLI
fallbacks only when needed.

## Agent-authored Enrichment

The future enrichment workflow should be:

1. The user asks the coding agent for a clearer explanation or better flow labels.
2. The agent calls LogicChart for deterministic context.
3. The agent generates summaries, explanations, and label suggestions using its own model.
4. The agent writes the annotations back through a LogicChart MCP write tool.
5. LogicChart validates target ids, schema, model hash, text limits, and annotation source.
6. The viewer, snapshots, MCP tools, and workflow slices display those annotations
   separately from deterministic diagnostics.

Potential tools:

- `preview_annotation_targets`
- `write_annotations`
- `validate_annotations`
- `clear_annotations`
- `annotation_status`

Annotations should support:

- flow names and summaries;
- node labels and summaries;
- scope/group summaries;
- review-signal explanations;
- remediation notes;
- domain concept descriptions;
- "what to inspect next" notes.

## Strategic Product Pillars

### 1. Navigate the workflow slice

LogicChart should turn a plain user question or code change into a focused workflow slice
that both humans and agents can follow.

### 2. Understand how code works

LogicChart should explain entrypoints, decisions, branches, calls, outcomes, and source
locations in a way that preserves decision-flow semantics.

### 3. Understand what changes affect

LogicChart should map edits to impacted flows, callers, review signals, decisions, and test
suggestions.

### 4. Understand domain logic

LogicChart should identify important domains such as statuses, roles, permissions,
lifecycle states, payment states, and feature flags, then show where they are handled or
missing.

### 5. Understand trust and uncertainty

LogicChart should expose analyzer capability, skipped files, parse warnings, unresolved
calls, evidence tier, confidence, and snapshot omissions so agents do not overstate what
they know.

### 6. Make visual context available without opening the UI

The viewer remains useful, but agents should be able to request compact deterministic SVG
snapshots directly through MCP.

## Documentation Narrative

This file should remain more than an execution checklist. It is the source of the product
story used by README, docs, generated agent instructions, and release notes.

When documentation is updated, keep the vision visible:

- Lead with the idea that LogicChart helps coding agents and humans understand code logic,
  not with a list of terminal commands.
- Present the workflow slice as the central product output: a focused, navigable piece of
  the decision flowchart selected for a user's question or change.
- Describe MCP as the primary runtime path, CLI as setup and maintenance, and the viewer
  as the official manual visual inspection mode.
- Present `logicchart view ...` as the one manual experience worth remembering.
- Explain that deterministic artifacts, evidence tiers, snapshots, and annotations exist
  to keep agent answers grounded in code.
- Avoid implying that provider LLM keys are required for the main workflow.
- Keep the language useful for a user who will ask an agent a plain question rather than
  manually operate low-level commands.

## Transformation Plan

The transformation should be executed in stable, reviewable phases. Each phase should keep
the deterministic core working, update docs and tests, and avoid making the viewer or
provider-managed LLM flows the center of the product.

Every phase should include repeated code-review passes. Reviews should explicitly check
for bugs, stale public surfaces, dead code, unreachable branches, obsolete docs, orphaned
tests, and duplicated logic introduced by the migration.

### Phase 0: Product Alignment

Goal: make every public surface describe the same product.

Deliverables:

- Update README, docs, CHANGELOG, `PROJECT_FINDINGS.md`, and generated agent
  instructions so LogicChart is presented as agent-first.
- Explain the hierarchy clearly: MCP runtime first, CLI substrate second,
  skills/instructions as activation, viewer as optional inspection.
- De-emphasize provider-managed LLM enrichment as an advanced optional path.
- Document agent-authored enrichment as the preferred path when generated summaries,
  labels, or explanations are useful.
- Remove stale references to old UI behavior, old install expectations, and command-first
  workflows.
- Replace references to `PRODUCT_VISION.md` with `PRODUCT_MIGRATION_PLAN.md`.
- Document the kept public CLI commands and the commands being removed from the public
  CLI.

Done criteria:

- A new reader understands that the normal workflow is "ask the coding agent", not
  "memorize LogicChart commands".
- No primary docs imply that API keys or provider setup are required for the main product
  experience.
- Instructions tell agents to use LogicChart help surfaces when they need command or tool
  details instead of guessing.

### Phase 1: Agent-first Setup

Goal: let users configure LogicChart once, then use it through their coding agent.

Deliverables:

- Add `logicchart setup-agent codex|claude|cursor`.
- Make setup verify the local install, create or update `logicchart.toml` only when
  needed, register MCP where supported, and refresh all known agent instruction files or
  skills together so Codex, Claude, Gemini, Cursor, and future agent surfaces do not drift.
- Run initial artifact generation, `doctor`, and validation as part of setup.
- Preserve local instruction blocks that are not owned by LogicChart.
- When changing generated guidance for one agent Markdown file, apply the equivalent
  product guidance to every supported agent Markdown target while preserving target-specific
  frontmatter and local notes.
- Explain successful setup in terms of questions users can ask the agent.
- Fold `logicchart init` and `logicchart install` into the new setup path.
- Remove stale generated instructions that tell users or agents to run `query`, `impact`,
  `explain`, `navigate`, or `snapshot` manually.

Done criteria:

- A fresh project can be prepared for agent use with one command.
- Setup does not erase important local instructions such as private-project warnings.
- The success output is user-oriented and agent-oriented, not just command-oriented.
- The public setup story does not require users to know `init` or `install`.

### Phase 2: Workflow Slice Agent Context

Goal: give agents one primary tool that turns ordinary code-logic questions into a
workflow slice.

Deliverables:

- Add a primary MCP `agent_context` tool.
- Accept natural question context: question text, changed files, selected code, current
  file, symbol, flow id, finding id, dependency path, token budget, and visual preference.
- Internally orchestrate the existing query, impact, navigation, explanation,
  review-signal inspection, and snapshot selection logic.
- Return one bounded `workflow_slice` with matched flows, selection reasons, ordered
  workflow steps, callers, callees, decisions, outcomes, domain logic, review signals,
  unresolved calls, source ranges, visual references, omissions, and suggested next
  actions.
- Add stable slice ids or handles so follow-up MCP calls can expand, render, or inspect the
  same slice without reselecting from scratch when the underlying artifact has not changed.
- Make the agent-facing payload structured enough that an agent can produce a user answer
  with clear sections: what happens, where it happens, important branches, evidence,
  uncertainty, and next checks.
- Remove `query`, `impact`, `explain`, `navigate`, and `snapshot` from the public CLI.

Done criteria:

- An agent can answer "how does this component work?" or "what is impacted by this
  change?" by calling one primary LogicChart tool and receiving a workflow slice.
- Lower-level MCP tools remain available for expert use, but are not required for the
  common path.
- `INFERRED` and `POTENTIAL_GAP` review signals remain clearly distinguished from
  confirmed defects.
- Manual users are routed to either `logicchart view` or the coding agent, not to
  low-level query/impact commands.

### Phase 3: Slice Navigation, Paths, and Snapshots

Goal: make workflow slices progressively navigable and visually useful without requiring a
human to open the viewer.

Deliverables:

- Add `expand_slice`, `workflow_path`, focused entity explanation, and deterministic
  snapshot/subgraph output through MCP.
- Support flow snapshots, workflow-slice snapshots, impact-set snapshots, review-signal
  context snapshots, and caller/callee neighborhoods.
- Return compact SVG/PNG paths or payload references plus machine-readable metadata.
- Make all snapshot generation budget-aware, with explicit omitted counts.
- Keep rendering deterministic and light enough for large repositories.
- Preserve flowchart ordering and decision semantics in snapshots instead of rendering a
  generic force graph.

Done criteria:

- An agent can request visual context for a workflow slice, focused flow, or change and use
  it in an explanation.
- Snapshot output is useful even when the full viewer would be too large or too slow.
- There is no public `logicchart snapshot` command; humans use `logicchart view` for
  manual visual exploration.

### Phase 4: Agent-authored Annotations

Goal: let the coding agent enrich LogicChart without provider keys or external LLM setup.

Deliverables:

- Add a validated annotation sidecar format.
- Add MCP write tools: `preview_annotation_targets`, `write_annotations`,
  `validate_annotations`, `clear_annotations`, and `annotation_status`.
- Keep annotation writes primarily MCP-driven. Add CLI mirrors only if they fit inside the
  kept maintenance surface and do not become a new manual workflow.
- Validate target ids, schema version, model hash, text limits, source type, and
  annotation provenance.
- Display annotations as `agent_generated` in MCP responses, snapshots, and the viewer.

Done criteria:

- The agent can write clearer flow names, summaries, review-signal explanations, remediation
  notes, and "what to inspect next" guidance.
- Generated annotations are never confused with deterministic analyzer facts.
- Provider-managed enrichment remains optional and advanced, not the primary path.

### Phase 5: Domain Logic Maps

Goal: expose business logic, not just code structure.

Deliverables:

- Extract domain concepts such as enums, statuses, roles, permissions, feature flags,
  lifecycle states, and payment states.
- Map handled values, missing values, transitions, invalid states, owners, and related
  flows.
- Connect domain maps to review signals, source ranges, snapshots, and `agent_context`.
- Support questions such as "where is this state handled?", "which enum values are
  missing?", and "what changes if I add this status?".

Done criteria:

- LogicChart can explain important domain state handling across a codebase.
- Agents can reason about missing cases and change impact at the domain level.

### Phase 6: Viewer as Secondary Inspection Surface

Goal: keep the UI valuable, fast, and available as the official manual flowchart
experience.

Deliverables:

- Keep `logicchart view ...` as the official manual command for opening the UI and
  visualizing the decision flowchart.
- Treat the UI as an intentional manual mode, not the default agent-first workflow.
- Align the viewer with workflow slices, review signals, annotations, snapshots, and domain
  maps.
- Let users open a workflow slice or snapshot target from an agent answer when such a link
  or artifact reference is available.
- Preserve progressive expand/collapse, focus, reset, export, zoom, pan, drag, and stable
  selection.
- Keep large-codebase performance healthy with layout cache, chunked expansion, and
  lightweight overview rendering.
- Avoid reintroducing the minimap.
- Keep UI styling professional, solid-color based, and free of overlapping elements.

Done criteria:

- The viewer is useful for deep inspection and debugging but not required for the main
  agent-first workflow.
- Users can still run one clear manual command to open and inspect the flowchart.
- Expand-heavy codebases remain responsive enough for practical use.

### Phase 7: Quality, Compatibility, and Release Readiness

Goal: make the transformation reliable enough to merge and release later.

Deliverables:

- Add focused tests for setup-agent, MCP `agent_context`, annotation validation,
  workflow-slice ranking, slice expansion, workflow paths, snapshot/subgraph output,
  domain maps, and viewer regressions.
- Keep generated artifacts synchronized.
- Preserve ignored/private behavior for local real-world fixtures such as
  `examples/Certifexp`.
- Update all relevant Markdown files when behavior changes.
- Track remaining gaps in `PROJECT_FINDINGS.md`.
- Run several code-review passes across each macro phase to catch bugs, dead code, stale
  command references, and inconsistent docs before committing a stable point.

Done criteria:

- The standard Python and viewer gates pass.
- Local Certifexp checks pass when the private fixture is present.
- The branch has clear commits for stable milestones.
- Merge is recommended only when the agent-first workflow works end to end.
- The final CLI public surface is limited to the kept commands listed in this plan.

Recommended verification gates:

```bash
UV_CACHE_DIR=/tmp/logicchart-uv-cache uv run ruff check .
UV_CACHE_DIR=/tmp/logicchart-uv-cache uv run ruff format --check .
UV_CACHE_DIR=/tmp/logicchart-uv-cache uv run mypy
UV_CACHE_DIR=/tmp/logicchart-uv-cache uv run pytest --cov
UV_CACHE_DIR=/tmp/logicchart-uv-cache uv run logicchart validate . --check-sync --json
npm run viewer:typecheck
npm run viewer:test
npm run viewer:build
UV_CACHE_DIR=/tmp/logicchart-uv-cache uv run logicchart update
UV_CACHE_DIR=/tmp/logicchart-uv-cache uv run logicchart view examples/demo --render-only --no-open
```

If `examples/Certifexp` exists locally:

```bash
UV_CACHE_DIR=/tmp/logicchart-uv-cache uv run pytest tests/test_certifexp_local.py
```

## Feature Acceptance Test

A feature belongs in LogicChart if it helps an agent or human answer at least one of these
questions better:

- Which workflow slice answers this question?
- What does this code do?
- Which logical path am I looking at?
- What decisions and states control the behavior?
- What calls or callers are involved?
- What changes if I edit this?
- What looks missing, risky, or uncertain?
- What evidence proves this?
- What visual context can clarify it quickly?

If a feature does not improve code-logic understanding, impact reasoning, trust, or visual
orientation, it should not be central to the product.
