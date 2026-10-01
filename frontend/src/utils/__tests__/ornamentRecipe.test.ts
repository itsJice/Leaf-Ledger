import { describe, expect, it } from "vitest";
import {
  COLORS,
  FINISHES,
  GOLDEN_RECIPES,
  ORNAMENT_OPTIONS,
  WIDTH_PROFILES,
  applySizeSwap,
  buildLeafLedgerRecipe,
  buildOrderLines,
  buildRecipe,
  buildRecipeFor,
  clampColorCount,
  coverageDensity,
  defaultWidthForHeight,
  enhancerAllocation,
  enhancerCount,
  enhancerLookup,
  ENHANCER_CARD,
  ENHANCER_CARD_HEIGHTS,
  splitAcrossColors,
  leafLedgerMinTopCount,
  leafLedgerSizes,
  leafLedgerSource,
  leafLedgerTopSize,
  packSummary,
  profileForWidth,
  recipeBucketNumber,
  sizeSwapSuggestions,
  totalColorPct,
  treeConfigLabel,
  treeDensityImage,
  treeSurfaceArea,
  widthForProfile,
  type RecipeResult,
  type WidthProfile,
} from "../ornamentRecipe";

/** [size, quantity] pairs — compact form of a recipe's lines. */
const pairs = (r: RecipeResult) => r.lines.map((l) => [l.option.size, l.quantity]);
const opt = (size: number) => ORNAMENT_OPTIONS.find((o) => o.size === size)!;

describe("constants", () => {
  it("pins table sizes and shapes", () => {
    expect(ORNAMENT_OPTIONS.map((o) => o.display)).toEqual(["1", "1.6", "2.4", "2.75", "3", "4", "4.75", "6", "8", "10", "12", "15.75", "20", "24"]);
    expect(GOLDEN_RECIPES.map((g) => [g.heightFt, g.widthIn])).toEqual([[7.5, 49], [8, 52], [10, 65], [12, 78]]);
    // The designers' enhancer card, every height and profile (confirmed 2026-10-01).
    expect(ENHANCER_CARD_HEIGHTS).toEqual([7, 7.5, 8, 9, 10, 12, 14, 15]);
    expect(ENHANCER_CARD).toEqual({
      pencil: [8, 10, 14, 20, 24, 28, 32, 36],
      slim: [10, 12, 16, 22, 26, 30, 34, 38],
      standard: [18, 20, 24, 30, 32, 36, 40, 44],
      full: [22, 24, 28, 34, 36, 40, 44, 48],
    });
    expect(Object.keys(WIDTH_PROFILES)).toEqual(["pencil", "slim", "standard", "full"]);
    // FIX: the doc comment said "All 58"; no rules doc names a 58th color,
    // so the comment (in ornamentRecipe.ts and ornamentRecipe.md) was
    // corrected to 57 rather than adding an unsourced entry.
    expect(COLORS).toHaveLength(57);
    expect(FINISHES.map((f) => f.code).join("")).toBe("SMGPQCXFIRVLBT");
  });
});

describe("treeSurfaceArea", () => {
  it("computes the cone area for representative trees", () => {
    expect(treeSurfaceArea(7.5, 55)).toBe(4929.005242832776);
    expect(treeSurfaceArea(9, 58)).toBe(6507.896192578912);
    expect(treeSurfaceArea(12, 78)).toBe(14244.086576271362);
    expect(treeSurfaceArea(20, 130)).toBe(48686.50076594007);
  });

  it("is 0 for too-small/zero/negative trees and NaN for NaN", () => {
    expect(treeSurfaceArea(0, 0)).toBe(0);
    expect(treeSurfaceArea(-3, 40)).toBe(0);
    expect(treeSurfaceArea(7.5, 20)).toBe(0);
    expect(treeSurfaceArea(1.5, 40)).toBe(0);
    expect(treeSurfaceArea(NaN, 50)).toBeNaN();
  });
});

describe("recipeBucketNumber", () => {
  it("maps coverage to 1-based buckets", () => {
    expect([0, 999, 1000, 4999, 5000, 9000, 13000, 18000, 24999, 25000, -1, NaN].map(recipeBucketNumber)).toEqual([1, 1, 2, 2, 3, 4, 5, 6, 6, 7, 1, 7]);
  });
});

