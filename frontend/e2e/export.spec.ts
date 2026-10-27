/**
 * e2e — Plan 07-06 (Export) implements the PDF + CSV dossier (EXPORT-01, D-12).
 *
 * Clicking "Export Project Dossier" generates, client-side, a CSV blob (the
 * flattened provenance ledger = the open-data dataset) AND a PDF blob
 * (@react-pdf/renderer) — both as downloads from a single action. The CSV header
 * carries the provenance (tier) column: every exported number stays auditable.
 *
 * Deterministic via the shared artifact mocks (no live backend / Mapbox token);
 * the dashboard is reached via the `?step=dashboard` deep-link seam.
 */
import { test, expect } from "@playwright/test";
import { mockArtifacts } from "./fixtures/dashboard-mocks";

test.describe("Export — PDF + CSV dossier with provenance (EXPORT-01)", () => {
  test("clicking Export produces a CSV blob (provenance column) and a PDF blob", async ({
    page,
  }) => {
    await mockArtifacts(page);
    await page.goto("/?step=dashboard");

    const exportBtn = page.getByTestId("export-dossier");
    await expect(exportBtn).toBeVisible();

    // A single click fires both downloads (CSV synchronously, then the PDF once
    // @react-pdf finishes rendering in the browser). Collect every download so we
    // never miss one that fires between awaits.
    const downloads: import("@playwright/test").Download[] = [];
    page.on("download", (d) => downloads.push(d));

    await exportBtn.click();

    // The PDF render takes a moment; wait until both downloads have landed.
    await expect.poll(() => downloads.length, { timeout: 30_000 }).toBe(2);

    const csvDownload = downloads.find((d) =>
      d.suggestedFilename().endsWith(".csv"),
    )!;
    const pdfDownload = downloads.find((d) =>
      d.suggestedFilename().endsWith(".pdf"),
    )!;
    expect(csvDownload).toBeTruthy();
    expect(pdfDownload).toBeTruthy();

    const csvPath = await csvDownload.path();
    expect(csvPath).toBeTruthy();

    // The CSV header includes the provenance (tier) column — the ledger IS the CSV.
    const fs = await import("node:fs/promises");
    const csvText = await fs.readFile(csvPath!, "utf-8");
    const header = csvText.split("\n")[0];
    expect(header).toContain("tier");
    expect(header).toContain("key");
    expect(header).toContain("value");

    expect(await pdfDownload.path()).toBeTruthy();
  });
});
