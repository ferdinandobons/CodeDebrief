import {
  layoutProgressiveRows,
  layoutScopeNodes,
  scopeEntryEdges,
  type Bounds,
  type ExpandedFlowMeasure,
  type InlineAnchor,
  type LayoutNodePosition,
  type ProgressiveFlowNode,
  type ProgressiveLayoutOptions,
  type ScopeEntryEdge,
  type ScopeLayoutOptions,
  type ScopeLayoutPosition,
  type ScopeNodePosition,
} from "./flowchart-layout";
import {
  buildProgressiveModel,
  scopeSummaries,
  type LogicChartFlow,
  type LogicChartPayload,
} from "./logicchart-model";

export const DEFAULT_PROGRESSIVE_LAYOUT_OPTIONS: ProgressiveLayoutOptions = {
  flowWidth: 238,
  flowHeight: 68,
  gapX: 70,
  rowGap: 150,
  layerGap: 360,
  chipY: 27,
  decisionPad: 90,
  maxNodesPerRow: 8,
};

export const DEFAULT_SCOPE_LAYOUT_OPTIONS: ScopeLayoutOptions = {
  scopeWidth: 220,
  scopeHeight: 108,
  gapX: 150,
  gapY: 110,
  maxColumns: 4,
  topY: 80,
};

export interface ViewerLayoutInput {
  scope: string;
  payload?: LogicChartPayload;
  layers?: ProgressiveFlowNode[][];
  routeFlowIds?: readonly string[];
  expandedMeasures?: ReadonlyMap<string, ExpandedFlowMeasure>;
  scopeNode?: ScopeNodePosition;
  progressiveOptions?: ProgressiveLayoutOptions;
  scopeOptions?: ScopeLayoutOptions;
}

export interface ViewerLayout {
  activeScopeNode: ScopeLayoutPosition;
  entryEdges: ScopeEntryEdge[];
  flowById: Map<string, ProgressiveFlowNode>;
  flowPositions: Map<string, LayoutNodePosition>;
  inlineAnchors: InlineAnchor[];
  scopeNodes: ScopeLayoutPosition[];
  viewBox: Bounds;
}

export interface LayoutBox {
  id: string;
  kind: "detail" | "flow" | "scope";
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
}

export function createViewerLayout(input: ViewerLayoutInput): ViewerLayout {
  const progressiveOptions = input.progressiveOptions ?? DEFAULT_PROGRESSIVE_LAYOUT_OPTIONS;
  const scopeOptions = input.scopeOptions ?? DEFAULT_SCOPE_LAYOUT_OPTIONS;
  const model = input.payload
    ? buildProgressiveModel(input.payload, input.scope, input.routeFlowIds ?? [])
    : null;
  const layers = input.layers ?? model?.layers ?? [];
  const progressiveLayout = layoutProgressiveRows(layers, {
    ...progressiveOptions,
    expandedMeasures: input.expandedMeasures,
  });
  const scopeInputs = input.payload
    ? scopeSummaries(input.payload).map(summary => ({
        name: summary.name,
        flowCount: summary.flowIds.length,
      }))
    : [{ name: input.scope, flowCount: layers.flat().length }];
  const scopeNodes = layoutScopeNodes(scopeInputs, input.scope, scopeOptions).map(item =>
    input.scopeNode && item.scope === input.scope
      ? {
          ...item,
          x: input.scopeNode.x,
          y: input.scopeNode.y,
          width: input.scopeNode.width,
          height: input.scopeNode.height,
          expanded: true,
        }
      : item,
  );
  const activeScopeNode =
    scopeNodes.find(item => item.scope === input.scope) ?? {
      scope: input.scope,
      x: 0,
      y: scopeOptions.topY,
      width: scopeOptions.scopeWidth,
      height: scopeOptions.scopeHeight,
      flowCount: layers.flat().length,
      expanded: true,
    };
  const scopeBottom = Math.max(
    activeScopeNode.y + activeScopeNode.height / 2,
    ...scopeNodes.map(item => item.y + item.height / 2),
  );
  const layoutCenter = (progressiveLayout.bounds.minX + progressiveLayout.bounds.maxX) / 2;
  const detailOffsetX = activeScopeNode.x - layoutCenter;
  const detailOffsetY = scopeBottom + 150 - progressiveLayout.bounds.minY;
  const flowPositions = new Map(
    [...progressiveLayout.positions.entries()].map(([id, position]) => [
      id,
      {
        ...position,
        x: position.x + detailOffsetX,
        y: position.y + detailOffsetY,
      },
    ]),
  );
  const entries = progressiveLayout.entryFlowIds
    .map(id => flowPositions.get(id))
    .filter(isLayoutNodePosition);
  const entryEdges = scopeEntryEdges(activeScopeNode, entries, progressiveOptions.flowHeight);
  const flowById = new Map(layers.flat().map(flow => [flow.id, flow]));
  const inlineAnchors = progressiveLayout.inlineAnchors.map(anchor => ({
    ...anchor,
    bounds: offsetBounds(anchor.bounds, detailOffsetX, detailOffsetY),
    x: anchor.x + detailOffsetX,
    y: anchor.y + detailOffsetY,
  }));
  const flowBounds = offsetBounds(progressiveLayout.bounds, detailOffsetX, detailOffsetY);
  const scopeBounds = boundsForScopes(scopeNodes);

  return {
    activeScopeNode,
    entryEdges,
    flowById,
    flowPositions,
    inlineAnchors,
    scopeNodes,
    viewBox: {
      minX: Math.min(0, scopeBounds.minX - 120, flowBounds.minX - 160),
      minY: Math.min(-80, scopeBounds.minY - 120, flowBounds.minY - 120),
      maxX: Math.max(scopeBounds.maxX + 160, flowBounds.maxX + 160),
      maxY: Math.max(scopeBounds.maxY + 160, flowBounds.maxY + 180),
    },
  };
}

