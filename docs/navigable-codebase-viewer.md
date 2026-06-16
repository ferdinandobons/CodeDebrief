# Navigable codebase viewer (design)

Status: design / brainstorming output (2026-06-16). Not yet implemented.

## Goal

Turn the viewer from "one flowchart per selected flow" into **one navigable model of a whole
codebase**: start at the macro level, drill into sub-pieces in place, and jump between the
graph, the directory, the source, and the logical findings - both ways. It must work for any
codebase LogicChart can analyze, not just the bundled demo.

## Background: what the viewer is today

`logicchart view` renders a single self-contained `logic-flow.html` (`render/html.py`, ~1050
lines) and serves it locally. The whole model is embedded as JSON in a
`<script type="application/json">` tag; no server round-trips for data. The page is already a
three-column shell (`grid-template-columns: 312px / 1fr / 336px`, an 78px top bar):

- left: a flat **flow list**
- center: the **flowchart of the selected flow** (decision nodes + edges, drag-to-arrange)
- right: a **detail panel** - a source *link*, the flow description, and related findings
  ("Review points")

This design is an evolution of that shell, not a rewrite.

## What the data already gives us (no IR/analyzer change)

Everything needed is already in `logic-flow.json`:

- **Directory + files**: `model.files[].path`, plus every `flow.location.path`.
- **Scopes**: `flow.metadata["scope"]` (a list of macro-parts) and `model.metadata["scopes"]`
  (per-scope counts). Scopes come from `[logicchart.scopes]` or the inferred top-level
  directory - the codebase decides how many there are, not this design.
- **Inter-flow call graph**: `flow.calls` / `flow.called_by` (resolved to target flow ids by
  the call linker), so flows can be drawn as nodes connected by call edges.
- **Per-flow decisions**: `flow.nodes` / `flow.edges` (the existing flowchart).
- **Findings**: `model.findings[]`, each carrying `flow_id`, `node_id` (the exact decision
  node), `kind`, and `evidence` - enough to tie a finding to its block and its source line.

The **one thing missing is source text**: today the right panel shows a source *link*, not
code. The new source panel needs the actual lines (see "Source snippets" below).

## Design decisions (settled in brainstorming)

1. **Navigation model: expand-in-place.** One canvas is *the* navigable graph. A node unfolds
   its detail in place; collapsing zooms back out. No separate "pages".
2. **Canvas starts at scope level.** Level 0 is one super-node per scope; the user expands
   down. (If the codebase declares no scopes, Level 0 is the inferred top-level directories;
   a flat repo starts at files.)
3. **Four regions** (evolving the existing three columns):
   - **Directory tree** (left) - real directory of the analyzed root; selects the subset.
   - **Canvas** (center) - the expand-in-place graph, with a full-screen toggle.
   - **Source** (right, top) - the file of the selection, the relevant line highlighted.
   - **Logical errors** (right, bottom) - the findings for the selection, by evidence tier.
4. **Bidirectional linking via a shared highlight.** Selecting any one of {a canvas block, a
   source line, a tree file, a finding} highlights the others in the same accent color.
5. **Full-screen canvas.** A toggle (and `Esc`) maximizes the canvas; side panels hide;
   selection is preserved on exit. Browser Fullscreen API with a CSS "maximize in page"
   fallback. Self-contained, no dependencies.
6. **Architecture: self-contained HTML, lazy rendering.** Only the expanded sub-graph is
   drawn; closed scopes stay single super-nodes. A local-server streaming mode is a possible
   future evolution for very large monorepos, not part of v1.

## Canvas: levels of detail

- **L0 - scopes.** One super-node per scope; edges are aggregated cross-scope calls. The whole
  codebase on one screen, readable.
- **L1 - a scope's flows.** Expanding a scope reveals its flows, grouped by directory/file,
  connected by call edges (`calls`/`called_by`). For a scope with hundreds of flows, the group
  is itself collapsible by folder/file so the canvas never dumps everything at once.
- **L2 - a flow's decisions.** Expanding a flow renders its decision flowchart inline in the
  flow card (reusing the current per-flow renderer). A `-` collapses it back.

