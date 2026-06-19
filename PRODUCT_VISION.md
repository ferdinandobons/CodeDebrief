# LogicChart Product Vision

## North Star

LogicChart is an agent-first, local understanding layer for code logic.

Developers should be able to set it up once, then ask their coding agent simple questions
such as:

- How does this feature work?
- What logic is involved in this change?
- What could break if I edit this file?
- Where is this state handled?
- Why did the AI-generated code create this branch?
- Which decisions, callers, callees, and missing cases should I review?

LogicChart should give the agent deterministic, visual, and structured context so the
answer is grounded in the actual codebase instead of plausible narration.

## Product Positioning

LogicChart is not primarily a terminal tool or a graph viewer.

It is a support system for coding agents. Its job is to make code logic inspectable,
queryable, and explainable for both humans and AI, especially in projects where modern
development is mediated by agents such as Codex, Claude, Cursor, or similar tools.

The distribution model should be hybrid, with one clear hierarchy:

1. MCP and agent workflows are the primary runtime surface.
2. CLI is the local executable substrate for setup, repair, CI, explicit refresh, and
   debugging.
3. Agent instructions and skills are the activation layer that teach each coding agent
   when and how to use LogicChart.
4. The viewer exists for optional human inspection and deep visual exploration.
5. Generated artifacts are the shared source of truth between humans, agents, CI, and UI.

MCP should remain the primary integration channel because it exposes structured tools and
resources directly to coding agents. The CLI should not compete with MCP; it should power
MCP, setup, validation, and fallback workflows. Skills or agent instruction files should
not replace MCP either; they should package the usage policy, examples, and decision rules
that make the agent reach for LogicChart automatically when the user asks about code logic.

## Core Promise

After setup, users should not need to remember LogicChart commands.

They should ask their coding agent ordinary questions, and the agent should use
LogicChart automatically to:

- retrieve the relevant flows;
- inspect decisions, calls, callers, callees, and outcomes;
- identify logical findings and their evidence tier;
- understand impact from changed files, symbols, flows, findings, and dependencies;
- request deterministic visual snapshots;
- distinguish verified facts from inferred review candidates;
- generate useful explanations without losing source-grounded traceability.

## Design Principles

### Agent-first

Every major capability should be usable through MCP and structured payloads. Human-facing
CLI commands should mirror these capabilities, but should not be the main expected path.

### Local-first and deterministic

The core model must work offline and must not require an LLM. Correctness comes from the
local analyzer, schema validation, source locations, evidence tiers, and deterministic
snapshots.

### Visual context for agents

Because the product is about flowcharts, agents need visual artifacts too. SVG snapshots
for flows, findings, impact sets, and explicit subgraphs are first-class context, not a
secondary export feature.

### One orchestration path

Agents should not have to manually stitch together many low-level tools for common tasks.
LogicChart should provide a unified context workflow that accepts a user question, changed
files, selected code, target flow, finding, or symbol, then returns a bounded understanding
pack.

The lower-level tools should remain available for expert or fallback use, but the expected
agent path should be:

