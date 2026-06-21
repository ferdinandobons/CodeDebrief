import type { Edge, Node } from "@xyflow/react";

import {
  layoutProgressiveRows,
  scopeEntryEdges,
  type ProgressiveFlowNode,
  type ProgressiveLayoutOptions,
  type ScopeNodePosition,
} from "./flowchart-layout";
import {
  buildProgressiveModel,
  flowLabel,
  type CodeDebriefPayload,
} from "./codedebrief-model";

export interface ReactFlowModel {
  nodes: Node[];
  edges: Edge[];
}

export function toReactFlowModel(
  scopeNode: ScopeNodePosition,
  layers: readonly (readonly ProgressiveFlowNode[])[],
  options: ProgressiveLayoutOptions,
): ReactFlowModel {
  const layout = layoutProgressiveRows(layers, options);
  const entries = layout.entryFlowIds
    .map(id => layout.positions.get(id))
    .filter(position => position !== undefined);
  const scopeEdges = scopeEntryEdges(scopeNode, entries, options.flowHeight);
  const nodes: Node[] = [
    {
      id: `scope:${scopeNode.scope}`,
      type: "scope",
      position: { x: scopeNode.x, y: scopeNode.y },
      data: { label: scopeNode.scope },
    },
    ...[...layout.positions.values()].map(position => ({
      id: position.id,
      type: "flow",
      position: { x: position.x, y: position.y },
      data: { label: position.id },
    })),
  ];
  const edges: Edge[] = scopeEdges.map(edge => ({
    id: `scope:${edge.scope}->${edge.target}`,
    source: `scope:${edge.scope}`,
    target: edge.target,
    type: "smoothstep",
    data: { kind: "scope-entry" },
  }));

  return { nodes, edges };
}

export function payloadToReactFlowModel(
  payload: CodeDebriefPayload,
  scopeNode: ScopeNodePosition,
  options: ProgressiveLayoutOptions,
  routeFlowIds: readonly string[] = [],
): ReactFlowModel {
  const model = buildProgressiveModel(payload, scopeNode.scope, routeFlowIds);
  const graph = toReactFlowModel(scopeNode, model.layers, options);
  const flows = new Map(model.layers.flat().map(flow => [flow.id, flow]));

  return {
    nodes: graph.nodes.map(node => {
      const flow = flows.get(node.id);
      if (!flow) return node;
      return {
        ...node,
        data: {
          ...node.data,
          label: flowLabel(flow),
          language: flow.language,
          entryKind: flow.entry_kind,
          path: flow.location?.path,
        },
      };
    }),
    edges: graph.edges,
  };
}
