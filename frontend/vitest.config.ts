/// <reference types="vitest" />
// Vitest runner config for the Phase-7 frontend test scaffold.
//
// Standalone from vite.config.ts ON PURPOSE: vite.config.ts is built on the
// @lovable.dev/vite-tanstack-config wrapper (tanstackStart + nitro + cloudflare
// build target + dev-only componentTagger). Loading that whole pipeline under the
// vitest node runner pulls in the SSR/build plugins and breaks collection. We only
// need the `@` / `src` path alias the app uses — reproduced here via
// vite-tsconfig-paths (the same plugin the wrapper applies), so imports like
// `@/lib/...` and relative `../draw-adapter` resolve identically.
import { defineConfig } from "vitest/config";
import tsconfigPaths from "vite-tsconfig-paths";

export default defineConfig({
  plugins: [tsconfigPaths()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    exclude: ["e2e/**", "node_modules/**", "tests/**"],
  },
});
