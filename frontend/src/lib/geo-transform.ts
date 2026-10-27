/**
 * WGS84 ↔ SVG coordinate transform for the 0–100×60 MapCanvas viewBox.
 *
 * MapCanvas.tsx already implements the forward transform `svgToLatLngs` which converts
 * SVG [x, y] back to {lat, lng}. This module implements the inverse — the projection
 * step that takes WGS84 artifact coordinates (lon, lat) from the FastAPI backend and
 * maps them into the 0–100×60 SVG space so HeatmapOverlay / FlowOverlay / AgentAnimation
 * can render as SVG elements directly inside the existing MapCanvas overlay system.
 *
 * Accuracy: linear bilinear interpolation over the Mapbox LngLatBounds. At zoom 16–17
 * over the ~800 m Parc del Fòrum site, error < 2 m (< 1/3 of the 6 m cell size).
 * This is the same accuracy class as MapCanvas.tsx's existing svgToLatLngs.
 *
 * Phase 7 (D-01/FE-01): re-typed from `google.maps.LatLngBounds` to a structural
 * `MapBounds` shape matching `mapboxgl.LngLatBounds` — the four numeric getters
 * getNorth()/getSouth()/getEast()/getWest(). The arithmetic is IDENTICAL; only the
 * getters changed (Pitfall 7: a wrong port silently shifts the grid). The real
 * `mapboxgl.LngLatBounds` satisfies this interface structurally, so callers may pass
 * `map.getBounds()` directly with no adapter.
 *
 * Phase 7 reuse: the same latLngToSvg transform will project shade-footprint polygons
 * and the structural geometry overlay. No rework needed.
 */

/** SVG coordinate: x ∈ [0, 100], y ∈ [0, 60] */
export type SvgPt = [number, number];

/**
 * Structural subset of `mapboxgl.LngLatBounds`: the four numeric corner getters.
 * Mapbox's `LngLatBounds` (and the fake bounds in geo-transform.test.ts) both
 * satisfy this, so no `mapbox-gl` import is needed here (keeps the module test-
 * friendly and free of the client-only mapbox-gl side effects — Pitfall 8).
 */
export type MapBounds = {
  getNorth(): number;
  getSouth(): number;
  getEast(): number;
  getWest(): number;
};

/**
 * Project a WGS84 (lon, lat) point into the 0–100×60 SVG viewBox.
 *
 * Inverse of MapCanvas.tsx `svgToLatLngs`:
 *   svgToLatLngs: ([x, y]) → { lat: ne.lat - (y/60)*(ne.lat-sw.lat), lng: sw.lng + (x/100)*(ne.lng-sw.lng) }
 *   latLngToSvg:  (lon, lat) → [ (lon-sw.lng)/(ne.lng-sw.lng)*100, (ne.lat-lat)/(ne.lat-sw.lat)*60 ]
 *
 * @param lon - WGS84 longitude (decimal degrees)
 * @param lat - WGS84 latitude (decimal degrees)
 * @param bounds - live mapboxgl.LngLatBounds from MapboxBackground onMoveEnd (map.getBounds())
 * @returns [x, y] in SVG viewBox units (clipped to 3 decimal places)
 */
export function latLngToSvg(
  lon: number,
  lat: number,
  bounds: MapBounds,
): SvgPt {
  const north = bounds.getNorth();
  const south = bounds.getSouth();
  const east = bounds.getEast();
  const west = bounds.getWest();
  const x = ((lon - west) / (east - west)) * 100;
  const y = ((north - lat) / (north - south)) * 60;
  return [+x.toFixed(3), +y.toFixed(3)];
}

/**
 * Compute the SVG dimensions of a square cell of `cellSizeM` metres.
 *
 * Used by HeatmapOverlay to set the `width` and `height` of each SVG `<rect>`.
 * Approximation: 1 degree latitude ≈ 111,320 m; longitude span corrected by cos(lat).
 *
 * @param cellSizeM - cell side length in metres (6.0 m for the UTCI master lattice)
 * @param bounds - live mapboxgl.LngLatBounds
 * @returns [svgWidth, svgHeight] in SVG viewBox units
 */
export function cellSizeSvg(
  cellSizeM: number,
  bounds: MapBounds,
): SvgPt {
  const north = bounds.getNorth();
  const south = bounds.getSouth();
  const east = bounds.getEast();
  const west = bounds.getWest();
  // ~111,320 m per degree latitude
  const latSpanM = (north - south) * 111320;
  // Longitude span in metres: corrected by cos(midLat) for Mercator accuracy
  const midLat = (north + south) / 2;
  const lngSpanM =
    (east - west) * 111320 * Math.cos((midLat * Math.PI) / 180);
  return [
    +((cellSizeM / lngSpanM) * 100).toFixed(4),
    +((cellSizeM / latSpanM) * 60).toFixed(4),
  ];
}
