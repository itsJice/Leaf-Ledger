// Tree Install: where every enhancer and ornament goes on a tree, in real inches.
//
// A faithful port of the designer-approved layout in tree-design-map/gen.js
// (buildOneway, ONEWAY_INPUTS, the 10/28 top-bow edit and the 15 A / 15 B relabel;
// git d0e15dd). The same constants, seed and steps: for the 9 ft x 56 in standard
// tree in 3 colors it reproduces tree-design-map/oneway/layout.js piece for piece
// (see __tests__/treeInstallLayout.test.ts). Other trees use the same rules, with
// the calculator's counts (generalized: counts per line, sizes and zones).
//
// The final rules (designers + user, 10/27-10/28/2026):
// - Six swirl lines, all turning the same way, evenly spaced.
// - 11" round bows (enhancers) on the lines, hanging diagonally (35-45 deg) down
//   their line. Every other line sits half a step lower. Each line alternates A, B;
//   the tree is half A, half B (which letter is on top doesn't matter, balance does).
// - No bows at the very top: the tree is skinny there and the topper comes down,
//   so the topmost bow on every other line moves to the bottom of its line.
// - Pieces sit IN the tree, nestled into the branches: touching and overlapping are
//   fine, but never two pieces on the same spot (centers at least 60% of the
//   smaller piece's diameter apart).
// - No ornament within 4" of its own color. 8" and bigger only below the top third.
// - Counts are never decided here: they come from the Ornament Calculator's engine
//   (utils/ornamentRecipe.ts) through `treeInstallCounts`.

import {
  buildLeafLedgerRecipe,
  enhancerAllocation,
  enhancerLookup,
  leafLedgerMinTopCount,
  roundToWholePacks,
  splitAcrossColors,
  clampColorCount,
  RECIPE_TARGET_COVERAGE,
  type DesignStyle,
  type EnhancerLookup,
  type EnhancerAllocationLine,
} from "./ornamentRecipe";

// ---------------------------------------------------------------------------
// Counts: straight from the Ornament Calculator's engine
// ---------------------------------------------------------------------------

export interface TreeInstallCountOptions {
  style?: DesignStyle;
  colorCount?: number;
  /** Round to whole packs, as the calculator does by default. */
  wholePacks?: boolean;
}

export interface TreeInstallCounts {
  heightFt: number;
  widthIn: number;
  colorCount: number;
  enhancers: number;
  enhancerSource: EnhancerLookup["source"];
  /** Every size, split into loose-on-the-tree and inside-the-enhancers. */
  lines: EnhancerAllocationLine[];
  /** Size (in) -> pieces loose on the tree. */
  loose: Record<number, number>;
  /** Size (in) -> pieces inside the enhancers. */
  inEnhancers: Record<number, number>;
  totalOrnaments: number;
}

/**
 * The calculator's numbers for a tree, unchanged: the Leaf & Ledger recipe at the
 * table's 40% (whole packs when asked, like the calculator's default), the
 * enhancer card count, and the loose vs inside-enhancer split.
 */
export function treeInstallCounts(
  heightFt: number,
  widthIn: number,
  options: TreeInstallCountOptions = {}
): TreeInstallCounts {
  const colorCount = clampColorCount(options.colorCount);
  const recipe = buildLeafLedgerRecipe(heightFt, widthIn, RECIPE_TARGET_COVERAGE, {
    style: options.style ?? "traditional",
    colorCount,
  });
  let lines = recipe.lines;
  if (options.wholePacks) {
    const sized = new Map(lines.map((l) => [l.option.size, l.quantity] as [number, number]));
    const rounded = roundToWholePacks(sized, colorCount, leafLedgerMinTopCount(colorCount)).quantities;
    lines = lines
      .map((l) => ({ option: l.option, quantity: rounded.get(l.option.size) ?? 0 }))
      .filter((l) => l.quantity > 0);
  }
  const lookup = enhancerLookup(heightFt, widthIn, colorCount);
  const alloc = enhancerAllocation(lines, heightFt, lookup.count, colorCount);
  const loose: Record<number, number> = {};
  const inEnhancers: Record<number, number> = {};
  for (const l of alloc) {
    if (l.loose > 0) loose[l.option.size] = l.loose;
    if (l.inEnhancers > 0) inEnhancers[l.option.size] = l.inEnhancers;
  }
  return {
    heightFt,
    widthIn,
    colorCount,
    enhancers: lookup.count,
    enhancerSource: lookup.source,
    lines: alloc,
    loose,
    inEnhancers,
    totalOrnaments: alloc.reduce((sum, l) => sum + l.quantity, 0),
  };
}