describe("buildRecipe (Vickerman)", () => {
  it("matches the live Vickerman calculator for 7.5 ft x 55 in", () => {
    const r = buildRecipe(7.5, 55);
    expect(r.surfaceArea).toBe(4929.005242832776);
    expect(r.recipeCoverage).toBe(1971.6020971331106);
    expect(r.bucketNumber).toBe(2);
    expect(pairs(r)).toEqual([[3, 42], [4, 41], [4.75, 21], [6, 10]]);
  });

  it("pins representative sizes across buckets", () => {
    expect([pairs(buildRecipe(6, 39)), buildRecipe(6, 39).bucketNumber]).toEqual([[[2.4, 25], [3, 28], [4, 11], [4.75, 6]], 1]);
    expect([pairs(buildRecipe(12, 78)), buildRecipe(12, 78).bucketNumber]).toEqual([[[4, 68], [4.75, 84], [6, 38], [8, 17]], 3]);
    expect([pairs(buildRecipe(15, 98)), buildRecipe(15, 98).bucketNumber]).toEqual([[[4.75, 84], [6, 93], [8, 37], [10, 19]], 4]);
    expect([pairs(buildRecipe(20, 130)), buildRecipe(20, 130).bucketNumber]).toEqual([[[8, 58], [10, 65], [12, 32], [15.75, 15]], 6]);
  });

  it("keeps zero-quantity lines (tiny tree, zero coverage)", () => {
    expect(pairs(buildRecipe(2, 21))).toEqual([[2.4, 0], [3, 0], [4, 0], [4.75, 0]]);
    expect(pairs(buildRecipe(7.5, 55, 0))).toEqual([[2.4, 0], [3, 0], [4, 0], [4.75, 0]]);
  });

  it("returns an empty result for zero/negative trees", () => {
    const empty = { surfaceArea: 0, recipeCoverage: 0, bucketNumber: 0, lines: [] };
    expect(buildRecipe(0, 0)).toEqual(empty);
    expect(buildRecipe(-3, 40)).toEqual(empty);
  });

  // FIX: NaN/non-finite dimensions used to slip past the `surfaceArea <= 0`
  // guard (NaN <= 0 is false) and throw a TypeError inside the bucket lookup.
  it("treats non-finite dimensions as invalid, same as 0", () => {
    const empty = { surfaceArea: 0, recipeCoverage: 0, bucketNumber: 0, lines: [] };
    expect(buildRecipe(NaN, 50)).toEqual(empty);
    expect(buildRecipe(7.5, NaN)).toEqual(empty);
    expect(buildRecipe(Infinity, 50)).toEqual(empty);
  });
});

