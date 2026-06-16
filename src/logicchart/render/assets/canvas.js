
    // Codebase canvas (Phase 2). Owns the two top levels of the viewer:
    //   L0 = one super-node per scope, edges = aggregated cross-scope calls.
    //   L1 = one expanded scope's flows grouped by file, call edges among the
    //        visible set; every OTHER scope stays a single L0 super-node.
    // Selecting a flow (here or from the tree) still defers to shell.js's
    // renderFlow via LC.selectFlow -- that is the L2 renderer (Phase 3 inlines it).
    //
    // OWNERSHIP SEAM: shell.js owns the SVG element, the shared `view` object, and
    // the pan/zoom/wheel handlers (generic over `view`). It exposes those as LC.svg,
    // LC.setView, LC.updateViewBox, LC.getView, LC.renderFlow and flips LC.mode to
    // "flow" right before renderFlow. canvas.js sets LC.mode = "canvas" and is the
    // SINGLE writer of the SVG for L0/L1 -- every entry (initial load, hashchange,
    // breadcrumb, expand/collapse) funnels through renderCanvas().
    //
    // LAZY INVARIANT: renderL0 builds only `scopes.length` super-node groups + the
    // scope_edges paths -- O(scopes), never O(flows). Expanding a scope adds ONLY
    // that scope's flows to the DOM; other scopes are re-drawn as their single
    // super-node. Collapsing replaceChildren() back to L0.
    (function () {
      const LC = window.LC;
      if (!LC || !LC.svg) return; // shell.js must have booted and exposed the seam.

      const model = LC.model || {};
      const byId = LC.byId || new Map();
      const svg = LC.svg;
      const sortFlows = LC.sortFlows || (list => [...list]);
      const findings = model.findings || [];
      // Flow ids carrying at least one finding -> the "has-finding" ring (reused CSS).
      const findingFlowIds = new Set(
        findings.map(item => item.flow_id).filter(Boolean)
      );

      // World units match the existing ~290px decision nodes so shell.js's pan/zoom
      // (which mutates the shared `view`) reuses exactly, no rescaling.
      const SCOPE_W = 220;
      const SCOPE_H_MIN = 96;
      const SCOPE_H_MAX = 200;
      const FLOW_W = 210;
      const FLOW_H = 64;
      const GAP_X = 70;
      const GAP_Y = 60;
      const FILE_PAD = 24;
      const BAND_GAP = 120;

      const canvasEl = document.getElementById("canvas");
      const breadcrumbEl = document.getElementById("breadcrumb");
      const emptyState = document.getElementById("emptyState");
      // The shared empty-state <p> is reused by renderFlow too, so remember its default
      // copy and restore it whenever we are not showing the L0 "no scopes" message --
      // otherwise a no-scopes repo would leave "No scopes" stuck on later empty flows.
      const emptyMessageEl = emptyState ? emptyState.querySelector("p") : null;
      const defaultEmptyMessage = emptyMessageEl ? emptyMessageEl.textContent : "";
      function setEmptyMessage(text) {
        if (emptyMessageEl) emptyMessageEl.textContent = text;
      }

      // --- State (single explicit object; no hidden DOM state) ---------------------
      // L1 also tracks which file chips are expanded; a file's flow nodes (and their
      // intra-file/visible call edges) are materialized only while its path is in this
      // set, so a scope with hundreds of flows never dumps everything onto the canvas.
      const canvasState = {
        level: 0,
        expandedScope: null,
        selectedFlowId: null,
        expandedFiles: new Set(),
      };
      // cache key ("L0" | "L1:"+scope) -> computed layout {nodePos|fileBoxes, flowPos, bounds}.
      const layoutCache = new Map();

      // --- Data precompute (cached on LC) ------------------------------------------

      // scope -> [flowId]. Provided by payload (inferred top-level dirs when no
      // [logicchart.scopes]); ALWAYS present, covers 0/1/many. Used directly for
      // membership + super-node sizing so canvas grouping == tree grouping.
      const scopeFlows = model.scopes || {};

      // [{from, to, count}] cross-scope aggregate. Prefer payload.scope_edges; fall
      // back to a pure-data JS derivation so canvas.js works before/without the Python
      // change. Both attribute a multi-scope flow's calls to EACH membership.
      function deriveScopeEdges() {
        const flowScope = new Map(); // flowId -> [scope]
        Object.keys(scopeFlows).forEach(scope => {
          (scopeFlows[scope] || []).forEach(id => {
            const list = flowScope.get(id) || [];
            list.push(scope);
            flowScope.set(id, list);
          });
        });
        const counts = new Map(); // "from\0to" -> count
        flowScope.forEach((srcScopes, flowId) => {
          const flow = byId.get(flowId);
          if (!flow) return;
          (flow.calls || []).forEach(target => {
            if (!byId.has(target)) return; // guard: unresolved/external target.
            const dstScopes = flowScope.get(target) || [];
            srcScopes.forEach(src => {
              dstScopes.forEach(dst => {
                if (src === dst) return; // drop self-scope calls at L0.
                const key = src + "\0" + dst;
                counts.set(key, (counts.get(key) || 0) + 1);
              });
            });
          });
        });
        const edges = [];
        counts.forEach((count, key) => {
          const parts = key.split("\0");
          edges.push({ from: parts[0], to: parts[1], count });
        });
        return edges;
      }

      const scopeEdges = Array.isArray(model.scope_edges)
        ? model.scope_edges
        : deriveScopeEdges();

      // flowId -> [scope], derived from the payload's scope index (the same membership
      // the canvas groups by, which already excludes test flows). Lets a flow opened
      // from the tree or a #flow= deep link recover its scope crumb.
      const scopeOfFlowIndex = new Map();
      Object.keys(scopeFlows)
        .sort()
        .forEach(scope => {
          (scopeFlows[scope] || []).forEach(id => {
            const list = scopeOfFlowIndex.get(id) || [];
            list.push(scope);
            scopeOfFlowIndex.set(id, list);
          });
        });

      // The scope a flow belongs to for breadcrumb purposes. Prefer the payload index;
      // fall back to flow.metadata.scope, then to the inferred top-level dir (mirroring
      // build_scope_index) so a flow always resolves to a deterministic FIRST scope.
      function scopeOfFlow(flow) {
        if (!flow) return null;
        const fromIndex = scopeOfFlowIndex.get(flow.id);
        if (fromIndex && fromIndex.length) return fromIndex[0];
        const declared = flow.metadata && flow.metadata.scope;
        if (Array.isArray(declared) && declared.length) {
          return [...declared].sort()[0];
        }
        const path = (flow.location && flow.location.path) || "";
        const parts = path.split("/").filter(Boolean);
        return parts.length ? parts[0] : path || null;
      }

      // --- Geometry helpers --------------------------------------------------------

      function clamp(min, value, max) {
        return Math.max(min, Math.min(max, value));
      }

      function svgEl(tag) {
        return document.createElementNS("http://www.w3.org/2000/svg", tag);
      }

      function superNodeHeight(count) {
        return clamp(SCOPE_H_MIN, SCOPE_H_MIN + 6 * Math.sqrt(count), SCOPE_H_MAX);
      }

      // Wrap a label to at most `max` lines of roughly `width` chars (mirrors shell.js).
      function wrapLabel(value, width, max) {
        const words = String(value).split(/\s+/);
        const lines = [];
        let current = "";
        words.forEach(word => {
          if (!current || (current + " " + word).length <= width) {
            current = current ? current + " " + word : word;
          } else {
            lines.push(current);
            current = word;
          }
        });
        if (current) lines.push(current);
        return lines.slice(0, max);
      }

      // True when wrapLabel dropped content: more lines than `max`, so the rendered
      // label is missing the overflow. Lets callers attach a <title> to recover it.
      function isTruncated(value, width, max) {
        const words = String(value).split(/\s+/);
        const lines = [];
        let current = "";
        words.forEach(word => {
          if (!current || (current + " " + word).length <= width) {
            current = current ? current + " " + word : word;
          } else {
            lines.push(current);
            current = word;
          }
        });
        if (current) lines.push(current);
        return lines.length > max;
      }

      // Attach a hover/long-press tooltip with the full text to an SVG element.
      function addTitle(target, text) {
        const title = svgEl("title");
        title.textContent = text;
        target.appendChild(title);
      }

      // Lightly-curved cubic between node CENTERS, clipped to each node's border using
      // its known {w,h}; arrow sits on the rect edge, not the center. `curveOffset`
      // pushes the control points perpendicular to the segment so parallel edges fan
      // out. General over node size + orientation (unlike shell.js's edgeGeometry,
      // which hardcodes the +43/-43 flow-node half-height and a top-to-bottom S-curve).
      function straightEdge(a, b, curveOffset) {
        curveOffset = curveOffset || 0;
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const len = Math.hypot(dx, dy) || 1;
        const ux = dx / len;
        const uy = dy / len;

        // Clip the endpoints to each node's rectangular border along the segment.
        const start = clipToRect(a, ux, uy);
        const end = clipToRect(b, -ux, -uy);

        // Perpendicular offset for the control points (so overlapping lines separate).
        const px = -uy * curveOffset;
        const py = ux * curveOffset;
        const c1x = start.x + dx * 0.3 + px;
        const c1y = start.y + dy * 0.3 + py;
        const c2x = start.x + dx * 0.7 + px;
        const c2y = start.y + dy * 0.7 + py;
        return {
          d: `M ${start.x} ${start.y} C ${c1x} ${c1y}, ${c2x} ${c2y}, ${end.x} ${end.y}`,
          labelX: (start.x + end.x) / 2 + px,
          labelY: (start.y + end.y) / 2 + py,
        };
      }

      // Point on `node`'s rect border in direction (ux,uy) from its center.
      function clipToRect(node, ux, uy) {
        const hw = (node.w || FLOW_W) / 2;
        const hh = (node.h || FLOW_H) / 2;
        // Scale to hit the nearer of the vertical/horizontal edges.
        const tx = ux !== 0 ? hw / Math.abs(ux) : Infinity;
        const ty = uy !== 0 ? hh / Math.abs(uy) : Infinity;
        const t = Math.min(tx, ty);
        return { x: node.x + ux * t, y: node.y + uy * t };
      }

      function defsBlock() {
        const defs = svgEl("defs");
        // Neutral black shadow (not the old hardcoded navy #1e2e4e, which read as a
        // blue tint in light mode); low opacity keeps it subtle in both themes.
        defs.innerHTML = `
          <filter id="nodeShadow" x="-30%" y="-30%" width="160%" height="180%">
            <feDropShadow dx="0" dy="8" stdDeviation="8" flood-color="#000" flood-opacity=".10"/>
          </filter>
          <filter id="nodeLift" x="-45%" y="-45%" width="190%" height="210%">
            <feDropShadow dx="0" dy="16" stdDeviation="14" flood-color="#000" flood-opacity=".22"/>
          </filter>
          <marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
            <path class="arrow" d="M0,0 L8,4 L0,8 z"></path>
          </marker>`;
        return defs;
      }

      // ViewBox fit over a {minX,maxX,minY,maxY} bounds, same math renderFlow uses.
      function fitBounds(bounds) {
        const padding = 120;
        LC.setView({
          x: bounds.minX - padding,
          y: bounds.minY - padding,
          width: Math.max(760, bounds.maxX - bounds.minX + padding * 2),
          height: Math.max(560, bounds.maxY - bounds.minY + padding * 2),
        });
      }

      // Wrapped-grid column count, shared by L0 super-nodes and L1 file boxes.
      function gridCols(count, cellW) {
        const containerW = (canvasEl && canvasEl.clientWidth) || 1000;
        const fitting = Math.max(1, Math.floor(containerW / (cellW + GAP_X)));
        return clamp(1, Math.round(Math.sqrt(count) * 1.3), fitting);
      }

      // --- L0 layout: scopes as a wrapped grid of super-nodes ----------------------

      function layoutL0(names) {
        const cached = layoutCache.get("L0");
        let nodePos;
        if (cached) {
          nodePos = cached.nodePos;
        } else {
          nodePos = new Map();
          const cols = gridCols(names.length, SCOPE_W);
          const heights = names.map(name => superNodeHeight((scopeFlows[name] || []).length));
          const rowH = Math.max(SCOPE_H_MIN, ...heights);
          names.forEach((name, i) => {
            const col = i % cols;
            const row = Math.floor(i / cols);
            const cx = col * (SCOPE_W + GAP_X) + SCOPE_W / 2;
            const cy = row * (rowH + GAP_Y) + rowH / 2;
            nodePos.set(name, {
              x: cx,
              y: cy,
              w: SCOPE_W,
              h: superNodeHeight((scopeFlows[name] || []).length),
              count: (scopeFlows[name] || []).length,
            });
          });
          layoutCache.set("L0", { nodePos });
        }
        return { nodePos, bounds: boundsOf([...nodePos.values()]) };
      }

      function boundsOf(nodes) {
        if (!nodes.length) return { minX: 0, maxX: 0, minY: 0, maxY: 0 };
        let minX = Infinity;
        let maxX = -Infinity;
        let minY = Infinity;
        let maxY = -Infinity;
        nodes.forEach(n => {
          minX = Math.min(minX, n.x - (n.w || FLOW_W) / 2);
          maxX = Math.max(maxX, n.x + (n.w || FLOW_W) / 2);
          minY = Math.min(minY, n.y - (n.h || FLOW_H) / 2);
          maxY = Math.max(maxY, n.y + (n.h || FLOW_H) / 2);
        });
        return { minX, maxX, minY, maxY };
      }

      // --- L1 layout: one expanded scope; flows in a file-grouped grid -------------

      // L1 layout. Each FILE in the expanded scope is a collapsed header chip by
      // default (file name + flow count); a file's flow nodes are laid out ONLY when
      // its path is in `canvasState.expandedFiles`. This keeps L1 lazy at scale: a
      // scope with hundreds of flows shows one chip per file, never every flow node.
      // The layout depends on the expanded-file set, so it is recomputed per render
      // (cheap: only expanded files materialize their flows) rather than cached by
      // scope alone.
      function layoutL1(scope) {
        const names = Object.keys(scopeFlows).sort();
        const others = names.filter(name => name !== scope);

        // Residual super-nodes for every OTHER scope, in a top band (y=0). This is the
        // lazy core: those scopes never materialize their flows.
        const residualPos = new Map();
        const cols = gridCols(Math.max(1, others.length), SCOPE_W);
        const rowH = SCOPE_H_MIN;
        let residualBottom = 0;
        others.forEach((name, i) => {
          const col = i % cols;
          const row = Math.floor(i / cols);
          const cx = col * (SCOPE_W + GAP_X) + SCOPE_W / 2;
          const cy = row * (rowH + GAP_Y) + rowH / 2;
          residualPos.set(name, {
            x: cx,
            y: cy,
            w: SCOPE_W,
            h: rowH,
            count: (scopeFlows[name] || []).length,
          });
          residualBottom = Math.max(residualBottom, cy + rowH / 2);
        });

        const bandTop = others.length ? residualBottom + BAND_GAP : 0;

        // Expanded scope's flows, grouped by file. Files become chips; flows inside an
        // expanded file are materialized, the rest are not.
        const visibleFlows = (scopeFlows[scope] || [])
          .map(id => byId.get(id))
          .filter(Boolean);
        const byPath = new Map();
        visibleFlows.forEach(flow => {
          const list = byPath.get(flow.location.path) || [];
          list.push(flow);
          byPath.set(flow.location.path, list);
        });
        const paths = [...byPath.keys()].sort((a, b) => a.localeCompare(b));

        // Pre-size each file box. A collapsed chip is header-only; an expanded box
        // grows to fit its flows in an inner grid.
        const HEADER_H = 22;
        const COLLAPSED_W = FILE_PAD * 2 + FLOW_W; // chip wide enough for the label.
        const COLLAPSED_H = FILE_PAD * 2 + HEADER_H;
        const boxes = paths.map(path => {
          const flowsInFile = sortFlows(byPath.get(path));
          const expanded = canvasState.expandedFiles.has(path);
          if (!expanded) {
            return { path, flows: flowsInFile, expanded: false, innerCols: 0, w: COLLAPSED_W, h: COLLAPSED_H };
          }
          const innerCols = Math.max(1, Math.floor(Math.sqrt(flowsInFile.length)));
          const innerRows = Math.ceil(flowsInFile.length / innerCols);
          const w = FILE_PAD * 2 + innerCols * FLOW_W + (innerCols - 1) * GAP_X;
          const h =
            FILE_PAD * 2 + HEADER_H + innerRows * FLOW_H + (innerRows - 1) * GAP_Y;
          return { path, flows: flowsInFile, expanded: true, innerCols, w, h };
        });

        // Outer wrapped grid of file boxes; row height = tallest box in the row.
        const fileBoxes = new Map();
        const flowPos = new Map();
        const outerContainerW = (canvasEl && canvasEl.clientWidth) || 1000;
        let cursorX = 0;
        let rowTop = bandTop;
        let rowMaxH = 0;
        let rowStart = 0;
        boxes.forEach((box, i) => {
          if (i > rowStart && cursorX + box.w > outerContainerW) {
            // wrap to a new row.
            rowTop += rowMaxH + GAP_Y;
            cursorX = 0;
            rowMaxH = 0;
            rowStart = i;
          }
          box.x = cursorX;
          box.y = rowTop;
          fileBoxes.set(box.path, box);
          // Only an expanded file places its flows in its inner grid; collapsed chips
          // contribute NO flow positions, so their flow nodes never enter the DOM.
          if (box.expanded) {
            box.flows.forEach((flow, fi) => {
              const col = fi % box.innerCols;
              const row = Math.floor(fi / box.innerCols);
              const cx = box.x + FILE_PAD + col * (FLOW_W + GAP_X) + FLOW_W / 2;
              const cy =
                box.y + FILE_PAD + HEADER_H + row * (FLOW_H + GAP_Y) + FLOW_H / 2;
              flowPos.set(flow.id, { x: cx, y: cy, w: FLOW_W, h: FLOW_H });
            });
          }
          cursorX += box.w + GAP_X;
          rowMaxH = Math.max(rowMaxH, box.h);
        });

        // The visible flow set is exactly the flows of EXPANDED files -- the only ones
        // with a position, the only ones drawn, and the only edge endpoints.
        const visibleIds = new Set(flowPos.keys());
        const allNodes = [...residualPos.values(), ...flowPos.values()];
        // Account for file-box extents too, so the viewBox includes box chrome.
        boxes.forEach(box => {
          allNodes.push({ x: box.x + box.w / 2, y: box.y + box.h / 2, w: box.w, h: box.h });
        });

        return {
          residualPos,
          fileBoxes,
          flowPos,
          visibleIds,
          bounds: boundsOf(allNodes),
        };
      }

      // --- Node builders -----------------------------------------------------------

      function makeSuperNode(name, count, pos, opts) {
        opts = opts || {};
        const group = svgEl("g");
        group.setAttribute(
          "class",
          "scope-node" + (opts.expanded ? " expanded" : "") + (opts.dimmed ? " dimmed" : "")
        );
        group.setAttribute("data-scope", name);
        group.setAttribute("transform", `translate(${pos.x} ${pos.y})`);
        group.setAttribute("tabindex", "0");
        group.setAttribute("role", "button");
        group.setAttribute("aria-label", `scope ${name}: ${count} flows`);

        const rect = svgEl("rect");
        rect.setAttribute("class", "shape");
        rect.setAttribute("x", String(-pos.w / 2));
        rect.setAttribute("y", String(-pos.h / 2));
        rect.setAttribute("width", String(pos.w));
        rect.setAttribute("height", String(pos.h));
        rect.setAttribute("rx", "16");
        group.appendChild(rect);

        const nameLines = wrapLabel(name, 18, 2);
        // Recover the full scope name on hover when wrapLabel dropped overflow.
        if (isTruncated(name, 18, 2)) addTitle(group, name);
        nameLines.forEach((line, index) => {
          const text = svgEl("text");
          text.setAttribute("class", "scope-name");
          text.setAttribute("text-anchor", "middle");
          text.setAttribute(
            "y",
            String((index - (nameLines.length - 1) / 2) * 20 - 8)
          );
          text.textContent = line;
          group.appendChild(text);
        });
        const meta = svgEl("text");
        meta.setAttribute("class", "scope-meta");
        meta.setAttribute("text-anchor", "middle");
        meta.setAttribute("y", String(pos.h / 2 - 14));
        meta.textContent = `${count} flow${count === 1 ? "" : "s"}`;
        group.appendChild(meta);

        const activate = () => expandScope(name);
        group.addEventListener("click", activate);
        group.addEventListener("keydown", event => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            activate();
          }
        });
        return group;
      }

      // A file is rendered as an expandable header chip. Collapsed by default it shows
      // only the file name + flow count; expanding (click / Enter / Space) materializes
      // its flow nodes, collapsing removes them. The header is the toggle target and
      // carries button semantics + aria-expanded so it is keyboard-accessible.
      function makeFileBox(path, box) {
        const count = box.flows.length;
        const group = svgEl("g");
        group.setAttribute(
          "class",
          "file-box" + (box.expanded ? " expanded" : "")
        );
        group.setAttribute("data-path", path);
        group.setAttribute("transform", `translate(${box.x} ${box.y})`);
        group.setAttribute("tabindex", "0");
        group.setAttribute("role", "button");
        group.setAttribute("aria-expanded", box.expanded ? "true" : "false");
        const segments = path.split("/");
        const tail = segments[segments.length - 1] || path;
        group.setAttribute(
          "aria-label",
          `file ${tail}: ${count} flow${count === 1 ? "" : "s"}, ${box.expanded ? "expanded" : "collapsed"}`
        );

        const rect = svgEl("rect");
        rect.setAttribute("class", "file-frame");
        rect.setAttribute("x", "0");
        rect.setAttribute("y", "0");
        rect.setAttribute("width", String(box.w));
        rect.setAttribute("height", String(box.h));
        rect.setAttribute("rx", "14");
        group.appendChild(rect);

        // Disclosure caret (rotates via CSS when expanded). Its position is baked into
        // the path data -- not an inline transform attribute -- because the CSS rotate
        // (transform-box: fill-box) would otherwise override an attribute transform.
        const cx = FILE_PAD - 12;
        const cy = FILE_PAD;
        const caret = svgEl("path");
        caret.setAttribute("class", "file-caret");
        caret.setAttribute("d", `M${cx},${cy - 4} L${cx + 5},${cy} L${cx},${cy + 4}`);
        group.appendChild(caret);

        const label = svgEl("text");
        label.setAttribute("class", "file-label");
        label.setAttribute("x", String(FILE_PAD));
        label.setAttribute("y", String(FILE_PAD + 4));
        // Show the file's tail so deep paths stay legible.
        label.textContent = tail;
        const full = svgEl("title");
        full.textContent = `${path} (${count} flow${count === 1 ? "" : "s"})`;
        label.appendChild(full);
        group.appendChild(label);

        // Flow-count chip on the header, so a collapsed file still advertises its size.
        const meta = svgEl("text");
        meta.setAttribute("class", "file-count");
        meta.setAttribute("x", String(box.w - FILE_PAD));
        meta.setAttribute("y", String(FILE_PAD + 4));
        meta.setAttribute("text-anchor", "end");
        meta.textContent = `${count}`;
        group.appendChild(meta);

        const toggle = () => toggleFile(path);
        group.addEventListener("click", toggle);
        group.addEventListener("keydown", event => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            toggle();
          }
        });
        return group;
      }

      function makeFlowNode(flow, pos) {
        const group = svgEl("g");
        const isEntry = !!flow.is_entrypoint;
        group.setAttribute(
          "class",
          "node flow-node " +
            (isEntry ? "entry" : "action") +
            (findingFlowIds.has(flow.id) ? " has-finding" : "") +
            (flow.id === canvasState.selectedFlowId ? " selected" : "")
        );
        group.setAttribute("data-flow-id", flow.id);
        group.setAttribute("transform", `translate(${pos.x} ${pos.y})`);
        group.setAttribute("tabindex", "0");
        group.setAttribute("role", "button");
        group.setAttribute("aria-label", `flow: ${flow.name}`);

        const rect = svgEl("rect");
        rect.setAttribute("class", "shape");
        rect.setAttribute("x", String(-FLOW_W / 2));
        rect.setAttribute("y", String(-FLOW_H / 2));
        rect.setAttribute("width", String(FLOW_W));
        rect.setAttribute("height", String(FLOW_H));
        rect.setAttribute("rx", isEntry ? "32" : "12");
        group.appendChild(rect);

        const lines = wrapLabel(flow.name, 24, 2);
        // Recover the full flow name on hover when wrapLabel dropped overflow.
        if (isTruncated(flow.name, 24, 2)) addTitle(group, flow.name);
        lines.forEach((line, index) => {
          const text = svgEl("text");
          text.setAttribute("text-anchor", "middle");
          text.setAttribute("y", String((index - (lines.length - 1) / 2) * 16 - 4));
          text.textContent = line;
          group.appendChild(text);
        });
        const meta = svgEl("text");
        meta.setAttribute("class", "meta");
        meta.setAttribute("text-anchor", "middle");
        meta.setAttribute("y", String(FLOW_H / 2 - 7));
        meta.textContent = `${flow.location.path}:${flow.location.start_line}`;
        group.appendChild(meta);

        const open = () => {
          setSelected(flow.id);
          LC.selectFlow(flow.id); // the single existing entry into renderFlow (L2).
        };
        group.addEventListener("click", open);
        group.addEventListener("keydown", event => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            open();
          }
        });
        return group;
      }

      function edgePath(geometry, count) {
        const path = svgEl("path");
        path.setAttribute("class", "edge");
        path.setAttribute("d", geometry.d);
        if (count != null) {
          path.setAttribute("stroke-width", String(clamp(1, Math.log2(count + 1), 6)));
        }
        return path;
      }

      // --- Renderers ---------------------------------------------------------------

      function renderL0() {
        const names = Object.keys(scopeFlows).sort();
        canvasEl.setAttribute("data-level", "0");

        if (names.length === 0) {
          svg.replaceChildren();
          if (emptyState) {
            emptyState.style.display = "grid";
            setEmptyMessage("No scopes");
          }
          renderBreadcrumb(canvasState);
          return;
        }
        if (names.length === 1) {
          // Skip the trivial single-scope L0 and go straight into it.
          expandScope(names[0]);
          return;
        }
        // Restore the default copy in case a prior no-scopes render left "No scopes".
        setEmptyMessage(defaultEmptyMessage);
        if (emptyState) emptyState.style.display = "none";

        const { nodePos, bounds } = layoutL0(names);
        svg.replaceChildren();
        svg.appendChild(defsBlock());

        // Aggregated cross-scope edges (from != to). EMPTY-EDGE GUARD: when sparse,
        // simply draw none -- the wrapped grid is already a clean, non-degenerate layout.
        const edgeLayer = svgEl("g");
        scopeEdges.forEach(edge => {
          if (edge.from === edge.to) return;
          const a = nodePos.get(edge.from);
          const b = nodePos.get(edge.to);
          if (!a || !b) return;
          edgeLayer.appendChild(edgePath(straightEdge(a, b, 0), edge.count));
        });
        svg.appendChild(edgeLayer);

        const nodeLayer = svgEl("g");
        names.forEach(name => {
          const pos = nodePos.get(name);
          nodeLayer.appendChild(
            makeSuperNode(name, (scopeFlows[name] || []).length, pos, {})
          );
        });
        svg.appendChild(nodeLayer);

        fitBounds(bounds);
        renderBreadcrumb(canvasState);
      }

      function renderL1(scope) {
        canvasEl.setAttribute("data-level", "1");
        setEmptyMessage(defaultEmptyMessage);
        if (emptyState) emptyState.style.display = "none";

        const layout = layoutL1(scope);
        svg.replaceChildren();
        svg.appendChild(defsBlock());

        // Intra-scope call edges among the VISIBLE set only, deduped by min|max id.
        // Cross-scope calls are NOT drawn here (already shown as the L0 aggregate), so
        // L1 deliberately shows only intra-scope structure.
        const edgeLayer = svgEl("g");
        const drawn = new Set();
        let fanIndex = 0;
        layout.visibleIds.forEach(id => {
          const flow = byId.get(id);
          if (!flow) return;
          (flow.calls || []).forEach(target => {
            if (!layout.visibleIds.has(target)) return; // skip cross-scope / unresolved.
            const a = layout.flowPos.get(id);
            const b = layout.flowPos.get(target);
            if (!a || !b) return;
            const key = id < target ? id + "|" + target : target + "|" + id;
            if (drawn.has(key)) return;
            drawn.add(key);
            const curve = ((fanIndex++ % 5) - 2) * 14; // small per-edge fan-out.
            edgeLayer.appendChild(edgePath(straightEdge(a, b, curve), null));
          });
        });
        svg.appendChild(edgeLayer);

        // Residual super-nodes for every OTHER scope (dimmed, still clickable).
        const residualLayer = svgEl("g");
        layout.residualPos.forEach((pos, name) => {
          residualLayer.appendChild(
            makeSuperNode(name, pos.count, pos, { dimmed: true })
          );
        });
        svg.appendChild(residualLayer);

        // File boxes + the expanded scope's flow nodes (the only flows in the DOM).
        const fileLayer = svgEl("g");
        layout.fileBoxes.forEach((box, path) => {
          fileLayer.appendChild(makeFileBox(path, box));
        });
        svg.appendChild(fileLayer);

        const nodeLayer = svgEl("g");
        layout.visibleIds.forEach(id => {
          const flow = byId.get(id);
          const pos = layout.flowPos.get(id);
          if (flow && pos) nodeLayer.appendChild(makeFlowNode(flow, pos));
        });
        // Background click on empty canvas collapses to L0.
        svg.appendChild(nodeLayer);

        fitBounds(layout.bounds);
        renderBreadcrumb(canvasState);
      }

      // --- Single dispatch entry ---------------------------------------------------

      function renderCanvas() {
        LC.mode = "canvas";
        if (canvasState.level === 0) renderL0();
        else renderL1(canvasState.expandedScope);
      }

      // --- Mutators ----------------------------------------------------------------

      // Enter L1 for `name`. File chips start collapsed; entering a DIFFERENT scope
      // resets the expanded-file set (a file path only makes sense within its scope).
      function setScope(name) {
        if (canvasState.expandedScope !== name) canvasState.expandedFiles.clear();
        canvasState.level = 1;
        canvasState.expandedScope = name;
      }

      function expandScope(name) {
        if (!Object.prototype.hasOwnProperty.call(scopeFlows, name)) return;
        setScope(name);
        location.hash = "scope=" + encodeURIComponent(name);
        renderCanvas();
      }

      function collapseToL0() {
        canvasState.level = 0;
        canvasState.expandedScope = null;
        canvasState.expandedFiles.clear();
        location.hash = "";
        renderCanvas();
      }

      // Expand/collapse one file chip at L1, materializing or removing its flow nodes.
      function toggleFile(path) {
        if (canvasState.expandedFiles.has(path)) canvasState.expandedFiles.delete(path);
        else canvasState.expandedFiles.add(path);
        renderCanvas();
      }

      function setSelected(id) {
        canvasState.selectedFlowId = id;
        // Refresh selection highlight without a full relayout when staying on canvas.
        if (LC.mode === "canvas" && canvasState.level === 1) {
          svg.querySelectorAll(".flow-node").forEach(node => {
            node.classList.toggle(
              "selected",
              node.getAttribute("data-flow-id") === id
            );
          });
        }
      }

      // --- Breadcrumb --------------------------------------------------------------

      function crumbButton(text, onClick, current) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "crumb" + (current ? " current" : "");
        if (current) button.setAttribute("aria-current", "page");
        button.textContent = text;
        if (onClick) button.addEventListener("click", onClick);
        return button;
      }

      function crumbSeparator() {
        const sep = document.createElement("span");
        sep.className = "crumb-sep";
        sep.setAttribute("aria-hidden", "true");
        sep.textContent = "/";
        return sep;
      }

      function renderBreadcrumb(state) {
        if (!breadcrumbEl) return;
        breadcrumbEl.replaceChildren();
        const inFlow = LC.mode === "flow";
        const atRoot = state.level === 0 && !inFlow;
        breadcrumbEl.appendChild(
          crumbButton("codebase", collapseToL0, atRoot)
        );
        if (state.level === 1 && state.expandedScope) {
          breadcrumbEl.appendChild(crumbSeparator());
          const scope = state.expandedScope;
          breadcrumbEl.appendChild(
            crumbButton(scope, () => {
              // Return to L1 for this scope (e.g. from a flow crumb).
              if (LC.mode === "flow" || canvasState.level !== 1) {
                setScope(scope);
                location.hash = "scope=" + encodeURIComponent(scope);
                renderCanvas();
              }
            }, state.level === 1 && !inFlow)
          );
        }
        if (inFlow && state.selectedFlowId) {
          const flow = byId.get(state.selectedFlowId);
          if (flow) {
            breadcrumbEl.appendChild(crumbSeparator());
            breadcrumbEl.appendChild(crumbButton(flow.name, null, true));
          }
        }
      }

      // --- Hash dispatch surface (shell.js routeFromHash calls these) --------------

      LC.showL0 = function () {
        canvasState.level = 0;
        canvasState.expandedScope = null;
        canvasState.expandedFiles.clear();
        renderCanvas();
      };
      LC.showScope = function (name) {
        if (!Object.prototype.hasOwnProperty.call(scopeFlows, name)) {
          LC.showL0();
          return;
        }
        setScope(name);
        renderCanvas();
      };
      // When shell.js enters flow mode (renderFlow), refresh the breadcrumb so it
      // gains the flow crumb. A flow opened from the tree or a #flow= deep link may
      // have no scope set yet, so derive the flow's scope (first membership, mirroring
      // build_scope_index) and pin it as the expanded scope -- otherwise the crumb
      // would read `codebase / <flow>` with the scope hop missing.
      LC.onCanvasFlow = function (flow) {
        canvasState.selectedFlowId = flow ? flow.id : null;
        if (flow) {
          const scope = scopeOfFlow(flow);
          if (scope && Object.prototype.hasOwnProperty.call(scopeFlows, scope)) {
            // Switching the pinned scope drops stale file expansions from any prior one.
            if (canvasState.expandedScope !== scope) canvasState.expandedFiles.clear();
            canvasState.expandedScope = scope;
            canvasState.level = 1;
          }
        }
        renderBreadcrumb(canvasState);
      };
      LC.resetCanvas = function () {
        // resetView in canvas mode: re-fit + redraw the current level. (Drag-to-arrange
        // on the canvas is out of scope for Phase 2, so there are no overrides to drop;
        // renderCanvas recomputes the layout and re-fits the viewBox.)
        renderCanvas();
      };
    })();
