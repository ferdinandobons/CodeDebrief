import { flushSync } from "react-dom";
import { createRoot, type Root } from "react-dom/client";

import { ViewerApp, type ViewerAppProps } from "./ViewerApp";

export type ExportImageFormat = "png" | "jpg";

export interface MountedLogicChartViewer {
  exportImage: (format: ExportImageFormat) => void;
  resetView: () => void;
  update: (props: ViewerAppProps) => void;
  zoom: (factor: number) => void;
  unmount: () => void;
}

export function mountLogicChartViewer(
  container: Element,
  props: ViewerAppProps,
): MountedLogicChartViewer {
  const root = createRoot(container);
  let baseViewBox: ViewBox | null = null;
  let cleanupPan: (() => void) | null = null;
  let panSvg: SVGSVGElement | null = null;

  const captureBaseViewBox = () => {
    const svg = findViewerSvg(container);
    baseViewBox = svg ? readViewBox(svg) : null;
  };
  const bindViewportControls = () => {
    const svg = findViewerSvg(container);
    if (svg === panSvg) return;
    cleanupPan?.();
    panSvg = svg;
    cleanupPan = svg ? bindSvgPan(svg) : null;
  };

  render(root, props);
  bindViewportControls();
  captureBaseViewBox();

  return {
    exportImage(format) {
      const svg = findViewerSvg(container);
      if (svg) exportSvgImage(svg, format);
    },
    resetView() {
      const svg = findViewerSvg(container);
      if (svg && baseViewBox) writeViewBox(svg, baseViewBox);
    },
    update(nextProps) {
      render(root, nextProps);
      bindViewportControls();
      captureBaseViewBox();
    },
    zoom(factor) {
      const svg = findViewerSvg(container);
      if (!svg) return;
      const current = readViewBox(svg);
      if (!current) return;
      const nextWidth = current.width * factor;
      const nextHeight = current.height * factor;
      writeViewBox(svg, {
        x: current.x + (current.width - nextWidth) / 2,
        y: current.y + (current.height - nextHeight) / 2,
        width: nextWidth,
        height: nextHeight,
      });
    },
    unmount() {
      cleanupPan?.();
      cleanupPan = null;
      panSvg = null;
      root.unmount();
    },
  };
}

function render(root: Root, props: ViewerAppProps) {
  flushSync(() => {
    root.render(<ViewerApp {...props} />);
  });
}

interface ViewBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

function findViewerSvg(container: Element): SVGSVGElement | null {
  return container.querySelector<SVGSVGElement>(".logicchart-viewer");
}

function readViewBox(svg: SVGSVGElement): ViewBox | null {
  const values = (svg.getAttribute("viewBox") || "")
    .trim()
    .split(/\s+/)
    .map(value => Number(value));
  if (values.length !== 4 || values.some(value => !Number.isFinite(value))) return null;
  const [x, y, width, height] = values;
  if (width <= 0 || height <= 0) return null;
  return { x, y, width, height };
}

function writeViewBox(svg: SVGSVGElement, viewBox: ViewBox) {
  svg.setAttribute(
    "viewBox",
    `${viewBox.x} ${viewBox.y} ${viewBox.width} ${viewBox.height}`,
  );
}

function bindSvgPan(svg: SVGSVGElement): () => void {
  let drag: {
    moved: number;
    origin: ViewBox;
    pointerId: number;
    startX: number;
    startY: number;
  } | null = null;

  const onPointerDown = (event: PointerEvent) => {
    if (event.button !== 0) return;
    const target = event.target;
    if (
      target instanceof Element &&
      target.closest(
        '[role="button"], a, .node, .detail-node, .edge-hit-path, .scope-entry-link, .edge-link-group',
      )
    ) {
      return;
    }
    const origin = readViewBox(svg);
    if (!origin) return;
    drag = {
      moved: 0,
      origin,
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
    };
    svg.classList.add("dragging");
    try {
      svg.setPointerCapture(event.pointerId);
    } catch {
      // JSDOM and some embedded renderers do not expose pointer capture.
    }
  };

  const onPointerMove = (event: PointerEvent) => {
    if (!drag) return;
    const width = svg.clientWidth || Number(svg.getAttribute("width")) || drag.origin.width;
    const height = svg.clientHeight || Number(svg.getAttribute("height")) || drag.origin.height;
    const dx = event.clientX - drag.startX;
    const dy = event.clientY - drag.startY;
    drag.moved = Math.max(drag.moved, Math.abs(dx) + Math.abs(dy));
    writeViewBox(svg, {
      ...drag.origin,
      x: drag.origin.x - dx * (drag.origin.width / width),
      y: drag.origin.y - dy * (drag.origin.height / height),
    });
    event.preventDefault();
  };

  const finishDrag = (event: PointerEvent) => {
    if (!drag) return;
    const pointerId = drag.pointerId;
    drag = null;
    svg.classList.remove("dragging");
    try {
      svg.releasePointerCapture(pointerId);
    } catch {
      // See setPointerCapture fallback above.
    }
    event.preventDefault();
  };

  svg.addEventListener("pointerdown", onPointerDown);
  svg.addEventListener("pointermove", onPointerMove);
  svg.addEventListener("pointerup", finishDrag);
  svg.addEventListener("pointercancel", finishDrag);

  return () => {
    svg.classList.remove("dragging");
    svg.removeEventListener("pointerdown", onPointerDown);
    svg.removeEventListener("pointermove", onPointerMove);
    svg.removeEventListener("pointerup", finishDrag);
    svg.removeEventListener("pointercancel", finishDrag);
  };
}

