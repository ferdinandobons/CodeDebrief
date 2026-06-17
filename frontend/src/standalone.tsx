import {
  mountLogicChartViewer,
  type MountedLogicChartViewer,
} from "./mount";
import type { ExportImageFormat } from "./mount";
import {
  buildFlowIndex,
  scopeNamesForFlow,
  scopeSummaries,
  type LogicChartPayload,
} from "./logicchart-model";
import type { ViewerAppProps } from "./ViewerApp";
import type { SelectedConnection } from "./viewer-store";

export interface StandaloneViewerOptions {
  initialScope?: string;
  location?: Pick<Location, "hash">;
}

export interface MountedStandaloneLogicChartViewer {
  exportImage: (format: ExportImageFormat) => void;
  resetView: () => void;
  selectFlow: (flowId: string) => void;
  selectScope: (scope: string) => void;
  update: () => void;
  zoom: (factor: number) => void;
  unmount: () => void;
}

export function mountStandaloneLogicChartViewer(
  container: Element,
  payload: LogicChartPayload,
  options: StandaloneViewerOptions = {},
): MountedStandaloneLogicChartViewer {
  const canSubscribe =
    typeof window !== "undefined" && options.location === undefined;
  const navigateToHash = (hash: string) => {
    if (!canSubscribe) return;
    if (window.location.hash === hash) return;
    window.location.hash = hash;
  };
  const buildProps = (): ViewerAppProps => {
    const props = propsFromLocation(payload, options);
    return {
      ...props,
      syncHash: canSubscribe,
      onConnectionSelect(connection) {
        if (connection.kind === "scope-entry") {
          navigateToHash(hashForScopeEntryConnection(connection.scope, connection.target));
        }
      },
      onFlowSelect(flowId) {
        navigateToHash(hashForFlow(flowId));
      },
      onSelectionClear() {
        navigateToHash(`#scope=${encodeHashValue(props.scope)}`);
      },
      onScopeSelect(scope) {
        navigateToHash(`#scope=${encodeHashValue(scope)}`);
      },
    };
  };
  let mounted: MountedLogicChartViewer | null = mountLogicChartViewer(container, buildProps());
  const update = () => {
    mounted?.update(buildProps());
  };

  if (canSubscribe) {
    window.addEventListener("hashchange", update);
  }

  return {
    exportImage(format) {
      mounted?.exportImage(format);
    },
    resetView() {
      mounted?.resetView();
      const props = propsFromLocation(payload, options);
      navigateToHash(`#scope=${encodeHashValue(props.scope)}`);
      update();
    },
    selectFlow(flowId) {
      navigateToHash(hashForFlow(flowId));
      update();
    },
    selectScope(scope) {
      navigateToHash(`#scope=${encodeHashValue(scope)}`);
      update();
    },
    update,
    zoom(factor) {
      mounted?.zoom(factor);
    },
    unmount() {
      if (canSubscribe) {
        window.removeEventListener("hashchange", update);
      }
      mounted?.unmount();
      mounted = null;
    },
  };
}

function hashForScopeEntryConnection(scope: string, target: string): string {
  return `#edge=${encodeHashValue(JSON.stringify({ scope, target }))}`;
}

function hashForFlow(flowId: string): string {
  return `#flow=${encodeHashValue(flowId)}`;
}

export function propsFromLocation(
  payload: LogicChartPayload,
  options: StandaloneViewerOptions = {},
): ViewerAppProps {
  const fallbackScope = firstScope(payload, options.initialScope);
  const route = routeFromHash(payload, options.location?.hash ?? currentHash());
  return {
    payload,
    routeFlowIds: route.routeFlowIds,
    selectedConnection: route.selectedConnection,
    scope: route.scope || fallbackScope,
  };
}

interface ViewerRoute {
  scope: string;
  routeFlowIds: string[];
  selectedConnection?: SelectedConnection;
}

function routeFromHash(payload: LogicChartPayload, hash: string): ViewerRoute {
  const fallback = firstScope(payload);
  const raw = hash.startsWith("#") ? hash.slice(1) : hash;
  if (!raw) return { scope: fallback, routeFlowIds: [] };
  const [key, encodedValue] = raw.includes("=")
    ? raw.split("=", 2)
    : ["flow", raw];
  const value = safeDecode(encodedValue);
  if (!value) return { scope: fallback, routeFlowIds: [] };

  if (key === "scope") {
    return { scope: value, routeFlowIds: [] };
  }

  if (key === "edge") {
    const connection = edgeSelectionFromHashValue(value);
    if (connection) {
      return {
        routeFlowIds: [],
        scope: connection.scope,
        selectedConnection: connection,
      };
    }
    return { scope: fallback, routeFlowIds: [] };
  }

  if (key === "path") {
    return { scope: value.split("/").filter(Boolean)[0] || fallback, routeFlowIds: [] };
  }

  const byId = buildFlowIndex(payload);
  const flow = byId.get(value);
  if (key === "flow" && flow) {
    return {
      scope: scopeNamesForFlow(flow)[0] || fallback,
      routeFlowIds: [flow.id],
    };
  }

  return { scope: fallback, routeFlowIds: [] };
}

function edgeSelectionFromHashValue(value: string): Extract<
  SelectedConnection,
  { kind: "scope-entry" }
> | null {
  try {
    const parsed = JSON.parse(value) as unknown;
    if (!parsed || typeof parsed !== "object") return null;
    const record = parsed as Record<string, unknown>;
    if (typeof record.scope !== "string" || typeof record.target !== "string") {
      return null;
    }
    return {
      kind: "scope-entry",
      scope: record.scope,
      target: record.target,
    };
  } catch {
    return null;
  }
}

function firstScope(payload: LogicChartPayload, preferred?: string): string {
  const scopes = scopeSummaries(payload).map(scope => scope.name);
  if (preferred && scopes.includes(preferred)) return preferred;
  return scopes[0] || "codebase";
}

function currentHash(): string {
  return typeof window === "undefined" ? "" : window.location.hash;
}

function safeDecode(value: string): string | null {
  try {
    if (typeof decodeURIComponent === "function") {
      return decodeURIComponent(value);
    }
  } catch {
    // Fall through to the local decoder below. Some embedded browser test
    // contexts expose a restricted global object without decodeURIComponent.
  }
  return decodePercentEncodedAscii(value);
}

function encodeHashValue(value: string): string {
  if (typeof encodeURIComponent === "function") return encodeURIComponent(value);
  return value.replace(/[^A-Za-z0-9_.~-]/g, char =>
    `%${char.charCodeAt(0).toString(16).padStart(2, "0").toUpperCase()}`,
  );
}

function decodePercentEncodedAscii(value: string): string | null {
  try {
    return value.replace(/%([0-9A-Fa-f]{2})/g, (_, hex: string) =>
      String.fromCharCode(Number.parseInt(hex, 16)),
    );
  } catch {
    return null;
  }
}
