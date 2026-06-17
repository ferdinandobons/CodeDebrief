import { act } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  mountStandaloneLogicChartViewer,
  propsFromLocation,
  type LogicChartPayload,
  type MountedStandaloneLogicChartViewer,
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

describe("standalone viewer bridge", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    window.history.replaceState(null, "", "/");
  });

  it("derives scope and route from hash values", () => {
    expect(propsFromLocation(payload, { location: { hash: "#scope=backend" } })).toMatchObject({
      routeFlowIds: [],
      scope: "backend",
    });

    expect(propsFromLocation(payload, { location: { hash: "#flow=orders-route" } })).toMatchObject({
      routeFlowIds: ["orders-route"],
      scope: "frontend",
    });

    expect(propsFromLocation(payload, { location: { hash: "#path=edge/native" } })).toMatchObject({
      routeFlowIds: [],
      scope: "edge",
    });

    expect(
      propsFromLocation(payload, {
        location: {
          hash: `#edge=${encodeURIComponent(
            JSON.stringify({ scope: "frontend", target: "orders-route" }),
          )}`,
        },
      }),
    ).toMatchObject({
      routeFlowIds: [],
      scope: "frontend",
      selectedConnection: {
        kind: "scope-entry",
        scope: "frontend",
        target: "orders-route",
      },
    });
  });

  it("decodes edge hash values without relying on browser URI globals", () => {
    vi.stubGlobal("decodeURIComponent", undefined);

    expect(
      propsFromLocation(payload, {
        location: {
          hash: `#edge=${encodeURIComponent(
            JSON.stringify({ scope: "frontend", target: "orders-route" }),
          )}`,
        },
      }),
    ).toMatchObject({
      selectedConnection: {
        kind: "scope-entry",
        scope: "frontend",
        target: "orders-route",
      },
    });
  });

  it("mounts the React viewer into an existing generated HTML host", async () => {
    const container = document.createElement("div");
    document.body.appendChild(container);

    let mounted: MountedStandaloneLogicChartViewer | undefined;
    await act(async () => {
      mounted = mountStandaloneLogicChartViewer(container, payload, {
        location: { hash: "#scope=frontend" },
      });
    });

    expect(container.querySelector(".logicchart-viewer")).not.toBeNull();
    expect(container.querySelectorAll("[data-scope]")).toHaveLength(2);
    expect(container.querySelector('[data-flow-id="orders-route"]')).not.toBeNull();

    await act(async () => {
      mounted?.unmount();
    });
    container.remove();
  });

  it("mounts with a selected edge from the hash", async () => {
    const container = document.createElement("div");
    document.body.appendChild(container);

    const mounted = mountStandaloneLogicChartViewer(container, payload, {
      location: {
        hash: `#edge=${encodeURIComponent(
          JSON.stringify({ scope: "frontend", target: "orders-route" }),
        )}`,
      },
    });

    expect(container.querySelector(".logicchart-viewer")?.getAttribute("data-selected-kind")).toBe(
      "scope-entry",
    );
    expect(container.querySelectorAll(".scope-entry-link.selected-link")).toHaveLength(1);
    expect(container.querySelectorAll(".node.edge-source")).toHaveLength(1);
    expect(container.querySelectorAll(".node.edge-target")).toHaveLength(1);

    mounted.unmount();
    container.remove();
  });

  it("syncs edge selection and blank-canvas clear back to the hash", async () => {
    window.history.replaceState(null, "", "/#scope=frontend");
    const container = document.createElement("div");
    document.body.appendChild(container);

    const mounted = mountStandaloneLogicChartViewer(container, payload);

    await act(async () => {
      container
        .querySelector(".scope-entry-link")
        ?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    expect(window.location.hash).toContain("#edge=");
    expect(container.querySelector(".logicchart-viewer")?.getAttribute("data-selected-kind")).toBe(
      "scope-entry",
    );

    await act(async () => {
      container
        .querySelector(".canvas-hit-zone")
        ?.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
    });

    expect(window.location.hash).toBe("#scope=frontend");
    expect(container.querySelector(".logicchart-viewer")?.getAttribute("data-selected-kind")).toBe(
      "none",
    );

    mounted.unmount();
    container.remove();
  });

  it("opens a flow detail chart when an entrypoint node is selected", async () => {
    window.history.replaceState(null, "", "/#scope=frontend");
    const container = document.createElement("div");
    document.body.appendChild(container);

    const mounted = mountStandaloneLogicChartViewer(container, payload);

    await act(async () => {
      container
        .querySelector('[data-flow-id="orders-route"]')
        ?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });

    expect(window.location.hash).toBe("#flow=orders-route");
    expect(container.querySelector(".flow-detail")).not.toBeNull();
    expect(container.textContent).toContain("Switch on order.state");

    mounted.unmount();
    container.remove();
  });
});
