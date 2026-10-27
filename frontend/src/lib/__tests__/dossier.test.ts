/**
 * RED spec — Plan 07-05 (Export / dossier) turns this GREEN.
 *
 * EXPORT-01: the CSV export IS the provenance ledger — one row per ledger entry,
 * each row carrying the full provenance columns (key, value, unit, tier, source,
 * stage). `buildCsvRows` lives in ../dossier (unwritten) → import FAILS → RED.
 */
import { describe, it, expect, vi, afterEach } from "vitest";
import { buildCsvRows, mapSnapshotUrl, type FootprintWgs84 } from "../dossier";
import type { LedgerEntry } from "../provenance";

const ledgerEntries: LedgerEntry[] = [
  {
    key: "coverage_pct",
    value: 100.0,
    unit: "%",
    tier: "GROUNDED",
    source: "acceptance.json",
    stage: "acceptance",
  },
  {
    key: "transport_carbon_kg",
    value: 1240.5,
    unit: "kgCO2e",
    tier: "ASSUMED",
    source: "material_selection.json",
    stage: "selection",
  },
];

const REQUIRED_COLUMNS = ["key", "value", "unit", "tier", "source", "stage"];

describe("buildCsvRows — the ledger IS the CSV (EXPORT-01)", () => {
  it("emits exactly one row per ledger entry", () => {
    const rows = buildCsvRows(ledgerEntries);
    expect(rows).toHaveLength(ledgerEntries.length);
  });

  it("every row carries all provenance columns", () => {
    const rows = buildCsvRows(ledgerEntries);
    for (const row of rows) {
      for (const col of REQUIRED_COLUMNS) {
        expect(row).toHaveProperty(col);
      }
    }
  });

  it("preserves the tier on each row (no row loses provenance)", () => {
    const rows = buildCsvRows(ledgerEntries);
    expect(rows.map((r: { tier: string }) => r.tier)).toEqual([
      "GROUNDED",
      "ASSUMED",
    ]);
  });
});

// Regression — Phase 11 bug sweep (DEFECT #3): a large footprint baked in as a
// geojson() overlay blew the Mapbox Static Images API URL-length limit (~8192),
// so the request failed with CORS/ERR_FAILED and the PDF map broke. The builder
// must fall back to the plain (no-overlay) satellite snapshot when too long.
describe("mapSnapshotUrl — Static Images URL length guard (DEFECT #3)", () => {
  const center = { lon: 2.2225, lat: 41.4108 };
  afterEach(() => vi.unstubAllEnvs());

  it("returns null when no Mapbox token is configured", () => {
    vi.stubEnv("VITE_MAPBOX_TOKEN", "");
    const small: FootprintWgs84 = [[center, { lon: 2.223, lat: 41.411 }, { lon: 2.224, lat: 41.412 }]];
    expect(mapSnapshotUrl(small, center, 16)).toBeNull();
  });

  it("includes the geojson() overlay for a small footprint", () => {
    vi.stubEnv("VITE_MAPBOX_TOKEN", "pk.test-token");
    const small: FootprintWgs84 = [[center, { lon: 2.223, lat: 41.411 }, { lon: 2.224, lat: 41.412 }]];
    const url = mapSnapshotUrl(small, center, 16);
    expect(url).toContain("api.mapbox.com");
    expect(url).toContain("geojson(");
    expect((url ?? "").length).toBeLessThanOrEqual(8000);
  });

  it("drops the overlay (plain satellite) when the footprint would exceed the URL limit", () => {
    vi.stubEnv("VITE_MAPBOX_TOKEN", "pk.test-token");
    // ~3000 vertices → the overlay URL far exceeds 8192 chars.
    const bigRing = Array.from({ length: 3000 }, (_, i) => ({
      lon: 2.22 + i * 1e-5,
      lat: 41.41 + i * 1e-5,
    }));
    const huge: FootprintWgs84 = [bigRing];
    const url = mapSnapshotUrl(huge, center, 16);
    expect(url).toContain("api.mapbox.com");
    expect(url).not.toContain("geojson("); // fell back to no-overlay
    expect(url).toContain("access_token=");
    expect((url ?? "").length).toBeLessThanOrEqual(8000);
  });
});
