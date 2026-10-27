/**
 * `parseBrief` — the Phase-1 deliverable: a single Anthropic structured-output
 * call wrapped in a CCA-F-compliant 3-attempt retry loop with TWO gates and a
 * two-axis failure model. This is the loop the whole project depends on for
 * "the LLM never designs and the cap is a backstop, not the terminator"
 * (CCA-F P1/P2/P9; RESEARCH §Architecture Pattern 1 + Pattern 2).
 *
 * ONE attempt = one `messages.create` call + Gate 1 (stop_reason) + Gate 2
 * (local Ajv validation + ASSUMED plausibility range). The loop's PRIMARY
 * terminator is the success predicate (`end_turn` AND validated); the
 * `maxAttempts` cap is only the backstop (P2). On exhaustion it throws a typed
 * `ParserError(code:500)` and returns nothing — never a partial/guessed brief.
 *
 * Two failure axes (RESEARCH §Pattern 2, Pitfall 6 — discriminated via
 * `instanceof`, never string-match):
 *   - DATA failure   (bad JSON / off-enum / out-of-range / non-end_turn) →
 *                     retry the SAME model with the specific error fed back
 *                     (P9 layer 3, via `buildRetryMessage`).
 *   - INFRA failure  (HTTP >=500 incl. 529 overloaded; rate-limit; connection) →
 *                     switch sonnet→haiku and retry; does NOT feed a data error
 *                     back into the next prompt (it is not a data problem). It
 *                     DOES advance the shared `attempt` counter: there is ONE
 *                     bounded `maxAttempts` budget across both axes, so sustained
 *                     provider overload eventually exhausts the cap and throws the
 *                     terminal `ParserError(500)` (the cap stays a meaningful cost
 *                     backstop, not a separate per-axis budget). The distinction
 *                     between the axes is in the *recovery action* (switch-model vs
 *                     feed-back-error), not in a separate attempt allowance.
 *
 * SDK NOTE (verified against @anthropic-ai/sdk@0.104.0): this SDK version has NO
 * `Anthropic.OverloadedError` class — a 529 overloaded response maps to
 * `Anthropic.InternalServerError` (status 529), same as a generic >=500. We
 * therefore discriminate infra failures via `instanceof Anthropic.InternalServerError`
 * (plus `RateLimitError`/`APIConnectionError`) and keep the instanceof discipline
 * the plan mandates (Plan 01-02 Task 1 note: adjust class names to the pinned SDK,
 * keep instanceof). We construct the client with `maxRetries: 0` so the SDK does
 * not silently auto-retry >=500/429 — THIS loop owns every retry, so the cap
 * counts our validation attempts exactly (RESEARCH §Pattern 2 note).
 *
 * Secrets: `new Anthropic({ fetch })` reads `ANTHROPIC_API_KEY` from the env in
 * production (no `fetch` injected); tests inject `fetch` and need no key. No key
 * literal appears here (threat T-01-01).
 */

import Anthropic from "@anthropic-ai/sdk";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import type { ParsedBrief, ParseOpts } from "./types.ts";
import { ParserError, AttemptFailure } from "./errors.ts";
import { toApiSchema } from "./schema.ts";
import { SYSTEM_PROMPT, buildRetryMessage } from "./prompt.ts";
import { validate } from "../validate/validate.ts";

/**
 * ASSUMED capacity plausibility band (RESEARCH A2). NOT in the contract
 * (`parsed_brief.schema.json` sets only `minimum:0`) — a removable garbage filter,
 * not a business rule. A value passing `minimum:0` but outside this band is a
 * retry trigger ("re-extract"), never silently clipped.
 */
const CAP = { min: 1, max: 5_000_000 } as const;
/**
 * ASSUMED budget (€) plausibility band (RESEARCH A2). NOT in the contract;
 * generous ceiling that rejects garbage (e.g. a phone number parsed as budget)
 * while never clipping a real festival shade budget.
 */
const BUD = { min: 1, max: 1_000_000_000 } as const;

const DEFAULT_MODEL = "claude-sonnet-4-6";
const FALLBACK_MODEL = "claude-haiku-4-5";

// Repo root = two levels up from src/parser/ — matches the `validate.ts` idiom.
const __dirname = dirname(fileURLToPath(import.meta.url));
const CONTRACT_PATH = resolve(
  __dirname,
  "..",
  "..",
  "contracts",
  "parsed_brief.schema.json",
);

/** Build the API-side shape gate ONCE from the frozen contract (single source). */
const apiSchema = toApiSchema(CONTRACT_PATH);

/** Anthropic chat message shape (minimal local view; matches the SDK param). */
type ChatMessage = { role: "user" | "assistant"; content: string };

/**
 * Discriminate an INFRA failure (switch model + retry) from a DATA failure
 * (same model + feedback). In @anthropic-ai/sdk@0.104.0 the 529 overloaded
 * response is an `InternalServerError` (status 529); we also treat rate-limit and
 * connection errors as infrastructure. Pitfall 6: `instanceof`, never string-match.
 */
function isInfraError(err: unknown): boolean {
  return (
    err instanceof Anthropic.InternalServerError ||
    err instanceof Anthropic.RateLimitError ||
    err instanceof Anthropic.APIConnectionError
  );
}

