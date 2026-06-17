import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it } from "vitest";

import { ViewerApp } from "../src/ViewerApp";
import type { LogicChartPayload } from "../src/logicchart-model";
import { useViewerStore } from "../src/viewer-store";

const payload: LogicChartPayload = {
  flows: [
    {
      id: "orders-route",
      name: "GET",
      language: "typescript",
      entry_kind: "route",
      is_entrypoint: true,
      location: { path: "frontend/app/api/orders/route.ts", start_line: 3 },
      calls: ["load-order"],
      called_by: [],
      metadata: { scope: ["frontend"] },
      nodes: [
        { id: "orders-route:n1", kind: "entry", label: "Route: GET", location: { path: "frontend/app/api/orders/route.ts", start_line: 3 } },
        { id: "orders-route:n2", kind: "decision", label: "Switch on order.state", location: { path: "frontend/app/api/orders/route.ts", start_line: 6 } },
        { id: "orders-route:n3", kind: "terminal", label: "Return Response.json(order)", location: { path: "frontend/app/api/orders/route.ts", start_line: 8 } },
      ],
      edges: [
        { source: "orders-route:n1", target: "orders-route:n2" },
        { source: "orders-route:n2", target: "orders-route:n3", label: "\"open\"" },
      ],
    },
    {
      id: "users-route",
      name: "POST",
      language: "typescript",
      entry_kind: "route",
      is_entrypoint: true,
      location: { path: "frontend/app/api/users/route.ts", start_line: 4 },
      calls: [],
      called_by: [],
      metadata: { scope: ["frontend"] },
    },
    {
      id: "load-order",
      name: "loadOrder",
      language: "typescript",
      entry_kind: "function",
      location: { path: "frontend/app/api/orders/route.ts", start_line: 18 },
      calls: [],
      called_by: ["orders-route"],
      metadata: { scope: ["frontend"] },
    },
    {
      id: "edge-admission",
      name: "AdmissionControl.route",
      language: "cpp",
      entry_kind: "function",
      is_entrypoint: true,
      location: { path: "edge/native/admission.cpp", start_line: 23 },
      calls: [],
      called_by: [],
      metadata: { scope: ["edge"] },
    },
    {
      id: "backend-auth",
      name: "AuthService.CanAccess",
      language: "csharp",
      entry_kind: "method",
      is_entrypoint: true,
      location: { path: "backend/auth/AuthService.cs", start_line: 12 },
      calls: [],
      called_by: [],
      metadata: { scope: ["backend"] },
    },
  ],
};

describe("ViewerApp", () => {
  beforeEach(() => {
    useViewerStore.getState().clearSelection();
  });

  it("renders a scope node connected to every first-layer entrypoint", () => {
    const html = renderToStaticMarkup(
      <ViewerApp scope="frontend" payload={payload} routeFlowIds={["orders-route"]} />,
    );

    expect(html).toContain('data-scope="frontend"');
    expect(html.match(/class="edge-link-group"/g)).toHaveLength(2);
    expect(html).toContain('data-target-flow-id="orders-route"');
    expect(html).toContain('data-target-flow-id="users-route"');
    expect(html).toContain('href="#edge=');
    expect(html).toContain('class="edge-hit-path"');
    expect(html).toContain('class="edge-link-group"');
    expect(html).toContain('id="typedNodeShadow"');
    expect(html).toContain('id="typedArrow"');
    expect(html.match(/<rect class="shape"/g)).toHaveLength(6);
    expect(html.match(/vector-effect="non-scaling-stroke"/g)?.length).toBeGreaterThanOrEqual(8);
    expect(html).toContain("loadOrder");
    expect(html).toContain("Switch on order.state");
    expect(html).toContain('class="flow-detail"');
    expect(html).toContain("route · typescript");
    expect(html).toContain('class="node entry scope-node expanded"');
    expect(html).not.toContain('scope-node dimmed');
  });

  it("dims unrelated flow nodes when a scope-entry connection is selected", () => {
    useViewerStore.getState().setSelectedConnection({
      kind: "scope-entry",
      scope: "frontend",
      target: "orders-route",
    });

    const html = renderToStaticMarkup(<ViewerApp scope="frontend" payload={payload} />);

    expect(html).toContain('data-selected-kind="scope-entry"');
    expect(html).toContain('class="node entry scope-node expanded edge-source"');
    expect(html).toContain('class="node flow-node edge-target"');
    expect(html).toContain('class="node flow-node dimmed"');
    expect(html).toContain('class="edge scope-entry-link selected-link"');
    expect(html).toContain('class="edge scope-entry-link dimmed"');
  });

  it("accepts a selected connection from the current route", () => {
    const html = renderToStaticMarkup(
      <ViewerApp
        scope="frontend"
        payload={payload}
        selectedConnection={{
          kind: "scope-entry",
          scope: "frontend",
          target: "orders-route",
        }}
      />,
    );

    expect(html).toContain('data-selected-kind="scope-entry"');
    expect(html).toContain('class="edge scope-entry-link selected-link"');
    expect(html).toContain('class="node entry scope-node expanded edge-source"');
    expect(html).toContain('class="node flow-node edge-target"');
  });

  it("keeps all top-level scope nodes at distinct positions in a multi-scope payload", () => {
    const html = renderToStaticMarkup(<ViewerApp scope="frontend" payload={payload} />);
    const transforms = new Map<string, string>();
    const scopePattern = /<g class="[^"]*scope-node[^"]*"[^>]*>/g;

    for (const match of html.matchAll(scopePattern)) {
      const tag = match[0];
      const scope = tag.match(/data-scope="([^"]+)"/)?.[1];
      const transform = tag.match(/transform="translate\(([^)]+)\)"/)?.[1];
      if (scope && transform) transforms.set(scope, transform);
    }

    expect([...transforms.keys()].sort()).toEqual(["backend", "edge", "frontend"]);
    expect(new Set(transforms.values()).size).toBe(3);
    expect(transforms.get("frontend")).not.toBe(transforms.get("edge"));
  });
});
