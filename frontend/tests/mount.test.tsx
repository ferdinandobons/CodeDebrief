import { act } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mountLogicChartViewer, type LogicChartPayload } from "../src";

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

describe("mountLogicChartViewer", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("mounts, updates, and unmounts the viewer in a DOM container", async () => {
    const container = document.createElement("main");
    document.body.appendChild(container);
    let mounted!: ReturnType<typeof mountLogicChartViewer>;

    await act(async () => {
      mounted = mountLogicChartViewer(container, {
        payload,
        routeFlowIds: ["orders-route"],
        scope: "frontend",
      });
    });

    expect(container.querySelector(".logicchart-viewer")).not.toBeNull();
    expect(container.querySelector('[data-scope="frontend"]')).not.toBeNull();
    expect(container.querySelector('[data-flow-id="load-order"]')).not.toBeNull();
    const svg = container.querySelector(".logicchart-viewer");
    const initialViewBox = svg?.getAttribute("viewBox");

    mounted.zoom(0.5);
    expect(svg?.getAttribute("viewBox")).not.toBe(initialViewBox);

    mounted.resetView();
    expect(svg?.getAttribute("viewBox")).toBe(initialViewBox);
    expect(typeof mounted.exportImage).toBe("function");

    if (!svg) throw new Error("expected mounted viewer svg");
    Object.defineProperty(svg, "clientWidth", { configurable: true, value: 1000 });
    Object.defineProperty(svg, "clientHeight", { configurable: true, value: 700 });

    svg.dispatchEvent(pointerEvent("pointerdown", { clientX: 240, clientY: 220 }));
    svg.dispatchEvent(pointerEvent("pointermove", { clientX: 320, clientY: 260 }));
    svg.dispatchEvent(pointerEvent("pointerup", { clientX: 320, clientY: 260 }));
    expect(svg.getAttribute("viewBox")).not.toBe(initialViewBox);

    mounted.resetView();
    expect(svg.getAttribute("viewBox")).toBe(initialViewBox);

    const flowShape = container.querySelector('[data-flow-id="orders-route"] .shape');
    if (!flowShape) throw new Error("expected flow node shape");
    flowShape.dispatchEvent(pointerEvent("pointerdown", { clientX: 420, clientY: 260 }));
    svg.dispatchEvent(pointerEvent("pointermove", { clientX: 500, clientY: 300 }));
    svg.dispatchEvent(pointerEvent("pointerup", { clientX: 500, clientY: 300 }));
    expect(svg.getAttribute("viewBox")).toBe(initialViewBox);

    await act(async () => {
      mounted.update({
        payload,
        scope: "backend",
      });
    });

    expect(container.querySelector('[data-scope="backend"]')?.getAttribute("class")).toContain(
      "expanded",
    );

    await act(async () => {
      mounted.unmount();
    });

    expect(container.innerHTML).toBe("");
    container.remove();
  });

  it("exports the current SVG as a raster image without invisible hit paths", async () => {
    const container = document.createElement("main");
    document.body.appendChild(container);
    const objectUrlBlobs: Blob[] = [];
    const downloads: Array<{ download: string; href: string }> = [];
    let rasterMime = "";

    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn((blob: Blob) => {
        objectUrlBlobs.push(blob);
        return `blob:logicchart-${objectUrlBlobs.length}`;
      }),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });

    class FakeImage {
      onerror: (() => void) | null = null;
      onload: (() => void) | null = null;

      set src(_value: string) {
        this.onload?.();
      }
    }

    vi.stubGlobal("Image", FakeImage);
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
      drawImage: vi.fn(),
      fillRect: vi.fn(),
      fillStyle: "",
    } as unknown as CanvasRenderingContext2D);
    vi.spyOn(HTMLCanvasElement.prototype, "toBlob").mockImplementation((callback, type) => {
      rasterMime = type || "";
      callback(new Blob(["raster"], { type: type || "image/png" }));
    });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function clickStub(
      this: HTMLAnchorElement,
    ) {
      downloads.push({ download: this.download, href: this.href });
    });

    const mounted = mountLogicChartViewer(container, {
      payload,
      scope: "frontend",
    });

    expect(container.querySelector(".edge-hit-path")).not.toBeNull();
    expect(container.querySelector(".canvas-hit-zone")).not.toBeNull();

    mounted.exportImage("jpg");

    expect(rasterMime).toBe("image/jpeg");
    expect(downloads).toHaveLength(1);
    expect(downloads[0].download).toMatch(/^logicchart-flowchart-.*\.jpg$/);
    expect(objectUrlBlobs).toHaveLength(2);
    await expect(readBlobText(objectUrlBlobs[0])).resolves.not.toContain("edge-hit-path");
    await expect(readBlobText(objectUrlBlobs[0])).resolves.not.toContain("canvas-hit-zone");

    mounted.unmount();
    container.remove();
  });
});

function readBlobText(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => resolve(String(reader.result || "")));
    reader.addEventListener("error", () => reject(reader.error));
    reader.readAsText(blob);
  });
}

function pointerEvent(
  type: string,
  options: {
    button?: number;
    clientX: number;
    clientY: number;
    pointerId?: number;
  },
): PointerEvent {
  const event = new MouseEvent(type, {
    bubbles: true,
    button: options.button ?? 0,
    cancelable: true,
    clientX: options.clientX,
    clientY: options.clientY,
  }) as PointerEvent;
  Object.defineProperty(event, "pointerId", {
    configurable: true,
    value: options.pointerId ?? 1,
  });
  return event;
}
