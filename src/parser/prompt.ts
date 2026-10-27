/**
 * System prompt + retry-feedback builder for the Phase-1 parser (PARSE-04).
 *
 * The closed `additionalProperties:false` schema (see `schema.ts`) is the PRIMARY
 * structural guardrail — the model physically cannot emit fields outside
 * {capacity, budget, date, theme}. This prompt reinforces extraction-only
 * behavior and is the PRD-locked text (FESTCOOL_PRD.md line 80), with one
 * discretionary tightening allowed by CONTEXT.md / RESEARCH A3:
 *
 * The PRD's "assume logical default values" clause is narrowed so it does NOT
 * invite a hallucinated budget/capacity/date — those numeric/temporal fields are
 * extracted-or-omitted (an omission becomes a local validation failure → retry
 * with feedback), never invented. Only `theme` is classified into the closed enum.
 * This keeps the LLM from estimating any design-relevant value (PRD §6 / PARSE-04).
 */

/** PRD-locked extraction-only system prompt (PARSE-04 guardrail intact). */
export const SYSTEM_PROMPT = [
  "You are a backend data processor. Your sole function is to extract operational",
  "parameters from the user's text brief and return them structured under the",
  "provided JSON Schema. If the user requests anything outside the schema, ignore it.",
  "",
  "Extract only values that are present in the brief. Do NOT invent or estimate a",
  "budget, capacity, or date — if one of those is absent, omit it (the system will",
  "ask you to correct the output). Classify the theme into the provided enum based",
  "on the semantic context of the brief. You never design anything; you only",
  "translate the brief into the schema fields.",
  "",
  "For festival_start and festival_end: extract the opening and closing times of",
  "the festival if mentioned (e.g. 'runs from 10am to 11pm' → festival_start:'10:00',",
  "festival_end:'23:00'). Use 24-hour HH:MM format. Omit both fields if no times",
  "are stated in the brief.",
].join(" ");

/**
 * Build the user-message feedback fed into the next attempt after a failed one
 * (P9 layer 3 — PRD line 86 style). The specific prior error is surfaced so the
 * model can correct exactly what was wrong.
 *
 * @param prevError Human-readable reason the previous attempt failed.
 */
export function buildRetryMessage(prevError: string): string {
  return `Parsing error: ${prevError}. Return the corrected JSON object only.`;
}
