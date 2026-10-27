/**
 * Festival-schema deck.gl layers — renders the committed site layout (stages,
 * entrances, amenities) so the map is LEGIBLE: you can see WHERE the stages are
 * (the crowd magnets) and where people enter. This is the context that makes the
 * crowd field + placement reason readable — without it the heat blob is meaningless.
 *
 * Source: GET /api/site/festival-schema (the SAME geojson the crowd sim flows
 * agents across — single source of truth, 1:1 with the simulation).
 */
import { ScatterplotLayer } from "@deck.gl/layers";
import type { Layer } from "@deck.gl/core";
import { hexToRgb, PALETTE } from "./tokens";
import type { SchemaFeature } from "./heatguard-api";

const AMBER = hexToRgb(PALETTE.amber);
const GREEN2 = hexToRgb(PALETTE.green2);
const GREY = hexToRgb(PALETTE.grey);
const PAPER = hexToRgb(PALETTE.paper);
const INK = hexToRgb(PALETTE.ink);

type SchemaPoint = { name: string; kind: string; lon: number; lat: number };

/** Stages are the crowd magnets; entrances/exits are the sources. */
const STAGE_KINDS = new Set(["stage"]);
const ENTRY_KINDS = new Set(["entrance", "exit", "emergency_exit"]);

function classOf(f: SchemaFeature): string {
  return (f.properties?.kind || f.properties?.class || "amenity") as string;
}

/** Pull point features (Point geometry) out of the schema into a flat list. */
export function schemaPoints(features: SchemaFeature[]): SchemaPoint[] {
  const out: SchemaPoint[] = [];
  for (const f of features) {
    if (f.geometry?.type !== "Point") continue;
    const [lon, lat] = f.geometry.coordinates as [number, number];
    out.push({ name: f.properties?.name || classOf(f), kind: classOf(f), lon, lat });
  }
  return out;
}

/**
 * Build the schema layers. `detail` controls amenity verbosity:
 *  - 'context' (default): stages + entrances labeled, amenities as faint dots.
 *  - 'full': everything (used if the user toggles amenity labels on).
 */
export function festivalSchemaLayers(points: SchemaPoint[]): Layer[] {
  const stages = points.filter((p) => STAGE_KINDS.has(p.kind));
  const entries = points.filter((p) => ENTRY_KINDS.has(p.kind));
  const amenities = points.filter((p) => !STAGE_KINDS.has(p.kind) && !ENTRY_KINDS.has(p.kind));

  return [
    // Amenities — faint grey dots, no labels (keeps the dense schema legible).
    new ScatterplotLayer<SchemaPoint>({
      id: "schema-amenities",
      data: amenities,
      getPosition: (d) => [d.lon, d.lat],
      getFillColor: [...GREY, 150],
      radiusUnits: "pixels",
      getRadius: 3,
      pickable: true,
    }),
    // Entrances/exits — green source dots + labels.
    new ScatterplotLayer<SchemaPoint>({
      id: "schema-entries",
      data: entries,
      getPosition: (d) => [d.lon, d.lat],
      getFillColor: [...GREEN2, 230],
      getLineColor: [...PAPER, 230],
      lineWidthMinPixels: 1.5,
      stroked: true,
      radiusUnits: "pixels",
      getRadius: 5,
      pickable: true,
    }),
    // Stages — amber crowd-magnet markers (largest) + labels.
    new ScatterplotLayer<SchemaPoint>({
      id: "schema-stages",
      data: stages,
      getPosition: (d) => [d.lon, d.lat],
      getFillColor: [...AMBER, 240],
      getLineColor: [...INK, 220],
      lineWidthMinPixels: 1.5,
      stroked: true,
      radiusUnits: "pixels",
      getRadius: 7,
      pickable: true,
    }),
    // NOTE: labels are HTML <Marker>s (SchemaLabels), not a deck TextLayer — the
    // SDF/atlas text rendered blank in this overlay setup; HTML pills are crisp.
  ];
}

/** Points that get an HTML name label: stages + MAIN entrances only (emergency
 *  exits stay as green dots — labelling all of them turns the map to mush). */
export function labelledSchemaPoints(points: SchemaPoint[]): SchemaPoint[] {
  return points.filter((p) => p.kind === "stage" || p.kind === "entrance");
}

export type { SchemaPoint };

/** Nearest named festival feature to a WGS84 point — organizer-language labels for
 *  zones ("near Estrella Damm"). Prefers stages/entrances as anchors. */
export function nearestFeature(center: [number, number], pts: SchemaPoint[]): string | null {
  let best: { name: string; d: number } | null = null;
  for (const p of pts) {
    const weight = p.kind === "stage" ? 0.5 : p.kind === "entrance" ? 0.7 : 1.5;
    const d = ((p.lon - center[0]) ** 2 + (p.lat - center[1]) ** 2) ** 0.5 * weight;
    if (!best || d < best.d) best = { name: p.name, d };
  }
  return best?.name ?? null;
}