describe("buildLeafLedgerRecipe", () => {
  it("golden table row at its own width is returned verbatim (odd counts kept)", () => {
    expect(pairs(buildLeafLedgerRecipe(7.5, 49))).toEqual([[3, 25], [4, 12], [4.75, 16], [6, 16], [8, 8]]);
    expect(pairs(buildLeafLedgerRecipe(10, 65))).toEqual([[4, 36], [4.75, 36], [6, 30], [8, 20], [10, 12]]);
    expect(pairs(buildLeafLedgerRecipe(12, 78))).toEqual([[4.75, 40], [6, 30], [8, 17], [10, 15], [12, 10]]);
  });

  it("scales a table row by width and rounds to even", () => {
    expect(pairs(buildLeafLedgerRecipe(7.5, 55))).toEqual([[3, 32], [4, 16], [4.75, 20], [6, 20], [8, 10]]);
  });

  it("interpolates between rows", () => {
    expect(pairs(buildLeafLedgerRecipe(9, 58))).toEqual([[4, 30], [4.75, 32], [6, 24], [8, 14], [10, 10]]);
  });

  it("uses the top-heavy formula beyond the table", () => {
    expect(pairs(buildLeafLedgerRecipe(6, 39))).toEqual([[2.4, 18], [3, 14], [4, 10], [4.75, 8], [6, 8]]);
    expect(pairs(buildLeafLedgerRecipe(15, 98))).toEqual([[6, 38], [8, 28], [10, 20], [12, 18], [15.75, 10]]);
    expect(pairs(buildLeafLedgerRecipe(20, 130))).toEqual([[8, 42], [10, 34], [12, 28], [15.75, 20], [20, 12]]);
    expect(pairs(buildLeafLedgerRecipe(2, 21))).toEqual([[2.4, 8]]);
  });

  it("applies style, color count and coverage modifiers", () => {
    expect(pairs(buildLeafLedgerRecipe(9, 58, 0.4, { style: "contemporary", colorCount: 3 }))).toEqual([[4, 21], [4.75, 24], [6, 18], [8, 15], [10, 9]]);
    expect(pairs(buildLeafLedgerRecipe(10, 65, 0.6, { colorCount: 1 }))).toEqual([[4, 54], [4.75, 54], [6, 45], [8, 30], [10, 18]]);
    expect(buildLeafLedgerRecipe(10, 65, 0).lines).toEqual([]);
  });

  it("returns an empty result for zero/negative trees", () => {
    expect(buildLeafLedgerRecipe(0, 0)).toEqual({ surfaceArea: 0, recipeCoverage: 0, bucketNumber: 0, lines: [] });
    expect(buildLeafLedgerRecipe(-3, 40).lines).toEqual([]);
  });

  // FIX: a non-finite height used to produce NaN surfaceArea/recipeCoverage
  // instead of the same empty result a 0 tree returns.
  it("treats non-finite dimensions as invalid, same as 0", () => {
    const empty = { surfaceArea: 0, recipeCoverage: 0, bucketNumber: 0, lines: [] };
    expect(buildLeafLedgerRecipe(NaN, 50)).toEqual(empty);
    expect(buildLeafLedgerRecipe(7.5, NaN)).toEqual(empty);
  });

  it("buildRecipeFor dispatches on mode", () => {
    expect(pairs(buildRecipeFor("vickerman", 7.5, 55))).toEqual(pairs(buildRecipe(7.5, 55)));
    expect(pairs(buildRecipeFor("leafledger", 9, 58, 0.4, { colorCount: 3 }))).toEqual(pairs(buildLeafLedgerRecipe(9, 58, 0.4, { colorCount: 3 })));
  });
});

describe("leaf & ledger helpers", () => {
  it("clampColorCount", () => {
    expect([undefined, 0, 1, 2.4, 2.5, 3, 4, 9, -1, NaN, Infinity].map((c) => clampColorCount(c))).toEqual([2, 1, 1, 2, 3, 3, 4, 4, 1, 2, 2]);
  });

  it("leafLedgerMinTopCount rounds 8 up to the color count", () => {
    expect([1, 2, 3, 4, 5].map((c) => leafLedgerMinTopCount(c))).toEqual([8, 8, 9, 8, 8]);
    expect(leafLedgerMinTopCount()).toBe(8);
  });

  it("leafLedgerTopSize / leafLedgerSizes", () => {
    expect([0, -3, 6, 7.5, 8, 9, 12, 15, 20, 25].map(leafLedgerTopSize)).toEqual([2.4, 2.4, 6, 8, 10, 10, 12, 15.75, 20, 20]);
    expect(leafLedgerSizes(7.5)).toEqual([3, 4, 4.75, 6, 8]);
    expect(leafLedgerSizes(9)).toEqual([4, 4.75, 6, 8, 10]);
    expect(leafLedgerSizes(12)).toEqual([4.75, 6, 8, 10, 12]);
    expect(leafLedgerSizes(0)).toEqual([2.4]);
  });

  it("leafLedgerSource", () => {
    expect(leafLedgerSource(7.5)).toEqual({ kind: "table", heightFt: 7.5 });
    expect(leafLedgerSource(7.505)).toEqual({ kind: "table", heightFt: 7.5 });
    expect(leafLedgerSource(9)).toEqual({ kind: "interpolated", lowerFt: 8, upperFt: 10 });
    expect(leafLedgerSource(6)).toEqual({ kind: "formula", from: "below" });
    expect(leafLedgerSource(15)).toEqual({ kind: "formula", from: "above" });
    expect(leafLedgerSource(NaN)).toEqual({ kind: "formula", from: "below" });
  });

  it("width helpers", () => {
    expect([7.5, 9, 12, 0, -1].map(defaultWidthForHeight)).toEqual([49, 59, 78, 0, -6]);
    expect(defaultWidthForHeight(NaN)).toBeNaN();
    expect((["pencil", "slim", "standard", "full"] as const).map((p) => widthForProfile(9, p))).toEqual([38, 50, 59, 70]);
    expect((["pencil", "slim", "standard", "full"] as const).map((p) => widthForProfile(12, p))).toEqual([50, 67, 78, 94]);
    expect([profileForWidth(7.5, 49), profileForWidth(7.5, 55), profileForWidth(7.5, 32), profileForWidth(7.5, 42)]).toEqual(["standard", "full", "pencil", "slim"]);
    expect([profileForWidth(10, 50), profileForWidth(0, 0), profileForWidth(NaN, 50), profileForWidth(-3, 40)]).toEqual([null, null, null, null]);
  });
});

