import { describe, expect, it } from "vitest";
import {
  BIG_ORNAMENT_IN,
  BIG_ORNAMENT_TOP_SHARE,
  buildTreeInstallLayout,
  checkTreeInstallLayout,
  enhancerLetters,
  enhancersPerLine,
  treeInstallCounts,
  type TreeInstallCounts,
  type TreeInstallLayout,
} from "utils/treeInstallLayout";
import { buildLeafLedgerRecipe, enhancerAllocation, enhancerLookup, widthForProfile } from "utils/ornamentRecipe";

// Laying out a full tree takes a second or two; CI runners are slower.
const SLOW = 60_000;

// The Tree Install mockup's placement: every rule the designers gave (10/27/2026),
// checked from scratch on the finished layout, in inches on the unrolled cone.

function layoutFor(heightFt: number, colorCount = 2): { counts: TreeInstallCounts; layout: TreeInstallLayout } {
  const widthIn = widthForProfile(heightFt, "standard");
  const counts = treeInstallCounts(heightFt, widthIn, { colorCount, wholePacks: true });
  const layout = buildTreeInstallLayout({
    heightFt,
    widthIn,
    colorCount,
    enhancers: counts.enhancers,
    loose: counts.loose,
    inEnhancers: counts.inEnhancers,
  });
  return { counts, layout };
}

describe("treeInstallCounts", () => {
  it("is the calculator's engine, unchanged", () => {
    for (const h of [7.5, 9, 12]) {
      for (const colorCount of [2, 3]) {
        const w = widthForProfile(h, "standard");
        const c = treeInstallCounts(h, w, { colorCount });
        const recipe = buildLeafLedgerRecipe(h, w, 0.4, { colorCount });
        const enh = enhancerLookup(h, w, colorCount).count;
        expect(c.enhancers).toBe(enh);
        expect(c.lines).toEqual(enhancerAllocation(recipe.lines, h, enh, colorCount));
        expect(c.totalOrnaments).toBe(recipe.lines.reduce((s, l) => s + l.quantity, 0));
      }
    }
  });

  it("keeps the designers' approved rows and enhancer card verbatim", () => {
    // 7.5 ft table row (traditional, 2 colors, table width) and the card's 20 enhancers
    const c = treeInstallCounts(7.5, 49, { colorCount: 2 });
    expect(Object.fromEntries(c.lines.map((l) => [l.option.size, l.quantity]))).toEqual({ 3: 25, 4: 12, 4.75: 16, 6: 16, 8: 8 });
    expect(c.enhancers).toBe(20);
    // 12 ft standard: 36 enhancers on the card
    expect(treeInstallCounts(12, 78).enhancers).toBe(36);
  });

  it("splits loose and inside-enhancer pieces so they add back up", () => {
    const c = treeInstallCounts(9, widthForProfile(9, "standard"), { colorCount: 2, wholePacks: true });
    for (const l of c.lines) {
      expect((c.loose[l.option.size] ?? 0) + (c.inEnhancers[l.option.size] ?? 0)).toBe(l.quantity);
    }
  });
});

describe("enhancers on six lines", () => {
  it("spreads the count over the lines", () => {
    expect(enhancersPerLine(30)).toEqual([5, 5, 5, 5, 5, 5]);
    expect(enhancersPerLine(20).reduce((a, b) => a + b, 0)).toBe(20);
    expect(Math.max(...enhancersPerLine(20)) - Math.min(...enhancersPerLine(20))).toBe(1);
  });

  it("alternates A and B on every line, half and half overall", () => {
    for (const total of [10, 12, 20, 22, 24, 30, 36]) {
      const letters = enhancerLetters(enhancersPerLine(total));
      for (const line of letters) for (let i = 1; i < line.length; i++) expect(line[i]).not.toBe(line[i - 1]);
      const flat = letters.flat();
      expect(flat.filter((l) => l === "A").length).toBe(total / 2);
    }
  });
});

describe.each([7.5, 9, 12])("%s ft standard tree", (heightFt) => {
  const { counts, layout } = layoutFor(heightFt);

  it("never stacks pieces on the same spot, never lets same colors touch", () => {
    expect(layout.check.stacks).toBe(0);
    expect(layout.check.enhancerTouches).toBe(0);
    expect(layout.check.colorTouches).toBe(0);
    // and the independent re-check agrees
    const again = checkTreeInstallLayout(layout, { colorCount: 2 });
    expect(again.stacks).toBe(0);
    expect(again.enhancerTouches).toBe(0);
    expect(again.colorTouches).toBe(0);
  });

  it("keeps 8\" and bigger out of the top 40%", () => {
    expect(layout.check.bigInTop).toBe(0);
    for (const o of layout.ornaments) if (o.size >= BIG_ORNAMENT_IN) expect(o.t).toBeGreaterThanOrEqual(BIG_ORNAMENT_TOP_SHARE);
  });

  it("alternates A and B along each line", () => {
    expect(layout.check.abAlternates).toBe(true);
  });

  it("places the calculator's counts, or says plainly what didn't fit", () => {
    const placedEnh = layout.enhancers.length;
    expect(placedEnh + layout.enhancersUnplaced).toBe(counts.enhancers);
    for (const [size, n] of Object.entries(counts.loose)) {
      const placed = layout.ornaments.filter((o) => o.size === Number(size)).length;
      expect(placed + (layout.unplaced[Number(size)] ?? 0)).toBe(n);
    }
    // nothing placed that the calculator didn't ask for
    for (const o of layout.ornaments) expect(counts.loose[o.size]).toBeGreaterThan(0);
    // every piece meant for the enhancers is inside one
    const inside = layout.enhancers.flatMap((e) => e.inside).length;
    if (layout.enhancersUnplaced === 0) {
      expect(inside).toBe(Object.values(counts.inEnhancers).reduce((a, b) => a + b, 0));
    }
    if (layout.fits) expect(layout.problems.filter((p) => !p.startsWith("One color"))).toEqual([]);
    else expect(layout.problems.length).toBeGreaterThan(0);
  });

  it("is the same tree every time", () => {
    const again = layoutFor(heightFt).layout;
    expect(again.ornaments).toEqual(layout.ornaments);
    expect(again.enhancers).toEqual(layout.enhancers);
  }, SLOW);
});

describe("what fits", () => {
  it("fits a 12 ft standard tree completely", () => {
    const { counts, layout } = layoutFor(12);
    expect(layout.fits).toBe(true);
    expect(layout.enhancers.length).toBe(counts.enhancers);
    for (const [size, n] of Object.entries(counts.loose)) {
      expect(layout.ornaments.filter((o) => o.size === Number(size)).length).toBe(n);
    }
  }, SLOW);

  it("fits a 7.5 ft standard tree, the calculator's default, at 2 and 3 colors", () => {
    expect(layoutFor(7.5, 2).layout.fits).toBe(true);
    expect(layoutFor(7.5, 3).layout.fits).toBe(true);
  }, SLOW);

  it("fits a 9 ft standard tree too: pieces may touch and overlap, never stack", () => {
    const { layout } = layoutFor(9);
    expect(layout.fits).toBe(true);
    expect(layout.check.stacks).toBe(0);
  }, SLOW);

  it("names the one-color case instead of pretending the color rule holds", () => {
    const { layout } = layoutFor(7.5, 1);
    expect(layout.problems.some((p) => p.startsWith("One color"))).toBe(true);
    expect(layout.check.stacks).toBe(0);
  }, SLOW);
});
