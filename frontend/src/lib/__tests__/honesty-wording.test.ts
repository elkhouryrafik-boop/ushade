/**
 * RED spec — Plan 07-04 (Dashboard honesty wording) turns this GREEN.
 *
 * LOAD-BEARING ASSERTION #3 (D-09): the UI must never overclaim. The structural
 * result is "structurally pre-screened" (Karamba prescreen), NEVER "engineered"
 * or "certified", and the dossier carries an explicit "decision support only"
 * disclaimer. These two string constants live in ../honesty (unwritten) →
 * import FAILS → RED.
 */
import { describe, it, expect } from "vitest";
// GREEN since Plan 07-05 created ../honesty.
import { DISCLAIMER_TEXT, STRUCTURE_WORDING } from "../honesty";

describe("honesty wording constants (D-09, load-bearing #3)", () => {
  it("DISCLAIMER_TEXT states the tool is decision support only", () => {
    expect(DISCLAIMER_TEXT.toLowerCase()).toContain("decision support only");
  });

  it("STRUCTURE_WORDING is exactly 'structurally pre-screened'", () => {
    expect(STRUCTURE_WORDING).toBe("structurally pre-screened");
  });

  it("NEITHER constant overclaims with 'engineered' or 'certified'", () => {
    for (const text of [DISCLAIMER_TEXT, STRUCTURE_WORDING]) {
      const lower = text.toLowerCase();
      expect(lower).not.toContain("engineered");
      expect(lower).not.toContain("certified");
    }
  });
});
