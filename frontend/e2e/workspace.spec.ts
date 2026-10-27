/**
 * RED-pending e2e — Plan 07-03 (Workspace) implements the Mapbox + Draw flow.
 *
 * FE-01: the workspace loads a Mapbox map container with a Draw control, and
 * drawing a boundary polygon updates the live area readout (m²). Marked fixme
 * until the Mapbox migration lands — the spec PARSES and is collected so the
 * harness tracks it RED-pending; remove test.fixme to activate in Plan 03.
 */
import { test, expect } from "@playwright/test";

test.describe("Workspace — Mapbox + Draw (FE-01)", () => {
  test.fixme(
    "loads a Mapbox map container with a draw control and updates the area readout",
    async ({ page }) => {
      await page.goto("/");
      // The workspace step renders a Mapbox GL canvas + a mapbox-gl-draw control.
      const mapContainer = page.locator(".mapboxgl-canvas-container");
      await expect(mapContainer).toBeVisible();

      const drawControl = page.locator(".mapbox-gl-draw_polygon");
      await expect(drawControl).toBeVisible();

      // Before any boundary is drawn, the site-area readout reads 0 m².
      const areaReadout = page.getByTestId("site-area-m2");
      await expect(areaReadout).toContainText("0");

      // Drawing a boundary updates siteAreaM2 to a positive value
      // (@turf/area over the drawn polygon).
      await drawControl.click();
      // … draw interaction (clicks on the map) lands in Plan 03 …
      await expect(areaReadout).not.toContainText("0 m²");
    },
  );
});
