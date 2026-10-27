/**
 * Typed fetch wrappers for the Phase 2.2 FastAPI backend (src/api/app.py).
 *
 * All requests go through the Vite dev proxy at /api → http://localhost:8000.
 * No hardcoded secrets — the Google Maps key is client-side only in import.meta.env
 * and is never sent to the backend (T-2.2-04 / CCA-F P7 / XFN-02).
 *
 * Error handling: throws on non-2xx responses with the status + body text.
 *
 * Artifact types below match the REAL JSON files served by the backend
 * (viz/data/demo_heat.json, demo_crowd_grid.json, demo_trajectories.json),
 * verified by direct inspection 2026-06-11.
 */

import type { Feature } from "geojson";

export type StageStatus = "pending" | "running" | "done" | "failed";

export interface RunResponse {
  project_id: string;
  /** "already_running": backend rejected an in-flight re-trigger (MD-01) —
   *  the run is still progressing; poll getStatus() exactly as for "started". */
  status: "started" | "already_running";
}

/**
 * THREE-stage status from GET /api/status/{id} (post v2.0 pivot, D-06):
 * climate (utci_grid) → crowd (crowd_grid) → placement (structure_zones).
 * The greedy score_grid + the geometry/material/acceptance chain RETIRED with the
 * pivot ("AI proposes, human commits" — structure_zones is the canonical output).
 * Each key flips to "done" ONLY when its backing stage fn returns on the backend
 * (CCA-F P1/P2 — never on elapsed time); "failed" is an internal error only.
 */
export interface StatusResponse {
  utci_grid: StageStatus;
  crowd_grid: StageStatus;
  structure_zones: StageStatus;
}

/** The 3 pipeline stage keys, in dependency order. */
export const STAGE_KEYS: (keyof StatusResponse)[] = [
  "utci_grid",
  "crowd_grid",
  "structure_zones",
];

/**
 * Full-run brief body for POST /api/run/{id} (A2 direct passthrough — NOT the LLM
 * parser). Omitted fields fall back to the persisted parsed_brief.json on the
 * backend; an omitted boundary_geojson falls back to the default Parc del Fòrum
 * site polygon (_SITE_POLYGON). The client sends typed fields + GeoJSON only —
 * never a file path (T-07-10).
 */
export interface FullRunBody {
  capacity: number;
  budget: number;
  date: string;
  theme: string;
  boundary_geojson?: Feature;
  zones?: Feature[];
}

/** Heat cell from demo_heat.json: WGS84 lon/lat + UTCI value (°C) */
export interface HeatCell {
  lon: number;
  lat: number;
  utci_c: number;
}

/** Full heat artifact (demo_heat.json): honesty label + scale bounds + 9,536 cells */
export interface HeatArtifact {
  /** Honesty label, e.g. "… entire site < 26 C comfort threshold on this date" */
  label: string;
  cell_size_m: number;
  utci_min_c: number;
  utci_max_c: number;
  cells: HeatCell[];
}

/** WGS84 [lon, lat] pair */
export type LonLat = [number, number];

/** Crowd density cell from demo_crowd_grid.json runs.v2.cells */
export interface CrowdCell {
  lon: number;
  lat: number;
  density: number;
}

/** Dwell zone from demo_crowd_grid.json: WGS84 polygon ring */
export interface DwellZone {
  polygon: LonLat[];
}

/** Flow vector from demo_crowd_grid.json: WGS84 origin → destination */
export interface FlowVector {
  origin: LonLat;
  destination: LonLat;
}

export interface CrowdArtifact {
  default: string;
  runs: {
    v2: {
      note: string;
      cell_size_m: number;
      cells: CrowdCell[];
      dwell_zones: DwellZone[];
      flow_vectors: FlowVector[];
    };
  };
}

/** Agent trajectory frame entry: [lon, lat, speed_m_per_step] per agent */
export type AgentFrame = [number, number, number];

