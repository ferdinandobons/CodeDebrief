import { describe, expect, it } from "vitest";

import {
  assertNoOverlaps,
  layoutScopeNodes,
  layoutProgressiveRows,
  rowWidthForLayer,
  scopeEntryEdges,
  type ExpandedFlowMeasure,
  type LayoutNodePosition,
  type ProgressiveLayoutOptions,
} from "../src/flowchart-layout";

const baseOptions: ProgressiveLayoutOptions = {
  flowWidth: 238,
  flowHeight: 68,
  gapX: 70,
  rowGap: 150,
  layerGap: 360,
  chipY: 27,
  decisionPad: 90,
};

function isPosition(value: LayoutNodePosition | undefined): value is LayoutNodePosition {
  return value !== undefined;
}

describe("progressive flowchart layout", () => {
  it("reserves expanded sub-flow width so sibling hosts do not overlap their inline bands", () => {
    const expandedMeasures = new Map<string, ExpandedFlowMeasure>([
      [
        "entry-a",
        {
          width: 760,
          height: 420,
          minX: -380,
          maxX: 380,
          minY: 0,
          maxY: 420,
        },
      ],
    ]);
    const options = { ...baseOptions, expandedMeasures };
    const layer = [{ id: "entry-a" }, { id: "entry-b" }, { id: "entry-c" }];

    const layout = layoutProgressiveRows([layer], options);
    const positions = layer.map(flow => layout.positions.get(flow.id));

    expect(rowWidthForLayer(layer, options)).toBe(760 + 180 + 238 * 2 + 70 * 2);
    expect(positions.every(Boolean)).toBe(true);
    expect(assertNoOverlaps(positions.filter(isPosition), 24)).toBe(true);
    expect(layout.inlineAnchors).toHaveLength(1);
    expect(layout.bounds.maxX - layout.bounds.minX).toBeGreaterThan(1000);
  });

  it("connects a scope node to every visible entrypoint with deterministic fan-out edges", () => {
    const layout = layoutProgressiveRows(
      [[{ id: "api-route" }, { id: "worker" }, { id: "cron" }]],
      baseOptions,
    );
    const entries = layout.entryFlowIds.map(id => layout.positions.get(id)).filter(isPosition);
    const edges = scopeEntryEdges(
      { scope: "backend", x: 500, y: 80, width: 220, height: 108 },
      entries,
      baseOptions.flowHeight,
    );

    expect(edges).toHaveLength(3);
    expect(edges.map(edge => edge.target)).toEqual(["api-route", "worker", "cron"]);
    expect(new Set(edges.map(edge => edge.points[0].x)).size).toBe(3);
    edges.forEach(edge => {
      expect(edge.scope).toBe("backend");
      expect(edge.d).toContain(" L ");
      expect(edge.points).toHaveLength(4);
    });
  });

  it("wraps very wide layers into readable rows without dropping entrypoints", () => {
    const layer = Array.from({ length: 18 }, (_, index) => ({ id: `entry-${index}` }));
    const layout = layoutProgressiveRows([layer], {
      ...baseOptions,
      maxNodesPerRow: 6,
    });
    const positions = layer.map(flow => layout.positions.get(flow.id));

    expect(layout.rows).toHaveLength(3);
    expect(layout.rows.every(row => row.width <= rowWidthForLayer(layer.slice(0, 6), baseOptions))).toBe(
      true,
    );
    expect(layout.entryFlowIds).toEqual(layer.map(flow => flow.id));
    expect(positions.every(Boolean)).toBe(true);
    expect(assertNoOverlaps(positions.filter(isPosition), 24)).toBe(true);
  });

  it("keeps expanded inline bands separated after wrapping a large row", () => {
    const layer = Array.from({ length: 14 }, (_, index) => ({ id: `entry-${index}` }));
    const expandedMeasures = new Map<string, ExpandedFlowMeasure>([
      [
        "entry-2",
        {
          width: 860,
          height: 420,
          minX: -430,
          maxX: 430,
          minY: 0,
          maxY: 420,
        },
      ],
      [
        "entry-11",
        {
          width: 700,
          height: 380,
          minX: -350,
          maxX: 350,
          minY: 0,
          maxY: 380,
        },
      ],
    ]);
    const layout = layoutProgressiveRows([layer], {
      ...baseOptions,
      expandedMeasures,
      maxNodesPerRow: 7,
    });

    expect(layout.rows).toHaveLength(2);
    expect(layout.inlineAnchors).toHaveLength(2);
    expect(layout.inlineAnchors[0].bounds.maxY).toBeLessThan(
      layout.inlineAnchors[1].bounds.minY,
    );
    expect(assertNoOverlaps([...layout.positions.values()], 24)).toBe(true);
  });

  it("lays out top-level scope nodes consistently without special-case names", () => {
    const scopes = layoutScopeNodes(
      [
        { name: "frontend", flowCount: 6 },
        { name: "backend", flowCount: 16 },
        { name: "edge", flowCount: 7 },
      ],
      "frontend",
      {
        scopeWidth: 220,
        scopeHeight: 108,
        gapX: 150,
        gapY: 110,
        maxColumns: 4,
        topY: 80,
      },
    );

    expect(scopes.map(scope => scope.scope)).toEqual(["backend", "edge", "frontend"]);
    expect(scopes.find(scope => scope.scope === "frontend")?.expanded).toBe(true);
    expect(assertNoOverlaps(scopes.map(scope => ({
      id: scope.scope,
      x: scope.x,
      y: scope.y,
      width: scope.width,
      height: scope.height,
      reservedWidth: scope.width,
      layer: 0,
    })), 24)).toBe(true);
  });
});
