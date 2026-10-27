/**
 * Shared deterministic artifact mocks for the dashboard e2e specs (Plan 07-05).
 * No live backend / Mapbox token required — the routes fulfill the six terminal
 * artifact endpoints with shapes matching projects/primavera-demo/.
 */
import type { Page } from "@playwright/test";

export const PROJECT = "primavera-demo";

export const MATERIAL = {
  schema_version: "1.1.0",
  selected_id: "membr-pe-yacht-shrinkwrap",
  is_membrane: true,
  transport_carbon_kgco2e: 1.290816,
  cost_total_eur: 0.0,
  solar_transmissivity: 0.4,
  selection_basis: "transport_carbon_min",
  cooling_correction_factor: 0.6,
  mass_balance: {
    label: "ASSUMED",
    scaffold_kg_rented: 0,
    membrane_m2_recovered: 5976,
    fixings_kg_new: 168,
  },
  next_life: { status: "ASSUMED", receiver: "TBD", return_mass_kg: 1075.68 },
  tent_comparison: {
    label: "ASSUMED",
    baseline_kgco2e_per_m2: 4.0,
    source: "single-use PVC marquee baseline, ICE v2.0",
  },
  infeasible: false,
};

export const ACCEPTANCE_PASS = {
  schema_version: "1.0.0",
  coverage_pct: 100.0,
  utci_delta_c: 4.8,
  X_c: 4.0,
  Y_pct: 70.0,
  verdict: "PASS",
  baseline_ref: "utci_grid.json#baseline_utci_c",
  meta: {
    comfort_gap_pct: 96.13,
    eur_per_deg_c: {
      value_eur_per_c: null,
      placeholder: true,
      note: "free recovered material; €/°C is a placeholder, not a real 0.",
    },
    baseline_conditions: {
      site: "Parc del Fòrum, Barcelona",
      latlon: [41.4106, 2.227],
      date: "2026-06-14",
      peak_band: "12-16 local (midpoint 14)",
      baseline_mean_c: 30.99,
    },
  },
};

export const BOM = {
  bom: { pillars: 84, membrane_m2: 5976.0 },
  egress: { clearance_width_m: 8.0 },
  certification_needs: [
    "wind-load certification",
    "engineering stamp",
    "on-site heat-safety sign-off",
  ],
  shadow_coverage_pct: 1.0,
};

export const PROVENANCE = {
  schema_version: "1.0.0",
  entries: [
    { key: "utci_delta_c", tier: "DERIVED", source: "acceptance" },
    { key: "coverage_pct", tier: "DERIVED", source: "acceptance" },
    { key: "comfort_gap_pct", tier: "DERIVED", source: "acceptance_meta" },
    { key: "eur_per_deg_c", tier: "ASSUMED", source: "acceptance_meta" },
    { key: "baseline_mean_c", tier: "GROUNDED", source: "acceptance_meta" },
    { key: "bom", tier: "DERIVED", source: "gh_response" },
    { key: "shadow_coverage_pct", tier: "DERIVED", source: "gh_response" },
  ],
};

export const RENDER_STUB = {
  render_url: null,
  status: "pending",
  phase: 6,
  note: "render pending — Phase 6",
};

export const FOOTPRINT = {
  crs: { epsg: 4326 },
  polygons: [
    [
      { lon: 2.2268, lat: 41.4104 },
      { lon: 2.2272, lat: 41.4104 },
      { lon: 2.2272, lat: 41.4108 },
      { lon: 2.2268, lat: 41.4108 },
      { lon: 2.2268, lat: 41.4104 },
    ],
  ],
};

export async function mockArtifacts(
  page: Page,
  acceptance: unknown = ACCEPTANCE_PASS,
) {
  const json = (body: unknown) => ({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
  await page.route(`**/api/artifacts/${PROJECT}/material_selection`, (r) =>
    r.fulfill(json(MATERIAL)),
  );
  await page.route(`**/api/artifacts/${PROJECT}/acceptance`, (r) =>
    r.fulfill(json(acceptance)),
  );
  await page.route(`**/api/artifacts/${PROJECT}/bom`, (r) =>
    r.fulfill(json(BOM)),
  );
  await page.route(`**/api/artifacts/${PROJECT}/provenance`, (r) =>
    r.fulfill(json(PROVENANCE)),
  );
  await page.route(`**/api/artifacts/${PROJECT}/render`, (r) =>
    r.fulfill(json(RENDER_STUB)),
  );
  await page.route(`**/api/artifacts/${PROJECT}/footprint`, (r) =>
    r.fulfill(json(FOOTPRINT)),
  );
}
