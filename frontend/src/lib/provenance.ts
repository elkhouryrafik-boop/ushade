/**
 * Provenance index + lookup (D-07, load-bearing #1).
 *
 * The honesty contract forbids any displayed number without a provenance tier.
 * The per-run provenance ledger (GET /api/artifacts/{id}/provenance) is an array
 * of {key, value, tier, source, stage, unit?, formula?} entries. This module
 * turns that array into a fast key→tier lookup and — critically — returns a LOUD
 * `UNLABELLED` sentinel on a miss, NEVER `undefined` and NEVER a bare value.
 *
 * A missing tag must be visible, not silent (Pitfall 1). The dashboard pairs the
 * result of `lookupTag` with a <ProvenanceTag/>; an UNLABELLED tier renders a
 * red warning badge next to the number rather than letting it escape untagged.
 */

/** The four LOCKED ledger tiers + the UNLABELLED miss sentinel (our addition). */
export type ProvenanceTier =
  | "GROUNDED"
  | "DERIVED"
  | "ASSUMED"
  | "INVENTED"
  | "UNLABELLED";

/** A single provenance-ledger entry as served by the backend. */
export interface LedgerEntry {
  key: string;
  value?: unknown;
  tier: ProvenanceTier;
  source?: string;
  stage?: string;
  unit?: string;
  formula?: string;
}

/** The resolved tag rendered next to a number. Always defined (never undefined). */
export interface ProvenanceTag {
  tier: ProvenanceTier;
  source?: string;
  formula?: string;
}

export type ProvenanceIndex = Map<string, ProvenanceTag>;

/**
 * Build a key→tag index from the ledger entries. On a key collision the LAST
 * entry wins (the backend merge namespaces by stage and lets the later stage
 * win — A4); we mirror that ordering here.
 */
export function buildProvenanceIndex(entries: LedgerEntry[]): ProvenanceIndex {
  const index: ProvenanceIndex = new Map();
  for (const e of entries ?? []) {
    if (!e || typeof e.key !== "string") continue;
    index.set(e.key, {
      tier: e.tier,
      source: e.source,
      formula: e.formula,
    });
  }
  return index;
}

/**
 * Resolve a number's provenance by key. A known key returns its recorded tier;
 * an UNKNOWN key returns the loud `{ tier: "UNLABELLED" }` sentinel — never
 * undefined, never a bare value (load-bearing #1 / Pitfall 1).
 */
export function lookupTag(index: ProvenanceIndex, key: string): ProvenanceTag {
  const found = index.get(key);
  if (found) return found;
  return { tier: "UNLABELLED" };
}