// ---------------------------------------------------------------------------
// Layout: buildOneway, ported from tree-design-map/gen.js
// ---------------------------------------------------------------------------

/** Rows for the build-it-row-by-row slider (gen.js: every 0.04 of the height from 0.13). */
const ROW_START = 0.13;
const ROW_STEP = 0.04;
/** Ornaments this size and up stay out of the top third. */
export const BIG_ORNAMENT_IN = 8;
export const BIG_ORNAMENT_TOP_SHARE = 1 / 3;
/** The bow cluster's diameter, in. */
export const BOW_IN = 11;

export interface OnewayInputs {
  heightFt: number;
  widthIn: number;
  /** Base radius / height. */
  R: number;
  colors: number;
  enhancers: number;
  /** Size (in) -> loose ornaments. */
  loose: Record<number, number>;
  /** Size (in) -> ornaments tucked inside the enhancers (not placed). */
  inEnhancers: Record<number, number>;
  lines: number;
  /** Radians a swirl line turns per unit of t, from t0. */
  swoop: number;
  t0: number;
  /** [first, last] bow on even lines, odd lines (share of height from the tip). */
  enhT: [[number, number], [number, number]];
  /** Bow cluster radius, in. */
  bowR: number;
  /** Min clear space between two ornaments, in (negative = may nestle/touch). */
  gap: number;
  /** Min clear space ornament to bow, in. */
  bowGap: number;
  /** The relax pass evens spacing toward this much room. */
  relaxGap: number;
  /** Ornaments may tuck into a bow's open corners. */
  nestBows: boolean;
  /** Never stacked: centers at least this x the smaller diameter apart. */
  stackFrac: number;
  /** Size (in) -> [lo, hi] share of height its center may sit at. */
  zone: Record<number, [number, number]>;
  /** Same color never within this many inches (edge to edge). */
  touch: number;
  tiltMin: number;
  tiltMax: number;
  /** 3D: share of each piece's diameter sunk into the branches. */
  sink: number;
  tries: number;
  triesAfter: number;
  relax: number;
  seed: number;
  /** 10/28 edit: the top bow on even lines moves to this t on its line (null = the 10/27 layout). */
  topBowEdit: { newT: number } | null;
}

/** gen.js ONEWAY_INPUTS, verbatim: the designer-approved 9 ft x 56 in standard tree, 3 colors. */
export const ONEWAY_INPUTS: OnewayInputs = {
  heightFt: 9,
  widthIn: 56,
  R: 0.258,
  colors: 3,
  enhancers: 30,
  loose: { 10: 9, 8: 15, 6: 24, 4.75: 15, 4: 15 },
  inEnhancers: { 4: 12, 4.75: 15 },
  lines: 6,
  swoop: 3.2,
  t0: 0.12,
  enhT: [
    [0.26, 0.86],
    [0.34, 0.95],
  ],
  bowR: 5.5,
  gap: -0.4,
  bowGap: -1.5,
  relaxGap: 0.8,
  nestBows: true,
  stackFrac: 0.6,
  zone: { 10: [0.62, 0.97], 8: [0.45, 0.97], 6: [0.3, 0.95], 4.75: [0.16, 0.9], 4: [0.14, 0.85] },
  touch: 4,
  tiltMin: 35,
  tiltMax: 45,
  sink: 0.55,
  tries: 6000,
  triesAfter: 1500,
  relax: 120,
  seed: 7,
  topBowEdit: { newT: 0.945 },
};

/**
 * Where a size may sit. The approved sizes use gen.js's zones; other sizes (3",
 * 12", 15.75" on short or tall trees) take the zone of the nearest approved size,
 * so big pieces stay low and small ones spread.
 */
function zoneFor(I: OnewayInputs, inch: number): [number, number] {
  if (I.zone[inch]) return I.zone[inch];
  if (inch > 10) return I.zone[10] ?? [0.62, 0.97];
  if (inch < 4) return I.zone[4] ?? [0.14, 0.85];
  const known = Object.keys(I.zone).map(Number);
  const nearest = known.reduce((a, b) => (Math.abs(b - inch) < Math.abs(a - inch) ? b : a));
  return I.zone[nearest];
}