export function viewerLayoutBoxes(layout: ViewerLayout): LayoutBox[] {
  return [
    ...layout.scopeNodes.map(item => ({
      id: item.scope,
      kind: "scope" as const,
      minX: item.x - item.width / 2,
      maxX: item.x + item.width / 2,
      minY: item.y - item.height / 2,
      maxY: item.y + item.height / 2,
    })),
    ...[...layout.flowPositions.values()].map(item => ({
      id: item.id,
      kind: "flow" as const,
      minX: item.x - item.width / 2,
      maxX: item.x + item.width / 2,
      minY: item.y - item.height / 2,
      maxY: item.y + item.height / 2,
    })),
    ...layout.inlineAnchors.map(item => ({
      id: `${item.flowId}:detail`,
      kind: "detail" as const,
      minX: item.bounds.minX,
      maxX: item.bounds.maxX,
      minY: item.bounds.minY,
      maxY: item.bounds.maxY,
    })),
  ];
}

export function overlappingLayoutBoxes(boxes: readonly LayoutBox[], gap = 0): Array<[string, string]> {
  const overlaps: Array<[string, string]> = [];
  for (let i = 0; i < boxes.length; i += 1) {
    for (let j = i + 1; j < boxes.length; j += 1) {
      if (boxesOverlap(boxes[i], boxes[j], gap)) overlaps.push([boxes[i].id, boxes[j].id]);
    }
  }
  return overlaps;
}

export function isLogicChartFlow(flow: ProgressiveFlowNode): flow is LogicChartFlow {
  return "location" in flow || "entry_kind" in flow || "language" in flow;
}

function boundsForPositions(positions: readonly LayoutNodePosition[]): Bounds {
  if (!positions.length) return { minX: 0, maxX: 0, minY: 0, maxY: 0 };
  return {
    minX: Math.min(...positions.map(item => item.x - item.width / 2)),
    maxX: Math.max(...positions.map(item => item.x + item.width / 2)),
    minY: Math.min(...positions.map(item => item.y - item.height / 2)),
    maxY: Math.max(...positions.map(item => item.y + item.height / 2)),
  };
}

function boundsForScopes(positions: readonly ScopeNodePosition[]): Bounds {
  if (!positions.length) return { minX: 0, maxX: 0, minY: 0, maxY: 0 };
  return {
    minX: Math.min(...positions.map(item => item.x - item.width / 2)),
    maxX: Math.max(...positions.map(item => item.x + item.width / 2)),
    minY: Math.min(...positions.map(item => item.y - item.height / 2)),
    maxY: Math.max(...positions.map(item => item.y + item.height / 2)),
  };
}

function offsetBounds(bounds: Bounds, x: number, y: number): Bounds {
  return {
    maxX: bounds.maxX + x,
    maxY: bounds.maxY + y,
    minX: bounds.minX + x,
    minY: bounds.minY + y,
  };
}

function boxesOverlap(a: LayoutBox, b: LayoutBox, gap: number): boolean {
  return !(
    a.maxX + gap <= b.minX ||
    b.maxX + gap <= a.minX ||
    a.maxY + gap <= b.minY ||
    b.maxY + gap <= a.minY
  );
}

function isLayoutNodePosition(value: LayoutNodePosition | undefined): value is LayoutNodePosition {
  return value !== undefined;
}
