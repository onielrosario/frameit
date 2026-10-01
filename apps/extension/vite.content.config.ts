import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

/**
 * Second build pass: the content script.
 *
 * Separate from vite.config.ts because a content script must be a single
 * self-contained file with no import statements — it is injected as a classic
 * script, not a module, so IIFE and no code splitting.
 *
 * `emptyOutDir: false` — this runs after the main build and must not wipe it.
 */
export default defineConfig({
  plugins: [react()],
  define: { "process.env.NODE_ENV": JSON.stringify("production") },
  build: {
    outDir: "dist",
    emptyOutDir: false,
    target: "es2022",
    minify: false,
    sourcemap: true,
    lib: {
      entry: fileURLToPath(new URL("src/content/index.ts", import.meta.url)),
      formats: ["iife"],
      name: "FrameOverlay",
      fileName: () => "content.js",
    },
  },
});
