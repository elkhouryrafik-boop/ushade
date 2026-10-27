/**
 * Typed errors for the Phase-1 parser (RESEARCH §Typed ParserError).
 *
 * Two distinct error roles:
 *  - `AttemptFailure` marks a SINGLE failed attempt inside the retry loop
 *    (bad JSON / off-enum / out-of-range / non-`end_turn` stop_reason). The loop
 *    catches it, feeds the reason back to the model, and retries. A `refusal`
 *    sets `nonRetryable = true` so the loop does not re-send the identical prompt.
 *  - `ParserError` is the TERMINAL error thrown after the attempt cap is
 *    exhausted; it carries `code = 500` (surfaced as HTTP 500 by the future
 *    Phase-7 gateway). Never return a partial/guessed brief — throw this instead.
 *
 * Callers discriminate via `instanceof`, never string-matching the message
 * (CCA-F P6). No API key or secret is referenced here.
 */

/**
 * Terminal parse failure after the retry cap is exhausted. `code = 500` is the
 * HTTP status the gateway will surface; `attempts` and `lastReason` are
 * diagnostics for logging.
 */
export class ParserError extends Error {
  readonly code = 500;
  constructor(
    message: string,
    readonly attempts: number,
    readonly lastReason?: string,
  ) {
    super(message);
    this.name = "ParserError";
  }
}

/**
 * Marks one failed attempt inside the loop. `nonRetryable` (e.g. set on a model
 * `refusal`) tells the loop not to re-send an identical prompt that will fail the
 * same way.
 */
export class AttemptFailure extends Error {
  constructor(
    reason: string,
    readonly nonRetryable = false,
  ) {
    super(reason);
    this.name = "AttemptFailure";
  }
}
