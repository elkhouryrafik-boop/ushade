/**
 * RED spec — Plan 07-03 turns this GREEN.
 *
 * latLngToSvg / cellSizeSvg are currently typed to `google.maps.LatLngBounds`
 * (see geo-transform.ts). Phase 7 migrates the map to Mapbox GL, whose bounds
 * object (`mapboxgl.LngLatBounds`) exposes getNorth()/getSouth()/getEast()/
 * getWest() — NOT getNorthEast()/getSouthWest(). Plan 03 re-types the function
 * to consume the Mapbox-shaped bounds. Until then this FAILS at the call site
 * because the fake Mapbox bounds has no getNorthEast/getSouthWest getters.
 *
 * Load-bearing: the <2 m alignment invariant (07 Pitfall 7) — the NE corner of
 * the site must land at SVG [100, 0] and the SW corner at [0, 60], with a mid
 * point at the bilinear midpoint.
 */
import { describe, it, expect } from "vitest";
import { latLngToSvg, cellSizeSvg } from "../geo-transform";

// Parc del Fòrum bounding corners (WGS84). NE = top-right, SW = bottom-left.
const NE = { lat: 41.4145, lng: 2.232 };
const SW = { lat: 41.407, lng: 2.222 };

/**
 * A FAKE Mapbox-shaped LngLatBounds: property-free getters getNorth/South/East/West.
 * This is the shape Plan 03 re-types latLngToSvg to accept. The current
 * google.maps-typed implementation calls getNorthEast()/getSouthWest() on this
 * object — which do not exist — so every assertion below FAILS today (RED).
 */
const mapboxBounds = {
  getNorth: () => NE.lat,
  getSouth: () => SW.lat,
  getEast: () => NE.lng,
  getWest: () => SW.lng,
};

describe("latLngToSvg — Mapbox-bounds alignment", () => {
  it("maps the NE corner to SVG top-right [100, 0]", () => {
    const [x, y] = latLngToSvg(NE.lng, NE.lat, mapboxBounds as never);
    expect(x).toBeCloseTo(100, 2);
    expect(y).toBeCloseTo(0, 2);
  });

  it("maps the SW corner to SVG bottom-left [0, 60]", () => {
    const [x, y] = latLngToSvg(SW.lng, SW.lat, mapboxBounds as never);
    expect(x).toBeCloseTo(0, 2);
    expect(y).toBeCloseTo(60, 2);
  });

  it("maps the geometric mid point to the bilinear SVG midpoint [50, 30]", () => {
    const midLng = (NE.lng + SW.lng) / 2;
    const midLat = (NE.lat + SW.lat) / 2;
    const [x, y] = latLngToSvg(midLng, midLat, mapboxBounds as never);
    expect(x).toBeCloseTo(50, 2);
    expect(y).toBeCloseTo(30, 2);
  });
});

describe("cellSizeSvg — 6 m UTCI cell footprint", () => {
  it("returns a positive [width, height] in SVG units for a 6 m cell", () => {
    const [w, h] = cellSizeSvg(6.0, mapboxBounds as never);
    expect(w).toBeGreaterThan(0);
    expect(h).toBeGreaterThan(0);
    // 6 m over a ~800 m site is a small fraction of the 100×60 viewBox.
    expect(w).toBeLessThan(5);
    expect(h).toBeLessThan(5);
  });
});
