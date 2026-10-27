/**
 * RED spec — Plan 07-03 (Workspace / Draw → store) turns this GREEN.
 *
 * FE-01: a Mapbox-GL-Draw GeoJSON Polygon Feature must convert into a store
 * `Shape` ({ id, kind: ShapeKind, points: [number,number][] }). The mapper
 * `shapeFromDrawFeature` does not exist yet (../draw-adapter is unwritten), so
 * the import FAILS at collection-resolution → RED.
 */
import { describe, it, expect } from "vitest";
import type { Feature } from "geojson";
import { shapeFromDrawFeature } from "../draw-adapter";
import { SHAPE_META, type Shape, type ShapeKind } from "../heatguard-store";

// A minimal Mapbox-GL-Draw Polygon feature as emitted by draw.create / draw.getAll().
const drawFeature: Feature = {
  id: "mapbox-draw-abc123",
  type: "Feature",
  properties: { kind: "boundary" },
  geometry: {
    type: "Polygon",
    coordinates: [
      [
        [2.222, 41.407],
        [2.232, 41.407],
        [2.232, 41.4145],
        [2.222, 41.4145],
        [2.222, 41.407],
      ],
    ],
  },
};

describe("shapeFromDrawFeature — GeoJSON Draw feature → store Shape (FE-01)", () => {
  it("produces a Shape with a valid ShapeKind and numeric points", () => {
    const shape: Shape = shapeFromDrawFeature(drawFeature);

    expect(typeof shape.id).toBe("string");
    expect(shape.id.length).toBeGreaterThan(0);

    // kind must be one of the frozen ShapeKinds (keys of SHAPE_META).
    const validKinds = Object.keys(SHAPE_META) as ShapeKind[];
    expect(validKinds).toContain(shape.kind);
    expect(shape.kind).toBe("boundary");

    // points are [number, number][] — no NaN, every entry a length-2 numeric pair.
    expect(Array.isArray(shape.points)).toBe(true);
    expect(shape.points.length).toBeGreaterThanOrEqual(3);
    for (const pt of shape.points) {
      expect(pt).toHaveLength(2);
      expect(typeof pt[0]).toBe("number");
      expect(typeof pt[1]).toBe("number");
      expect(Number.isNaN(pt[0])).toBe(false);
      expect(Number.isNaN(pt[1])).toBe(false);
    }
  });
});
