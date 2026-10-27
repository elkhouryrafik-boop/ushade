import { useEffect, useRef } from "react";
import { useControl } from "react-map-gl/mapbox";
import type { MapRef } from "react-map-gl/mapbox";
import type { ControlPosition } from "mapbox-gl";
import MapboxDraw from "@mapbox/mapbox-gl-draw";
import type { Feature } from "geojson";
import { useHeatGuard, SHAPE_META, type ShapeKind } from "@/lib/heatguard-store";
import { shapeFromDrawFeature, resolveKind, computeAreaM2 } from "@/lib/draw-adapter";
import "@mapbox/mapbox-gl-draw/dist/mapbox-gl-draw.css";

/**
 * Mapbox-GL-Draw control (D-01 / FE-01), replacing the hand-rolled SVG click-capture.
 * Mounts via react-map-gl's `useControl` so it shares the live <Map> instance, and
 * binds draw.create / draw.update / draw.delete to the heatguard-store via the
 * draw-adapter. The active drawing tool stamps `properties.kind` onto each new
 * feature so boundary vs zone is distinguishable downstream (the boundary is the
 * multi-festival site input, D-04). The drawn-boundary area is reported in m² via
 * @turf/area (replaces the retired Maps spherical-geometry area call).
 */

type Props = {
  /** The currently selected tool; stamped onto new features as properties.kind. */
  activeTool: ShapeKind | null;
  /** Cleared to null after a feature is placed (one-shot placement per tool click). */
  setActiveTool?: (t: ShapeKind | null) => void;
  position?: ControlPosition;
};

export function DrawControl({ activeTool, setActiveTool, position = "top-left" }: Props) {
  const { dispatch } = useHeatGuard();
  // Keep the latest tool/clear-fn reachable from the (stable) event handlers.
  const toolRef = useRef<ShapeKind | null>(activeTool);
  const clearToolRef = useRef<typeof setActiveTool>(setActiveTool);
  // Holds the bound draw event handlers so useControl's cleanup can detach the
  // exact same references (mapbox-gl's `off` is keyed on the listener identity).
  const handlersRef = useRef<{
    onCreate: (e: { features: Feature[] }) => void;
    onUpdate: (e: { features: Feature[] }) => void;
    onDelete: (e: { features: Feature[] }) => void;
  } | null>(null);
  useEffect(() => { toolRef.current = activeTool; }, [activeTool]);
  useEffect(() => { clearToolRef.current = setActiveTool; }, [setActiveTool]);

  // Holds the live MapboxDraw instance so a tool selection can start the matching
  // draw mode (otherwise the toolbar buttons only stamp `kind` and nothing draws).
  const drawRef = useRef<MapboxDraw | null>(null);

  function commitFeatures(features: Feature[], isUpdate: boolean) {
    for (const raw of features) {
      // Stamp the active tool's kind so boundary vs zone is preserved; fall back
      // to the feature's own kind (default "boundary") when no tool is active.
      const kind = toolRef.current ?? resolveKind(raw.properties?.kind);
      const feature: Feature = {
        ...raw,
        properties: { ...(raw.properties ?? {}), kind },
      };
      const m2 = computeAreaM2(feature); // 0 for points
      // Store raw WGS84 (geo:true) so the shape projects to the map live + tracks
      // pan/zoom (MapCanvas projectShape) and is sent as real geography on run.
      const shape = { ...shapeFromDrawFeature(feature), geo: true, areaM2: m2 || undefined };
      // create → add; edit/move/resize (draw.update) → update by id, never a duplicate.
      dispatch(isUpdate ? { type: "updateShape", shape } : { type: "addShape", shape });
      if (kind === "boundary" && m2 > 0) {
        dispatch({ type: "setProject", patch: { siteAreaM2: m2 } });
      }
    }
    // After placing a new feature, clear the tool so one click = one placement
    // (the user re-picks a tool for the next element — predictable, no surprise re-draw).
    if (!isUpdate) clearToolRef.current?.(null);
  }

  const draw = useControl<MapboxDraw>(
    () =>
      // No native UI — the single labelled DrawingToolbar is the only toolbar; a tool
      // click drives changeMode (below). Delete a selected shape with Delete/Backspace.
      new MapboxDraw({
        displayControlsDefault: false,
        controls: {},
      }),
    ({ map }) => {
      // mapbox-gl-draw fires custom "draw.*" events not in mapbox-gl's typed event
      // map; bind via a loosely-typed `on`/`off` view so the named handlers can be
      // detached symmetrically in cleanup (map.off requires the listener ref).
      const m = map as unknown as {
        on(type: string, listener: (e: { features: Feature[] }) => void): unknown;
        off(type: string, listener: (e: { features: Feature[] }) => void): unknown;
      };
      const onCreate = (e: { features: Feature[] }) => commitFeatures(e.features, false);
      const onUpdate = (e: { features: Feature[] }) => commitFeatures(e.features, true);
      const onDelete = (e: { features: Feature[] }) => {
        for (const f of e.features) {
          if (typeof f.id === "string") dispatch({ type: "removeShape", id: f.id });
        }
      };
      m.on("draw.create", onCreate);
      m.on("draw.update", onUpdate);
      m.on("draw.delete", onDelete);
      handlersRef.current = { onCreate, onUpdate, onDelete };
    },
    ({ map }) => {
      const m = map as unknown as {
        off(type: string, listener: (e: { features: Feature[] }) => void): unknown;
      };
      const h = handlersRef.current;
      if (h) {
        m.off("draw.create", h.onCreate);
        m.off("draw.update", h.onUpdate);
        m.off("draw.delete", h.onDelete);
      }
    },
    { position },
  );

  // Keep the instance reachable for the tool→mode effect below.
  useEffect(() => { drawRef.current = draw ?? null; }, [draw]);
  // NOTE: the committed boundary is rendered as a deck.gl layer (BoundaryLayer in the
  // shell) so it survives a resume reliably — no fragile re-hydration into the draw
  // store needed. mapbox-gl-draw here owns only live drawing/editing this session.

  // Selecting a tool actually STARTS the matching mapbox-gl-draw mode (previously
  // the toolbar only stamped `kind` and nothing drew until you also hit mapbox's
  // own polygon button). point-kind → draw_point; everything else → draw_polygon;
  // no tool → simple_select (so the user can click a placed shape to move/resize it).
  useEffect(() => {
    const d = draw;
    if (!d) return;
    try {
      if (activeTool) {
        const mode = SHAPE_META[activeTool].mode === "point" ? "draw_point" : "draw_polygon";
        d.changeMode(mode);
      } else {
        d.changeMode("simple_select");
      }
    } catch {
      // changeMode can throw if the control isn't mounted yet; the next tool click retries.
    }
  }, [activeTool, draw]);

  return null;
}

// Re-export to satisfy callers that pass the MapRef explicitly (unused here — the
// control is wired through useControl's map context).
export type { MapRef };
