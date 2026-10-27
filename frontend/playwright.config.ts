import { defineConfig, devices } from "@playwright/test";

// Phase 2.2 e2e specs live in the repo-root tests/ tree; Phase 7 adds the
// workspace / simulation / dashboard / verdict / export specs under
// frontend/e2e/. Each project pins its OWN testDir so BOTH trees collect
// reliably (a single testDir + "../" glob does not traverse above the testDir
// in Playwright). Both share the same chromium device + baseURL.
const chromium = { ...devices["Desktop Chrome"] };

export default defineConfig({
  testMatch: "**/*.spec.ts",
  use: {
    baseURL: "http://localhost:5173",
  },
  projects: [
    {
      // Phase 2.2 console smoke (repo-root tests/).
      name: "console-2.2",
      testDir: "../tests",
      use: chromium,
    },
    {
      // Phase 7 frontend e2e (frontend/e2e/).
      name: "frontend-e2e",
      testDir: "e2e",
      use: chromium,
    },
  ],
  webServer: {
    command: "bun run dev",
    url: "http://localhost:5173",
    reuseExistingServer: !process.env.CI,
    cwd: ".",
  },
});
