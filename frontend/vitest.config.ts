import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    restoreMocks: true,
    unstubGlobals: true,
    // Full runs start one jsdom worker per core; screen-level flows near the 5 s default timed out under that load.
    testTimeout: 20000,
  },
});