/** Spread `total` bows over the lines: 30 -> 5 each; 20 -> 4, 3, 3, 4, 3, 3. Extras alternate odd and even lines so A and B stay balanced. */
export function enhancersPerLine(total: number, lines = 6): number[] {
  const n = Math.max(0, Math.floor(total));
  const base = Math.floor(n / lines);
  const extra = n - base * lines;
  const order = lines === 6 ? [0, 3, 1, 4, 2, 5] : Array.from({ length: lines }, (_, i) => i);
  const out = Array<number>(lines).fill(base);
  for (let i = 0; i < extra; i++) out[order[i]] += 1;
  return out;
}

export interface LayoutItemBase {
  /** Share of the height from the tip (0) to the floor (1). */
  t: number;
  /** Radians around the trunk; 0 faces the front. */
  ang: number;
  row: number;
  /** The piece's diameter as a share of the height. */
  gap: number;
}

export interface LayoutOrnament extends LayoutItemBase {
  kind: "orn";
  inch: number;
  /** 1-based color number. */
  color: number;
  size: "L" | "M" | "S";
}

export interface LayoutEnhancer extends LayoutItemBase {
  kind: "enh";
  line: number;
  letter: "A" | "B";
  /** Degrees the bow hangs off vertical, tails down its swirl line. */
  tilt: number;
}

export type LayoutItem = LayoutOrnament | LayoutEnhancer;

export interface OnewayCheck {
  placed: number;
  touching: number;
  stacked: number;
  closestCenters: number;
  colorClash: number;
  bowsTouch: number;
  bigTop: number;
  moved: { index: number; inch: number; color: number; from: [number, number]; to: [number, number]; movedIn: number }[];
  colors: number[];
  A: number;
  B: number;
}

export interface OnewayLayout {
  tree: { heightFt: number; widthIn: number; colors: number; enhancers: number; loose: Record<number, number>; inEnhancers: Record<number, number> };
  R: number;
  rows: number;
  rowT: number[];
  lines: { fam: string; pts: [number, number][] }[];
  bowIn: number;
  hin: number;
  slantIn: number;
  sink: number;
  check: OnewayCheck;
  items: LayoutItem[];
  /** Size (in) -> ornaments with no free spot (never stacked instead). Not in gen.js. */
  unplaced: Record<number, number>;
}

interface Piece {
  kind: "orn" | "enh";
  t: number;
  ang: number;
  inch?: number;
  color?: number;
  size?: "L" | "M" | "S";
  line?: number;
  letter?: "A" | "B" | "?";
  tilt?: number;
}

