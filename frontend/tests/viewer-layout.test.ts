import { describe, expect, it } from "vitest";

import {
  createViewerLayout,
  overlappingLayoutBoxes,
  viewerLayoutBoxes,
  type ExpandedFlowMeasure,
  type LogicChartPayload,
} from "../src";

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
        {
          id: "orders-route:n1",
          kind: "entry",
          label: "Route: GET",
          location: { path: "frontend/app/api/orders/route.ts", start_line: 3 },
        },
        {
          id: "orders-route:n2",
          kind: "decision",
          label: "Switch on order.state",
          location: { path: "frontend/app/api/orders/route.ts", start_line: 6 },
        },
        {
          id: "orders-route:n3",
          kind: "terminal",
          label: "Return Response.json(order)",
          location: { path: "frontend/app/api/orders/route.ts", start_line: 8 },
        },
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

describe("viewer layout composition", () => {
  it("keeps top-level scopes and visible flow nodes separated", () => {
    const layout = createViewerLayout({
      expandedMeasures,
      payload,
      routeFlowIds: ["orders-route"],
      scope: "frontend",
    });

    expect(layout.scopeNodes.map(node => node.scope)).toEqual(["backend", "edge", "frontend"]);
    expect(layout.activeScopeNode.scope).toBe("frontend");
    expect(layout.entryEdges.map(edge => edge.target)).toEqual(["orders-route", "users-route"]);
    expect(layout.inlineAnchors.map(anchor => anchor.flowId)).toEqual(["orders-route"]);
    expect(layout.flowPositions.get("load-order")?.y).toBeGreaterThan(
      layout.flowPositions.get("orders-route")?.y ?? 0,
    );
    expect(viewerLayoutBoxes(layout).some(box => box.kind === "detail")).toBe(true);
    expect(overlappingLayoutBoxes(viewerLayoutBoxes(layout), 24)).toEqual([]);
  });

  it("preserves explicit active scope overrides without moving sibling scopes", () => {
    const layout = createViewerLayout({
      payload,
      scope: "frontend",
      scopeNode: { scope: "frontend", x: 520, y: 80, width: 220, height: 108 },
    });
    const positions = new Map(layout.scopeNodes.map(node => [node.scope, node.x]));

    expect(positions.get("frontend")).toBe(520);
    expect(positions.get("edge")).not.toBe(520);
    expect(overlappingLayoutBoxes(viewerLayoutBoxes(layout), 24)).toEqual([]);
  });

  it("wraps large codebase entrypoint sets while preserving scope fan-out", () => {
    const largePayload: LogicChartPayload = {
      flows: Array.from({ length: 26 }, (_, index) => ({
        id: `api-entry-${index}`,
        name: `GET /resource/${index}`,
        language: "typescript",
        entry_kind: "route",
        is_entrypoint: true,
        location: {
          path: `frontend/app/api/resource-${index}/route.ts`,
          start_line: 1,
        },
        calls: [],
        called_by: [],
        metadata: { scope: ["frontend"] },
      })),
    };
    const layout = createViewerLayout({
      payload: largePayload,
      scope: "frontend",
    });

    expect(layout.entryEdges).toHaveLength(26);
    expect(layout.flowPositions).toHaveLength(26);
    expect(overlappingLayoutBoxes(viewerLayoutBoxes(layout), 24)).toEqual([]);
    expect(layout.viewBox.maxX - layout.viewBox.minX).toBeLessThan(3000);
  });
});

const expandedMeasures = new Map<string, ExpandedFlowMeasure>([
  [
    "orders-route",
    {
      height: 398,
      maxX: 150,
      maxY: 398,
      minX: -150,
      minY: 0,
      width: 300,
    },
  ],
]);
