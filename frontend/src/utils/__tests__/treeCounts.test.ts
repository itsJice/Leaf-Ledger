import { describe, expect, it } from "vitest";
import {
  COUNT_SIZES,
  DRIFT_MIN_PCT,
  DRIFT_MIN_PIECES,
  HEIGHT_TOLERANCE_FT,
  averageCounts,
  compareToTable,
  countsFromForm,
  driftCell,
  goldenRowSnippet,
  recordsNearHeight,
  roundToEven,
  summariseCounts,
  totalPieces,
  type TreeCountRecord,
} from "../treeCounts";

function rec(id: number, height_ft: number, counts: Record<string, number>, extra: Partial<TreeCountRecord> = {}): TreeCountRecord {
  return {
    id,
    recorded_at: "2026-09-01T00:00:00Z",
    kind: "install",
    height_ft,
    width_in: 65,
    profile: null,
    style: null,
    label: null,
    counts,
    enhancers: 24,
    notes: null,
    created_by: null,
    created_name: null,
    ...extra,
  };
}

describe("constants", () => {
  it("pins count sizes and drift thresholds", () => {
    expect(COUNT_SIZES.map((o) => o.display)).toEqual(["3", "4", "4.75", "6", "8", "10", "12", "15.75"]);
    expect([HEIGHT_TOLERANCE_FT, DRIFT_MIN_PIECES, DRIFT_MIN_PCT]).toEqual([0.25, 4, 0.2]);
  });
});

describe("totalPieces", () => {
  it("sums values, treating non-numbers as 0", () => {
    expect(totalPieces({})).toBe(0);
    expect(totalPieces({ "3": 12, "4": 6 })).toBe(18);
    expect(totalPieces({ "3": 12, "4": "x" as unknown as number, "6": NaN, "8": 2 })).toBe(14);
  });
});

describe("countsFromForm", () => {
  it("drops blank, zero, negative and non-numeric cells; rounds the rest", () => {
    expect(countsFromForm({ "3": "12", "4": " ", "4.75": "0", "6": "abc", "8": "3.6", "10": "-2", "12": "1e1" })).toEqual({ "3": 12, "8": 4, "12": 10 });
    expect(countsFromForm({ "3": "0.4" })).toEqual({});
    expect(countsFromForm({})).toEqual({});
  });
});

describe("recordsNearHeight", () => {
  const records = [rec(1, 10, {}), rec(2, 10.25, {}), rec(3, 9.75, {}), rec(4, 10.3, {}), rec(6, 9.74, {}), rec(5, 12, {})];
  it("keeps records within the (inclusive) tolerance", () => {
    expect(recordsNearHeight(records, 10).map((r) => r.id)).toEqual([1, 2, 3]);
    expect(recordsNearHeight(records, 10, 0).map((r) => r.id)).toEqual([1]);
    expect(recordsNearHeight(records, 10, 2).map((r) => r.id)).toEqual([1, 2, 3, 4, 6, 5]);
    expect(recordsNearHeight([], 10)).toEqual([]);
  });
});

describe("averageCounts", () => {
  it("returns null for no records", () => {
    expect(averageCounts([])).toBeNull();
  });

  it("averages width, enhancers and per-size counts (missing size = real zero)", () => {
    const avg = averageCounts([
      rec(1, 10, { "4": 30, "6": 10 }, { width_in: 64, enhancers: 20 }),
      rec(2, 10, { "4": 40 }, { width_in: 66, enhancers: 25 }),
      rec(3, 10, { "4": 20, abc: 99 }, { width_in: 0, enhancers: NaN }),
    ]);
    expect(avg).toEqual({ n: 3, widthIn: 130 / 3, enhancers: 15, counts: { 4: 30, 6: 10 / 3 } });
  });
});

describe("roundToEven", () => {
  it("rounds to the nearest even, halves up", () => {
    expect([0, 1, 2, 3, 25, 24.9, 0.5, -3].map(roundToEven)).toEqual([0, 2, 2, 4, 26, 24, 0, -2]);
    expect(roundToEven(-1)).toBe(-0);
    expect(roundToEven(NaN)).toBeNaN();
  });
});