/** gen.js buildOneway, step for step. */
export function buildOneway(opts: Partial<OnewayInputs> = {}): OnewayLayout {
  const I: OnewayInputs = { ...ONEWAY_INPUTS, ...opts };
  const TAU = 2 * Math.PI;
  const R = I.R;
  const HIN = I.heightFt * 12;
  const RIN = R * HIN;
  const S = Math.hypot(HIN, RIN);
  const TH = (TAU * RIN) / S; // fan angle
  const NL = I.lines;
  const counts = enhancersPerLine(I.enhancers, NL);
  const BOW = I.bowR;
  let seed = I.seed;
  const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  const fan = (p: Piece): [number, number] => {
    const s = p.t * S;
    const ps = (((p.ang % TAU) + TAU) % TAU) * RIN / S;
    return [s, ps];
  };
  // shortest distance on the fan, across the seam too
  const dist = (a: Piece, b: Piece) => {
    const [sa, pa] = fan(a);
    const [sb, pb] = fan(b);
    let best = Infinity;
    for (const k of [-1, 0, 1]) {
      const q = pb + k * TH;
      best = Math.min(best, Math.hypot(sa * Math.cos(pa) - sb * Math.cos(q), sa * Math.sin(pa) - sb * Math.sin(q)));
    }
    return best;
  };
  const rad = (p: Piece) => (p.kind === "enh" ? BOW : (p.inch as number) / 2);
  const minD = (p: Piece, q: Piece) =>
    Math.max(
      rad(p) + rad(q) + (p.kind === "enh" || q.kind === "enh" ? I.bowGap : I.gap),
      I.stackFrac * 2 * Math.min(rad(p), rad(q))
    );
  // The fan distance is never less than the difference in slant, so a quick |ds| test
  // skips far pieces without changing any answer (gen.js checks every piece; same result).
  const clear = (p: Piece, list: Piece[]) =>
    list.every((q) => {
      if (q === p) return true;
      const need = minD(p, q);
      return Math.abs(p.t - q.t) * S >= need || dist(p, q) >= need;
    });
  // room as the eye sees it: a bow's open corners count as room, so ornaments nestle against it
  const vis = (p: Piece) => (p.kind === "enh" ? BOW + (I.nestBows ? I.bowGap : 0) : (p.inch as number) / 2);
  const angAt = (frac: number, tt: number) => (frac * TAU) / NL + I.swoop * (tt - I.t0);
  const lines: OnewayLayout["lines"] = [];
  const enh: Piece[] = [];
  for (let j = 0; j < NL; j++) {
    const pts: [number, number][] = [];
    for (let s = 0; s <= 80; s++) {
      const tt = I.t0 + ((0.96 - I.t0) * s) / 80;
      pts.push([+tt.toFixed(4), +angAt(j, tt).toFixed(4)]);
    }
    lines.push({ fam: "right", pts });
  }
  // 1. enhancers. Diagonal hang: the line's own lean off vertical, held to tiltMin..tiltMax.
  const lean = (t: number) => (Math.atan((RIN * t * I.swoop) / S) * 180) / Math.PI;
  const tiltAt = (t: number) => +Math.min(I.tiltMax, Math.max(I.tiltMin, lean(t))).toFixed(1);
  for (let j = 0; j < NL; j++) {
    const n = counts[j];
    for (let i = 0; i < n; i++) {
      const f = j % 2;
      const [a, b] = I.enhT[f];
      const tt = n > 1 ? a + ((b - a) * i) / (n - 1) : (a + b) / 2;
      enh.push({ kind: "enh", t: tt, ang: angAt(j, tt), line: j, letter: (i % 2 === 0) === (f === 0) ? "A" : "B", tilt: tiltAt(tt) });
    }
  }
  // 2. ornaments: biggest first, each at the random candidate with the most room
  const all: Piece[] = enh.slice();
  const orn: Piece[] = [];
  const unplaced: Record<number, number> = {};
  const sizes = Object.keys(I.loose)
    .map(Number)
    .sort((a, b) => b - a);
  for (const inch of sizes) {
    const [lo, hi] = zoneFor(I, inch);
    for (let k = 0; k < I.loose[inch]; k++) {
      let best: { p: Piece; room: number } | null = null;
      for (let tries = 0; tries < I.tries; tries++) {
        const tt = lo + (hi - lo) * Math.sqrt(rnd()) ** (inch >= 8 ? 0.6 : 1);
        const p: Piece = { kind: "orn", inch, t: Math.min(hi, tt), ang: rnd() * TAU };
        if (!clear(p, all)) continue;
        let room = Infinity;
        for (const q of all) {
          if (Math.abs(p.t - q.t) * S - vis(p) - vis(q) >= room) continue; // can't be the closest
          room = Math.min(room, dist(p, q) - vis(p) - vis(q));
        }
        if (!best || room > best.room) best = { p, room };
        if (tries > I.triesAfter && best) break;
      }
      if (best) {
        orn.push(best.p);
        all.push(best.p);
      } else unplaced[inch] = (unplaced[inch] ?? 0) + 1;
    }
  }
  // 3. relax: push ornaments apart so the spacing evens out (no holes), never stacking
  for (let it = 0; it < I.relax; it++)
    for (const p of orn) {
      let fs = 0;
      let fp = 0;
      const [sp, pp] = fan(p);
      for (const q of all) {
        if (q === p) continue;
        const want = vis(p) + vis(q) + I.relaxGap;
        if (Math.abs(p.t - q.t) * S >= want) continue; // farther than `want`: no push
        const d = dist(p, q);
        if (d >= want) continue;
        const [sq, pq] = fan(q);
        let dpsi = pq - pp;
        if (dpsi > TH / 2) dpsi -= TH;
        if (dpsi < -TH / 2) dpsi += TH;
        fs += ((sp - sq) / (d + 0.01)) * (want - d);
        fp += ((-dpsi * sp) / (d + 0.01)) * (want - d);
      }
      const [lo, hi] = zoneFor(I, p.inch as number);
      const np: Piece = {
        ...p,
        t: Math.min(hi, Math.max(lo, p.t + (0.15 * fs) / S)),
        ang: p.ang + ((0.15 * fp) / Math.max(8, sp)) * (S / RIN),
      };
      if (clear(np, all.map((q) => (q === p ? np : q)))) {
        p.t = np.t;
        p.ang = np.ang;
      }
    }
  // 4. colors: never the same color within `touch` inches; then balance the counts
  const C = I.colors;
  const cols = Array.from({ length: C }, (_, i) => i + 1);
  const near = (p: Piece, q: Piece) => {
    const lim = rad(p) + rad(q) + I.touch;
    return Math.abs(p.t - q.t) * S < lim && dist(p, q) < lim;
  };
  const nb = (p: Piece) => orn.filter((q) => q !== p && near(p, q));
  orn.forEach((p, i) => (p.color = (i % C) + 1));
  // one color: there is nothing to swap, so skip the passes (not in gen.js; it only runs 3)
  if (C > 1) {
    for (let pass = 0; pass < 500; pass++) {
      let bad = 0;
      for (const p of orn) {
        const c = nb(p).map((q) => q.color);
        if (!c.includes(p.color)) continue;
        bad++;
        const cnt = cols.map((x) => c.filter((y) => y === x).length);
        const m = Math.min(...cnt);
        const o = cols.filter((x, i) => cnt[i] === m);
        p.color = o[Math.floor(rnd() * o.length)];
      }
      if (!bad) break;
    }
    for (let pass = 0; pass < 300; pass++) {
      const cnt = cols.map((c) => orn.filter((p) => p.color === c).length);
      const over = cnt.indexOf(Math.max(...cnt)) + 1;
      const under = cnt.indexOf(Math.min(...cnt)) + 1;
      if (cnt[over - 1] - cnt[under - 1] <= (orn.length % C ? 1 : 0)) break;
      const p = orn.find((p) => p.color === over && !nb(p).some((q) => q.color === under));
      if (!p) break;
      p.color = under;
    }
  }
  for (const p of orn) p.size = (p.inch as number) >= 8 ? "L" : p.inch === 6 ? "M" : "S";
  // 4b. designer edit 10/28/2026: the tree is skinny at the top and the topper hangs
  // down, so the topmost bow on each even line goes back on the same line below its
  // last bow. Ornaments that hit a new bow move the least distance to a free spot,
  // same size and color.
  const moved: OnewayCheck["moved"] = [];
  if (I.topBowEdit) {
    for (let j = 0; j < NL; j += 2) {
      const mine = enh.filter((e) => e.line === j).sort((a, b) => a.t - b.t);
      if (!mine.length) continue;
      enh.splice(enh.indexOf(mine[0]), 1);
      const tt = I.topBowEdit.newT;
      enh.push({ kind: "enh", t: tt, ang: angAt(j, tt), line: j, letter: "?", tilt: tiltAt(tt) });
    }
    // every line alternates; odd lines start A and even lines B, top down (15 A / 15 B)
    for (let j = 0; j < NL; j++)
      enh
        .filter((e) => e.line === j)
        .sort((a, b) => a.t - b.t)
        .forEach((e, i) => (e.letter = (i % 2 === 0) === (j % 2 === 1) ? "A" : "B"));
    for (const p of [...orn]) {
      const others = enh.concat(orn.filter((q) => q !== p));
      if (clear(p, others)) continue;
      const [lo, hi] = zoneFor(I, p.inch as number);
      let best: { q: Piece; d: number } | null = null;
      for (let dt = -0.3; dt <= 0.3; dt += 0.002)
        for (let da = -1.5; da <= 1.5; da += 0.004) {
          const q: Piece = { ...p, t: p.t + dt, ang: p.ang + da };
          if (q.t < lo || q.t > hi) continue;
          if (!clear(q, others)) continue;
          if (C > 1 && orn.some((o) => o !== p && o.color === p.color && dist(q, o) < rad(q) + rad(o) + I.touch)) continue;
          const d = dist(p, q);
          if (!best || d < best.d) best = { q, d };
        }
      if (!best) {
        // gen.js stops here; the app leaves the piece off and says so instead
        orn.splice(orn.indexOf(p), 1);
        unplaced[p.inch as number] = (unplaced[p.inch as number] ?? 0) + 1;
        continue;
      }
      moved.push({
        index: orn.indexOf(p),
        inch: p.inch as number,
        color: p.color as number,
        from: [+p.t.toFixed(4), +p.ang.toFixed(4)],
        to: [+best.q.t.toFixed(4), +best.q.ang.toFixed(4)],
        movedIn: +best.d.toFixed(2),
      });
      p.t = best.q.t;
      p.ang = best.q.ang;
    }
  }
  balanceLetters(enh);
  // 5. checks
  const items = orn.concat(enh.sort((a, b) => (a.line as number) - (b.line as number) || a.t - b.t));
  let touching = 0;
  let stacked = 0;
  let minRatio = Infinity;
  let colorClash = 0;
  let bowsTouch = 0;
  for (let i = 0; i < items.length; i++)
    for (let j = i + 1; j < items.length; j++) {
      const p = items[i];
      const q = items[j];
      const d = dist(p, q);
      if (d < rad(p) + rad(q)) touching++;
      const r = d / (2 * Math.min(rad(p), rad(q)));
      minRatio = Math.min(minRatio, r);
      if (r < I.stackFrac - 1e-6) stacked++;
      if (p.kind === "enh" && q.kind === "enh" && d < 2 * BOW) bowsTouch++;
    }
  if (C > 1) for (const p of orn) if (nb(p).some((q) => q.color === p.color)) colorClash++;
  const bigTop = orn.filter((p) => (p.inch as number) >= 8 && p.t < 1 / 3).length;
  const rowT: number[] = [];
  for (let t = ROW_START; t <= 0.96; t += ROW_STEP) rowT.push(t);
  const rowOf = (tt: number) => {
    let b = 0;
    rowT.forEach((r, i) => {
      if (Math.abs(r - tt) < Math.abs(rowT[b] - tt)) b = i;
    });
    return b;
  };
  return {
    tree: { heightFt: I.heightFt, widthIn: I.widthIn, colors: C, enhancers: I.enhancers, loose: I.loose, inEnhancers: I.inEnhancers },
    R,
    rows: rowT.length,
    rowT: rowT.map((x) => +x.toFixed(4)),
    lines,
    bowIn: BOW * 2,
    hin: HIN,
    slantIn: +S.toFixed(2),
    sink: I.sink,
    check: {
      placed: orn.length,
      touching,
      stacked,
      closestCenters: +minRatio.toFixed(2),
      colorClash,
      bowsTouch,
      bigTop,
      moved,
      colors: cols.map((c) => orn.filter((p) => p.color === c).length),
      A: enh.filter((e) => e.letter === "A").length,
      B: enh.filter((e) => e.letter === "B").length,
    },
    items: items.map((it) => {
      const base = { row: rowOf(it.t), t: +it.t.toFixed(4), ang: +(((it.ang % TAU) + TAU) % TAU).toFixed(4), gap: +((rad(it) * 2) / HIN).toFixed(4) };
      return it.kind === "orn"
        ? { kind: "orn", inch: it.inch as number, color: it.color as number, size: it.size as "L" | "M" | "S", ...base }
        : { kind: "enh", line: it.line as number, letter: it.letter as "A" | "B", tilt: it.tilt as number, ...base };
    }),
    unplaced,
  };
}

