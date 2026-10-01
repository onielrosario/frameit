import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

// Two entries, one build:
//   popup.html  -> dist/popup.html   (settings / about only — ADR-0001)
//   background  -> dist/background.js (MV3 module service worker)
//
// No content script yet. It arrives at stage 05 with the shadow-DOM overlay.
// Selection capture at stage 04 uses chrome.scripting.executeScript on demand,
// which keeps host permissions out of the manifest.
/** Resolve a path relative to this config file. No __dirname: the package is ESM. */
const entry = (path: string) => fileURLToPath(new URL(path, import.meta.url));

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
    target: "es2022",
    // MV3 forbids eval. Keep the output readable while debugging stage 04.
    minify: false,
    sourcemap: true,
    rollupOptions: {
      input: {
        popup: entry("popup.html"),
        background: entry("src/background/index.ts"),
      },
      output: {
        entryFileNames: "[name].js",
        chunkFileNames: "chunks/[name]-[hash].js",
        assetFileNames: "assets/[name][extname]",
      },
    },
  },
});