describe("driftCell", () => {
  it("flags by pieces, by percent, or by an unapproved size", () => {
    expect(driftCell(20, 24)).toEqual({ approved: 20, actual: 24, diff: 4, pct: 0.2, flagged: true });
    expect(driftCell(20, 23)).toEqual({ approved: 20, actual: 23, diff: 3, pct: 0.15, flagged: false });
    expect(driftCell(10, 12)).toEqual({ approved: 10, actual: 12, diff: 2, pct: 0.2, flagged: true });
    expect(driftCell(5, 3)).toEqual({ approved: 5, actual: 3, diff: -2, pct: -0.4, flagged: true });
    expect(driftCell(0, 1)).toEqual({ approved: 0, actual: 1, diff: 1, pct: null, flagged: true });
    expect(driftCell(0, 0)).toEqual({ approved: 0, actual: 0, diff: 0, pct: null, flagged: false });
  });
});

describe("goldenRowSnippet", () => {
  it("sorts sizes, rounds to even, drops zeros and rounds width", () => {
    expect(goldenRowSnippet(10, 64.6, { 4: 35, 4.75: 37.2, 6: 0.4, 3: 0 })).toBe("{ heightFt: 10, widthIn: 65, quantities: { 4: 36, 4.75: 38 } },");
    expect(goldenRowSnippet(7.5, 49, {})).toBe("{ heightFt: 7.5, widthIn: 49, quantities: {  } },");
  });
});

describe("summariseCounts", () => {
  it("lists positive sizes largest first", () => {
    expect(summariseCounts({ "3": 12, "4.75": 4, "15.75": 2, "6": 0 })).toBe('15.75"×2 · 4.75"×4 · 3"×12');
    expect(summariseCounts({})).toBe("");
  });
});

describe("compareToTable", () => {
  it("with no records: one empty row per golden height", () => {
    const rows = compareToTable([]);
    expect(rows.map((r) => [r.heightFt, r.sizes, r.average, r.cells, r.drifted, r.snippet, r.records])).toEqual([
      [7.5, [3, 4, 4.75, 6, 8], null, {}, false, "", []],
      [8, [4, 4.75, 6, 8, 10], null, {}, false, "", []],
      [10, [4, 4.75, 6, 8, 10], null, {}, false, "", []],
      [12, [4.75, 6, 8, 10, 12], null, {}, false, "", []],
    ]);
  });

  it("matching counts are not drift; the snippet reproduces the approved row", () => {
    const rows = compareToTable([rec(1, 10.2, { "4": 36, "4.75": 36, "6": 30, "8": 20, "10": 12 }, { width_in: 70 }), rec(2, 9, { "4": 1 })]);
    const ten = rows.find((r) => r.heightFt === 10)!;
    expect(ten.records.map((r) => r.id)).toEqual([1]);
    expect(ten.drifted).toBe(false);
    expect(ten.snippet).toBe("{ heightFt: 10, widthIn: 65, quantities: { 4: 36, 4.75: 36, 6: 30, 8: 20, 10: 12 } },");
    expect(rows.find((r) => r.heightFt === 8)!.average).toBeNull();
  });

  it("flags under-counts and sizes the table never asked for", () => {
    const rows = compareToTable([
      rec(1, 7.5, { "3": 20, "4": 12, "4.75": 16, "6": 16, "8": 8, "12": 2 }),
      rec(2, 7.4, { "3": 20, "4": 12, "4.75": 16, "6": 16, "8": 8 }),
    ]);
    const row = rows[0];
    expect(row.sizes).toEqual([3, 4, 4.75, 6, 8, 12]);
    expect(row.cells[3]).toEqual({ approved: 25, actual: 20, diff: -5, pct: -0.2, flagged: true });
    expect(row.cells[12]).toEqual({ approved: 0, actual: 1, diff: 1, pct: null, flagged: true });
    expect(row.cells[4].flagged).toBe(false);
    expect(row.drifted).toBe(true);
    expect(row.snippet).toBe("{ heightFt: 7.5, widthIn: 49, quantities: { 3: 20, 4: 12, 4.75: 16, 6: 16, 8: 8, 12: 2 } },");
  });
});
