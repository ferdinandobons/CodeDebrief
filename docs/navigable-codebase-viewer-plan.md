# Navigable codebase viewer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **This plan is executed with multi-agent `Workflow` orchestration** — see "Execution model" below — including a periodic code-review workflow between every phase.

**Goal:** Evolve `logicchart view` into one navigable model of a whole codebase: an expand-in-place canvas (scopes → flows → decisions), a directory tree, a source panel, and a logical-errors panel, all cross-linked, with a full-screen canvas.

**Architecture:** Self-contained HTML viewer, lazy-rendered. No analyzer/IR/schema change — all data is already in `logic-flow.json`; the only new data is per-flow source snippets embedded at render time. Phase 0 refactors the monolithic `render/html.py` into a Python payload builder plus focused, separately-editable asset fragments (CSS + JS modules) that `render_html` inlines, so later phases parallelize cleanly under `Workflow`.

**Tech Stack:** Python 3.10+ (render path, pytest), vanilla JS + SVG (the embedded viewer, no runtime deps), `uv` for tooling.

**Spec:** [docs/navigable-codebase-viewer.md](navigable-codebase-viewer.md)

---

## Execution model (Workflow orchestration)

Per the user's requirement, implementation and review run as `Workflow` scripts, not solo edits.

**Implementation workflows (per phase):**
- Where a phase touches **independent files** (e.g. Phase 4's `source`, `errors`, `fullscreen` modules), fan out one agent per file with `isolation: 'worktree'` so parallel edits never conflict, then integrate.
- Where a phase is one **hard algorithm** (Phase 2 canvas layout / expand-collapse state), first run a **judge-panel**: 3 agents each draft an approach from a different angle (minimal-DOM, layered-layout-first, state-machine-first), parallel judges score them, synthesize the winner. Then a single implementer agent builds it (same-file work stays sequential).
- Same-file sequential tasks (Phase 0 refactor, Phase 3) run as a **pipeline** of one agent per task in order — the workflow value here is the structured per-task agent plus the review gate, not parallelism.

**Periodic code-review workflow (between every phase — the gate):** after a phase's tasks pass locally, run a review `Workflow` that fans out one reviewer per dimension, then adversarially verifies each finding before it counts:

```js
// review-phase.js (sketch — run after each phase, gates the next)
export const meta = { name: 'review-viewer-phase', description: 'Multi-dimension review of a viewer phase', phases: [{title:'Review'},{title:'Verify'}] }
const DIMENSIONS = [
  { key: 'correctness',  prompt: 'Review the git diff for this phase for logic bugs and broken behavior. Run the CI mirror.' },
  { key: 'generality',   prompt: 'Does anything hard-code demo scopes/paths/languages? It must work for any codebase (0..N scopes, any tree, any of the 10 languages, any finding kind).' },
  { key: 'performance',  prompt: 'Is rendering lazy? Are closed scopes left as super-nodes? Any O(all-nodes) work on load?' },
  { key: 'a11y-ui',      prompt: 'Keyboard nav, focus, ARIA, dark mode, no layout breakage in the existing shell.' },
  { key: 'security',     prompt: 'Embedded source snippets and labels must stay escaped (no HTML/JS injection from source-derived text).' },
]
const results = await pipeline(DIMENSIONS,
  d => agent(d.prompt, { label:`review:${d.key}`, phase:'Review', schema: FINDINGS }),
  review => parallel((review.findings||[]).map(f => () =>
    agent(`Adversarially verify, default to refuted if unsure: ${f.detail}`, {label:`verify:${f.key}`, phase:'Verify', schema: VERDICT})
      .then(v => ({...f, verdict:v})))))
return { confirmed: results.flat().filter(Boolean).filter(f => f.verdict?.real) }
```

The phase is **not** considered done until the review workflow returns zero confirmed major findings and the CI mirror is green.

**CI mirror (run locally before every commit):**
```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q
```

---

## File structure (after Phase 0)

| Path | Responsibility |
|---|---|
| `src/logicchart/render/html.py` | `render_html`: assemble the page — inline CSS + JS assets, embed the payload. Thin. |
| `src/logicchart/render/payload.py` | `build_payload(model, source_root)`: the JSON-serializable dict — model + per-flow source snippets + derived directory tree + scope index. Pure Python, fully unit-tested. |
| `src/logicchart/render/assets/styles.css` | All viewer CSS (moved out of the Python string). |
| `src/logicchart/render/assets/shell.js` | App bootstrap, layout shell, the shared selection store. |
| `src/logicchart/render/assets/tree.js` | Directory tree render + click-to-select. |
| `src/logicchart/render/assets/canvas.js` | Expand-in-place graph: L0 scopes, L1 flows/call-graph, L2 decisions; layered layout; full-screen. |
| `src/logicchart/render/assets/panels.js` | Source panel + logical-errors panel. |
| `tests/test_render_payload.py` | Unit tests for `build_payload`. |
| `tests/test_render_html.py` (exists) | Smoke tests: rendered HTML contains the expected hooks/ids. |

`render_html` reads the asset files via `importlib.resources`/`Path(__file__).parent` and inlines them, so the output stays a single self-contained `logic-flow.html`.

---

## Phase 0 — Refactor to focused, parallelizable modules

Goal: behavior-preserving split so later phases parallelize. Run as a **sequential pipeline workflow**, one agent per task, review gate at the end.

### Task 0.1: Extract the viewer payload into `payload.py`

**Files:**
- Create: `src/logicchart/render/payload.py`
- Modify: `src/logicchart/render/html.py` (use `build_payload`)
- Test: `tests/test_render_payload.py`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path
from logicchart.analysis.project import ProjectAnalyzer
from logicchart.render.payload import build_payload

def test_payload_carries_model_and_root(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def f(x):\n    if x:\n        return 1\n    return 0\n")
    model = ProjectAnalyzer(tmp_path).analyze(full=True).model
    payload = build_payload(model, tmp_path)
    assert payload["root"]
    assert isinstance(payload["flows"], list) and payload["flows"]
```

- [ ] **Step 2: Run it, expect ImportError/FAIL** — `uv run pytest tests/test_render_payload.py -q`

- [ ] **Step 3: Implement `build_payload`** — move the `model.to_dict()` + `root` assembly currently inside `render_html` into `build_payload(model, source_root)`; return the dict.

- [ ] **Step 4: Rewire `render_html`** to call `build_payload` and JSON-encode its result (keep the existing `</`→`<\/` escaping).

- [ ] **Step 5: Run CI mirror, expect PASS** (existing `tests/test_render_html.py` must still pass — behavior preserved).

- [ ] **Step 6: Commit** — `chore(render): extract build_payload (no behavior change)`

### Task 0.2: Move CSS and JS out of the Python string into `assets/`

**Files:**
- Create: `src/logicchart/render/assets/styles.css`, `.../shell.js`, `.../tree.js`, `.../canvas.js`, `.../panels.js`
- Modify: `src/logicchart/render/html.py`

- [ ] **Step 1:** Add a smoke test that the rendered HTML still contains a known existing marker (e.g. `id="logicchart-data"`, the data script) and the existing flow-canvas hook, so the move is verified behavior-preserving.
- [ ] **Step 2:** Run it (passes today).
- [ ] **Step 3:** Cut the existing `<style>` body into `assets/styles.css`; cut the existing `<script>` body into the JS asset files (start by putting all current JS in `shell.js`; the split into tree/canvas/panels happens as those phases land). Have `render_html` read each asset (`(Path(__file__).parent / "assets" / name).read_text()`) and inline it inside `<style>`/`<script>` tags.
- [ ] **Step 4:** Run the smoke test + a manual `uv run logicchart view examples/demo` to confirm the viewer is visually identical.
- [ ] **Step 5:** Ensure asset files ship in the wheel — add to `pyproject.toml` (`[tool.hatch.build.targets.wheel] force-include` or package-data) and verify with `uv build` that `assets/` is included.
- [ ] **Step 6: Commit** — `refactor(render): move viewer CSS/JS into assets/ fragments`

### Task 0.3: Phase-0 review gate
- [ ] Run the periodic review workflow (above). Fix confirmed findings. Require green CI + zero confirmed majors before Phase 1.

---

## Phase 1 — Directory tree + selection

Goal: replace the flat flow list with the real directory tree; selecting a node filters what the center shows (still the current per-flow chart). Sequential pipeline workflow.

### Task 1.1: Build the tree + scope index in the payload

**Files:**
- Modify: `src/logicchart/render/payload.py`
- Test: `tests/test_render_payload.py`

- [ ] **Step 1: Write the failing test**

```python
def test_payload_has_directory_tree_and_scopes(tmp_path: Path) -> None:
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "svc.py").write_text("def handler(x):\n    if x:\n        return 1\n    return 0\n")
    model = ProjectAnalyzer(tmp_path).analyze(full=True).model
    payload = build_payload(model, tmp_path)
    tree = payload["tree"]                      # nested {name, path, type, children, flow_ids}
    assert tree["type"] == "dir"
    names = {c["name"] for c in tree["children"]}
    assert "backend" in names
    assert "scopes" in payload                  # {scope_name: [flow_id, ...]} or inferred top-level
```

- [ ] **Step 2:** Run it, expect KeyError/FAIL.
- [ ] **Step 3: Implement** a pure helper `build_tree(files, flows)` that folds `file.path` segments into a nested dir/file tree, attaching `flow_ids` to file leaves; and `build_scope_index(flows)` that groups flow ids by `flow.metadata.get("scope")` (falling back to the top-level directory of `flow.location.path` when no scopes are declared — never hard-code names). Add both to the payload.
- [ ] **Step 4:** Run CI mirror, expect PASS.
- [ ] **Step 5: Commit** — `feat(render): directory tree + scope index in the viewer payload`

### Task 1.2: Render the tree and wire selection (`tree.js`)

**Files:**
- Modify: `src/logicchart/render/assets/tree.js`, `assets/shell.js` (selection store)

- [ ] **Step 1:** Add a rendered-HTML smoke test (`tests/test_render_html.py`): output contains `id="tree"` and a `data-path` attribute (the tree hooks).
- [ ] **Step 2:** Run it, expect FAIL.
- [ ] **Step 3: Implement** in `shell.js` a tiny selection store: `const selection = { path:null, flowId:null, nodeId:null, findingId:null }` and a `select(partial)` that updates it and notifies subscribers. In `tree.js`, render the `payload.tree` recursively (folders collapsible, files clickable, `data-path`/`data-flow-ids`); a click calls `select({path})`. For Phase 1, a `path` selection filters the existing center chart to flows under that path (root → all).
- [ ] **Step 4:** Run smoke test + manual `view`: tree shows, clicking a file scopes the center.
- [ ] **Step 5: Commit** — `feat(viewer): directory tree drives flow selection`

### Task 1.3: Phase-1 review gate — run the review workflow; require green.

---

## Phase 2 — Canvas levels (scopes → flows)

Goal: the center becomes the expand-in-place graph: L0 scope super-nodes, expand a scope to its flows linked by calls, with collapse. **Hard layout** → run the judge-panel workflow first, then implement.

### Task 2.0: Layout judge-panel (workflow, design only)
- [ ] Run a judge-panel `Workflow`: 3 agents draft the L0/L1 layered-layout + expand/collapse state model (angles: minimal-DOM/SVG reuse of the existing edge renderer; dagre-style layered layout in vanilla JS; explicit state-machine for expansion). Parallel judges score on simplicity, lazy-rendering, and fit with the existing `edgeGeometry`/positioning code. Output: the chosen approach written into this task's notes. No code committed yet.

### Task 2.1: L0 — scope super-nodes from the payload

**Files:** Modify `assets/canvas.js`, `payload.py` (cross-scope call aggregation), `tests/test_render_payload.py`

- [ ] **Step 1: Write the failing test** — `build_payload` exposes `scope_edges`: aggregated cross-scope call counts derived from `flow.calls` (flow ids) mapped to each flow's scope.

```python
def test_payload_aggregates_cross_scope_calls(tmp_path: Path) -> None:
    # two files in two top-level dirs, one calling the other; assert scope_edges links them
    ...
    payload = build_payload(model, tmp_path)
    assert any(e["from"] != e["to"] for e in payload["scope_edges"])
```

- [ ] **Step 2:** Run it, expect FAIL. **Step 3:** Implement `build_scope_edges(flows, scope_index)` (map each `call` target flow id → scope, count cross-scope pairs). **Step 4:** CI green. **Step 5:** Commit `feat(render): aggregate cross-scope call edges`.
- [ ] **Step 6 (JS):** In `canvas.js`, render L0: one node per scope (sized by flow count from `payload.scopes`), edges from `scope_edges`. Clicking a scope node expands it (Task 2.2). Manual-verify on `examples/demo` (4 scopes) **and** on a no-scope repo (top-level dirs) to confirm generality. Commit `feat(viewer): L0 scope super-nodes`.

### Task 2.2: L1 — a scope's flows as a call graph, expand/collapse

**Files:** Modify `assets/canvas.js`

- [ ] **Step 1:** Smoke test: HTML contains the canvas hooks (`id="canvas"`, a `data-level` attribute).
- [ ] **Step 2:** FAIL. **Step 3:** Implement expand: clicking a scope reveals its flows (from `scopes[scope]`) grouped by file, edges from `calls`/`called_by` restricted to the visible set; collapse returns to L0. **Lazy:** only the expanded scope's flows are added to the DOM; other scopes stay super-nodes. Breadcrumb reflects the path. **Step 4:** Manual-verify expand/collapse + a scope with many flows stays grouped-by-file (no full dump). **Step 5:** Commit `feat(viewer): expand a scope into its call graph`.

### Task 2.3: Phase-2 review gate — review workflow (emphasis: lazy rendering + generality on 0/1/many scopes). Require green.

---

## Phase 3 — Expand-in-place decisions (L2)

Goal: expanding a flow renders its decision flowchart inline in the flow card, reusing the existing per-flow renderer. Sequential pipeline workflow.

### Task 3.1: Inline decision sub-chart

**Files:** Modify `assets/canvas.js`

- [ ] **Step 1:** Smoke test: a flow card exposes an expand control (`data-expand="flow"`).
- [ ] **Step 2:** FAIL. **Step 3:** Refactor the existing per-flow render function so it can render into a given container at a given offset; call it when a flow node is expanded (the `−`/`+` toggle), drawing `flow.nodes`/`flow.edges` inside the card; collapse removes it. Keep drag-to-arrange working for the expanded sub-chart. **Step 4:** Manual-verify expand/collapse of a decision chart in place; breadcrumb shows `scope / file / flow`. **Step 5:** Commit `feat(viewer): expand a flow into its decisions in place`.

### Task 3.2: Phase-3 review gate — review workflow. Require green.

---

## Phase 4 — Source panel, errors panel, bidirectional highlight, full screen

Goal: the right column becomes Source (top) + Logical errors (bottom); selection cross-highlights everywhere; the canvas gets a full-screen toggle. These modules are **independent** → run the implementation as a **parallel workflow** (worktree isolation per module), then integrate.

### Task 4.1: Embed per-flow source snippets in the payload

**Files:** Modify `src/logicchart/render/payload.py`, `tests/test_render_payload.py`

- [ ] **Step 1: Write the failing test**

```python
def test_payload_embeds_source_snippets(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def f(x):\n    if x:\n        return 1\n    return 0\n")
    model = ProjectAnalyzer(tmp_path).analyze(full=True).model
    payload = build_payload(model, tmp_path)
    flow = payload["flows"][0]
    snip = flow["source"]                       # {"start_line": int, "lines": [str, ...]}
    assert snip["start_line"] == flow["location"]["start_line"]
    assert any("if x" in line for line in snip["lines"])
```

- [ ] **Step 2:** FAIL. **Step 3: Implement** `attach_source_snippets(flows, source_root)`: for each flow read `location.path` under `source_root`, slice `start_line..end_line`, store `{start_line, lines}`. Read each file once (cache by path). Tolerate missing/binary files (skip snippet, never crash) so it stays general. **Step 4:** CI green. **Step 5:** Commit `feat(render): embed per-flow source snippets`.

### Task 4.2 (parallel module): Source panel (`panels.js`)
- [ ] Render the selected flow's snippet with line numbers; when `selection.nodeId` is set, highlight the node's `location` line(s). Source text must be inserted as **text nodes** (never `innerHTML`) — no injection. Commit `feat(viewer): source panel with line highlight`.

### Task 4.3 (parallel module): Logical-errors panel (`panels.js`)
- [ ] List `findings` for the current selection (filter by `flow_id`, or by scope/path at higher levels), each row showing the evidence tier and `kind`/`message`; clicking a finding calls `select({flowId, nodeId, findingId})`. Commit `feat(viewer): logical-errors panel`.

### Task 4.4 (parallel module): Full-screen canvas (`canvas.js`/`fullscreen` helper)
- [ ] Add a toolbar toggle: `requestFullscreen()` on the canvas container with a CSS `.maximized` fallback (fixed-to-viewport within the page) when the API is unavailable; `Esc` and the toggle exit; side panels hide via a `body[data-fullscreen]` class; `selection` is untouched so panels are correct on exit. Commit `feat(viewer): full-screen canvas toggle`.

### Task 4.5: Integrate bidirectional highlight (`shell.js` selection store)
- [ ] **Step 1:** Smoke test: HTML contains `id="source"`, `id="errors"`, and a fullscreen toggle (`data-action="fullscreen"`).
- [ ] **Step 2:** FAIL. **Step 3:** Make every surface subscribe to the selection store: setting `nodeId` highlights the canvas block, the source line, the tree file, and the matching finding in one accent class; clicking any surface updates the store. Single source of truth, one accent color. **Step 4:** Manual-verify all four directions of highlighting, in and out of full screen. **Step 5:** Commit `feat(viewer): bidirectional cross-panel highlight`.

### Task 4.6: Phase-4 review gate — review workflow (emphasis: source-injection safety + highlight consistency). Require green.

---

## Final acceptance

- [ ] `uv run logicchart view examples/demo` — tree, L0 scopes, expand to flows, expand a flow to decisions, source + errors panels, full screen, bidirectional highlight all work.
- [ ] Generality check on a **non-demo** repo (e.g. `examples/shop` and a repo with no `[logicchart.scopes]`): nothing hard-codes demo specifics.
- [ ] CI mirror green; README "Viewer" notes updated to describe the navigable canvas, panels, and full screen.
- [ ] Final whole-feature review workflow returns zero confirmed majors.

---

## Self-review (spec coverage)

- Expand-in-place navigation → Phases 2–3. Scope-level start → Task 2.1. Directory tree → Phase 1. Source panel → 4.1–4.2. Logical-errors panel → 4.3. Bidirectional (incl. findings) → 4.5. Full screen → 4.4. Self-contained + lazy → Phase 0 + lazy rendering in 2.2/2.1. Source snippets (only new data) → 4.1. Generality / no overfitting → review gates + explicit no-scope/non-demo checks. `render/html.py`-only (no IR change) → enforced (only `render/` and `tests/` are modified).
- Open spec questions to resolve during execution: L1 default grouping (always-by-file vs threshold) — decide in Task 2.2; full-screen source overlay — decide in Task 4.4.