export interface TrajectoriesArtifact {
  default: string;
  runs: {
    v2: {
      label: string;
      note: string;
      n_agents: number;
      n_steps_recorded: number;
      stride: number;
      v_max_m_per_step: number;
      agent_format: string;
      frames: AgentFrame[][];
    };
  };
}

/**
 * One ranked shade-priority zone from GET /api/artifacts/{id}/structure_zones
 * (WGS84 projection of the placer output — the SOLE placement artifact post-pivot).
 * `footprint` is a closed WGS84 ring (square of side √area_m2 around `center`);
 * coverage/demand figures stay ASSUMED-grade (crowd weights unvalidated per site).
 */
export interface StructureZone {
  rank: number;
  center: LonLat;
  footprint: LonLat[];
  area_m2: number;
  coverage_pct: number;
  marginal_demand: number;
  cumulative_demand: number;
  newly_covered_cell_count: number;
  robustness: string;
  surviving_snapshots: string[];
}

export interface StructureZonesArtifact {
  note: string;
  coverage_model: string;
  stopping_rule: { k: number; budget: number; cost_per_structure: number };
  total_demand: number;
  covered_demand: number;
  coverage_pct: number;
  infeasible: boolean | null;
  structures: StructureZone[];
}

/**
 * GET /api/artifacts/{id}/structure_zones — the ranked placement output in WGS84.
 * Honest 404 (never fabricated) when a run has no structure_zones yet.
 */
export async function getStructureZones(
  projectId: string,
): Promise<StructureZonesArtifact> {
  return _fetch<StructureZonesArtifact>(
    `${API_BASE}/artifacts/${projectId}/structure_zones`,
  );
}

// ---------------------------------------------------------------------------
// Terminal artifact shapes (Plan 07-02 endpoints) — consumed by the Dashboard.
// Shapes match the persisted JSON in projects/primavera-demo/, verified 2026-06-15.
// ---------------------------------------------------------------------------

/** GET /api/artifacts/{id}/material_selection (material_selection.json). */
export interface MaterialSelectionArtifact {
  schema_version: string;
  selected_id: string;
  is_membrane: boolean;
  transport_carbon_kgco2e: number;
  cost_total_eur: number;
  solar_transmissivity: number;
  selection_basis: string;
  cooling_correction_factor: number;
  mass_balance: {
    label: string;
    scaffold_kg_rented: number;
    membrane_m2_recovered: number;
    fixings_kg_new: number;
  };
  next_life: {
    status: string;
    receiver: string;
    return_mass_kg: number;
  };
  tent_comparison: {
    label: string;
    baseline_kgco2e_per_m2: number;
    source: string;
  };
  infeasible: boolean;
}

/** Comfort-Gap €/°C figure — a labelled placeholder when cost is 0 (D-08, never a misleading 0). */
export interface EurPerDegC {
  value_eur_per_c: number | null;
  placeholder: boolean;
  cost_total_eur?: number;
  provenance?: string;
  note?: string;
}

export interface BaselineConditions {
  site: string;
  latlon: [number, number];
  date: string;
  peak_band: string;
  baseline_mean_c: number;
  coverage_basis?: string;
  sky_albedo?: string;
}

export interface AcceptanceMeta {
  comfort_gap_pct?: number;
  eur_per_deg_c?: EurPerDegC;
  baseline_conditions?: BaselineConditions;
  predicted_vs_measured?: {
    predicted_utci_delta_c: number;
    measured_utci_delta_c: number | null;
    monitoring_protocol: string;
  };
  provenance_labels?: Record<string, string>;
}

/** GET /api/artifacts/{id}/acceptance (acceptance.json verbatim + meta sidecar). */
export interface AcceptanceArtifact {
  schema_version: string;
  coverage_pct: number;
  utci_delta_c: number;
  X_c: number;
  Y_pct: number;
  /** PASS or FAIL — served verbatim from the gate; a FAIL is shown honestly (D-11). */
  verdict: "PASS" | "FAIL";
  baseline_ref: string;
  meta?: AcceptanceMeta;
}

