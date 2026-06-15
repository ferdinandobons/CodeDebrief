# LogicChart Technical Design

## Product

LogicChart turns a source folder into navigable decision flowcharts. Its primary job is
to help humans and coding agents understand what a project can do, identify behavior that
was handled in one path but forgotten in another, and evaluate the impact of a change.

The initial language support is Python and TypeScript/TSX. The initial framework adapters
cover FastAPI and Next.js, including shallow React component, hook, and event recognition.

## Principles

1. The deterministic analyzer is useful without an API key.
2. Source-backed facts and heuristic findings are never presented as equivalent.
3. The human-facing artifact is a decision flowchart, not a generic dependency graph.
4. Functional decisions are shown by default; implementation noise is compressed.
5. Every visual node links back to a source file and line.
6. One canonical JSON artifact powers the CLI, MCP server, Markdown, and HTML UI.
7. Updates are explicit and incremental.

## Architecture

```text
Source folder
    |
    v
Discovery and ignore rules
    |
    +--> Python AST analyzer
    |
    +--> TypeScript/TSX Tree-sitter analyzer
    |
    v
Language-neutral logical IR
    |
    +--> Cross-file call linker
    +--> Framework entry-point adapters
    +--> Gap and inconsistency detectors
    +--> Test-reference annotator
    |
    v
logicchart-out/logic-flow.json
    |
    +--> logic-flow.md
    +--> logic-flow.html
    +--> CLI queries and impact analysis
    +--> MCP tools
```

## Logical IR

The project contains flows, nodes, edges, findings, file hashes, and source locations.

Node kinds:

- `entry`: route, command, event, job, public function, or component entry.
- `action`: a compressed unit of work.
- `decision`: a functional branch such as authorization, validation, state, or outcome.
- `call`: a call to another internal flow or an important external boundary.
- `terminal`: return, response, or successful completion.
- `error`: raised or returned failure.

Decision metadata (carried in the open `node.metadata`):

- Identity: `subject` (dotted left-hand side), `operator` (`==`/`!=`/`is`/`in`/…),
  `negation`, and `value_namespace` (the shared dotted enum prefix of the compared values).
- `branches`: one record per outgoing branch with its `outcome`
  (`returns`/`raises`/`falls_through`/`empty`/`continues`) and an `implicit` flag for the
  synthetic else/default branch.
- `reachable_from_entry` / `reaches_terminal`: deterministic graph-reachability flags on
  every node.

Evidence levels:

- `VERIFIED`: extracted directly from syntax or framework conventions.
- `INFERRED`: produced by a deterministic heuristic.
- `POTENTIAL_GAP`: a missing or inconsistent case that requires review.

## Update Model

`.logicchart/cache/` stores one normalized analysis result per source file. `logicchart
update` hashes source files, reparses changed files, removes deleted entries, reloads
unchanged entries from cache, then reruns project-level linking and findings.

The committed artifacts are:

- `logicchart-out/logic-flow.json`
- `logicchart-out/logic-flow.md`

The generated HTML is local by default and ignored by Git.

## Agent Workflow

`logicchart install` writes an idempotent instruction block to supported agent files.
After a substantial code change, an agent must:

1. Run `logicchart impact`.
2. Review affected flows and potential gaps.
3. Run `logicchart update`.
4. Ensure the generated JSON and Markdown are synchronized.

The MCP server exposes read tools plus an explicit update tool so an authorized agent can
query and refresh the model autonomously.

## Scope Boundaries

The first version does not attempt full symbolic execution, runtime tracing, exact data-flow
analysis, or deep React state reconstruction. It favors explainable high-signal heuristics
and always links findings to the evidence that produced them.
