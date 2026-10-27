/**
 * e2e — Plan 07-05 (Dashboard) implements the provenance-tagged results view.
 *
 * LOAD-BEARING ASSERTION #1 (FE-03 / D-07): every numeric KPI/BOM/Comfort-Gap
 * cell on the dashboard MUST have a sibling provenance tag. The honesty contract
 * forbids any displayed number without a tier — this spec asserts there is NO
 * `[data-value-cell]` lacking a `[data-provenance]` sibling.
 *
 * Deterministic via network mocks (no live backend / Mapbox token); the
 * dashboard is reached via the `?step=dashboard` deep-link seam.
 */
import { test, expect } from "@playwright/test";
import { mockArtifacts } from "./fixtures/dashboard-mocks";

test.describe("Dashboard — every value carries provenance (FE-03, load-bearing #1)", () => {
  test("no numeric KPI/BOM cell is rendered without a [data-provenance] sibling tag", async ({
    page,
  }) => {
    await mockArtifacts(page);
    await page.goto("/?step=dashboard");

    const valueCells = page.locator("[data-value-cell]");
    await expect(valueCells.first()).toBeVisible();
    const count = await valueCells.count();
    expect(count).toBeGreaterThan(0);

    for (let i = 0; i < count; i++) {
      const cell = valueCells.nth(i);
      const tag = cell.locator(
        "xpath=following-sibling::*[@data-provenance] | preceding-sibling::*[@data-provenance]",
      );
      await expect(tag.first()).toBeVisible();
    }
  });

  test("the render hero shows the 'render pending — Phase 6' stub when render_url is null", async ({
    page,
  }) => {
    await mockArtifacts(page);
    await page.goto("/?step=dashboard");
    const render = page.getByTestId("render-panel");
    await expect(render).toContainText(/render pending — Phase 6/i);
  });
});