describe("splitAcrossColors", () => {
  it("splits a size's quantity evenly, remainder to the first colors", () => {
    expect(splitAcrossColors(30, 3)).toEqual([10, 10, 10]);
    expect(splitAcrossColors(31, 3)).toEqual([11, 10, 10]);
    expect(splitAcrossColors(17, 2)).toEqual([9, 8]);
    expect(splitAcrossColors(25, 1)).toEqual([25]);
    expect(splitAcrossColors(0, 2)).toEqual([0, 0]);
  });
});

describe("enhancers", () => {
  it("returns the designer's card verbatim for every height and profile", () => {
    for (const profile of Object.keys(ENHANCER_CARD) as WidthProfile[]) {
      ENHANCER_CARD_HEIGHTS.forEach((h, i) => {
        const e = enhancerLookup(h, widthForProfile(h, profile));
        expect([h, profile, e.count, e.source.kind]).toEqual([h, profile, ENHANCER_CARD[profile][i], "card"]);
      });
    }
    // Spot-check the card itself (designer, 2026-10-01).
    expect(enhancerCount(9, widthForProfile(9, "slim"))).toBe(22);
    expect(enhancerCount(14, widthForProfile(14, "standard"))).toBe(40);
    expect(enhancerCount(15, widthForProfile(15, "full"))).toBe(48);
    expect(enhancerCount(7, widthForProfile(7, "pencil"))).toBe(8);
  });

  it("enhancerLookup covers every source kind", () => {
    const view = (h: number, w: number, c?: number) => {
      const e = enhancerLookup(h, w, c);
      return [e.count, e.source.kind];
    };
    // Between card heights, same profile: a straight line, rounded to even.
    expect(view(11, 72)).toEqual([34, "interpolated"]);
    expect(view(13, 73)).toEqual([32, "interpolated"]);
    // Beyond the card: its end trend (+4 a foot) continued.
    expect(view(6, 39)).toEqual([14, "extrapolated"]);
    expect(view(16, 125)).toEqual([52, "extrapolated"]);
    // A custom width: blended between the profiles either side, or the end profile past them.
    expect(view(9, 54)).toEqual([26, "customWidth"]);
    expect(view(9, 63)).toEqual([32, "customWidth"]);
    expect(view(9, 30)).toEqual([20, "customWidth"]);
    expect(view(9, 90)).toEqual([34, "customWidth"]);
    // No usable dimensions.
    expect(view(0, 0)).toEqual([0, "none"]);
    expect(view(-3, 40)).toEqual([0, "none"]);
  });

  it("enhancerCount rounds computed counts to the color count", () => {
    expect([enhancerCount(11, 72, 3), enhancerCount(7.25, 47), enhancerCount(18, 76)]).toEqual([33, 20, 48]);
  });

  // A direct card hit returns the designers' count verbatim, unrounded, even when
  // it isn't a multiple of the color count (32 with 3 colors).
  it("a direct card hit returns the designer's count verbatim, not rounded to the color count", () => {
    expect(enhancerCount(10, 65, 3)).toBe(32);
  });

  // FIX: a non-finite height used to fall through every lookup branch to
  // `row.widthMinIn` on an undefined row, throwing a TypeError.
  it("treats a non-finite height/width as 0", () => {
    expect(enhancerLookup(NaN, 50)).toEqual(enhancerLookup(0, 50));
    expect(enhancerLookup(10, NaN)).toEqual(enhancerLookup(10, 0));
  });

  it("enhancerAllocation splits small sizes half into enhancers", () => {
    const lines = buildLeafLedgerRecipe(9, 58).lines;
    const view = (a: ReturnType<typeof enhancerAllocation>) => a.map((x) => [x.option.size, x.quantity, x.loose, x.inEnhancers]);
    expect(view(enhancerAllocation(lines, 9))).toEqual([[4, 30, 16, 14], [4.75, 32, 16, 16], [6, 24, 24, 0], [8, 14, 14, 0], [10, 10, 10, 0]]);
    expect(view(enhancerAllocation(lines, 9, 0))).toEqual([[4, 30, 30, 0], [4.75, 32, 32, 0], [6, 24, 24, 0], [8, 14, 14, 0], [10, 10, 10, 0]]);
    expect(view(enhancerAllocation(lines, 9, 18, 3))).toEqual([[4, 30, 15, 15], [4.75, 32, 17, 15], [6, 24, 24, 0], [8, 14, 14, 0], [10, 10, 10, 0]]);
  });
});