/** GET /api/artifacts/{id}/bom (gh_meta.json projection). */
export interface BomArtifact {
  bom: { pillars: number; membrane_m2: number };
  egress: { clearance_width_m: number; flow_vector_count?: number };
  certification_needs: string[];
  shadow_coverage_pct: number;
}

/** GET /api/artifacts/{id}/footprint — endpoint projects UTM31N → WGS84 (A3). */
export interface FootprintArtifact {
  crs: { epsg: number };
  polygons: { lon: number; lat: number }[][];
}

/**
 * GET /api/artifacts/{id}/render — Phase 6 render record.
 * Three states: `done` (real render_url), `pending_live` (ControlNet conditioning map
 * ready via controlnet_input_url, live FLUX.1 render awaits a fal.ai key), or `pending`
 * (no geometry yet). A render_url is NEVER fabricated.
 */
export interface RenderArtifact {
  render_url: string | null;
  status: string;
  phase?: number;
  note?: string;
  schema_version?: string;
  model?: string | null;
  conditioning_scale?: number | null;
  controlnet_input_url?: string | null;
}

/** GET /api/artifacts/{id}/provenance — merged per-stage ledgers. */
export interface ProvenanceArtifact {
  schema_version: string;
  entries: {
    key: string;
    value?: unknown;
    tier: "GROUNDED" | "DERIVED" | "ASSUMED" | "INVENTED";
    source?: string;
    stage?: string;
    unit?: string;
    formula?: string;
  }[];
}

const API_BASE = "/api";

async function _fetch<T>(url: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(url, init);
  if (!resp.ok) {
    const body = await resp.text().catch(() => "(no body)");
    throw new Error(`API ${resp.status} from ${url}: ${body}`);
  }
  return resp.json() as Promise<T>;
}

/**
 * POST /api/run/{projectId} — start the climate + crowd pipeline.
 * Returns immediately; poll getStatus() for progress.
 */
export async function startRun(projectId: string): Promise<RunResponse> {
  return _fetch<RunResponse>(`${API_BASE}/run/${projectId}`, { method: "POST" });
}

/**
 * POST /api/run/{projectId} WITH a full-run brief body — triggers the complete
 * six-stage pipeline (climate → crowd → greedy → geometry → material → acceptance,
 * Plan 07-02 `_do_full_run`). The body is the A2 direct passthrough (capacity/
 * budget/date/theme + optional drawn boundary/zones); the backend re-validates
 * project_id and extracts the boundary outer ring — the client never sends a path.
 * Returns immediately; poll getStatus() (6 keys) for progress.
 */
