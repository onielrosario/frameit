import { defineConfig } from "vitest/config";

// Separate from vite.config.ts: that config builds two named entries for the
// extension, which has nothing to do with running tests.
export default defineConfig({
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
