/**
 * GEOM-03 — deterministic IN_SunVector from the brief date + Parc del Fòrum site.
 *
 * Pure + network-free: suncalc is a tiny offline ephemeris (no I/O), so a top-level
 * import is fine (unlike axios / child_process in client.ts, which are lazy).
 *
 * The vector is a 3D UNIT vector (gh_request `x-units: { IN_SunVector: "unit-vector" }`),
 * computed at the peak-sun hour over the fixed venue centroid — so a fixed `briefDate`
 * yields a byte-identical tuple every call (determinism = the GEOM-03 gate).
 *
 * Constants mirror `src/geom/constants.py` (the ONE source of truth); the Python module
 * stays canonical and these are tagged with a back-reference + provenance tier.
 *
 * Source: github.com/mourner/suncalc — getPosition(date, lat, lon) -> { altitude, azimuth }
 * in radians; azimuth measured from SOUTH, clockwise toward west.
 */

import SunCalc from "suncalc";

// [ASSUMED A1] mirrors src/geom/constants.py PEAK_SUN_HOUR (= midpoint of the climate
// PEAK_HEAT_HOUR_BAND (12, 16)); so the geometry's solar assumption matches the heat grid.
const PEAK_SUN_HOUR = 14;

// [ASSUMED A3] mirrors src/geom/constants.py PARC_DEL_FORUM_LATLON — the Phase-2a fixed-site
// centroid (lat, lon, WGS84); anchors the sun-position math to the venue the climate grid used.
const PARC_DEL_FORUM = { lat: 41.4106, lon: 2.227 };

/**
 * Deterministic solar direction (FROM the ground TO the sun) at the peak-sun hour for the
 * given brief date over Parc del Fòrum. Returns a length-3 UNIT vector [x=east, y=north, z=up],
 * matching the canonical Python `geom.request.sun_vector` for the same date.
 */
export function sunVector(briefDate: string): [number, number, number] {
  const d = new Date(
    `${briefDate.slice(0, 10)}T${String(PEAK_SUN_HOUR).padStart(2, "0")}:00:00Z`,
  );
  const { altitude, azimuth } = SunCalc.getPosition(
    d,
    PARC_DEL_FORUM.lat,
    PARC_DEL_FORUM.lon,
  );
  // MJ-03: SunCalc's azimuth is measured FROM SOUTH clockwise toward west, so the ground->sun
  // horizontal direction is east = -cosα·sin(az), north = -cosα·cos(az). The east component must
  // be negated; the old `+cosα·sin(az)` mirrored the vector east<->west (an afternoon SW sun was
  // reported in the SE), diverging from the canonical Python vector that feeds a live solve.
  const x = -Math.cos(altitude) * Math.sin(azimuth); // east
  const y = -Math.cos(altitude) * Math.cos(azimuth); // north
  const z = Math.sin(altitude); // up — ground->sun, matches Python
  // ||v||² = cos²α·(sin²az + cos²az) + sin²α = cos²α + sin²α = 1 → unit vector by construction.
  return [x, y, z];
}
