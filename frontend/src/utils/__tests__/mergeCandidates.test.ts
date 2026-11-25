import { describe, expect, it } from "vitest";
import { mergeCandidates } from "utils/mergeCandidates";

// FAKE names, shaped like the 11/24 duplicate (Comments #50).
const DUP = { id: 599, name: "Test Byrd (Fake/Example Design Associates L.L.P)" };
const ROWS = [
  DUP,
  { id: 303, name: "Byrd, Test - (Fake/Example Design Associates L.L.P)" },
  { id: 12, name: "Anderson, Sample" },
  { id: 13, name: "Byrd Garden Club" },
  { id: null, name: "Unsaved Project Client" },
];

describe("mergeCandidates", () => {
  it("never offers the card itself or an unsaved one, and puts the likely twin first", () => {
    const out = mergeCandidates(DUP, ROWS, "");
    expect(out.map((c) => c.id)).toEqual([303, 13, 12]);
  });

  it("narrows by every typed word, by word start", () => {
    expect(mergeCandidates(DUP, ROWS, "byr gard").map((c) => c.id)).toEqual([13]);
    expect(mergeCandidates(DUP, ROWS, "andersen")).toEqual([]);
  });
});
