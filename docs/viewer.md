# LogicChart Viewer

The LogicChart viewer is the manual exploration surface for a codebase logic graph. It is
offline, generated, and opened with `logicchart view`.

The default artifact is `logic-flow.html`: a single local HTML file with embedded CSS,
JavaScript, payload data, and the viewer runtime. It can be opened through
`logicchart view`, regenerated with `logicchart view --render-only`, or committed only when
that is useful for a project.

## Product Shape

The canvas should read as one navigable flowchart:

1. The first row is the codebase scope map.
2. Selecting a scope reveals entrypoints in that scope without closing previously opened
   scopes.
3. Selecting an entrypoint expands that flow in place, including decisions, outcomes, and
   direct call targets.
4. Selecting an internal flow reconstructs the visible caller chain from the scope
   entrypoint instead of placing that flow as a detached island.
5. Selecting a connection highlights the source node, target node, and connection while
   dimming unrelated blocks.
6. Selecting empty canvas space clears connection focus and returns the scope view to its
   normal contrast.

The renderer must remain shape-agnostic. It should never special-case names such as
`backend`, `frontend`, or `edge`; those are ordinary scope values from the generated model.

## Runtime Path

There is one official viewer path:

| Runtime | How to open it | Responsibility |
| --- | --- | --- |
| React runtime | `logic-flow.html` | Progressive canvas, scope nodes, scope-entry links, flow detail charts, viewport zoom/pan/reset, graph-bounds-aware raster export |

The React runtime is built from `frontend/` into
`src/logicchart/render/assets/generated/logicchart-viewer-runtime.iife.js` and then embedded
by `src/logicchart/render/html.py`.

The shell and React runtime share the same generated payload. The shell drives side panels
and tree selection; the React runtime synchronizes through hashes such as:

```text
#scope=frontend
#flow=<flow-id>
#root
#node=codebase
#edge=<encoded scope-entry connection>
```

Direct `#flow=<flow-id>` and `#path=<source-path>` openings should select the matching
source context and open the Details rail automatically.

## Manual And Agentic Modes

LogicChart has one purpose and two modes:

- Manual mode: `logicchart view` opens the full interactive graph for exploration.
- Agentic mode: MCP returns a bounded `workflow_slice` for a specific question or change.

The manual viewer should stay rich and interactive. It is not replaced by Mermaid or a
static screenshot. MCP snapshots and canonical Mermaid diagrams are for agent answers,
chat clients, and compact slice sharing.

For repeated visual workflow requests, agents should use `snapshot_slice` first and render
`snapshot.svg` through an SVG/HTML visualization widget when the client provides one. When
inline SVG is unavailable, `snapshot_slice include_svg=false` returns local
`artifact.html_path` and `artifact.svg_path` values that can be opened outside the chat.
`workflow_slice.presentation.canonical_visual.diagram` is the exact top-to-bottom Mermaid
text fallback for copyable output.

Agents should inspect the full returned slice, request expansion or paths when relevant
context is missing, then choose the clearest useful first-pass subset to show. That choice
may omit low-signal implementation nodes, but every visible block must be derived from the
selected slice or focused explain-tool payloads. The answer should say the diagram is a
bounded summary that can be expanded, then offer to simplify labels in the user's
language, expand omitted nodes or adjacent flows, or explore a related area.

## Details Rail

The Details rail provides bounded context for the current selection:

- project quality and analyzer coverage;
- selected source range;
- selected flow, node, edge, caller, or callee context;
- optional agent-authored annotations for flow, node, or scope labels and summaries.

Project quality is a compact analyzer snapshot. It may show skipped files, parse warnings,
call-resolution rate, generic-label ratio, graph density, huge-flow signals, language
distribution, and per-language capability notes. These are model-coverage signals, not
application defect reports.

The Details rail sections are independently collapsible from their headings. The viewer
remembers the state locally in the browser.

## Layout Rules

The viewer layout should preserve these invariants:

- Top-level scope nodes use the same node styling family as entrypoints and flows.
- Scope colors come from deterministic per-payload hues, not hard-coded names.
- A scope connects to every visible entrypoint below it.
- Previously opened scopes remain expanded when another scope is selected.
- Selecting the codebase root uses `#node=codebase` and highlights connected scopes
  without expanding an arbitrary fallback scope.
- Reset clears opened scopes, opened flows, manual positions, and viewport state, then
  returns to `#root`.
- Expand all opens every non-test scope and flow from the generated payload as a
  lightweight overview with a visible progress indicator.
- Expanded scope sections follow the root-map rows, so large codebases pack into readable
  vertical bands instead of one unbounded horizontal strip.
- Fit re-centers the current visible flowchart without closing expanded scopes, expanded
  flows, or manual block positions.
- Expanded flow detail charts reserve their visual band before later rows are placed.
- Every visible flow node is reachable from the codebase root through root-scope,
  scope-entry, or flow-call edges.
- Hidden hit paths exist for pointer targeting but must never render visible boxes.
- Pan and zoom are viewport operations; they must not mutate model layout.
- Wheel and trackpad zoom must stay anchored to the cursor in the active runtime.
- The left tree may normalize display labels for scanning, but tooltips and source panels
  must preserve the original symbol and source path.
