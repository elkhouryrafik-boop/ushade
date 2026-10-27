/**
 * One-click "Load Parc del Fòrum" — the demo-site shortcut (owner directive 2026-06-25).
 *
 * The architect shouldn't have to trace the Fòrum by hand to see the product. This pulls
 * the REAL committed boundary (viz/data/boundary_2026.geojson, served via
 * GET /api/site/festival-schema) and drops it in as the project's editable site geometry
 * — area computed from @turf/area, exactly as a hand-drawn boundary would be.
 *
 * The festival points of interest (stages, entrances, WC, medical, water) already render
 * as a READ-ONLY map context layer (FestivalSchemaContext in the shell), so loading the
 * site makes the full Fòrum legible in one click without touching the layout shapes.
 *
 * Architecture note: a boundary held in the store renders via the deck.gl `site-boundary`
 * layer and is NOT re-hydrated into mapbox-gl-draw (see DrawControl) — same as a resumed
 * drawn boundary. It is visible, area-locked, and feeds the engine; redraw to replace it.
 */
import { useState } from "react";
import type { Feature, Polygon } from "geojson";
import { getFestivalSchema } from "./heatguard-api";
import { computeAreaM2 } from "./draw-adapter";
import { useHeatGuard, type Shape } from "./heatguard-store";
import { useMapCanvas } from "@/components/wizard/PersistentMapCanvas";

/** Stable id so re-loading replaces the Fòrum boundary instead of stacking copies. */
export const FORUM_BOUNDARY_ID = "forum-site-boundary";

/** Canonical Primavera-demo brief facts, mirrored from the welcome "Try Parc del Fòrum"
 *  door so the Brief shortcut prefills the same numbers. */
export const FORUM_BRIEF = {
  capacity: 70000,
  budget: 80000,
  date: "2025-06-01",
  theme: "Sun-bleached natural canopy, reclaimed timber and woven jute",
} as const;

/**
 * Pull the outer ring `[[lon,lat], …]` out of the schema's `boundary` payload. The
 * endpoint returns a FeatureCollection whose polygon carries TWO rings (outer + a hole);
 * the editable site geometry is the OUTER ring only.
 */
export function forumOuterRing(boundary: unknown): [number, number][] | null {
  const findPoly = (o: unknown): number[][][] | null => {
    if (!o || typeof o !== "object") return null;
    const node = o as Record<string, unknown>;
    if (node.type === "Polygon") return node.coordinates as number[][][];
    if (node.type === "MultiPolygon") return (node.coordinates as number[][][][])?.[0] ?? null;
    if (node.type === "Feature") return findPoly(node.geometry);
    if (node.type === "FeatureCollection") {
      for (const f of (node.features as unknown[]) ?? []) {
        const r = findPoly(f);
        if (r) return r;
      }
    }
    return null;
  };
  const rings = findPoly(boundary);
  const outer = rings?.[0];
  if (!outer || outer.length < 3) return null;
  const pts = outer.map((c) => [c[0], c[1]] as [number, number]);
  // GeoJSON rings repeat the first vertex to close; our Shape stores an open ring.
  if (pts.length > 3) {
    const [fx, fy] = pts[0];
    const [lx, ly] = pts[pts.length - 1];
    if (fx === lx && fy === ly) pts.pop();
  }
  return pts;
}

interface LoadOpts {
  /** Also prefill the four brief facts with the Primavera-demo values (Brief shortcut). */
  withBriefFacts?: boolean;
}

/**
 * Hook returning `{ load, loading, error }`. `load()` fetches the schema, sets the Fòrum
 * boundary as the project's site geometry (replacing any prior boundary, keeping amenity
 * shapes), locks the area, and gently frames the site on the live map.
 */
export function useForumSite() {
  const { state, dispatch } = useHeatGuard();
  const { mapRef } = useMapCanvas();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load(opts: LoadOpts = {}): Promise<boolean> {
    setLoading(true);
    setError(null);
    try {
      const schema = await getFestivalSchema();
      const ring = forumOuterRing(schema.boundary);
      if (!ring) throw new Error("No Parc del Fòrum boundary in the schema response");

      const closed: number[][] = [...ring, ring[0]];
      const areaM2 = computeAreaM2({
        type: "Feature",
        properties: {},
        geometry: { type: "Polygon", coordinates: [closed] },
      } as Feature<Polygon>);

      const boundary: Shape = {
        id: FORUM_BOUNDARY_ID,
        kind: "boundary",
        points: ring,
        geo: true,
        areaM2: areaM2 || undefined,
        label: "Parc del Fòrum",
      };

      // Replace any existing boundary; keep amenity/layout shapes the architect may hold.
      const kept = state.project.shapes.filter((s) => s.kind !== "boundary");
      dispatch({ type: "setShapes", shapes: [...kept, boundary] });
      dispatch({
        type: "setProject",
        patch: {
          siteAreaM2: areaM2 || 0,
          ...(opts.withBriefFacts ? FORUM_BRIEF : {}),
        },
      });

      // Frame the site so the loaded boundary lands in view (best-effort).
      const map = mapRef.current?.getMap?.();
      if (map) {
        const lons = ring.map((p) => p[0]);
        const lats = ring.map((p) => p[1]);
        map.fitBounds(
          [
            [Math.min(...lons), Math.min(...lats)],
            [Math.max(...lons), Math.max(...lats)],
          ],
          { padding: 72, duration: 800, maxZoom: 16 },
        );
      }
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't load the Parc del Fòrum site");
      return false;
    } finally {
      setLoading(false);
    }
  }

  return { load, loading, error };
}