```text
user question -> agent instruction/skill trigger -> MCP agent_context -> deterministic
context pack -> agent explanation or code change
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

Agents must not present inferred findings or generated enrichment as confirmed bugs.

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

The primary MCP capability should become a unified context tool, conceptually:

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

The response should include:

- matched flows and why they were selected;
- impact reasons;
- direct and transitive flow ids;
- caller and callee summaries;
- decision nodes and handled values;
- unresolved calls;
- related findings with evidence tiers;
- source snippets or source ranges;
- subgraph flow and finding ids;
- visual snapshot payloads or follow-up snapshot tool calls;
- omitted counts and budget guardrails;
- recommended next tools;
- recommended human review points.

This should be the default path for questions such as:

- "Explain how checkout works."
- "Review the logical impact of my change."
- "What logic touches this status?"
- "Show me the flow around this bug."
- "What should I test after this edit?"

The context tool should be opinionated enough that an agent can use it from natural
language, but transparent enough that advanced users can inspect which flows, findings,
source files, snapshots, and omissions were included.

## Channel Strategy

### MCP: primary runtime integration

MCP should expose a small set of high-value tools and resources that map to real agent
tasks:

- `agent_context` for question-driven understanding;
- `impact` for change review;
- `query` for targeted search across generated flow artifacts;
- `navigate` and `explain` for focused flow inspection;
- `snapshot` or subgraph rendering for visual context;
- annotation write/validate tools for agent-authored enrichment.

The MCP surface should avoid forcing agents to call many tiny tools before they can answer
ordinary user questions. Low-level tools are useful, but the default path should be the
single context pack.

### CLI: setup, maintenance, and fallback

The CLI remains essential because it is the stable local executable:

- setup agent integrations;
- analyze and update artifacts;
- validate synchronization;
- run doctor checks;
- support CI;
- debug or reproduce MCP behavior;
- provide explicit commands when an agent integration is unavailable.

The CLI should mirror agent capabilities where useful, but its documentation should make
clear that most users are expected to interact through their coding agent after setup.

### Skills and agent instructions: activation layer

Skills and instruction files are how LogicChart becomes discoverable inside the agent's
normal workflow. Their job is to encode behavior:

- when the agent should call LogicChart;
- which user questions imply code-flow analysis;
- how to respect trust tiers;
- when to refresh artifacts;
- how to cite source ranges and flow ids;
- how to avoid overstating inferred findings;
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
6. The viewer, snapshots, `navigate`, `explain`, and context packs display those
   annotations separately from deterministic diagnostics.

Potential tools:

- `preview_annotation_targets`
- `write_annotations`
- `validate_annotations`
- `clear_annotations`
- `annotation_status`

Potential CLI mirrors:

- `logicchart annotations validate`
- `logicchart annotations import`
- `logicchart annotations clear`

Annotations should support:

- flow names and summaries;
- node labels and summaries;
- scope/group summaries;
- finding explanations;
- remediation notes;
- domain concept descriptions;
- "what to inspect next" notes.

## Strategic Product Pillars

### 1. Understand how code works

LogicChart should explain entrypoints, decisions, branches, calls, outcomes, and source
locations in a way that both humans and agents can follow.

### 2. Understand what changes affect

LogicChart should map edits to impacted flows, callers, findings, decisions, and test
suggestions.

### 3. Understand domain logic

LogicChart should identify important domains such as statuses, roles, permissions,
lifecycle states, payment states, and feature flags, then show where they are handled or
missing.

### 4. Understand trust and uncertainty

LogicChart should expose analyzer capability, skipped files, parse warnings, unresolved
calls, evidence tier, confidence, and snapshot omissions so agents do not overstate what
they know.

### 5. Make visual context available without opening the UI

The viewer remains useful, but agents should be able to request compact deterministic SVG
snapshots directly through MCP or CLI.

## Product Roadmap Direction

### Phase 1: Agent-first setup

- Add `logicchart setup-agent`.
- Make MCP setup and instruction refresh the default recommended path.
- Make `doctor` and artifact validation part of setup.
- Document common user questions instead of command-first workflows.
- Generate or refresh agent-specific instructions/skills that explain when to use
  LogicChart.

### Phase 2: Unified agent context

- Add a primary MCP `agent_context` tool.
- Add a CLI mirror for debugging and CI.
- Internally orchestrate query, impact, navigate, explain, and snapshot selection.
- Return one bounded context pack with next actions.

### Phase 3: Agent-authored annotations

- Add MCP write tools for validated annotations.
- Treat provider-managed LLM enrichment as advanced and optional.
- Keep annotation sidecars separate from deterministic model artifacts.
- Make annotations traceable to the agent, model context, model hash, target ids, and
  validation status without requiring provider API keys.

### Phase 4: Domain and state maps

- Extract state machines and domain concepts.
- Show handled values, missing values, transitions, invalid states, and ownership.
- Expose the same maps through MCP, CLI, and viewer.

### Phase 5: Change review intelligence

- Add change-aware review packs from diff/current files.
- Suggest logical tests from decisions and missing branches.
- Highlight generated or modified logic that lacks callers, outcomes, or explicit handling.

## Feature Acceptance Test

A feature belongs in LogicChart if it helps an agent or human answer at least one of these
questions better:

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