A breadcrumb at the top of the canvas (e.g. `codebase / backend / orders/service.go`) walks
back up the levels.

## Interactions

- **Tree -> canvas.** Clicking a folder or file in the tree sets the canvas subset: a folder
  shows that subtree's flows; a file shows just its flows; the root shows the L0 scope view.
- **Expand / collapse** as above, in place, on the single canvas.
- **Bidirectional highlight.** Clicking a canvas block highlights its source line and its tree
  file (and its finding, if any); clicking a finding highlights its block + source line;
  clicking a tree file brings its graph forward. One selection model, one accent color.
- **Full screen.** Toggle on the canvas toolbar; panels hide; `Esc` or the toggle exits;
  selection survives. While full screen, block selection still highlights inside the canvas;
  the source/error highlights are already applied when the panels reappear.

## Source snippets (the only new data)

To show real code with a highlighted line, `render_html` (which already receives
`source_root`) embeds the source the panel needs into the JSON payload. Each file's lines are
embedded **once** in `payload["source_files"][path] = {start_line, lines}` (covering the union
of the line ranges its flows need), and each flow carries a lightweight reference
`flow["source"] = {path, start_line, end_line, elided?}` that slices its own window out of
that single copy. This:

- keeps the viewer self-contained (no fetch, works offline);
- is **bounded two ways**: a per-flow cap of `MAX_SNIPPET_LINES` (200) keeps only the head
  lines of a very long function and marks the tail `elided` (the panel shows an "N more lines"
  marker), and the file-level store embeds each file's lines once instead of re-embedding them
  per flow, so a file with many flows is not duplicated;
- is language-agnostic (plain text by line range, works for any supported language);
- changes only the **render payload**, not the model schema or the analyzer.

A node's `location` (path + line range) maps a clicked block to the exact line(s) to
highlight within its flow's snippet.

## Generality (no overfitting to the demo)

The design reads only the generic IR, so it holds for any codebase:

- **Scopes**: however many the project declares or infers (2, 5, 20, or none). None -> L0 is
  top-level directories; flat repo -> start at files.
- **Tree**: the actual analyzed directory, any shape.
- **Canvas**: call graph + decisions from the IR, identical across all 10 languages.
- **Errors**: any finding kind, shown with its evidence tier.
- **Scale**: large scope -> group by folder/file and stay lazy; large call graph -> draw only
  the expanded part. No hard-coded names, scopes, or language assumptions anywhere.

The bundled demo is only the concrete example used in mockups.

## Scope of changes

Concentrated in `render/html.py`:

- left column: flow list -> **directory tree** built from `files`/`flow.location`.
- center: per-flow chart -> **expand-in-place canvas** (L0 scopes / L1 flows / L2 decisions),
  reusing the existing decision renderer for L2.
- right column: detail panel -> **source panel** (embedded snippet) + **logical-errors panel**
  (findings by tier).
- add the **full-screen** toggle and the **cross-panel highlight** wiring.
- `render_html`: also embed per-flow source snippets (reads files under `source_root`).

No changes to the analyzer, the IR/model, or `logic-flow.json`'s schema.

## Phasing (each step verifiable on its own)

1. **Directory tree + selection.** Replace the flow list with a tree; selecting a node filters
   what the center shows (still the current per-flow chart). Ships value immediately.
2. **Canvas levels.** Scope super-nodes (L0) + a scope's call graph (L1) with expand/collapse.
3. **Expand-in-place decisions (L2).** Unfold a flow's decision chart inside its card.
4. **Source + errors panels, bidirectional highlight, full screen.** Embed snippets; split the
   right column; wire the shared selection; add the full-screen toggle.

## Non-goals / future

- Server-streamed sub-graphs for very large monorepos (keep the self-contained file for v1).
- Editing or running code from the viewer (it stays a read-only map).
- Cross-repo / multi-root views.

## Open questions

- L1 default grouping inside a scope: by file always, or only when a flow count threshold is
  crossed?
- Full-screen source: keep panels hidden (current decision) or offer an optional slim source
  overlay while full screen?