describe("coverageDensity / packSummary / treeDensityImage", () => {
  it("coverageDensity", () => {
    expect(coverageDensity(7.5, 55, new Map([[3, 42], [4, 41], [4.75, 21], [6, 10]]))).toBe(40);
    expect(coverageDensity(7.5, 55, new Map())).toBe(0);
    expect(coverageDensity(0, 0, new Map([[3, 1]]))).toBe(0);
    expect(coverageDensity(7.5, 55, new Map([[24, 1000]]))).toBe(100);
  });

  it("packSummary", () => {
    expect([packSummary(opt(3), 42), packSummary(opt(3), 12), packSummary(opt(4), 7), packSummary(opt(8), 5), packSummary(opt(3), 0), packSummary(opt(3), NaN)]).toEqual([
      "4 packs of 12",
      "1 pack of 12",
      "2 packs of 6",
      "5 each",
      "",
      "",
    ]);
  });

  // FIX: a negative quantity used to pass the `!quantity` guard (a negative
  // number is truthy) and report "0 packs of 12" via Math.ceil rounding
  // toward zero.
  it("packSummary on a negative quantity returns '' like 0 does", () => {
    expect(packSummary(opt(3), -5)).toBe("");
  });

  it("treeDensityImage clamps to 0..90 in 5% steps", () => {
    expect([-10, 0, 4, 5, 42, 90, 95, 200].map(treeDensityImage)).toEqual([
      "/ornament-calculator/tree_density_0.jpg",
      "/ornament-calculator/tree_density_0.jpg",
      "/ornament-calculator/tree_density_0.jpg",
      "/ornament-calculator/tree_density_5.jpg",
      "/ornament-calculator/tree_density_40.jpg",
      "/ornament-calculator/tree_density_90.jpg",
      "/ornament-calculator/tree_density_90.jpg",
      "/ornament-calculator/tree_density_90.jpg",
    ]);
  });

  // FIX: NaN used to slip past both clamp checks (`NaN > 90` and `NaN < 0`
  // are both false) straight into the filename.
  it("treeDensityImage(NaN) clamps like an out-of-range value, to 0", () => {
    expect(treeDensityImage(NaN)).toBe(treeDensityImage(-10));
    expect(treeDensityImage(NaN)).toBe("/ornament-calculator/tree_density_0.jpg");
  });
});

