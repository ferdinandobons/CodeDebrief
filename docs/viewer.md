# LogicChart viewer

The LogicChart viewer is an offline, generated UI for studying large codebases as one
progressive decision flowchart.

The default artifact is still `logic-flow.html`: a single local HTML file with embedded
CSS, JavaScript, payload data, and the optional framework runtime. It can be opened through
`logicchart view`, committed as a generated artifact when useful, or regenerated with
`logicchart view --render-only`.

## Product shape

The canvas should read as one navigable flowchart:

1. The first row is the codebase scope map (`backend`, `frontend`, `edge`, or any configured
   macro-part).
2. Selecting a scope reveals the entrypoints in that scope while keeping the whole map
   understandable.
3. Selecting an entrypoint expands that flow in place, including its decisions, outcomes,
   and direct call targets.
4. Selecting a connection highlights the source node, target node, and connection while
   dimming unrelated blocks.
5. Selecting empty canvas space clears connection focus and returns the scope view to its
   normal contrast.

The renderer must remain shape-agnostic. It should never special-case names such as
`backend`, `frontend`, or `edge`; those are ordinary scope values from the generated model.

## Runtime paths

There are two viewer paths during the frontend migration:

| Runtime | How to open it | Responsibility |
| --- | --- | --- |
| Static shell | `logic-flow.html` | Default viewer, tree, panels, theme, side rails, legacy canvas, fullscreen |
| React runtime | `logic-flow.html?runtime=react` | Framework-backed progressive canvas, scope nodes, scope-entry links, flow detail charts, viewport zoom/pan/reset, raster export |

The React runtime is built from `frontend/` into
`src/logicchart/render/assets/generated/logicchart-viewer-runtime.iife.js` and then embedded
by `src/logicchart/render/html.py`. The generated HTML falls back to the static runtime if
the React bundle is unavailable or fails to mount.

The shell and React runtime deliberately share the same generated payload. The shell still
drives the side panels and tree selection; the React runtime synchronizes through hashes
such as:

```text
#scope=frontend
#flow=<flow-id>
#edge=<encoded scope-entry connection>
```

## Layout rules

The viewer layout should preserve these invariants:

- Top-level scope nodes use the same node styling family as entrypoints and flows.
- A scope connects to every visible entrypoint below it.
- Expanded flow detail charts reserve their visual band before later rows are placed.
- Hidden hit paths exist for pointer targeting but must never render visible boxes.
- Pan and zoom are viewport operations; they must not mutate model layout.
- Reset returns to the current route's automatic layout and viewBox.
- Large entrypoint rows wrap instead of forcing unbounded horizontal overflow.

The frontend tests expose reusable layout checks through `viewerLayoutBoxes` and
`overlappingLayoutBoxes`. Add new overlap cases when changing spacing, node sizes, row
wrapping, or inline detail measurements.

## Development workflow

Install the frontend workspace once:

```bash
npm install
```

For viewer changes, run:

```bash
npm run viewer:typecheck
npm run viewer:test
npm run viewer:build
UV_CACHE_DIR=/tmp/logicchart-uv-cache uv run logicchart update
UV_CACHE_DIR=/tmp/logicchart-uv-cache uv run logicchart view examples/demo --render-only --no-open
```

Before declaring a viewer change done, also run:

```bash
node --check src/logicchart/render/assets/generated/logicchart-viewer-runtime.iife.js
node --check src/logicchart/render/assets/shell.js
node --check src/logicchart/render/assets/canvas.js
node --check src/logicchart/render/assets/tree.js
UV_CACHE_DIR=/tmp/logicchart-uv-cache uv run pytest tests/test_render_html.py
UV_CACHE_DIR=/tmp/logicchart-uv-cache uv run pytest
```

Browser checks should use a regenerated demo artifact and a cache-buster URL:

```text
http://localhost:<port>/examples/demo/logicchart-out/logic-flow.html?runtime=react&v=<stamp>#scope=frontend
```

High-value browser checks:

- Scope view stays on `#scope=frontend` and does not open a flow by default.
- Scope node count, entrypoint node count, and scope-entry edge count match the payload.
- Clicking a scope-entry connection selects exactly one link, one source, and one target,
  while unrelated nodes/links dim.
- Clicking blank canvas clears connection focus.
- Clicking an entrypoint from the canvas and from the tree opens the same flow detail.
- The source panel shows the selected flow's file and line range.
- Zoom, pan, reset, PNG export, and JPG export route through the active runtime.
- SVG hit paths remain invisible in screenshots and exports.

## Documentation discipline

Keep `README.md`, `CONTRIBUTING.md`, this file, and the generated agent instructions in
sync whenever the viewer workflow changes. Do not document React runtime behavior as the
default until `logicchart view` enables it without `?runtime=react` and the browser parity
checks above are green.
