import type { ProgressiveFlowNode } from "./flowchart-layout";

export interface LogicChartLocation {
  path?: string;
  start_line?: number;
  end_line?: number;
}

export interface LogicChartFlowNode {
  id: string;
  kind?: string;
  label?: string;
  location?: LogicChartLocation;
  metadata?: Record<string, unknown>;
}

export interface LogicChartFlowEdge {
  id?: string;
  source: string;
  target: string;
  label?: string;
}

export interface LogicChartFlow extends ProgressiveFlowNode {
  name?: string;
  language?: string;
  entry_kind?: string;
  is_entrypoint?: boolean;
  location?: LogicChartLocation;
  nodes?: LogicChartFlowNode[];
  edges?: LogicChartFlowEdge[];
  calls?: string[];
  called_by?: string[];
  metadata?: {
    scope?: string | string[];
    test?: boolean;
    [key: string]: unknown;
  };
}

export interface LogicChartPayload {
  flows: LogicChartFlow[];
  metadata?: {
    scopes?: Record<string, number>;
    [key: string]: unknown;
  };
}

export interface ScopeSummary {
  name: string;
  flowIds: string[];
}

export interface ProgressiveModel {
  scope: string;
  layers: LogicChartFlow[][];
  entryFlowIds: string[];
}

export function flowLabel(flow: LogicChartFlow): string {
  return flow.name || flow.id;
}

export function flowPath(flow: LogicChartFlow): string {
  const path = flow.location?.path;
  if (!path) return "";
  const line = flow.location?.start_line;
  return line ? `${path}:${line}` : path;
}

export function buildFlowIndex(payload: LogicChartPayload): Map<string, LogicChartFlow> {
  return new Map(payload.flows.map(flow => [flow.id, flow]));
}

export function scopeNamesForFlow(flow: LogicChartFlow): string[] {
  const declared = flow.metadata?.scope;
  if (Array.isArray(declared) && declared.length) return [...declared].sort();
  if (typeof declared === "string" && declared) return [declared];
  const path = flow.location?.path || "";
  const topLevel = path.split("/").filter(Boolean)[0];
  return topLevel ? [topLevel] : ["codebase"];
}

export function buildScopeIndex(payload: LogicChartPayload): Map<string, string[]> {
  const index = new Map<string, string[]>();
  payload.flows.forEach(flow => {
    if (flow.metadata?.test) return;
    scopeNamesForFlow(flow).forEach(scope => {
      const ids = index.get(scope) || [];
      ids.push(flow.id);
      index.set(scope, ids);
    });
  });
  return new Map([...index.entries()].sort(([a], [b]) => a.localeCompare(b)));
}

export function scopeSummaries(payload: LogicChartPayload): ScopeSummary[] {
  return [...buildScopeIndex(payload).entries()].map(([name, flowIds]) => ({
    name,
    flowIds,
  }));
}

export function flowsForScope(payload: LogicChartPayload, scope: string): LogicChartFlow[] {
  const byId = buildFlowIndex(payload);
  const ids = buildScopeIndex(payload).get(scope) || [];
  return ids.map(id => byId.get(id)).filter(isFlow);
}

export function entryFlowsForScope(payload: LogicChartPayload, scope: string): LogicChartFlow[] {
  const flows = sortFlows(flowsForScope(payload, scope));
  const ids = new Set(flows.map(flow => flow.id));
  const entries = flows.filter(flow => flow.is_entrypoint);
  const rootEntries = entries.filter(
    flow => !(flow.called_by || []).some(source => ids.has(source)),
  );
  if (rootEntries.length) return rootEntries;
  if (entries.length) return entries;
  const roots = flows.filter(flow => !(flow.called_by || []).some(source => ids.has(source)));
  return roots.length ? roots : flows;
}

export function directCallTargets(
  payload: LogicChartPayload,
  flow: LogicChartFlow,
): LogicChartFlow[] {
  const byId = buildFlowIndex(payload);
  return (flow.calls || []).map(id => byId.get(id)).filter(isFlow);
}

export function buildProgressiveModel(
  payload: LogicChartPayload,
  scope: string,
  routeFlowIds: readonly string[] = [],
): ProgressiveModel {
  const byId = buildFlowIndex(payload);
  const firstLayer = entryFlowsForScope(payload, scope);
  const layers: LogicChartFlow[][] = [firstLayer];
  const seen = new Set(firstLayer.map(flow => flow.id));

  routeFlowIds
    .map(id => byId.get(id))
    .filter(isFlow)
    .forEach(flow => {
      if (!seen.has(flow.id)) {
        layers.push([flow]);
        seen.add(flow.id);
      }
      const targets = sortFlows(
        directCallTargets(payload, flow).filter(target => !seen.has(target.id)),
      );
      if (targets.length) {
        targets.forEach(target => seen.add(target.id));
        layers.push(targets);
      }
    });

  return {
    scope,
    layers: layers.filter(layer => layer.length),
    entryFlowIds: firstLayer.map(flow => flow.id),
  };
}

function sortFlows<T extends LogicChartFlow>(flows: readonly T[]): T[] {
  return [...flows].sort((a, b) => {
    const pathCompare = (a.location?.path || "").localeCompare(b.location?.path || "");
    if (pathCompare) return pathCompare;
    const lineCompare = (a.location?.start_line || 0) - (b.location?.start_line || 0);
    if (lineCompare) return lineCompare;
    return flowLabel(a).localeCompare(flowLabel(b));
  });
}

function isFlow(value: LogicChartFlow | undefined): value is LogicChartFlow {
  return value !== undefined;
}