export async function startFullRun(
  projectId: string,
  body: FullRunBody,
): Promise<RunResponse> {
  return _fetch<RunResponse>(`${API_BASE}/run/${projectId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

/**
 * GET /api/status/{projectId} — poll stage completion states.
 * utci_grid flips to "done" fast (cache hit); crowd_grid takes minutes.
 * Stage progress comes ONLY from these polled states — never from elapsed
 * time (CCA-F P1/P2).
 */
export async function getStatus(projectId: string): Promise<StatusResponse> {
  return _fetch<StatusResponse>(`${API_BASE}/status/${projectId}`);
}

/** A GeoJSON-ish feature from the committed Primavera site schema. */
export interface SchemaFeature {
  type: "Feature";
  properties: { name?: string; class?: string; kind?: string };
  geometry: { type: string; coordinates: unknown };
}
export interface FestivalSchema {
  boundary: { type: string; features?: unknown[] } | Record<string, unknown>;
  features: SchemaFeature[];
  source: string;
  schema_version: string;
}

/**
 * GET /api/site/festival-schema — the committed Primavera site schema (19 stages +
 * 2 entrances + amenities) the crowd sim flows agents across. The workspace 'Load
 * Primavera preset' renders this as the on-map layout so it matches the sim 1:1.
 */
export async function getFestivalSchema(): Promise<FestivalSchema> {
  return _fetch<FestivalSchema>(`${API_BASE}/site/festival-schema`);
}

/**
 * GET /api/artifacts/{projectId}/heat — WGS84 heat cells from demo_heat.json.
 * Returns the full artifact: honesty label, UTCI scale bounds, and 9,536
 * { lon, lat, utci_c } cells for the Primavera site.
 */
export async function getHeatArtifact(projectId: string): Promise<HeatArtifact> {
  return _fetch<HeatArtifact>(`${API_BASE}/artifacts/${projectId}/heat`);
}

/**
 * GET /api/artifacts/{projectId}/crowd — WGS84 crowd grid
 * (density cells + dwell-zone polygons + flow vectors).
 */
export async function getCrowdArtifact(projectId: string): Promise<CrowdArtifact> {
  return _fetch<CrowdArtifact>(`${API_BASE}/artifacts/${projectId}/crowd`);
}

/**
 * GET /api/artifacts/{projectId}/trajectories — 11.8 MB agent trajectory file.
 * Fetch ONCE and store in a ref — do NOT call on every render (Pitfall: re-fetching).
 * 701 frames × 650 agents × [lon, lat, speed].
 */
export async function getTrajectories(
  projectId: string,
): Promise<TrajectoriesArtifact> {
  return _fetch<TrajectoriesArtifact>(
    `${API_BASE}/artifacts/${projectId}/trajectories`,
  );
}

// ---------------------------------------------------------------------------
// Terminal artifact fetchers (Plan 07-02 endpoints) — the Dashboard reads these
// REAL persisted artifacts, never heatguard-mock numbers (Pitfall 6).
// ---------------------------------------------------------------------------

/** GET /api/artifacts/{id}/material_selection — selected membrane + carbon/cost/recovery. */
export async function getMaterialSelection(
  projectId: string,
): Promise<MaterialSelectionArtifact> {
  return _fetch<MaterialSelectionArtifact>(
    `${API_BASE}/artifacts/${projectId}/material_selection`,
  );
}

/** GET /api/artifacts/{id}/acceptance — verdict (verbatim) + Comfort-Gap meta sidecar (D-08/D-11). */
export async function getAcceptance(
  projectId: string,
): Promise<AcceptanceArtifact> {
  return _fetch<AcceptanceArtifact>(
    `${API_BASE}/artifacts/${projectId}/acceptance`,
  );
}

/** GET /api/artifacts/{id}/bom — pillars, membrane m², egress, certification needs. */
export async function getBom(projectId: string): Promise<BomArtifact> {
  return _fetch<BomArtifact>(`${API_BASE}/artifacts/${projectId}/bom`);
}

/**
 * URL for GET /api/artifacts/{id}/geometry — binary GLB consumed by drei useGLTF.
 * NOT routed through _fetch (which calls resp.json() and would choke on the binary);
 * useGLTF does its own binary fetch and just needs the URL string. Mirrors the
 * RenderArtifact.controlnet_input_url precedent (a URL string to a binary endpoint).
 */
export function getGeometryUrl(projectId: string): string {
  return `${API_BASE}/artifacts/${projectId}/geometry`;
}

/** GET /api/artifacts/{id}/footprint — shade footprint projected to WGS84 (A3). */
export async function getFootprintWgs84(
  projectId: string,
): Promise<FootprintArtifact> {
  return _fetch<FootprintArtifact>(
    `${API_BASE}/artifacts/${projectId}/footprint`,
  );
}

/** GET /api/artifacts/{id}/render — labelled STUB (render_url null) until Phase 6 (D-03). */
export async function getRender(projectId: string): Promise<RenderArtifact> {
  return _fetch<RenderArtifact>(`${API_BASE}/artifacts/${projectId}/render`);
}

/** GET /api/artifacts/{id}/provenance — merged per-stage ledger for the tag lookup (D-07). */
export async function getProvenance(
  projectId: string,
): Promise<ProvenanceArtifact> {
  return _fetch<ProvenanceArtifact>(
    `${API_BASE}/artifacts/${projectId}/provenance`,
  );
}
