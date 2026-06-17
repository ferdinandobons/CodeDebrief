import { describe, expect, it } from "vitest";

import demoPayloadJson from "../../examples/demo/logicchart-out/logic-flow.json";
import {
  buildProgressiveModel,
  buildScopeIndex,
  scopeSummaries,
  type LogicChartPayload,
} from "../src";

const demoPayload = demoPayloadJson as LogicChartPayload;

describe("generated demo payload", () => {
  it("derives the visible top-level codebase scopes from real LogicChart output", () => {
    const scopes = buildScopeIndex(demoPayload);

    expect([...scopes.keys()]).toEqual(["backend", "edge", "frontend"]);
    expect(scopeSummaries(demoPayload)).toEqual([
      { name: "backend", flowIds: expect.any(Array) },
      { name: "edge", flowIds: expect.any(Array) },
      { name: "frontend", flowIds: expect.any(Array) },
    ]);
  });

  it("builds first-layer entrypoints for every real demo scope", () => {
    for (const scope of ["backend", "edge", "frontend"]) {
      const model = buildProgressiveModel(demoPayload, scope);

      expect(model.scope).toBe(scope);
      expect(model.layers.length).toBeGreaterThan(0);
      expect(model.entryFlowIds.length).toBeGreaterThan(0);
      expect(new Set(model.entryFlowIds).size).toBe(model.entryFlowIds.length);
    }
  });
});