/**
 * Half A, half B. The approved 9 ft tree already is (15/15) and is left alone. With
 * other counts per line the line-start rule can tip one way; then whole lines swap
 * their letters (still alternating) until the two differ by at most one.
 */
function balanceLetters(enh: Piece[]) {
  const count = (l: string) => enh.filter((e) => e.letter === l).length;
  for (let guard = 0; guard < 12; guard++) {
    const diff = count("A") - count("B");
    if (Math.abs(diff) <= 1) return;
    const more = diff > 0 ? "A" : "B";
    // a line with an odd count that starts (and ends) on the bigger letter: swap it
    const lineIds = Array.from(new Set(enh.map((e) => e.line as number)));
    const swap = lineIds.find((j) => {
      const mine = enh.filter((e) => e.line === j).sort((a, b) => a.t - b.t);
      return mine.length % 2 === 1 && mine[0].letter === more;
    });
    if (swap === undefined) return;
    for (const e of enh) if (e.line === swap) e.letter = e.letter === "A" ? "B" : "A";
  }
}

// ---------------------------------------------------------------------------
// The app's entry point: calculator counts in, layout plus a plain verdict out
// ---------------------------------------------------------------------------

export interface TreeInstallLayoutInput {
  heightFt: number;
  widthIn: number;
  colorCount: number;
  enhancers: number;
  /** Size (in) -> pieces loose on the tree. */
  loose: Record<number, number>;
  /** Size (in) -> pieces inside the enhancers. */
  inEnhancers?: Record<number, number>;
}

