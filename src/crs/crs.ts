/**
 * Canonical CRS constant — Node side of the single coordinate-reference boundary
 * (CONTRACT-01).
 *
 * HeatGuard carries ONE projected CRS everywhere downstream of ingestion:
 * UTM 31N / EPSG:32631, units metre. The heavy lat/lon <-> metre transform lives
 * in the Python microservice (`src/crs/crs.py`, pyproj-backed) per the
 * Architectural Responsibility Map — the Node orchestrator only needs the
 * constant to STAMP and VALIDATE coordinates at the HTTP seam (e.g. reject an
 * artifact whose `crs.epsg` is not 32631 before forwarding it).
 *
 * This file deliberately contains no projection math and no ETRS89 zone-31 EPSG
 * reference — the trap NatureGooddest mixes in is not inherited (see REUSE.md).
 */

/** UTM zone 31N — the canonical projected CRS for every HeatGuard spatial artifact. */
export const EPSG = 32631 as const;

/** Canonical linear unit. Every `*_m` field is metres in EPSG:32631. */
export const UNITS = "metre" as const;

/**
 * True iff `epsg` is the canonical CRS (32631). Used at the HTTP seam to reject
 * any artifact that arrives in a non-canonical CRS (fail-closed at the boundary).
 */
export function isCanonicalCrs(epsg: number): boolean {
  return epsg === EPSG;
}
