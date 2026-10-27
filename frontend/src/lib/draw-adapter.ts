/**
 * Mapbox-GL-Draw GeoJSON ↔ HeatGuard store-Shape adapter (FE-01, D-01).
 *
 * The Phase-7 map migration (Plan 03) replaces the hand-rolled SVG click-capture
 * drawing with `@mapbox/mapbox-gl-draw`, which emits standard GeoJSON Polygon/Point
 * Features on its `draw.create` / `draw.update` events. This module converts those
 * features into the store's `Shape` model ({ id, kind, points }) so the existing SVG
 * overlay layer renders committed shapes unchanged, and reports the drawn-boundary
 * area in m² via `@turf/area` (the spec-pure replacement for the retired Maps
 * spherical-geometry area call).
 *
 * Coordinate spaces:
 *  - GeoJSON coordinates are WGS84 [lon, lat].
 *  - The store `Shape.points` are the 0..100×60 SVG viewBox frac space the overlays
 *    render in (heatguard-store.tsx). When a live `MapBounds` is supplied we project
 *    each ring vertex through `latLngToSvg`; without bounds (e.g. the unit test) the
 *    raw [lon, lat] pair is preserved — still a valid `[number, number]`.
 */
import area from "@turf/area";
import type { Feature, Polygon, Point, Position } from "geojson";
import { latLngToSvg, type MapBounds } from "./geo-transform";
import { SHAPE_META, type Shape, type ShapeKind } from "./heatguard-store";

/** The frozen ShapeKind set — keys of SHAPE_META (boundary/stage/restroom/…). */
const VALID_KINDS = new Set<ShapeKind>(
  Object.keys(SHAPE_META) as ShapeKind[],
);

/**
 * Resolve a feature's `properties.kind` to a valid ShapeKind. Anything missing or
 * not in the frozen set defaults to "boundary" (never throws — the boundary is the
 * load-bearing multi-festival input, D-04).
 */
export function resolveKind(raw: unknown): ShapeKind {
  return typeof raw === "string" && VALID_KINDS.has(raw as ShapeKind)
    ? (raw as ShapeKind)
    : "boundary";
}

/** Extract the ring/point vertices of a Draw feature as raw [lon, lat] positions. */
function featurePositions(feature: Feature): Position[] {
  const g = feature.geometry;
  if (!g) return [];
  if (g.type === "Polygon") {
    // Outer ring; drop the GeoJSON closing vertex (duplicate of the first).
    const ring = (g as Polygon).coordinates[0] ?? [];
    if (
      ring.length > 1 &&
      ring[0][0] === ring[ring.length - 1][0] &&
      ring[0][1] === ring[ring.length - 1][1]
    ) {
      return ring.slice(0, -1);
    }
    return ring;
  }
  if (g.type === "Point") {
    return [(g as Point).coordinates];
  }
  return [];
}

/**
 * Convert a Mapbox-GL-Draw GeoJSON Feature into a store `Shape` (FE-01).
 *
 * @param feature - the GeoJSON Feature from draw.create / draw.getAll().
 * @param bounds  - optional live map bounds; when supplied, vertices are projected
 *                  into the 0..100×60 SVG frac space the overlays render in. When
 *                  omitted, raw [lon, lat] pairs are kept (still numeric, non-NaN).
 */
export function shapeFromDrawFeature(
  feature: Feature,
  bounds?: MapBounds | null,
): Shape {
  const kind = resolveKind(feature.properties?.kind);
  const positions = featurePositions(feature);
  const points: [number, number][] = positions.map(([lon, lat]) =>
    bounds ? latLngToSvg(lon, lat, bounds) : [lon, lat],
  );
  const id =
    (typeof feature.id === "string" && feature.id.length > 0
      ? feature.id
      : crypto.randomUUID());
  return { id, kind, points };
}

/** Alias kept for the plan-prose name; identical to shapeFromDrawFeature. */
export const geoJsonToShape = shapeFromDrawFeature;

/**
 * Real-world area of a drawn boundary in m², via @turf/area (the spec-pure
 * replacement for the retired Maps spherical-geometry area call).
 * Non-polygon features → 0.
 */
export function computeAreaM2(feature: Feature): number {
  if (feature.geometry?.type !== "Polygon") return 0;
  return Math.round(area(feature));
}

/**
 * True when a Shape's points are raw WGS84 [lon, lat] (i.e. drawn with no live
 * bounds projection) rather than the 0..100×60 SVG frac space. Used by the
 * full-run assembler so a faithful boundary GeoJSON is only sent when the
 * coordinates are real geography — never fabricated SVG-space numbers (T-07-10).
 *
 * Heuristic: SVG points live in x∈[0,100], y∈[0,60]; Parc del Fòrum lon/lat are
 * ≈ (2.22, 41.41). A point whose |lat| > 60 (the SVG y-ceiling) is unambiguously
 * geographic. We treat a Shape as geographic only when EVERY vertex lies outside
 * the SVG box, so the SVG-space preset placeholders never round-trip as a site.
 */
export function isGeographicShape(shape: Shape): boolean {
  if (shape.points.length === 0) return false;
  return shape.points.every(
    ([x, y]) => x < 0 || x > 100 || y < 0 || y > 60,
  );
}

/**
 * Convert a store `Shape` back to a GeoJSON Feature with WGS84 coordinates
 * (the inverse of shapeFromDrawFeature's no-bounds path). The Shape.points are
 * treated as raw [lon, lat]; callers MUST gate on isGeographicShape so SVG-space
 * shapes are never emitted as geography. A single-vertex shape → Point; otherwise
 * a closed Polygon ring. The `kind` is carried in properties for the backend.
 */
export function shapeToGeoJson(shape: Shape): Feature {
  if (shape.points.length === 1) {
    return {
      type: "Feature",
      id: shape.id,
      properties: { kind: shape.kind },
      geometry: { type: "Point", coordinates: shape.points[0] },
    };
  }
  const ring: Position[] = shape.points.map(([lon, lat]) => [lon, lat]);
  // Close the ring (GeoJSON Polygon rings repeat the first vertex last).
  if (ring.length > 0) {
    const [fx, fy] = ring[0];
    const [lx, ly] = ring[ring.length - 1];
    if (fx !== lx || fy !== ly) ring.push([fx, fy]);
  }
  return {
    type: "Feature",
    id: shape.id,
    properties: { kind: shape.kind },
    geometry: { type: "Polygon", coordinates: [ring] },
  };
}
