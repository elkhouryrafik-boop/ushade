/**
 * Dossier export helpers (EXPORT-01, D-12) — the CSV builder + the static map
 * URL the @react-pdf DossierDocument consumes.
 *
 * The CSV IS the flattened provenance ledger — one row per ledger entry carrying
 * its full provenance columns (key, value, unit, tier, source, stage). It doubles
 * as the open-data campaign dataset donated to the municipality (INSTRUCTOR §Phase 7).
 *
 * Honesty / security (T-07-18 / T-07-21):
 * - The CSV contains the ledger ONLY — never an env var, token, or internal path.
 * - The Mapbox Static Images token is read from import.meta.env at call time and
 *   lives in the request URL only — never inlined as a `pk.` literal, never written
 *   into the CSV/PDF text body.
 */

import type { LedgerEntry } from "./provenance";

/** The locked CSV columns — the open-data dataset schema (key,value,unit,tier,source,stage). */
export const CSV_COLUMNS = [
  "key",
  "value",
  "unit",
  "tier",
  "source",
  "stage",
] as const;

export type CsvColumn = (typeof CSV_COLUMNS)[number];

/** A single flattened CSV row — one per ledger entry, every provenance column present. */
export type CsvRow = Record<CsvColumn, string>;

/** Stringify a ledger value for the CSV without losing it. Objects are JSON-encoded. */
function stringifyValue(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/**
 * Flatten the per-run provenance ledger into one CSV row per entry. Row count ===
 * entry count — no entry is ever silently dropped (every number stays auditable,
 * D-12). Every row carries all six provenance columns; a missing optional field
 * becomes "" rather than disappearing.
 */
export function buildCsvRows(entries: LedgerEntry[]): CsvRow[] {
  return (entries ?? []).map((e) => ({
    key: stringifyValue(e?.key),
    value: stringifyValue(e?.value),
    unit: stringifyValue(e?.unit),
    tier: stringifyValue(e?.tier),
    source: stringifyValue(e?.source),
    stage: stringifyValue(e?.stage),
  }));
}

/** RFC-4180 escape: quote fields containing a comma, quote, CR, or LF; double inner quotes. */
function escapeCsvField(field: string): string {
  if (/[",\r\n]/.test(field)) {
    return `"${field.replace(/"/g, '""')}"`;
  }
  return field;
}

/** Serialize the rows to RFC-4180 CSV text: a header row + one row per ledger entry. */
export function serializeCsv(entries: LedgerEntry[]): string {
  const header = CSV_COLUMNS.join(",");
  const rows = buildCsvRows(entries).map((row) =>
    CSV_COLUMNS.map((col) => escapeCsvField(row[col])).join(","),
  );
  return [header, ...rows].join("\n");
}

/**
 * Build a text/csv Blob of the flattened ledger (header row + escaped fields) —
 * the open-data campaign dataset that downloads alongside the PDF.
 */
export function buildCsvBlob(entries: LedgerEntry[]): Blob {
  return new Blob([serializeCsv(entries)], { type: "text/csv;charset=utf-8" });
}

export interface LonLatPoint {
  lon: number;
  lat: number;
}

/** A WGS84 footprint as an array of polygons, each a ring of {lon,lat} vertices. */
export type FootprintWgs84 = LonLatPoint[][];

/** Round a coordinate to 5 decimals (~1 m) to keep the static-map URL short. */
function round5(n: number): number {
  return Math.round(n * 1e5) / 1e5;
}

/**
 * Encode the footprint polygons as a GeoJSON FeatureCollection of Polygons for the
 * Mapbox Static Images `geojson(...)` path overlay (the shade footprint baked into
 * the PNG — A5, preferred over canvas.toDataURL which misses the SVG overlay).
 */
function footprintToGeoJson(footprint: FootprintWgs84): string {
  const features = (footprint ?? [])
    .filter((ring) => ring && ring.length >= 3)
    .map((ring) => ({
      type: "Feature" as const,
      properties: {
        "fill-opacity": 0.4,
        fill: "#06b6d4",
        stroke: "#06b6d4",
        "stroke-width": 2,
      },
      geometry: {
        type: "Polygon" as const,
        coordinates: [ring.map((p) => [round5(p.lon), round5(p.lat)])],
      },
    }));
  return JSON.stringify({ type: "FeatureCollection", features });
}

/**
 * Build a Mapbox Static Images API URL with the shade footprint baked in as a
 * geojson() overlay. The access_token comes from import.meta.env.VITE_MAPBOX_TOKEN
 * — NEVER a `pk.` literal (T-07-21). Returns `null` when no token is configured so
 * the PDF omits the map image gracefully rather than embedding a broken/secretless
 * request.
 */
export function mapSnapshotUrl(
  footprintWgs84: FootprintWgs84,
  center: LonLatPoint,
  zoom: number,
  size: { width: number; height: number } = { width: 600, height: 400 },
): string | null {
  const token = import.meta.env?.VITE_MAPBOX_TOKEN as string | undefined;
  if (!token) return null;

  const style = "mapbox/satellite-streets-v12";
  const overlay = `geojson(${encodeURIComponent(footprintToGeoJson(footprintWgs84))})`;
  const lon = round5(center.lon);
  const lat = round5(center.lat);
  const dims = `${size.width}x${size.height}`;
  const base = `https://api.mapbox.com/styles/v1/${style}/static`;
  const tokenQ = `?access_token=${encodeURIComponent(token)}`;

  const withOverlay = `${base}/${overlay}/${lon},${lat},${zoom}/${dims}${tokenQ}`;
  // The Mapbox Static Images API rejects URLs beyond ~8192 chars; a detailed
  // footprint baked in as a geojson() overlay easily blows that (the demo
  // footprint alone is ~22k chars) → the request fails (surfacing as a CORS /
  // ERR_FAILED console error) and the PDF map breaks. When the overlay URL is too
  // long, fall back to the plain satellite snapshot (no overlay) so the dossier
  // still carries a real site image instead of a broken/erroring request.
  if (withOverlay.length <= 8000) return withOverlay;
  return `${base}/${lon},${lat},${zoom}/${dims}${tokenQ}`;
}

/** Compute the centroid of the first non-empty footprint ring (the map center). */
export function footprintCenter(
  footprint: FootprintWgs84,
): LonLatPoint | null {
  const ring = (footprint ?? []).find((r) => r && r.length > 0);
  if (!ring) return null;
  const sum = ring.reduce(
    (acc, p) => ({ lon: acc.lon + p.lon, lat: acc.lat + p.lat }),
    { lon: 0, lat: 0 },
  );
  return { lon: sum.lon / ring.length, lat: sum.lat / ring.length };
}
