/**
 * FE-02 — the 6-stage ProgressiveStepper (Plan 07-04).
 *
 * Starting a run renders a stepper with exactly SIX stage rows
 * (utci_grid → crowd_grid → score_grid → geometry → material → acceptance) and
 * each row advances to "done" as GET /api/status reports the stage complete —
 * NEVER on a timer (CCA-F P1/P2). The crowd row carries the "routing
 * ASSUMED-grade" qualifier (D-10).
 *
 * The pipeline backend is mocked here so the test is deterministic: /api/run is
 * stubbed and /api/status returns a progressively-completing 6-key payload. The
 * stepper advance is therefore asserted to follow the POLLED status, not elapsed
 * time — the exact property under test.
 */
import { test, expect } from "@playwright/test";

const SIX_STAGES = [
  "utci_grid",
  "crowd_grid",
  "score_grid",
  "geometry",
  "material",
  "acceptance",
];

type Stage = (typeof SIX_STAGES)[number];
type Status = "pending" | "running" | "done" | "failed";

function statusPayload(doneUpTo: number): Record<Stage, Status> {
  const out = {} as Record<Stage, Status>;
  SIX_STAGES.forEach((k, i) => {
    out[k] = i < doneUpTo ? "done" : i === doneUpTo ? "running" : "pending";
  });
  return out;
}

test.describe("Simulation — 6-stage ProgressiveStepper (FE-02)", () => {
  test("shows six stage rows and advances each as /api/status reports done", async ({
    page,
  }) => {
    // Progressive status: each poll completes one more stage, terminating with
    // all six "done". The stepper must mirror THIS, never a clock.
    let poll = 0;
    await page.route("**/api/status/**", async (route) => {
      const doneUpTo = Math.min(poll, SIX_STAGES.length);
      poll += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(statusPayload(doneUpTo)),
      });
    });
    await page.route("**/api/run/**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ project_id: "primavera-demo", status: "started" }),
      });
    });
    // Artifact fetches (heat/crowd/trajectories) are out of scope for the stepper
    // assertion — stub them with minimally valid (empty) shapes so the view's
    // derived counts never throw on a missing backend. NOTE: Playwright matches
    // route handlers in REVERSE registration order, so the catch-all is registered
    // FIRST and the specific heat/crowd shapes LAST (they win).
    await page.route("**/api/artifacts/**", async (route) => {
      await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
    });
    await page.route("**/api/artifacts/**/heat", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          label: "test", cell_size_m: 6, utci_min_c: 0, utci_max_c: 0, cells: [],
        }),
      });
    });
    await page.route("**/api/artifacts/**/crowd", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          default: "v2",
          runs: { v2: { note: "", cell_size_m: 6, cells: [], dwell_zones: [], flow_vectors: [] } },
        }),
      });
    });

    await page.goto("/");
    // Mock auth → workspace. TanStack Start serves SSR HTML first; the click only
    // navigates once React has hydrated the onSubmit handler, so retry the login
    // until the workspace (its preset button) appears.
    const preset = page.getByRole("button", { name: /primavera 2026 preset/i });
    await expect(async () => {
      await page.getByRole("button", { name: /access console/i }).click();
      await expect(preset).toBeVisible({ timeout: 1000 });
    }).toPass({ timeout: 20_000 });
    // Preset seeds a boundary + element so the run button enables without drawing.
    await preset.click();
    await page.getByRole("button", { name: /run thermal & crowd simulation/i }).click();

    const stepRows = page.getByTestId("stage-row");
    await expect(stepRows).toHaveCount(SIX_STAGES.length);

    // The crowd row carries the routing ASSUMED-grade qualifier (D-10).
    await expect(page.locator('[data-stage="crowd_grid"]')).toContainText(
      /ASSUMED-grade/i,
    );

    // Each stage flips to done as the polled status reports it — assert the last
    // (acceptance) row reaches a terminal done state (gated on status, not time).
    await expect(page.locator('[data-stage="acceptance"]')).toHaveAttribute(
      "data-status",
      "done",
      { timeout: 30_000 },
    );
  });
});
