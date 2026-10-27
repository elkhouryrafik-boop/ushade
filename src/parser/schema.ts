/**
 * API-side schema derivation (RESEARCH §API-Side Schema Derivation, Pitfall A).
 *
 * The ONE source of truth for the brief contract is `contracts/parsed_brief.schema.json`.
 * The Anthropic Structured Outputs API enforces only object shape, types, `enum`,
 * `required`, and `additionalProperties:false` — it does NOT enforce `minimum`/
 * `maximum`, `format` (`date`), `const`, or any `x-*` annotation, and may reject
 * unknown keywords. So we DERIVE a stripped "shape gate" view from the loaded
 * contract at load time rather than hand-maintaining a second JSON file (which
 * would drift — the exact Pitfall A Phase 0 exists to prevent).
 *
 * Two views, one file:
 *  - API-side (this): shape gate sent as `output_config.format.schema`.
 *  - Local (full contract): the Phase-0 Ajv2020 validator asserts `date` format,
 *    `minimum:0`, and `schema_version` — defense-in-depth (P9 layer 2).
 *
 * `schema_version` is EXCLUDED here and injected in code before local validation
 * (A1) — keeping the LLM's job to the 4 true semantic fields (PARSE-04 spirit).
 */

import { readFileSync } from "node:fs";

type JsonSchema = Record<string, any>;

/**
 * Derive the API-side shape gate from the frozen `parsed_brief` contract.
 *
 * @param contractPath Path to `contracts/parsed_brief.schema.json`.
 * @returns A constraint-free JSON Schema with `type:"object"`,
 *          `additionalProperties:false`, the 4 required fields, integer/string
 *          types, and the `theme` enum echoed verbatim from the contract.
 *          Strips `minimum`/`format`/`const`/`$schema`/`$id`/`title`/`description`/`x-*`
 *          and excludes `schema_version` (injected in code, A1).
 */
export function toApiSchema(contractPath: string): JsonSchema {
  const c = JSON.parse(readFileSync(contractPath, "utf-8")) as JsonSchema;
  return {
    type: "object",
    additionalProperties: false,
    required: ["capacity", "budget", "date", "theme"],
    properties: {
      capacity: { type: "integer" }, // minimum:0 dropped -> local Ajv check
      budget: { type: "integer" }, //  minimum:0 dropped -> local Ajv check
      date: { type: "string" }, //     format:"date" dropped -> local ajv-formats check
      theme: { enum: c.properties.theme.enum }, // closed set echoed; API enforces enum
      // Optional hour window — pattern dropped (API may not support it); local Ajv checks pattern.
      festival_start: { type: "string" },
      festival_end: { type: "string" },
    },
  };
}