/**
 * Parse a natural-language festival brief into a schema-valid `ParsedBrief`.
 *
 * @param text  The raw brief text (untrusted input; the closed schema +
 *              system prompt make design fields physically unreachable — PARSE-04).
 * @param opts  {@link ParseOpts}: `model` (default `claude-sonnet-4-6`),
 *              `fetch` (injected seam for offline tests), `maxAttempts` (default 3).
 * @returns     A `ParsedBrief` that has passed Gate 2 (Ajv + range) — `schema_version`
 *              is injected in code, never requested from the model (A1).
 * @throws      {@link ParserError} (`code:500`) after `maxAttempts` failed attempts.
 *              Never returns a partial or guessed brief.
 */
export async function parseBrief(
  text: string,
  opts: ParseOpts = {},
): Promise<ParsedBrief> {
  let model = opts.model ?? DEFAULT_MODEL;
  const maxAttempts = opts.maxAttempts ?? 3;

  // `maxRetries: 0` → THIS loop owns every retry/fallback, so the cap counts our
  // validation attempts exactly (no double-counting the SDK's own >=500 retries).
  //
  // Key handling: in prod (`fetch` undefined) the SDK reads ANTHROPIC_API_KEY from
  // the env. When a `fetch` seam is injected (offline tests), the request never
  // leaves the process, but the SDK still requires *some* apiKey to build the
  // Authorization header — so we pass a non-secret placeholder. This is a sentinel
  // string, NOT a credential (threat T-01-01: no real key literal here); it is used
  // only on the injected-fetch path where the value is never transmitted.
  const client = new Anthropic({
    fetch: opts.fetch,
    maxRetries: 0,
    ...(opts.fetch ? { apiKey: "offline-injected-fetch" } : {}),
  });

  const messages: ChatMessage[] = [{ role: "user", content: text }];
  let lastReason: string | undefined;

  // PRIMARY terminator = the success predicate below (return). The cap is the
  // backstop (P2) — reaching it falls through to the terminal ParserError.
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      const resp = await client.messages.create({
        model,
        max_tokens: 1024,
        temperature: 0,
        system: SYSTEM_PROMPT,
        // Structured output via output_config.format — never the parse() helper
        // (parse hides stop_reason → forces text-based termination, P1).
        output_config: { format: { type: "json_schema", schema: apiSchema } },
        messages,
      } as Anthropic.MessageCreateParamsNonStreaming);

      // GATE 1 — stop_reason (NEVER response text). P1: the loop branches on
      // stop_reason, not on content. Anything other than end_turn is a failed
      // attempt; a refusal is non-retryable (re-sending the identical prompt
      // would refuse again).
      if (resp.stop_reason !== "end_turn") {
        throw new AttemptFailure(
          `stop_reason ${resp.stop_reason}`,
          resp.stop_reason === "refusal",
        );
      }

      const first = resp.content[0];
      const obj: Record<string, unknown> = JSON.parse(
        first && first.type === "text" ? first.text : "{}",
      );
      // schema_version is a code-owned constant, NOT a model output (A1).
      obj.schema_version = "1.0.0";

      // GATE 2 — local validation (single source of truth) + ASSUMED range.
      // P9 layer 2: the API schema is a shape gate only; this asserts
      // date-format, minimum:0, enum membership, then plausibility bounds.
      validate(obj, "parsed_brief"); // throws on shape/type/enum/date/minimum
      const cap = obj.capacity as number;
      const bud = obj.budget as number;
      if (cap < CAP.min || cap > CAP.max) {
        throw new AttemptFailure(`capacity ${cap} implausible`);
      }
      if (bud < BUD.min || bud > BUD.max) {
        throw new AttemptFailure(`budget ${bud} implausible`);
      }

      return obj as unknown as ParsedBrief; // SUCCESS predicate — primary terminator
    } catch (err) {
      if (isInfraError(err)) {
        // INFRA failure → switch model (sonnet→haiku) and retry. Do NOT feed a
        // data error back; this is not a data problem (Pattern 2). This `continue`
        // advances the shared `attempt` counter — infra and data failures draw on
        // the ONE bounded `maxAttempts` budget, so sustained overload exhausts the
        // cap and falls through to the terminal ParserError(500) below (WR-01: the
        // cap is a single shared cost backstop, not a per-axis allowance).
        model = FALLBACK_MODEL;
        lastReason = `infra ${(err as Error).message} → ${FALLBACK_MODEL}`;
        continue;
      }

      // DATA failure (validate throw / JSON.parse / AttemptFailure) → SAME model.
      lastReason = (err as Error).message;

      // A refusal is non-retryable: stop early rather than re-send the identical
      // prompt (it will refuse again). Surface as the terminal 500 immediately.
      if (err instanceof AttemptFailure && err.nonRetryable) {
        break;
      }

      // Feed the specific error back so the next attempt corrects exactly what
      // was wrong (P9 layer 3). SAME model.
      messages.push({ role: "user", content: buildRetryMessage(lastReason) });
    }
  }

  // Cap exhausted (or non-retryable refusal) → terminal 500. Return NOTHING.
  throw new ParserError(
    `brief parse failed after ${maxAttempts} attempts`,
    maxAttempts,
    lastReason,
  );
}
