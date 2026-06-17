import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig(({ command }) => ({
  define:
    command === "build"
      ? {
          "process.env.NODE_ENV": JSON.stringify("production"),
        }
      : undefined,
  plugins: [react()],
  build: {
    emptyOutDir: true,
    lib: {
      entry: "frontend/src/index.ts",
      fileName: "logicchart-viewer-runtime",
      formats: ["iife"],
      name: "LogicChartViewer",
    },
    outDir: "src/logicchart/render/assets/generated",
    sourcemap: false,
  },
  test: {
    environment: "jsdom",
    include: ["frontend/tests/**/*.test.{ts,tsx}"],
  },
}));
