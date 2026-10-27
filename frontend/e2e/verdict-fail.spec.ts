/**
 * e2e — Plan 07-05 (Dashboard verdict) implements FAIL handling.
 *
 * LOAD-BEARING ASSERTION #2 (D-11): a FAIL verdict is a first-class terminal
 * outcome — it must be shown PROMINENTLY (visible, never hidden), and the render
 * remains a labelled stub (no fake success render on a failing design). Driven
 * by the synthetic FAIL fixture (src/test-fixtures/acceptance_fail.json:
 * coverage 42 %, Δ 1.9 °C, verdict FAIL).
 *
 * Deterministic via network mocks + the `?step=dashboard` deep-link seam.
 */
import { test, expect } from "@playwright/test";
import { mockArtifacts } from "./fixtures/dashboard-mocks";

// Synthetic FAIL fixture (mirrors src/test-fixtures/acceptance_fail.json):
// coverage 42 %, Δ 1.9 °C, verdict FAIL.
const acceptanceFail = {
  schema_version: "1.0.0",
  coverage_pct: 42.0,
  utci_delta_c: 1.9,
  X_c: 4.0,
  Y_pct: 70.0,
  verdict: "FAIL",
  baseline_ref: "utci_grid.json#baseline_utci_c",
};

test.describe("Dashboard — FAIL verdict is shown prominently (D-11, load-bearing #2)", () => {
  test("with the synthetic FAIL acceptance loaded, the FAIL verdict is visible and render stays a labelled stub", async ({
    page,
  }) => {
    // The FAIL fixture has no meta sidecar; the dashboard must still render.
    await mockArtifacts(page, { ...acceptanceFail });
    await page.goto("/?step=dashboard");

    const verdict = page.getByTestId("acceptance-verdict");
    await expect(verdict).toBeVisible();
    await expect(verdict).toContainText("FAIL");

    // The render panel stays an explicit stub (no overclaimed success render).
    const render = page.getByTestId("render-panel");
    await expect(render).toContainText(/stub|pending|not.*generated/i);
  });
});
