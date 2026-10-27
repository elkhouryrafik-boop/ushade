/**
 * Shared type contracts for the Phase-1 LLM brief parser.
 *
 * These are the fixed interfaces Plan 02 (the stop_reason-gated retry loop) and
 * Plan 03 (artifact write + CLI) build against — defined first so downstream
 * plans implement against a frozen contract with no codebase scavenging.
 *
 * `ParsedBrief` mirrors the LOCAL-validation view of `contracts/parsed_brief.schema.json`
 * (all 5 fields incl. the code-injected `schema_version`). The API-side view drops
 * `schema_version` (injected in code) and the numeric/format constraints — see
 * `schema.ts` `toApiSchema`.
 */

/**
 * The parse-only structured output: exactly the 4 PRD semantic fields plus the
 * code-owned `schema_version` constant. The LLM emits the 4 fields; the parser
 * injects `schema_version` before local validation (RESEARCH §API-Side Schema
 * Derivation, A1). The LLM never designs — this is its sole output (PARSE-04).
 */
export interface ParsedBrief {
  schema_version: "1.0.0";
  capacity: number;
  budget: number;
  /** ISO `YYYY-MM-DD` (asserted locally via ajv-formats `date`). */
  date: string;
  theme: "maritime" | "natural" | "industrial" | "urban";
  /** Festival opening time HH:MM (24h). Defaults to "09:00" if absent. */
  festival_start?: string;
  /** Festival closing time HH:MM (24h). Defaults to "23:00" if absent. */
  festival_end?: string;
}

/**
 * Options for a parse call.
 *
 * @property model       Anthropic model id. Default `"claude-sonnet-4-6"`;
 *                       fallback `"claude-haiku-4-5"` on infrastructure errors.
 * @property fetch       Injected fetch seam for offline tests
 *                       (`new Anthropic({ fetch })`). Defaults to the global `fetch`.
 * @property maxAttempts Validation-attempt backstop cap. Default `3` (CCA-F P2 —
 *                       the cap is the backstop, not the primary terminator).
 */
export interface ParseOpts {
  model?: string;
  fetch?: typeof fetch;
  maxAttempts?: number;
}
