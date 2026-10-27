/**
 * GEOM-01 — validate-then-POST gh_request assembler.
 *
 * Assembles the FROZEN `gh_request` (contracts/gh_request.schema.json) from the real
 * Phase-3 artifacts — footprint.json.polygons IS the IN_Footprint shape and
 * crowd_grid.flow_vectors IS the IN_FlowVectors `{ origin, destination }` line shape — so
 * both drop in with NO reshape. The assembled request is ajv-validated HERE, before any
 * network/subprocess call, using the SAME single-source validator the rest of the runtime
 * uses (src/validate/validate.ts → the frozen contract). An invalid request throws and
 * never reaches the wire (validate-then-POST; clone parser.ts Gate 2).
 *
 * `schema_version` is a code-owned const (clone parser A1) — never read from the input.
 *
 * The GhRequest / GhResponse types mirror the frozen contracts so client.ts can consume them.
 */

import { validate } from "../validate/validate.ts";

/** A metre-space point — `gh_request` #/$defs/point_m. */
export interface PointM {
  x_m: number;
  y_m: number;
}

/** A flow line — `gh_request` #/$defs/line. crowd_grid.flow_vectors IS this shape. */
export interface Line {
  origin: PointM;
  destination: PointM;
}

/** A footprint polygon ring — `gh_request` #/$defs/polygon (>= 3 points). */
export type Polygon = PointM[];

/** The FROZEN gh_request (contracts/gh_request.schema.json). */
export interface GhRequest {
  schema_version: "1.0.0";
  IN_Footprint: Polygon[];
  IN_FlowVectors: Line[];
  IN_SunVector: [number, number, number];
}

/** The FROZEN gh_response (contracts/gh_response.schema.json). */
export interface GhResponse {
  schema_version: "1.0.0";
  OUT_Mesh: { b64: string };
  OUT_BOM: { pillars: number; membrane_m2: number };
}

/**
 * Assemble + ajv-validate the frozen gh_request from the footprint polygons, flow vectors,
 * and sun vector. Throws (validate-then-POST) if the assembled request is contract-invalid —
 * so an invalid request never reaches the Rhino.Compute wire or the reference subprocess.
 */
export function buildGhRequest(
  footprintPolygons: Polygon[],
  flowVectors: Line[],
  sun: [number, number, number],
): GhRequest {
  const req: GhRequest = {
    schema_version: "1.0.0", // code-owned const (clone parser A1) — never from input
    IN_Footprint: footprintPolygons,
    IN_FlowVectors: flowVectors, // already the line shape — NO reshape
    IN_SunVector: sun,
  };
  validate(req, "gh_request"); // throws if invalid — never reaches the wire
  return req;
}
