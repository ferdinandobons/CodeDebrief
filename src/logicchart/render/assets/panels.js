
    // Right-column panels (Phase 4): Source (top) + Logical errors (bottom), plus the
    // canvas full-screen toggle. Both panels SUBSCRIBE to the shared selection store
    // (shell.js's LC.select / LC.onSelection) and PUBLISH back into it, so selecting any
    // one of {a canvas decision block, a source line, a tree file/flow, a finding row}
    // highlights the others in the one shared accent. No duplicated highlight/inspect
    // logic: block highlighting stays in shell.js (driven off the store), the tree
    // reflects via tree.js's store subscription, and these panels own only their own DOM.
    //
    // SECURITY: every character of source text and every finding string is inserted as a
    // TEXT NODE (textContent / createTextNode), NEVER innerHTML -- the snippet lines are
    // source-derived and must not be interpreted as markup. `<`, `>`, `&`, `"` in code
    // render literally.
    (function () {
      const LC = window.LC;
      if (!LC) return;

      const model = LC.model || {};
      const byId = LC.byId || new Map();
      const flows = LC.flows || [];
      const findings = LC.findings || model.findings || [];
      const findingsByNode = LC.findingsByNode || new Map();
      const scopeFlows = model.scopes || {};
      const findingRules = (model.metadata && model.metadata.finding_rules) || {};
      const quality = (model.metadata && model.metadata.quality) || null;
      // File-level source store: path -> {start_line, lines}. Each file's lines are
      // embedded ONCE here (payload.attach_source_snippets), and a flow's `source` is a
      // lightweight {path, start_line, end_line, elided?} reference that slices its own
      // window out of this. Resolving through the store is what de-dups a file shared by
      // many flows -- we never re-embed or re-slice the whole file per flow.
      const sourceFiles = model.source_files || {};

      // At most this many findings are rendered in the errors panel for a broad (L0 /
      // empty / scope) selection, with an "N more" affordance after; a node selection is
      // exact and always shown in full. Keeps the panel from rendering an unbounded list
      // (a large codebase has thousands of findings) -- general over finding count.
      const MAX_FINDING_ROWS = 50;

      const sourcePanel = document.getElementById("sourcePanel");
      const sourceBody = document.getElementById("source");
      const sourceFileEl = document.getElementById("sourceFile");
      const qualityPanel = document.getElementById("qualityPanel");
      const qualityBody = document.getElementById("quality");
      const qualityCountEl = document.getElementById("qualityCount");
      const errorsBody = document.getElementById("errors");
      const errorsCountEl = document.getElementById("errorsCount");
      const reviewQueueBtn = document.getElementById("reviewQueueToggle");
      const liveRegion = document.getElementById("panelStatus");
      let reviewQueueMode = false;

      // aria-live announcer: screen readers are not notified when the panels rebuild on a
      // selection change. Each panel records its own status ("source: file:line", "<n>
      // findings"); onSelection then writes ONE combined message into the visually-hidden
      // polite live region -- so the two panels do not overwrite each other's announcement.
      let sourceStatus = "";
      let errorsStatus = "";
      function flushAnnounce() {
        if (!liveRegion) return;
        const parts = [];
        if (sourceStatus) parts.push(sourceStatus);
        if (errorsStatus) parts.push(errorsStatus);
        liveRegion.textContent = parts.join(", ");
      }

      // --- small DOM helpers (text-node only) -------------------------------------

      const SVG_NS = "http://www.w3.org/2000/svg";

      function el(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text != null) node.textContent = text; // text node, never markup.
        return node;
      }

      function svgEl(tag, attrs, text) {
        const node = document.createElementNS(SVG_NS, tag);
        Object.keys(attrs || {}).forEach(key => node.setAttribute(key, String(attrs[key])));
        if (text != null) node.textContent = text;
        return node;
      }

      function clear(node) {
        if (node) node.replaceChildren();
      }

      function metricValue(value) {
        if (value == null || value === "") return "0";
        if (typeof value === "number") return String(value);
        return String(value);
      }

      function ratioPercent(value) {
        return typeof value === "number" ? Math.round(value * 100) + "%" : "0%";
      }

      function qualityMetric(label, value, tone) {
        const item = el("div", "quality-metric" + (tone ? " " + tone : ""));
        item.append(el("span", "quality-label", label), el("strong", "", metricValue(value)));
        return item;
      }

      function qualitySignal(label, value, tone) {
        const row = el("div", "quality-signal" + (tone ? " " + tone : ""));
        row.append(el("span", "quality-label", label), el("span", "quality-value", metricValue(value)));
        return row;
      }

      function countPairs(counts, limit) {
        if (!counts || typeof counts !== "object") return [];
        return Object.keys(counts)
          .map(key => [key, counts[key]])
          .filter(([, value]) => Number(value) > 0)
          .sort((a, b) => Number(b[1]) - Number(a[1]) || String(a[0]).localeCompare(String(b[0])))
          .slice(0, limit);
      }

      function renderQuality() {
        if (!qualityPanel || !qualityBody) return;
        clear(qualityBody);
        if (!quality || typeof quality !== "object") {
          qualityPanel.hidden = true;
          return;
        }
        qualityPanel.hidden = false;
        const files = quality.files || {};
        const flows = quality.flows || {};
        const calls = quality.calls || {};
        const findingsQuality = quality.findings || {};
        const labels = quality.labels || {};
        const source = quality.source_locations || {};
        const graph = quality.graph || {};
        const languagesQuality = quality.languages || {};
        const skipped = (files.skipped && typeof files.skipped === "object") ? files.skipped : { total: 0 };
        const parseErrors = (files.parse_errors && typeof files.parse_errors === "object")
          ? files.parse_errors
          : { total: 0 };

        if (qualityCountEl) qualityCountEl.textContent = ratioPercent(source.coverage);

        const metrics = el("div", "quality-metrics");
        metrics.append(
          qualityMetric("Files", files.total),
          qualityMetric("Flows", flows.total),
          qualityMetric("Entrypoints", flows.entrypoints),
          qualityMetric("Source", ratioPercent(source.coverage))
        );
        qualityBody.appendChild(metrics);

        const signals = el("div", "quality-signals");
        const unresolved = Number(calls.unresolved || 0);
        const ambiguous = Number(calls.ambiguous || 0);
        const generic = Number(labels.generic_nodes || 0);
        const skippedTotal = Number(skipped.total || 0);
        const parseWarnings = Number(parseErrors.total || 0);
        const huge = Array.isArray(flows.huge) ? flows.huge.length : 0;
        const languageAttention = Array.isArray(languagesQuality.attention)
          ? languagesQuality.attention.length
          : 0;
        signals.append(
          qualitySignal("Call resolution", ratioPercent(calls.resolution_rate), unresolved || ambiguous ? "attention" : ""),
          qualitySignal("Skipped files", skippedTotal, skippedTotal ? "attention" : ""),
          qualitySignal("Parse warnings", parseWarnings, parseWarnings ? "attention" : ""),
          qualitySignal("Unresolved calls", unresolved, unresolved ? "attention" : ""),
          qualitySignal("Ambiguous calls", ambiguous, ambiguous ? "attention" : ""),
          qualitySignal("Generic labels", generic + " · " + ratioPercent(labels.generic_ratio), generic ? "attention" : ""),
          qualitySignal("Findings", findingsQuality.total || 0, findingsQuality.total ? "attention" : ""),
          qualitySignal("Language attention", languageAttention, languageAttention ? "attention" : ""),
          qualitySignal("Graph density", graph.edge_to_node_ratio, graph.dense_graph_warning ? "attention" : "")
        );
        if (huge) signals.append(qualitySignal("Huge flows", huge, "attention"));
        qualityBody.appendChild(signals);

        const languages = countPairs(flows.by_language || files.by_language, 8);
        if (languages.length) {
          const chips = el("div", "quality-chips");
          languages.forEach(([language, count]) => {
            chips.appendChild(el("span", "quality-chip", language + " " + count));
          });
          qualityBody.appendChild(chips);
        }
      }

      // Focus restoration across a panel re-render. Activating a finding row or a code line
      // re-renders the panel (replaceChildren destroys the focused element, dropping focus
      // to <body>). When an activation originates INSIDE a panel, we record the stable id of
      // the activated item here, then restore focus to the equivalent row/line AFTER the
      // whole selection cascade settles. Deferring matters: a code-line click can trigger
      // a chart selection focus update; restoring synchronously during render would be
      // immediately overwritten by that.
      // Scheduling the restore last (a microtask after the cascade) lets the panel keep
      // focus. Cleared once consumed so a later unrelated selection does not steal focus.
      let pendingFocus = null;
      // Run a callback after the current synchronous selection cascade. Falls back to a
      // direct call if neither timer is available (degraded shell).
      function afterCascade(fn) {
        if (typeof queueMicrotask === "function") queueMicrotask(fn);
        else if (typeof setTimeout === "function") setTimeout(fn, 0);
        else fn();
      }
      // Opening a flow updates location.hash and the chart reacts to that hash after the
      // immediate selection notification. Publish the exact source/finding selection one
      // timer tick later so it wins over the broader flow-open state.
      function afterFlowOpen(fn) {
        afterCascade(() => {
          if (typeof setTimeout === "function") setTimeout(fn, 0);
          else fn();
        });
      }
      // Restore focus to the panel element carrying the pending stable id, if it is still in
      // the DOM. data-line for the source panel, data-finding-id for the errors panel.
      function restorePendingFocus() {
        if (!pendingFocus) return;
        const sel =
          pendingFocus.panel === "source"
            ? '.code-line[data-line="' + cssAttr(pendingFocus.id) + '"]'
            : '.finding-row[data-finding-id="' + cssAttr(pendingFocus.id) + '"]';
        const body = pendingFocus.panel === "source" ? sourceBody : errorsBody;
        const target = body && body.querySelector ? body.querySelector(sel) : null;
        if (target && typeof target.focus === "function") target.focus();
        pendingFocus = null;
      }
      // Escape a value for use inside an [attr="..."] selector (ids/line numbers are simple,
      // but a finding id could contain quotes/backslashes).
      function cssAttr(value) {
        return String(value).replace(/(["\\])/g, "\\$1");
      }

      // --- selection -> findings ---------------------------------------------------

      // The set of flow ids whose findings are "relevant" to the current selection:
      //   node selected  -> that node's findings only (handled separately, exact).
      //   flow selected  -> that one flow.
      //   scope selected -> every flow in the scope (L1 subtree).
      //   path selected  -> every flow whose file path is under that path (tree dir/file).
      //   nothing        -> all flows (L0: the whole codebase's findings).
      // General over any codebase: scopes/paths come straight from the payload, no
      // hard-coded names.
      function relevantFlowIds(sel) {
        if (sel.flowId && byId.has(sel.flowId)) return new Set([sel.flowId]);
        if (sel.path) {
          // A path selection ALWAYS scopes, even when it matches no flows: returning the
          // (possibly empty) set keeps the panels showing "this file/dir's findings" rather
          // than falling through to the whole-codebase list. An empty set => no findings.
          const prefix = sel.path;
          const ids = new Set();
          flows.forEach(flow => {
            const p = (flow.location && flow.location.path) || "";
            if (p === prefix || p.startsWith(prefix + "/")) ids.add(flow.id);
          });
          return ids;
        }
        if (sel.scope && Object.prototype.hasOwnProperty.call(scopeFlows, sel.scope)) {
          return new Set(scopeFlows[sel.scope] || []);
        }
        return null; // null => "all findings" (no scoping).
      }

      // Findings to list for a selection. A selected node narrows to that node's findings;
      // otherwise the relevant flow set's findings, deduped and stable-ordered.
      function findingsForSelection(sel) {
        if (reviewQueueMode) return prioritizedFindings(findings.slice());
        if (sel.nodeId) {
          return (findingsByNode.get(sel.nodeId) || []).slice();
        }
        const ids = relevantFlowIds(sel);
        if (ids === null) return findings.slice();
        return findings.filter(f => ids.has(f.flow_id));
      }

      function findingPriority(finding) {
        const severity = { error: 0, warning: 1, info: 2 };
        const evidence = { VERIFIED: 0, INFERRED: 1, POTENTIAL_GAP: 2 };
        return (severity[finding.severity] ?? 3) * 10 + (evidence[finding.evidence] ?? 3);
      }

      function prioritizedFindings(list) {
        return list.sort((a, b) =>
          findingPriority(a) - findingPriority(b) ||
          String(a.location && a.location.path || "").localeCompare(String(b.location && b.location.path || "")) ||
          String(a.message || "").localeCompare(String(b.message || ""))
        );
      }

      // --- Logical-errors panel ----------------------------------------------------

      // Evidence tier label exactly as the model emits it (VERIFIED / INFERRED /
      // POTENTIAL_GAP). Falls back to the raw value for forward-compatibility with any
      // future tier, so the panel never hard-codes the closed set.
      function tierClass(evidence) {
        return "tier-" + String(evidence || "").toLowerCase().replace(/[^a-z0-9]+/g, "-");
      }

      function findingDiagnostic(finding) {
        const metadata = finding && finding.metadata;
        const diagnostic = metadata && metadata.diagnostic;
        return diagnostic && typeof diagnostic === "object" ? diagnostic : null;
      }

      function findingRule(finding, diagnostic) {
        const ruleId = diagnostic && diagnostic.rule_id ? diagnostic.rule_id : finding.kind;
        const rule = findingRules && findingRules[ruleId];
        return rule && typeof rule === "object" ? rule : null;
      }

      function confidenceLabel(diagnostic) {
        const confidence = diagnostic && diagnostic.confidence;
        if (!confidence || typeof confidence !== "object") return "";
        const parts = [];
        if (typeof confidence.score === "number") {
          parts.push(Math.round(confidence.score * 100) + "%");
        }
        if (confidence.basis) parts.push(String(confidence.basis));
        return parts.join(" · ");
      }

      function compactValue(value) {
        if (value == null) return "";
        if (Array.isArray(value)) return value.map(compactValue).filter(Boolean).join(", ");
        if (typeof value === "object") {
          try {
            return JSON.stringify(value);
          } catch {
            return String(value);
          }
        }
        return String(value);
      }

      function compactList(values, maxItems) {
        if (!Array.isArray(values)) return compactValue(values);
        const kept = values.slice(0, maxItems).map(compactValue).filter(Boolean);
        const remaining = values.length - kept.length;
        return kept.join(", ") + (remaining > 0 ? " +" + remaining + " more" : "");
      }

      function diagnosticDisplayValue(label, value) {
        if (!value || typeof value !== "object" || Array.isArray(value)) {
          return compactValue(value);
        }
        if (Array.isArray(value.handle_declared_values)) {
          return "Declared values: " + compactList(value.handle_declared_values, 6);
        }
        if (Array.isArray(value.handle_quorum_values)) {
          return "Quorum values: " + compactList(value.handle_quorum_values, 6);
        }
        if (Array.isArray(value.handled_values)) {
          const parts = ["Handled values: " + compactList(value.handled_values, 6)];
          if (value.condition) parts.unshift("Condition: " + compactValue(value.condition));
          return parts.join(" · ");
        }
        if (value.guard_always != null) return "Guard always: " + compactValue(value.guard_always);
        if (value.reachable_guard != null) return "Reachable guard expected";
        return compactValue(value);
      }

      function diagnosticLine(label, value) {
        const text = diagnosticDisplayValue(label, value);
        if (!text) return null;
        const line = el("div", "diagnostic-line");
        line.append(el("span", "diagnostic-label", label), el("span", "diagnostic-value", text));
        return line;
      }

      function asTextList(value) {
        if (value == null) return [];
        if (Array.isArray(value)) return value.map(String).filter(Boolean);
        return [String(value)].filter(Boolean);
      }

      function findingMetadata(finding) {
        const metadata = finding && finding.metadata;
        return metadata && typeof metadata === "object" ? metadata : {};
      }

      function flowNodeById(flow, nodeId) {
        if (!flow || !nodeId) return null;
        return (flow.nodes || []).find(node => node.id === nodeId) || null;
      }

      function decisionValues(node) {
        const values = new Set(asTextList(node && node.metadata && node.metadata.values));
        const branches = node && node.metadata && Array.isArray(node.metadata.branches)
          ? node.metadata.branches
          : [];
        branches.forEach(branch => {
          if (branch && typeof branch === "object" && branch.label != null) {
            values.add(String(branch.label));
          }
        });
        return values;
      }

      function addContextRole(map, id, role) {
        if (!id || !role) return;
        const roles = map.get(id) || new Set();
        roles.add(role);
        map.set(id, roles);
      }

      function contextRoleLabel(role) {
        return String(role || "").replace(/_/g, " ");
      }

      function contextForFinding(finding, diagnostic) {
        const metadata = findingMetadata(finding);
        const scope = diagnostic && diagnostic.scope && typeof diagnostic.scope === "object"
          ? diagnostic.scope
          : {};
        const flowRoles = new Map();
        const nodeRoles = new Map();
        const focusFlow = byId.get(finding.flow_id);
        const focusNode = flowNodeById(focusFlow, finding.node_id);
        const focusNodeMetadata = focusNode && focusNode.metadata ? focusNode.metadata : {};
        const subject = metadata.subject || focusNodeMetadata.subject || "";
        const namespace = metadata.value_namespace || focusNodeMetadata.value_namespace || "";
        const condition = metadata.condition || focusNodeMetadata.condition || "";
        const missingValues = new Set(asTextList(metadata.missing));

        asTextList(scope.related_flow_ids).forEach(flowId => addContextRole(flowRoles, flowId, "diagnostic scope"));
        asTextList(scope.related_node_ids).forEach(nodeId => {
          if (focusFlow) addContextRole(nodeRoles, focusFlow.id + "\u0000" + nodeId, "diagnostic evidence");
        });
        if (focusFlow) {
          addContextRole(flowRoles, focusFlow.id, "finding flow");
          (focusFlow.calls || []).forEach(flowId => addContextRole(flowRoles, flowId, "called by finding flow"));
          (focusFlow.called_by || []).forEach(flowId => addContextRole(flowRoles, flowId, "caller of finding flow"));
        }

        flows.forEach(flow => {
          (flow.nodes || []).forEach(node => {
            if (node.kind !== "decision") return;
            const nodeMetadata = node.metadata || {};
            const values = decisionValues(node);
            const reasons = [];
            if (subject && nodeMetadata.subject === subject) {
              if (namespace && nodeMetadata.value_namespace === namespace) reasons.push("same subject namespace");
              else if (!namespace) reasons.push("same subject");
            }
            if (condition && nodeMetadata.condition === condition) reasons.push("same condition");
            if (missingValues.size && [...missingValues].some(value => values.has(value))) {
              reasons.push("handles missing value");
            }
            reasons.forEach(reason => {
              addContextRole(flowRoles, flow.id, reason);
              addContextRole(nodeRoles, flow.id + "\u0000" + node.id, reason);
            });
          });
        });

        const relatedFlows = [...flowRoles.entries()]
          .map(([flowId, roles]) => ({ flow: byId.get(flowId), roles: [...roles].sort() }))
          .filter(item => item.flow && item.flow.id !== finding.flow_id)
          .sort((a, b) => String(a.flow.name || a.flow.id).localeCompare(String(b.flow.name || b.flow.id)))
          .slice(0, 6);
        const relatedNodes = [...nodeRoles.entries()]
          .map(([key, roles]) => {
            const [flowId, nodeId] = key.split("\u0000");
            const flow = byId.get(flowId);
            const node = flowNodeById(flow, nodeId);
            return { flow, node, roles: [...roles].sort() };
          })
          .filter(item => item.flow && item.node)
          .sort((a, b) =>
            String(a.flow.name || a.flow.id).localeCompare(String(b.flow.name || b.flow.id)) ||
            String(a.node.label || a.node.id).localeCompare(String(b.node.label || b.node.id))
          )
          .slice(0, 6);
        return { relatedFlows, relatedNodes };
      }

      function selectRelatedFlow(flow) {
        if (!flow) return;
        if (LC.selectFlow) LC.selectFlow(flow.id);
        afterFlowOpen(() => {
          LC.select({
            edgeId: null,
            endLine: (flow.location && (flow.location.end_line || flow.location.start_line)) || null,
            findingId: null,
            flowId: flow.id,
            line: (flow.location && flow.location.start_line) || null,
            nodeId: null,
            path: (flow.location && flow.location.path) || null,
          });
        });
      }

      function selectRelatedNode(flow, node) {
        if (!flow || !node) return;
        if (LC.selectFlow) LC.selectFlow(flow.id);
        afterFlowOpen(() => {
          LC.select({
            edgeId: null,
            endLine: (node.location && (node.location.end_line || node.location.start_line)) || null,
            findingId: null,
            flowId: flow.id,
            line: (node.location && node.location.start_line) || null,
            nodeId: node.id,
            path: (node.location && node.location.path) || (flow.location && flow.location.path) || null,
          });
        });
      }

      function contextButton(label, meta, activate) {
        const button = el("button", "diagnostic-context-button");
        button.type = "button";
        button.appendChild(el("span", "diagnostic-context-label", label));
        if (meta) button.appendChild(el("span", "diagnostic-context-meta", meta));
        button.addEventListener("click", event => {
          event.preventDefault();
          event.stopPropagation();
          activate();
        });
        return button;
      }

      function chartLabel(value, limit) {
        const text = compactValue(value).replace(/\s+/g, " ").trim();
        if (text.length <= limit) return text;
        return text.slice(0, Math.max(0, limit - 3)).trim() + "...";
      }

      function diagnosticChartItems(finding, context) {
        const focusFlow = byId.get(finding.flow_id);
        if (!focusFlow) return [];
        const focusNode = flowNodeById(focusFlow, finding.node_id);
        const focusId = focusNode ? focusFlow.id + "::" + focusNode.id : focusFlow.id;
        const items = [
          {
            activate: () =>
              focusNode ? selectRelatedNode(focusFlow, focusNode) : selectRelatedFlow(focusFlow),
            key: focusId,
            kind: "focus",
            label: focusNode ? (focusNode.label || focusNode.id) : (focusFlow.name || focusFlow.id),
            meta: focusNode ? (focusFlow.name || focusFlow.id) : "finding flow",
          }
        ];
        const seen = new Set([focusId]);
        context.relatedNodes.slice(0, 4).forEach(item => {
          const key = item.flow.id + "::" + item.node.id;
          if (seen.has(key)) return;
          seen.add(key);
          items.push({
            activate: () => selectRelatedNode(item.flow, item.node),
            key: key,
            kind: "evidence",
            label: item.node.label || item.node.id,
            meta: item.roles.map(contextRoleLabel).join(", ") || (item.flow.name || item.flow.id),
          });
        });
        context.relatedFlows.slice(0, 3).forEach(item => {
          const key = item.flow.id;
          if (seen.has(key)) return;
          seen.add(key);
          items.push({
            activate: () => selectRelatedFlow(item.flow),
            key: key,
            kind: "flow",
            label: item.flow.name || item.flow.id,
            meta: item.roles.map(contextRoleLabel).join(", "),
          });
        });
        return items.slice(0, 6);
      }

      function appendDiagnosticChart(wrap, finding, context) {
        const items = diagnosticChartItems(finding, context);
        if (!items.length) return;
        const block = el("div", "diagnostic-chart");
        block.appendChild(el("div", "diagnostic-chart-title", "Diagnostic subgraph"));
        const targetCount = Math.max(0, items.length - 1);
        const height = Math.max(112, 36 + Math.max(1, targetCount) * 52);
        const svg = svgEl("svg", {
          "aria-label": "Focused diagnostic subgraph",
          "class": "diagnostic-chart-svg",
          "role": "img",
          "viewBox": "0 0 320 " + height,
        });
        const focus = items[0];
        const focusBox = { x: 14, y: Math.max(28, height / 2 - 20), width: 122, height: 42 };
        const targetBoxes = items.slice(1).map((item, index) => ({
          item: item,
          x: 180,
          y: 20 + index * 52,
          width: 124,
          height: 42,
        }));
        targetBoxes.forEach(box => {
          svg.appendChild(svgEl("line", {
            "class": "diagnostic-chart-edge",
            "x1": focusBox.x + focusBox.width,
            "x2": box.x,
            "y1": focusBox.y + focusBox.height / 2,
            "y2": box.y + box.height / 2,
          }));
        });

        function appendChartNode(item, box) {
          const group = svgEl("g", {
            "class": "diagnostic-chart-node " + item.kind,
            "data-diagnostic-chart-node": item.key,
            "role": "button",
            "tabindex": "0",
            "transform": "translate(" + box.x + " " + box.y + ")",
          });
          group.appendChild(svgEl("rect", {
            "class": "diagnostic-chart-box",
            "height": box.height,
            "rx": "7",
            "width": box.width,
            "x": "0",
            "y": "0",
          }));
          group.appendChild(svgEl("text", {
            "class": "diagnostic-chart-label",
            "x": "10",
            "y": "18",
          }, chartLabel(item.label, 20)));
          group.appendChild(svgEl("text", {
            "class": "diagnostic-chart-meta",
            "x": "10",
            "y": "32",
          }, chartLabel(item.meta, 24)));
          group.addEventListener("click", event => {
            event.preventDefault();
            event.stopPropagation();
            item.activate();
          });
          group.addEventListener("keydown", event => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              event.stopPropagation();
              item.activate();
            }
          });
          svg.appendChild(group);
        }

        appendChartNode(focus, focusBox);
        targetBoxes.forEach(box => appendChartNode(box.item, box));
        block.appendChild(svg);
        wrap.appendChild(block);
      }

      function appendFindingContext(wrap, finding, diagnostic, context) {
        context = context || contextForFinding(finding, diagnostic);
        if (!context.relatedFlows.length && !context.relatedNodes.length) return;
        const block = el("div", "diagnostic-related");
        if (context.relatedFlows.length) {
          block.appendChild(el("div", "diagnostic-related-title", "Related flows"));
          const list = el("div", "diagnostic-context-list");
          context.relatedFlows.forEach(item => {
            list.appendChild(
              contextButton(
                item.flow.name || item.flow.id,
                item.roles.map(contextRoleLabel).join(", "),
                () => selectRelatedFlow(item.flow)
              )
            );
          });
          block.appendChild(list);
        }
        if (context.relatedNodes.length) {
          block.appendChild(el("div", "diagnostic-related-title", "Evidence nodes"));
          const list = el("div", "diagnostic-context-list");
          context.relatedNodes.forEach(item => {
            list.appendChild(
              contextButton(
                (item.node.label || item.node.id) + " - " + (item.flow.name || item.flow.id),
                item.roles.map(contextRoleLabel).join(", "),
                () => selectRelatedNode(item.flow, item.node)
              )
            );
          });
          block.appendChild(list);
        }
        wrap.appendChild(block);
      }

      function appendFindingDiagnostic(row, finding) {
        const diagnostic = findingDiagnostic(finding);
        if (!diagnostic) return;
        const rule = findingRule(finding, diagnostic);
        const wrap = el("div", "finding-diagnostic");
        const grid = el("div", "diagnostic-grid");
        [
          diagnosticLine("Severity", diagnostic.severity || finding.severity),
          diagnosticLine("Confidence", confidenceLabel(diagnostic)),
          diagnosticLine("Category", diagnostic.category),
          diagnosticLine("Missing", diagnostic.missing),
          diagnosticLine("Expected", diagnostic.expected),
          diagnosticLine("Actual", diagnostic.actual),
        ].forEach(line => {
          if (line) grid.appendChild(line);
        });
        if (grid.childNodes.length) wrap.appendChild(grid);
        if (rule && rule.purpose) {
          const ruleText = el("p", "diagnostic-copy", rule.purpose);
          wrap.appendChild(ruleText);
        }
        if (diagnostic.review_prompt) {
          const prompt = el("p", "diagnostic-copy diagnostic-review", diagnostic.review_prompt);
          wrap.appendChild(prompt);
        }
        const actions = Array.isArray(diagnostic.suggested_next_actions)
          ? diagnostic.suggested_next_actions.slice(0, 3)
          : [];
        if (actions.length) {
          const actionList = el("ul", "diagnostic-actions");
          actions.forEach(action => {
            actionList.appendChild(el("li", "", action));
          });
          wrap.appendChild(actionList);
        }
        const context = contextForFinding(finding, diagnostic);
        appendDiagnosticChart(wrap, finding, context);
        appendFindingContext(wrap, finding, diagnostic, context);
        row.appendChild(wrap);
      }

      function findingRow(finding, expanded) {
        // A finding row is an activatable listitem. It must NOT be a <button role="listitem">
        // (a button is not a valid listitem child of role="list"); use a div with
        // role="listitem", made keyboard-activatable via tabindex + an Enter/Space handler.
        const row = el("div", "finding-row finding " + (finding.severity || ""));
        row.setAttribute("role", "listitem");
        row.setAttribute("tabindex", "0");
        row.setAttribute("data-finding-id", finding.id);
        if (finding.flow_id) row.setAttribute("data-flow-id", finding.flow_id);
        if (finding.node_id) row.setAttribute("data-node-id", finding.node_id);

        const head = el("div", "finding-head");
        const tier = el("span", "tier-badge " + tierClass(finding.evidence), finding.evidence || "");
        const kind = el("span", "finding-kind", finding.kind || "");
        head.append(tier, kind);
        row.appendChild(head);

        row.appendChild(el("div", "finding-message", finding.message || ""));
        // Source coordinate of the finding, so a row stands alone without the panels.
        if (finding.location && finding.location.path) {
          row.appendChild(
            el(
              "div",
              "finding-loc",
              finding.location.path + ":" + finding.location.start_line
            )
          );
        }
        const diagnostic = findingDiagnostic(finding);
        row.title =
          (diagnostic && diagnostic.review_prompt) ||
          finding.detail ||
          `Open finding ${finding.kind || "review item"} in the flowchart`;
        if (expanded) appendFindingDiagnostic(row, finding);

        // Activating a finding selects its flow + node (bidirectional: lights the block,
        // the source line, and the tree file). selectFlow opens the flow inline so its
        // decision block exists to highlight; then publish the node + finding so the block
        // highlight + source line land. selectFlow's notify completes first (not
        // re-entrant), so this second select() re-notifies cleanly. The activation came
        // from THIS panel, so record the finding id to restore focus after the re-render.
        function activate() {
          pendingFocus = { panel: "errors", id: finding.id };
          const publishFindingSelection = () => {
            LC.select({
              flowId: finding.flow_id || null,
              nodeId: finding.node_id || null,
              path: (finding.location && finding.location.path) || null,
              findingId: finding.id,
              line: (finding.location && finding.location.start_line) || null,
              endLine:
                (finding.location && (finding.location.end_line || finding.location.start_line)) || null,
            });
          };
          if (finding.flow_id && LC.selectFlow) {
            LC.selectFlow(finding.flow_id);
            afterFlowOpen(publishFindingSelection);
          } else {
            publishFindingSelection();
          }
        }
        row.addEventListener("click", activate);
        row.addEventListener("keydown", event => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            activate();
          }
        });
        return row;
      }

      // Compact counts-by-tier/kind summary for a broad (empty / L0 / scope) selection, so
      // the panel never renders an unbounded finding list at the top level. Returns a
      // <div> with one count line per evidence tier plus the total.
      function findingSummary(list) {
        const byTier = new Map();
        list.forEach(f => {
          const tier = String(f.evidence || "other");
          byTier.set(tier, (byTier.get(tier) || 0) + 1);
        });
        const wrap = el("div", "errors-summary");
        wrap.appendChild(
          el("p", "panel-empty", list.length + " finding" + (list.length === 1 ? "" : "s") + " across the current view.")
        );
        [...byTier.keys()].sort().forEach(tier => {
          const line = el("div", "summary-line");
          line.appendChild(el("span", "tier-badge " + tierClass(tier), tier));
          line.appendChild(el("span", "summary-count", String(byTier.get(tier))));
          wrap.appendChild(line);
        });
        wrap.appendChild(
          el("p", "panel-empty", "Select a flow or node to list its findings.")
        );
        return wrap;
      }

      function renderErrors(sel) {
        if (!errorsBody) return;
        const list = findingsForSelection(sel);
        clear(errorsBody);
        if (errorsCountEl) errorsCountEl.textContent = list.length ? String(list.length) : "";
        errorsStatus = list.length
          ? list.length + " finding" + (list.length === 1 ? "" : "s")
          : "no findings";
        if (!list.length) {
          errorsBody.appendChild(
            el("p", "panel-empty", "No findings for the current selection.")
          );
          return;
        }
        // A node selection is exact -- show all of its (few) findings. A broad selection
        // (nothing / L0 / a scope / a path) can match thousands; show a compact summary
        // instead of an unbounded list, so the panel stays bounded at the top level.
        if (reviewQueueMode && list.length > MAX_FINDING_ROWS) {
          list.slice(0, MAX_FINDING_ROWS).forEach(finding => {
            errorsBody.appendChild(findingRow(finding, sel.findingId === finding.id));
          });
          errorsBody.appendChild(
            el("p", "panel-empty", String(list.length - MAX_FINDING_ROWS) + " more findings not shown.")
          );
          return;
        }
        const exact = !!sel.nodeId;
        if (!exact && list.length > MAX_FINDING_ROWS) {
          errorsBody.appendChild(findingSummary(list));
          return;
        }
        list.forEach(finding => {
          const expanded =
            (sel.findingId && finding.id === sel.findingId) ||
            (sel.nodeId && finding.node_id === sel.nodeId && list.length <= 3);
          const row = findingRow(finding, expanded);
          if (
            (sel.findingId && finding.id === sel.findingId) ||
            (sel.nodeId && finding.node_id === sel.nodeId)
          ) {
            row.classList.add("selected");
          }
          errorsBody.appendChild(row);
        });
        // Focus is restored once after the whole cascade settles (see onSelection), not here.
      }

      // --- Source panel ------------------------------------------------------------

      // The flow whose snippet the source panel shows for a selection: the selected flow,
      // else (a bare scope/path selection) the first flow under it, so a file click still
      // shows code. null when nothing resolves.
      function sourceFlowFor(sel) {
        if (sel.flowId && byId.has(sel.flowId)) return byId.get(sel.flowId);
        if (!sel.path) return null;
        const ids = relevantFlowIds(sel);
        if (ids && ids.size) {
          // Deterministic: the lowest-line flow in the smallest path, good enough as a
          // representative; the user normally selects a flow before reading source.
          let best = null;
          ids.forEach(id => {
            const flow = byId.get(id);
            if (!flow) return;
            if (
              !best ||
              flow.location.path < best.location.path ||
              (flow.location.path === best.location.path &&
                flow.location.start_line < best.location.start_line)
            ) {
              best = flow;
            }
          });
          return best;
        }
        return null;
      }

      // Resolve a flow's own source lines from the SHARED file store. flow.source is a
      // lightweight {path, start_line, end_line, elided?} reference; the file is embedded
      // ONCE in sourceFiles[path] (deduped across every flow sharing it), so we slice this
      // flow's window out of that one copy. Returns {start_line, lines, elided, total} for
      // the flow's window, or null when the source is unavailable.
      function resolveFlowSource(flow) {
        const ref = flow && flow.source;
        if (!ref || !ref.path) return null;
        const file = sourceFiles[ref.path];
        if (!file || !Array.isArray(file.lines)) return null;
        const from = ref.start_line;
        if (from == null) return null;
        const to = ref.end_line != null ? ref.end_line : from;
        // The store covers a union range starting at file.start_line; slice this flow's
        // window out of it. The embedded (capped) window may be shorter than from..to when
        // the flow's tail was elided, so the slice naturally stops at the embedded end.
        const offset = from - file.start_line;
        if (offset < 0) return null;
        const lines = file.lines.slice(offset, offset + (to - from + 1));
        if (!lines.length) return null;
        return {
          start_line: from,
          lines: lines,
          // elided => the flow spans more lines than were embedded; total is the full
          // (uncapped) count so the panel can show how many lines were dropped.
          elided: !!ref.elided,
          total: to - from + 1,
        };
      }

      // Map each source line to the node that should be selected when that line is clicked,
      // preferring the NARROWEST-span node covering it. The entry node (and any whole-flow
      // node) spans the ENTIRE flow, so a naive first-node-wins maps every line to it and a
      // code click always selects the entry block. Instead: skip any node whose span equals
      // the flow's own span (the entry/whole-flow node), and when two nodes cover a line keep
      // the one with the smaller (end_line - start_line) -- so the `if` line lands on the
      // decision and a `return` line on that terminal. General over node order and nesting.
      function buildLineToNode(flow) {
        const loc = flow.location || {};
        const flowSpan =
          loc.start_line != null && loc.end_line != null
            ? loc.end_line - loc.start_line
            : null;
        const lineToNode = new Map(); // line -> {id, span}
        (flow.nodes || []).forEach(node => {
          const nloc = node.location || {};
          const from = nloc.start_line;
          if (from == null) return;
          const to = nloc.end_line != null ? nloc.end_line : from;
          const span = to - from;
          // Skip the entry/whole-flow node: it covers everything, so it is never the
          // "block on this line". A node whose span >= the flow's span is that node.
          if (flowSpan != null && span >= flowSpan) return;
          for (let ln = from; ln <= to; ln++) {
            const cur = lineToNode.get(ln);
            if (!cur || span < cur.span) lineToNode.set(ln, { id: node.id, span: span });
          }
        });
        return lineToNode;
      }

      // Resolve the source range that should read as selected. A node selection wins and
      // marks the exact logic block. A plain flow selection still marks the flow span, so
      // clicking a top-level block or an edge target visibly lands on a concrete piece of
      // code rather than merely opening the surrounding file.
      function selectedSourceRange(flow, sel) {
        if (sel.nodeId) {
          const node = LC.nodeById ? LC.nodeById(flow.id, sel.nodeId) : null;
          if (node && node.location) {
            const from = node.location.start_line;
            return {
              from: from,
              to: node.location.end_line != null ? node.location.end_line : from,
            };
          }
        }
        if (
          sel.line != null &&
          (!sel.path || !flow.location || !flow.location.path || sel.path === flow.location.path)
        ) {
          return {
            from: sel.line,
            to: sel.endLine != null ? sel.endLine : sel.line,
          };
        }
        if (sel.flowId === flow.id && flow.location && flow.location.start_line != null) {
          const from = flow.location.start_line;
          return {
            from: from,
            to: flow.location.end_line != null ? flow.location.end_line : from,
          };
        }
        return null;
      }

      // Render the flow's snippet with gutter line numbers. When a flow or node is
      // selected, the covered line range is marked + scrolled into view. The snippet spans
      // exactly the flow's own range, so node lines fall inside it.
      function renderSource(sel) {
        if (!sourceBody) return;
        const flow = sourceFlowFor(sel);
        clear(sourceBody);
        if (sourceFileEl) sourceFileEl.textContent = "";
        if (sourcePanel) sourcePanel.hidden = !flow;

        if (!flow) {
          sourceBody.appendChild(
            el("p", "panel-empty", "Select a flow or node to view its source.")
          );
          sourceStatus = "no source selected";
          return;
        }
        if (sourceFileEl) {
          sourceFileEl.textContent = flow.location.path + ":" + flow.location.start_line;
          sourceFileEl.title = flow.location.path;
        }
        sourceStatus = "source: " + flow.location.path + ":" + flow.location.start_line;

        const snippet = resolveFlowSource(flow);
        if (!snippet || !snippet.lines.length) {
          // Source unavailable (missing/binary file, or no snippet embedded) -- tolerated,
          // never a crash. Show a clear note rather than empty space.
          sourceBody.appendChild(
            el("p", "panel-empty", "Source unavailable for this file.")
          );
          return;
        }

        const lineToNode = buildLineToNode(flow);

        const selectedRange = selectedSourceRange(flow, sel);
        const hiFrom = selectedRange ? selectedRange.from : null;
        const hiTo = selectedRange ? selectedRange.to : null;

        const pre = el("div", "code-block");
        pre.setAttribute("role", "presentation");
        let firstHi = null;
        snippet.lines.forEach((text, i) => {
          const lineNo = snippet.start_line + i;
          const entry = lineToNode.get(lineNo);
          const nodeId = entry ? entry.id : null;
          // A div (not a <button>) so the line sits cleanly inside the code block; made
          // keyboard-activatable via role=button + tabindex + the Enter/Space handler below.
          const lineEl = el("div", "code-line" + (nodeId ? " has-node" : ""));
          lineEl.setAttribute("data-line", String(lineNo));
          if (nodeId) {
            lineEl.setAttribute("role", "button");
            lineEl.setAttribute("tabindex", "0");
            lineEl.setAttribute("data-node-id", nodeId);
            lineEl.title = `Select logic block on line ${lineNo}`;
          }
          const isHi = hiFrom != null && lineNo >= hiFrom && lineNo <= hiTo;
          if (isHi) {
            lineEl.classList.add("selected");
            if (!firstHi) firstHi = lineEl;
          }

          const gutter = el("span", "code-gutter", String(lineNo));
          gutter.setAttribute("aria-hidden", "true");
          // The code text is the ONE place untrusted source enters the DOM: textContent
          // only. A line containing markup or a closing script tag renders as literal
          // characters -- never parsed, never executed.
          const code = el("span", "code-text", text.length ? text : " ");

          lineEl.append(gutter, code);

          if (nodeId) {
            const activateLine = () => {
              // Selecting a source line selects its block: publish the node so shell.js
              // lights the canvas block, the tree marks the file, and this panel marks the
              // line -- all from the one store. Record the line so focus returns to the
              // equivalent line after the re-render this triggers (else it drops to <body>).
              pendingFocus = { panel: "source", id: lineNo };
              const publishLineSelection = () => LC.select({
                flowId: flow.id,
                nodeId: nodeId,
                path: flow.location.path,
                findingId: null,
                line: lineNo,
                endLine: lineNo,
              });
              if (LC.selectFlow) {
                LC.selectFlow(flow.id);
                afterFlowOpen(publishLineSelection);
              } else {
                publishLineSelection();
              }
            };
            lineEl.addEventListener("click", activateLine);
            lineEl.addEventListener("keydown", event => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                activateLine();
              }
            });
          }
          pre.appendChild(lineEl);
        });
        sourceBody.appendChild(pre);

        // When the flow's tail was elided (a very long function), say how many lines were
        // dropped rather than silently showing a truncated snippet.
        if (snippet.elided) {
          const dropped = snippet.total - snippet.lines.length;
          sourceBody.appendChild(
            el("p", "code-elided", dropped + " more line" + (dropped === 1 ? "" : "s") + " not shown")
          );
        }
        // Focus is restored once after the whole cascade settles (see onSelection), not here.

        // Bring the highlighted block's first line into view within the scroll area
        // (not the page): a large snippet scrolls, it never overflows the panel.
        if (firstHi && typeof firstHi.scrollIntoView === "function") {
          firstHi.scrollIntoView({ block: "nearest" });
        }
      }

      // --- Subscribe both panels to the shared store -------------------------------

      renderQuality();

      function onSelection(sel) {
        renderSource(sel);
        renderErrors(sel);
        // One combined announcement per selection (source + findings), so neither panel's
        // status clobbers the other's in the single shared live region.
        flushAnnounce();
        // Restore focus to the panel item the user just activated AFTER the whole cascade
        // settles, so chart focus updates do not immediately overwrite it.
        if (pendingFocus) afterCascade(restorePendingFocus);
      }
      if (LC.onSelection) LC.onSelection(onSelection);
      // Prime once with the initial (empty) selection so the panels show their hints.
      onSelection(LC.selection || {});

      if (reviewQueueBtn) {
        reviewQueueBtn.addEventListener("click", () => {
          reviewQueueMode = !reviewQueueMode;
          reviewQueueBtn.setAttribute("aria-pressed", reviewQueueMode ? "true" : "false");
          reviewQueueBtn.classList.toggle("active", reviewQueueMode);
          onSelection(LC.selection || {});
        });
      }

      // --- Full-screen canvas (Phase 4.5) -----------------------------------------
      // Maximizes the canvas and hides the side panels. Uses the browser Fullscreen API
      // when available; otherwise a CSS "maximize in page" fallback via a
      // body[data-fullscreen] class. Esc and the toggle both exit; the selection store is
      // never touched, so the panels are correct the moment the layout returns.
      const fsToggle = document.getElementById("fullscreenToggle");
      const mainEl = document.querySelector("main");
      const body = document.body;
      const fsApiSupported = !!(
        mainEl &&
        (mainEl.requestFullscreen ||
          mainEl.webkitRequestFullscreen ||
          mainEl.msRequestFullscreen)
      );

      function fsElement() {
        return document.fullscreenElement || document.webkitFullscreenElement || null;
      }
      // The in-page CSS fallback is intentional state we own (true only when we chose the
      // class fallback). The real Fullscreen API state is read live from fsElement(). The
      // body[data-fullscreen] attribute is a DERIVED CSS flag set by reflectFsState -- it
      // is NEVER read back as state, so the two mechanisms can never feed back into a loop
      // (an API exit clears the attribute instead of latching it on).
      let fallbackActive = false;
      function isMaximized() {
        return fallbackActive || fsElement() === mainEl;
      }
      // Expose the in-page fallback state so other shell handlers can defer to panels.js:
      // while the CSS fallback is maximized, panels.js owns Esc and exits the fallback.
      // The real Fullscreen API path is handled by the browser, so this flag is only ever
      // true for the fallback.
      LC.fullscreenFallbackActive = () => fallbackActive;

      function reflectFsState() {
        const on = isMaximized();
        if (fsToggle) {
          fsToggle.setAttribute("aria-pressed", on ? "true" : "false");
          fsToggle.title = on ? "Exit full screen (Esc)" : "Full screen (Esc to exit)";
        }
        // Derived CSS flag: drives the in-page maximize + panel hiding for BOTH the class
        // fallback and the real API (so :fullscreen and [data-fullscreen] share one rule).
        // Leaving fullscreen by any means (our toggle, F11, platform Esc -> fullscreenchange)
        // clears it and restores the layout.
        if (on) body.setAttribute("data-fullscreen", "");
        else body.removeAttribute("data-fullscreen");
        // The viewBox depends on the SVG's pixel size, which just changed; re-apply it so
        // the drawing fills the new area without a manual pan/zoom.
        if (LC.updateViewBox) LC.updateViewBox();
      }

      function requestFs() {
        if (!mainEl) return Promise.resolve();
        const req =
          mainEl.requestFullscreen ||
          mainEl.webkitRequestFullscreen ||
          mainEl.msRequestFullscreen;
        try {
          const r = req.call(mainEl);
          return r && typeof r.then === "function" ? r : Promise.resolve();
        } catch (_) {
          return Promise.reject();
        }
      }

      function exitFs() {
        const exit =
          document.exitFullscreen ||
          document.webkitExitFullscreen ||
          document.msExitFullscreen;
        if (exit) {
          try {
            const r = exit.call(document);
            return r && typeof r.then === "function" ? r : Promise.resolve();
          } catch (_) {}
        }
        return Promise.resolve();
      }

      function enterMaximize() {
        if (fsApiSupported) {
          // Try the real API; if it rejects (e.g. no user-activation), fall back to the
          // in-page class so the toggle always does something.
          requestFs().then(reflectFsState, () => {
            fallbackActive = true;
            reflectFsState();
          });
        } else {
          fallbackActive = true;
          reflectFsState();
        }
      }

      function exitMaximize() {
        // Clear the fallback intent first, then drop the real fullscreen if we are in it.
        // reflectFsState (called now and again on fullscreenchange) recomputes from the
        // live API state + this flag, never from the derived CSS attribute.
        fallbackActive = false;
        if (fsElement() === mainEl) {
          exitFs().then(reflectFsState, reflectFsState);
        } else {
          reflectFsState();
        }
      }

      function toggleFullscreen() {
        if (isMaximized()) exitMaximize();
        else enterMaximize();
      }

      LC.toggleFullscreen = toggleFullscreen;

      if (fsToggle) {
        fsToggle.addEventListener("click", toggleFullscreen);
      }
      // Keep aria-pressed + layout correct when fullscreen changes outside our toggle.
      ["fullscreenchange", "webkitfullscreenchange"].forEach(evt => {
        document.addEventListener(evt, reflectFsState);
      });
      // Esc exits the in-page maximize fallback (the real Fullscreen API handles its own
      // Esc, which fires fullscreenchange -> reflectFsState). Ignored while typing.
      document.addEventListener("keydown", event => {
        if (event.key !== "Escape") return;
        const t = event.target;
        if (t && /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName || "")) return;
        if (fallbackActive) {
          exitMaximize();
        }
      });
    })();
