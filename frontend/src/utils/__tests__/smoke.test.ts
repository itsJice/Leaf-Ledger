import { describe, expect, it } from "vitest";
import { formatCurrency } from "../format";
import { ORNAMENT_OPTIONS } from "../ornamentRecipe";

describe("formatCurrency", () => {
  it("formats a USD amount", () => {
    expect(formatCurrency(1234.5)).toBe("$1,234.50");
  });
});

describe("ORNAMENT_OPTIONS planarArea literals", () => {
  // The original source literals had more digits than a double can hold
  // (eslint no-loss-of-precision). They were rewritten to the shortest literal
  // that parses to the identical double; this pins that equivalence.
  const original: Record<string, string> = {
    "2.4": "4.5238934211692976",
    "3": "7.0685834705770275",
    "15.75": "194.82783190777932",
    "24": "452.38934211692976",
  };

  for (const [display, digits] of Object.entries(original)) {
    it(`display ${display} keeps the original planarArea value`, () => {
      const option = ORNAMENT_OPTIONS.find((o) => o.display === display);
      expect(option).toBeDefined();
      expect(option!.planarArea).toBe(Number(digits));
    });
  }
});