export interface TreeInstallLayout extends OnewayLayout {
  fits: boolean;
  /** Plain sentences for the page when something can't be shown. */
  problems: string[];
  /** Set when the approved spacing was loosened to fit this tree. */
  note: string | null;
}

/** The calculator's counts for any tree, laid out with the approved rules and settings. */
export function buildTreeInstallLayout(input: TreeInstallLayoutInput): TreeInstallLayout {
  const colors = clampColorCount(input.colorCount);
  const tree: Partial<OnewayInputs> = {
    heightFt: input.heightFt,
    widthIn: input.widthIn,
    R: input.widthIn / 2 / (input.heightFt * 12),
    colors,
    enhancers: Math.max(0, Math.floor(input.enhancers)),
    loose: input.loose,
    inEnhancers: input.inEnhancers ?? {},
  };
  // The approved settings first. A tree they can't hold (more pieces per inch than
  // the approved 9 ft, or two colors, where "never within 4 inches" can't be kept)
  // gets the same rules a little looser, in this order. The first that fits wins;
  // otherwise the one that leaves the least off.
  const looser = (zones: boolean, touch: boolean): Partial<OnewayInputs> => ({
    ...(zones
      ? {
          gap: -1,
          bowGap: -2.5,
          zone: { ...ONEWAY_INPUTS.zone, 10: [0.45, 0.97], 8: [0.36, 0.97], 6: [0.26, 0.96] },
        }
      : {}),
    // two colors: same color never actually touching (a 4" moat can't alternate two)
    ...(touch && colors === 2 ? { touch: 0.5 } : {}),
  });
  const attempts: { opts: Partial<OnewayInputs>; note: string | null }[] = [
    { opts: {}, note: null },
    ...(colors === 2 ? [{ opts: looser(false, true), note: "Two colors: same colors never touch (the 4 inch rule is for 3 or more colors)." }] : []),
    { opts: looser(true, false), note: "Packed a little tighter than the approved 9 ft tree, with big ornaments allowed from just below the top third." },
    ...(colors === 2 ? [{ opts: looser(true, true), note: "Packed a little tighter than the approved 9 ft tree; two colors never touch." }] : []),
    // the same, from other starting draws (still the same tree every time)
    ...[11, 23, 37].map((seed) => ({
      opts: { ...looser(true, true), seed },
      note: "Packed a little tighter than the approved 9 ft tree, with big ornaments allowed from just below the top third.",
    })),
  ];
  let L: OnewayLayout | null = null;
  let note: string | null = null;
  const missingOf = (x: OnewayLayout) => Object.values(x.unplaced).reduce((a, b) => a + b, 0);
  for (const a of attempts) {
    const next = buildOneway({ ...tree, ...a.opts });
    const better = !L || missingOf(next) * 100 + next.check.colorClash < missingOf(L) * 100 + L.check.colorClash;
    if (better) {
      L = next;
      note = a.note;
    }
    if (missingOf(next) === 0 && (colors === 1 || next.check.colorClash === 0)) break;
  }
  if (!L) throw new Error("no layout");
  const problems: string[] = [];
  const missing = Object.entries(L.unplaced)
    .filter(([, n]) => n > 0)
    .sort((a, b) => Number(b[0]) - Number(a[0]));
  if (missing.length) {
    problems.push(
      `No free spot for ${missing.map(([size, n]) => `${n} x ${size}"`).join(", ")} without stacking them on another piece. They are left off the mockup.`
    );
  }
  if (L.check.colorClash) problems.push(`${L.check.colorClash} ornaments end up within 4" of their own color.`);
  if (colors === 1) problems.push("One color: every ornament is the same color, so the no-same-color-touching rule can't apply.");
  return { ...L, fits: missing.length === 0 && L.check.colorClash === 0, problems, note };
}