describe("purchase list helpers", () => {
  it("treeConfigLabel", () => {
    expect(treeConfigLabel({ heightFt: 9, profile: "standard", style: "traditional", colorNames: ["Red", "Gold"] })).toBe("9 ft standard · traditional · Red + Gold");
    expect(treeConfigLabel({ heightFt: 7.5, widthIn: 55, colorNames: ["Red", " ", ""] })).toBe("7.5 ft × 55 in · Red");
    expect(treeConfigLabel({ heightFt: 12 })).toBe("12 ft");
    expect(treeConfigLabel({ widthIn: 40 })).toBe("40 in wide");
    expect(treeConfigLabel({ heightFt: 0, widthIn: 0, style: "contemporary" })).toBe("contemporary");
    expect(treeConfigLabel({})).toBe("");
  });

  const recipe = [4, 4.75, 6, 8].map((s, i) => ({ option: opt(s), quantity: [36, 36, 30, 20][i] }));
  const prices = new Map([[4, 1.0], [4.75, 1.3], [6, 3.0], [8, 4]]);

  it("sizeSwapSuggestions finds adjacent swaps within tolerance", () => {
    expect(sizeSwapSuggestions(recipe, prices)).toEqual([
      { fromSize: 4, toSize: 4.75, fromQty: 36, toQty: 26, fromCostPerSqIn: 0.07957747154594776, toCostPerSqIn: 0.07336117044457455, extraCost: -2.1999999999999957 },
      { fromSize: 6, toSize: 8, fromQty: 30, toQty: 16, fromCostPerSqIn: 0.10610329539459701, toCostPerSqIn: 0.07957747154594776, extraCost: -26 },
    ]);
    expect(sizeSwapSuggestions(recipe, prices, 0.15, 3).map((s) => [s.toQty, s.extraCost])).toEqual([[27, -0.8999999999999986], [18, -18]]);
  });

  it("sizeSwapSuggestions skips missing prices, pricier larger sizes and empty input", () => {
    expect(sizeSwapSuggestions(recipe, new Map([[4, 1], [4.75, 5]]))).toEqual([]);
    expect(sizeSwapSuggestions(recipe, new Map())).toEqual([]);
    expect(sizeSwapSuggestions([], prices)).toEqual([]);
  });

  it("applySizeSwap zeroes the smaller size and adds to the larger ('' counts as 0)", () => {
    const [swap] = sizeSwapSuggestions(recipe, prices);
    expect(applySizeSwap({ 4: 36, 4.75: "", 6: 30 } as Record<number, number | "">, swap)).toEqual({ 4: 0, 4.75: 26, 6: 30 });
    expect(applySizeSwap({ 4: 36, 4.75: 10 }, swap)).toEqual({ 4: 0, 4.75: 36 });
  });
});

describe("SKUs and order lines", () => {
  it("buildOrderLines expands, merges duplicates, skips invalid blocks, sorts", () => {
    const lines = buildOrderLines(new Map([["08", 42], ["10", 41], ["12", 21]]), [
      { id: 1, colorCode: "03", finishCode: "S", sharePct: 50 },
      { id: 2, colorCode: "08", finishCode: "M", sharePct: 30 },
      { id: 3, colorCode: "03", finishCode: "S", sharePct: 20 },
      { id: 4, colorCode: "zz", finishCode: "Y", sharePct: 10 },
      { id: 5, colorCode: "", finishCode: "S", sharePct: 50 },
      { id: 6, colorCode: "11", finishCode: "S", sharePct: 0 },
    ]);
    expect(lines.map((l) => [l.sizeCode, l.color, l.finish, l.quantity])).toEqual([
      ["08", "Gold", "Matte", 13],
      ["08", "Red", "Shiny", 29],
      ["08", "zz", "Y", 4],
      ["10", "Gold", "Matte", 12],
      ["10", "Red", "Shiny", 29],
      ["10", "zz", "Y", 4],
      ["12", "Gold", "Matte", 6],
      ["12", "Red", "Shiny", 15],
      ["12", "zz", "Y", 2],
    ]);
    expect(lines[0]).toEqual({ size: 3, sizeCode: "08", color: "Gold", colorCode: "08", finish: "Matte", finishCode: "M", quantity: 13 });
    expect(buildOrderLines(new Map(), [{ id: 1, colorCode: "03", finishCode: "S", sharePct: 100 }])).toEqual([]);
  });

  it("totalColorPct treats falsy shares as 0", () => {
    expect(totalColorPct([])).toBe(0);
    expect(
      totalColorPct([
        { id: 1, colorCode: "", finishCode: "", sharePct: 40 },
        { id: 2, colorCode: "", finishCode: "", sharePct: NaN },
        { id: 3, colorCode: "", finishCode: "", sharePct: 35.5 },
      ]),
    ).toBe(75.5);
  });
});
