import { useCallback } from "react";
import { useHeatGuard } from "./heatguard-store";
import { startFullRun, type FullRunBody } from "./heatguard-api";

/** A custom (organizer-drawn) run id, vs the pre-baked "primavera-demo". */
export const CUSTOM_RUN_PREFIX = "custom-";
export const isCustomRun = (id: string | null): boolean =>
  !!id && id.startsWith(CUSTOM_RUN_PREFIX);

/**
 * useRunPipeline — wires "Create your own festival" to a REAL backend run on the
 * organizer's own drawn site (P7: site-general). runCustomSite():
 *   1. builds a boundary_geojson Feature from the drawn boundary shape,
 *   2. POSTs the full-run brief to a fresh project id (POST /api/run/{id}),
 *   3. enters the analysis stage; PlacementStage then polls GET /api/status/{id}
 *      and reveals each stage on REAL state (CCA-F P1/P2 — never a fake timer).
 *
 * The poll deliberately lives in PlacementStage, not here: this hook is called from
 * MaterialsStage, which unmounts the instant we navigate to Placement — a poll
 * started here would be torn down immediately. The Parc del Fòrum demo keeps its
 * instant pre-baked path (startRun "primavera-demo"). The live climate step is still
 * wired to the Fòrum site upstream (P7); a custom site is fully laid out while its
 * heat grid runs on the site we have, until infrared generalizes — we never hide that.
 */
export function useRunPipeline() {
  const { state, dispatch } = useHeatGuard();

  const runCustomSite = useCallback(async () => {
    const boundary = state.project.shapes.find(
      (s) => s.kind === "boundary" && s.points.length >= 3,
    );
    const projectId = `${CUSTOM_RUN_PREFIX}${Date.now()}`;

    // Closed WGS84 ring → a single-Feature Polygon (the backend extracts the outer ring).
    let boundary_geojson: FullRunBody["boundary_geojson"];
    if (boundary && boundary.geo) {
      const ring = [...boundary.points];
      const [fx, fy] = ring[0];
      const [lx, ly] = ring[ring.length - 1];
      if (fx !== lx || fy !== ly) ring.push(ring[0]);
      boundary_geojson = {
        type: "Feature",
        properties: {},
        geometry: { type: "Polygon", coordinates: [ring] },
      } as FullRunBody["boundary_geojson"];
    }

    const body: FullRunBody = {
      capacity: state.project.capacity,
      budget: state.project.budget,
      date: state.project.date,
      theme: state.project.theme,
      ...(boundary_geojson ? { boundary_geojson } : {}),
    };

    // Enter the analysis screen immediately; it reveals on real status.
    dispatch({ type: "startRun", runId: projectId });
    dispatch({ type: "setStage", stage: "placement" });

    try {
      await startFullRun(projectId, body);
    } catch (e) {
      // A failed POST still lands on the analysis screen; the status poll surfaces
      // the failure honestly rather than faking progress.
      console.error("run start failed", e);
    }
  }, [state.project, dispatch]);

  return { runCustomSite };
}