function exportSvgImage(svg: SVGSVGElement, format: ExportImageFormat) {
  const bounds = svgContentBounds(svg) ?? readViewBox(svg);
  if (!bounds) return;

  const maxPixelSide = 4096;
  const scale = Math.min(2, maxPixelSide / Math.max(bounds.width, bounds.height));
  const width = Math.max(1, Math.round(bounds.width * scale));
  const height = Math.max(1, Math.round(bounds.height * scale));
  const clone = svg.cloneNode(true) as SVGSVGElement;
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  clone.setAttribute("width", String(width));
  clone.setAttribute("height", String(height));
  clone.setAttribute("viewBox", `${bounds.x} ${bounds.y} ${bounds.width} ${bounds.height}`);
  clone.setAttribute("data-theme", document.documentElement.dataset.theme || "light");
  clone.querySelectorAll(".canvas-hit-zone, .edge-hit-path").forEach(node => node.remove());

  const style = document.createElementNS("http://www.w3.org/2000/svg", "style");
  style.textContent = [...document.querySelectorAll("style")]
    .map(node => node.textContent || "")
    .join("\n");
  clone.prepend(style);

  const background = document.createElementNS("http://www.w3.org/2000/svg", "rect");
  background.setAttribute("x", String(bounds.x));
  background.setAttribute("y", String(bounds.y));
  background.setAttribute("width", String(bounds.width));
  background.setAttribute("height", String(bounds.height));
  background.setAttribute("fill", cssVar("--paper", "#ffffff"));
  clone.insertBefore(background, style.nextSibling);

  const serialized = new XMLSerializer().serializeToString(clone);
  const svgBlob = new Blob([serialized], { type: "image/svg+xml;charset=utf-8" });
  const imageUrl = URL.createObjectURL(svgBlob);
  const image = new Image();
  image.onload = () => {
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d");
    if (!context) {
      URL.revokeObjectURL(imageUrl);
      return;
    }
    context.fillStyle = cssVar("--paper", "#ffffff");
    context.fillRect(0, 0, width, height);
    context.drawImage(image, 0, 0, width, height);
    URL.revokeObjectURL(imageUrl);
    const mime = format === "jpg" ? "image/jpeg" : "image/png";
    canvas.toBlob(blob => {
      if (!blob) return;
      downloadBlob(blob, `logicchart-flowchart-${timestamp()}.${format}`);
    }, mime, format === "jpg" ? 0.92 : undefined);
  };
  image.onerror = () => URL.revokeObjectURL(imageUrl);
  image.src = imageUrl;
}

function svgContentBounds(svg: SVGSVGElement): ViewBox | null {
  const hitPaths = [...svg.querySelectorAll<SVGElement>(".canvas-hit-zone, .edge-hit-path")];
  const previousDisplays = hitPaths.map(node => node.style.display);
  hitPaths.forEach(node => {
    node.style.display = "none";
  });

  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  try {
    [...svg.children].forEach(node => {
      if (node.tagName.toLowerCase() === "defs" || !hasBBox(node)) return;
      try {
        const box = node.getBBox();
        if (!box || !Number.isFinite(box.width) || !Number.isFinite(box.height)) return;
        minX = Math.min(minX, box.x);
        minY = Math.min(minY, box.y);
        maxX = Math.max(maxX, box.x + box.width);
        maxY = Math.max(maxY, box.y + box.height);
      } catch {
        // Some test DOMs do not implement SVG geometry APIs; export falls back to viewBox.
      }
    });
  } finally {
    hitPaths.forEach((node, index) => {
      node.style.display = previousDisplays[index] || "";
    });
  }

  if (!Number.isFinite(minX) || !Number.isFinite(minY)) return null;
  const padding = 90;
  return {
    x: minX - padding,
    y: minY - padding,
    width: Math.max(1, maxX - minX + padding * 2),
    height: Math.max(1, maxY - minY + padding * 2),
  };
}

function hasBBox(node: Element): node is Element & { getBBox: () => DOMRect } {
  return typeof (node as { getBBox?: unknown }).getBBox === "function";
}

function cssVar(name: string, fallback: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

function downloadBlob(blob: Blob, fileName: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.download = fileName;
  link.href = url;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function timestamp(): string {
  return new Date().toISOString().replace(/[:.]/g, "-");
}
