// Copies manifest.json into dist/ after the Vite build.
// Kept as an explicit step rather than public/ so the manifest sits at the
// package root where anyone looking for it expects to find it.
import { copyFile, access } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const src = resolve(root, "manifest.json");
const dest = resolve(root, "dist", "manifest.json");

await access(src);
await copyFile(src, dest);
console.log("postbuild: manifest.json -> dist/manifest.json");
