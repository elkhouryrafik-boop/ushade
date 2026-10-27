/**
 * RED spec — Plan 07-04 (Dashboard provenance) turns this GREEN.
 *
 * LOAD-BEARING ASSERTION #1 (D-07): every displayed value carries a provenance
 * tier; an UNKNOWN key must resolve to a sentinel `{ tier: "UNLABELLED" }` —
 * NEVER `undefined`, never a bare value. A silent undefined would let an
 * unlabelled number reach the UI, breaking the honesty contract.
 *
 * `buildProvenanceIndex` / `lookupTag` live in ../provenance, which does not
 * exist yet → import FAILS → RED.
 */
import { describe, it, expect } from "vitest";
// GREEN since Plan 07-05 created ../provenance.
import { buildProvenanceIndex, lookupTag, type LedgerEntry } from "../provenance";

const entries: LedgerEntry[] = [
  { key: "coverage_pct", tier: "GROUNDED", source: "acceptance.json" },
  { key: "transport_carbon_kg", tier: "ASSUMED", source: "material_selection.json" },
  { key: "crowd_density", tier: "ASSUMED", source: "crowd_grid.json" },
];

describe("provenance index + lookup (D-07, load-bearing #1)", () => {
  it("returns the recorded tier for a known key", () => {
    const index = buildProvenanceIndex(entries);
    expect(lookupTag(index, "coverage_pct").tier).toBe("GROUNDED");
    expect(lookupTag(index, "transport_carbon_kg").tier).toBe("ASSUMED");
  });

  it("returns the UNLABELLED sentinel for an unknown key — never undefined, never a bare value", () => {
    const index = buildProvenanceIndex(entries);
    const result = lookupTag(index, "totally_unknown_key");
    expect(result).toBeDefined();
    expect(result).not.toBeNull();
    expect(result.tier).toBe("UNLABELLED");
  });
});
