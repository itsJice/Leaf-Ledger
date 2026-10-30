import { describe, expect, it } from "vitest";
import {
  BIG_ORNAMENT_IN,
  ONEWAY_INPUTS,
  buildOneway,
  buildTreeInstallLayout,
  enhancersPerLine,
  treeInstallCounts,
  type LayoutEnhancer,
  type LayoutOrnament,
  type TreeInstallCounts,
  type TreeInstallLayout,
} from "utils/treeInstallLayout";
import { buildLeafLedgerRecipe, enhancerAllocation, enhancerLookup, widthForProfile } from "utils/ornamentRecipe";
import golden from "./fixtures/oneway-9ft-layout.json";

// The Tree Install mockup's placement: a port of tree-design-map/gen.js buildOneway
// (designer-approved, git d0e15dd), checked piece for piece against its output, then
// the same rules on other trees with the calculator's counts.

// Laying out a full tree takes a second or two; CI runners are slower.
const SLOW = 120_000;

const ornamentsOf = (L: TreeInstallLayout) => L.items.filter((i): i is LayoutOrnament => i.kind === "orn");
const bowsOf = (L: TreeInstallLayout) => L.items.filter((i): i is LayoutEnhancer => i.kind === "enh");

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

describe("buildOneway: the designer-approved 9 ft tree", () => {
  it(
    "reproduces tree-design-map/oneway/layout.js piece for piece",
    () => {
      const L = buildOneway();
      expect(L.items.length).toBe(golden.items.length);
      L.items.forEach((it, i) => {
        const g = golden.items[i] as Record<string, unknown>;
        expect(it.kind).toBe(g.kind);
        expect(it.t).toBeCloseTo(g.t as number, 4);
        expect(it.ang).toBeCloseTo(g.ang as number, 4);
        if (it.kind === "orn") {
          expect(it.inch).toBe(g.inch);
          expect(it.color).toBe(g.color);
        } else {
          expect(it.letter).toBe(g.letter);
          expect(it.line).toBe(g.line);
          expect(it.tilt).toBe(g.tilt);
        }
      });
      // and the same checks gen.js printed
      expect(L.check).toEqual(golden.check);
    },
    SLOW
  );

  it("keeps gen.js's settings", () => {
    expect(ONEWAY_INPUTS.seed).toBe(7);
    expect(ONEWAY_INPUTS.swoop).toBe(3.2);
    expect(ONEWAY_INPUTS.bowR * 2).toBe(11);
    expect(ONEWAY_INPUTS.topBowEdit).toEqual({ newT: 0.945 });
  });
});

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

  it("keeps the designers' approved row and enhancer card verbatim", () => {
    const c = treeInstallCounts(7.5, 49, { colorCount: 2 });
    expect(Object.fromEntries(c.lines.map((l) => [l.option.size, l.quantity]))).toEqual({ 3: 25, 4: 12, 4.75: 16, 6: 16, 8: 8 });
    expect(c.enhancers).toBe(20);
    expect(treeInstallCounts(12, 78).enhancers).toBe(36);
  });
});

describe("bows on six lines", () => {
  it("spreads the count over the lines", () => {
    expect(enhancersPerLine(30)).toEqual([5, 5, 5, 5, 5, 5]);
    const twenty = enhancersPerLine(20);
    expect(twenty.reduce((a, b) => a + b, 0)).toBe(20);
    expect(Math.max(...twenty) - Math.min(...twenty)).toBe(1);
  });
});

describe.each([
  [7.5, 2],
  [7.5, 3],
  [9, 2],
  [9, 3],
  [12, 2],
  [12, 3],
])("%s ft standard tree, %s colors", (heightFt, colorCount) => {
  const { counts, layout } = layoutFor(heightFt, colorCount);
  const orn = ornamentsOf(layout);
  const bows = bowsOf(layout);

  it("places the calculator's exact counts", () => {
    expect(layout.fits).toBe(true);
    expect(bows.length).toBe(counts.enhancers);
    for (const [size, n] of Object.entries(counts.loose)) {
      expect(orn.filter((o) => o.inch === Number(size)).length).toBe(n);
    }
    expect(orn.length).toBe(Object.values(counts.loose).reduce((a, b) => a + b, 0));
  });

  it("never stacks two pieces on the same spot, never lets a color touch itself", () => {
    expect(layout.check.stacked).toBe(0);
    expect(layout.check.closestCenters).toBeGreaterThanOrEqual(0.6);
    expect(layout.check.colorClash).toBe(0);
  });

  it("keeps 8\" and bigger out of the top third", () => {
    expect(layout.check.bigTop).toBe(0);
    for (const o of orn) if (o.inch >= BIG_ORNAMENT_IN) expect(o.t).toBeGreaterThanOrEqual(1 / 3);
  });

  it("alternates A and B down every line, half and half overall", () => {
    for (let j = 0; j < 6; j++) {
      const line = bows.filter((b) => b.line === j).sort((a, b) => a.t - b.t);
      for (let i = 1; i < line.length; i++) expect(line[i].letter).not.toBe(line[i - 1].letter);
    }
    const a = bows.filter((b) => b.letter === "A").length;
    expect(Math.abs(a - (bows.length - a))).toBeLessThanOrEqual(1);
    if (bows.length % 2 === 0) expect(a).toBe(bows.length / 2);
  });

  it("keeps the top clear of bows and hangs them diagonally", () => {
    // the approved tree's highest bow sits at 0.34 of the height (odd lines)
    for (const b of bows) expect(b.t).toBeGreaterThanOrEqual(0.34 - 1e-9);
    for (const b of bows) {
      expect(b.tilt).toBeGreaterThanOrEqual(35);
      expect(b.tilt).toBeLessThanOrEqual(45);
    }
  });

  it(
    "is the same tree every time",
    () => {
      expect(layoutFor(heightFt, colorCount).layout.items).toEqual(layout.items);
    },
    SLOW
  );
});

describe("saying so plainly", () => {
  it(
    "names the one-color case instead of pretending the color rule holds",
    () => {
      const { layout } = layoutFor(7.5, 1);
      expect(layout.problems.some((p) => p.startsWith("One color"))).toBe(true);
      expect(layout.check.stacked).toBe(0);
    },
    SLOW
  );

  it(
    "says when a tree can't keep its colors apart (7 ft pencil, 3 colors)",
    () => {
      const w = widthForProfile(7, "pencil");
      const c = treeInstallCounts(7, w, { colorCount: 3, wholePacks: true });
      const L = buildTreeInstallLayout({ heightFt: 7, widthIn: w, colorCount: 3, enhancers: c.enhancers, loose: c.loose, inEnhancers: c.inEnhancers });
      expect(L.fits).toBe(false);
      expect(L.problems.join(" ")).toMatch(/own color/);
      expect(L.check.stacked).toBe(0);
    },
    SLOW
  );
});
