/**
 * Honesty wording constants (D-09, load-bearing #3).
 *
 * The UI must never overclaim. The structural result is "structurally
 * pre-screened" (a Karamba prescreen), NEVER "engineered" or "certified", and
 * the results carry an explicit "decision support only" disclaimer. Routing /
 * crowd density is ASSUMED-grade wherever it surfaces (D-10).
 *
 * These constants are the single source of truth for that wording so the
 * honesty grep (no "engineered"/"certified" in the bundle) has one place to
 * police and the dashboard/structural views never inline an overclaim.
 */

/** The prominent results disclaimer (D-09). */
export const DISCLAIMER_TEXT =
  "decision support only — requires licensed engineering + on-site heat-safety sign-off";

/** The structural wording (D-09). Karamba pre-screen — never "engineered"/"certified". */
export const STRUCTURE_WORDING = "structurally pre-screened";

/** Routing / crowd-density honesty note (D-10) — stage-reach deferred at 54.8%. */
export const ROUTING_NOTE =
  "routing ASSUMED-grade — stage-reach gate not validated";
