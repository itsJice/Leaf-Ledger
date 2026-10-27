// Tree Install: where every enhancer and ornament goes on a tree, in real inches.
//
// Ported from the design-training prototype (tree-design-map/gen.js, buildOneway(),
// designer rules of 10/27/2026) into a typed, seeded module the app can run live.
//
// The rules (designer, 10/27/2026):
// - Six swirl lines start at the tip and all turn the same way, evenly spaced, so
//   every side of the tree looks the same.
// - Enhancers sit on the swirl lines, A, B, A, B along each line. Two never touch.
//   An enhancer is a long spray, about 24" x 6" (ribbon loops, a center ball, tails
//   and leaves), lying along its line.
// - Ornaments fill between the lines. Two of the same color never touch.
// - Big ornaments (8" and up) never go in the top 40% of the tree.
// - A spray-and-bow topper fills the very top.
// - Nothing overlaps. The cone unrolls flat into a fan (distances on the cone equal
//   distances on the fan), so every check is done in true inches on that fan.
//
// Counts are never decided here: they come from the Ornament Calculator's engine
// (utils/ornamentRecipe.ts) through `treeInstallCounts`. When a tree can't hold
// everything without overlaps, the layout says so (`fits: false`, `problems`)
// rather than squeezing pieces on top of each other.

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
// Layout
// ---------------------------------------------------------------------------

/**
 * Enhancer size. The user picked the 11" round bow (10/27/2026) over the 24" x 6"
 * spray; a spray still works by passing `enhancerLengthIn` / `enhancerWidthIn`.
 */
export const ENHANCER_LENGTH_IN = 11;
export const ENHANCER_WIDTH_IN = 11;
/**
 * Pieces go IN the tree, nestled into the branches, so touching and overlapping
 * are fine (user, 10/27/2026). What's never allowed is two pieces stacked on the
 * same spot: centers closer than this share of the smaller piece's diameter.
 */
export const STACK_SHARE = 0.6;
/** Room the enhancers aim for between each other (a goal, not a rule: they may touch). */
export const ENHANCER_GAP_IN = 0;
/** Two ornaments of the same color closer than this (edge to edge) count as touching. */
export const SAME_COLOR_GAP_IN = 2.5;
/** Ornaments this size and up stay out of the top of the tree. */
export const BIG_ORNAMENT_IN = 8;
/** "Never large at the top": the share of the height, from the tip, kept free of them. */
export const BIG_ORNAMENT_TOP_SHARE = 0.4;
/** Rows for the build-it-row-by-row slider, in inches down the tree. */
export const ROW_STEP_IN = 6;

export interface TreeInstallLayoutInput {
  heightFt: number;
  widthIn: number;
  colorCount: number;
  enhancers: number;
  /** Size (in) -> pieces loose on the tree. */
  loose: Record<number, number>;
  /** Size (in) -> pieces inside the enhancers (drawn inside each spray). */
  inEnhancers?: Record<number, number>;
  enhancerLengthIn?: number;
  enhancerWidthIn?: number;
  seed?: number;
}

/** A spot on the cone: `t` is the share of the slant from the tip (0) to the bottom edge (1); `ang` is radians around the trunk, 0 = front. */
export interface ConePoint {
  t: number;
  ang: number;
}

export interface PlacedOrnament extends ConePoint {
  kind: "ornament";
  id: number;
  size: number;
  /** 1-based color number. */
  color: number;
  row: number;
}

export interface PlacedEnhancer extends ConePoint {
  kind: "enhancer";
  id: number;
  letter: "A" | "B";
  /** Which swirl line (0-5) and its place on that line, top first. */
  line: number;
  indexOnLine: number;
  /** The spray's spine along its swirl line, top end first. */
  spine: ConePoint[];
  /** A spot a few inches further down its swirl line: the bow hangs diagonally toward it. */
  downhill: ConePoint;
  /** Sizes (in) of the ornaments tucked inside this spray. */
  inside: number[];
  row: number;
}

export type PlacedItem = PlacedOrnament | PlacedEnhancer;

export interface TreeInstallCheck {
  /** Pieces on the same spot (centers closer than STACK_SHARE of the smaller one): never allowed. */
  stacks: number;
  /** Pieces touching or overlapping: fine, they sit in the branches. For information. */
  overlaps: number;
  enhancerTouches: number;
  colorTouches: number;
  bigInTop: number;
  abAlternates: boolean;
  minClearanceIn: number;
}

export interface TreeInstallLayout {
  heightIn: number;
  baseRadiusIn: number;
  slantIn: number;
  /** The six swirl lines' shared shape. */
  swirl: SwirlShape;
  topperIn: number;
  lines: ConePoint[][];
  ornaments: PlacedOrnament[];
  enhancers: PlacedEnhancer[];
  rows: number;
  /** Size (in) -> pieces that would not fit without overlapping. */
  unplaced: Record<number, number>;
  enhancersUnplaced: number;
  fits: boolean;
  problems: string[];
  check: TreeInstallCheck;
}

// --- small helpers ---------------------------------------------------------

/** Seeded random numbers (mulberry32): the same tree always gives the same layout. */
function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function hashInput(input: TreeInstallLayoutInput): number {
  const text = JSON.stringify([
    input.heightFt,
    input.widthIn,
    input.colorCount,
    input.enhancers,
    Object.entries(input.loose).sort(),
    input.enhancerLengthIn ?? ENHANCER_LENGTH_IN,
    input.enhancerWidthIn ?? ENHANCER_WIDTH_IN,
    input.seed ?? 7,
  ]);
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619);
  return h >>> 0;
}

const TAU = Math.PI * 2;
const wrapPi = (a: number) => {
  let x = (a + Math.PI) % TAU;
  if (x < 0) x += TAU;
  return x - Math.PI;
};
const wrapTau = (a: number) => ((a % TAU) + TAU) % TAU;

/** A disc on the unrolled cone: `s` inches down the slant from the tip, at angle `ang` around the trunk. */
interface Disc {
  s: number;
  ang: number;
  r: number;
  owner: number;
  /** Ornament color (0 = not an ornament). */
  color: number;
  enh: boolean;
}

/** Discs this far apart along an enhancer spine keep the capsule's edge within ~0.1". */
const SPINE_STEP_IN = 1.5;
const SPINE_SLACK_IN = 0.1;

class Cone {
  readonly H: number;
  readonly R: number;
  readonly S: number;
  /** Fan angle per radian of trunk angle. */
  readonly k: number;
  constructor(heightIn: number, baseRadiusIn: number) {
    this.H = heightIn;
    this.R = baseRadiusIn;
    this.S = Math.hypot(heightIn, baseRadiusIn);
    this.k = baseRadiusIn / this.S;
  }
  /** Straight-line distance on the unrolled fan: the true distance across the tree's surface. */
  dist(s1: number, a1: number, s2: number, a2: number): number {
    const dphi = wrapPi(a2 - a1) * this.k;
    return Math.sqrt(Math.max(0, s1 * s1 + s2 * s2 - 2 * s1 * s2 * Math.cos(dphi)));
  }
}

/** One swirl line: angle grows straight with the share of the slant. */
interface SwirlLine {
  a0: number;
  /** Arc-length table: slant `s` and inches along the line from its top. */
  ss: number[];
  len: number[];
}

/**
 * A swirl line's shape: `turn` radians of turn from tip to bottom, and `bend`, how
 * the turn is spread down the tree: 1 turns evenly (the prototype), below 1 turns
 * more up high and leans less at the bottom. Either way a line runs nearly straight
 * down at the tip and leans more lower down, and all six lines share one shape.
 */
export interface SwirlShape {
  turn: number;
  bend: number;
}

const swirlAng = (a0: number, s: number, cone: Cone, sw: SwirlShape) => a0 + sw.turn * Math.pow(s / cone.S, sw.bend);

function angOnLine(line: SwirlLine, s: number, cone: Cone, sw: SwirlShape): number {
  return swirlAng(line.a0, s, cone, sw);
}

function buildLine(a0: number, cone: Cone, sw: SwirlShape, sTop: number, sBottom: number): SwirlLine {
  const ss: number[] = [];
  const len: number[] = [];
  const steps = 600;
  let acc = 0;
  let prevS = sTop;
  let prevA = swirlAng(a0, sTop, cone, sw);
  for (let i = 0; i <= steps; i++) {
    const s = sTop + ((sBottom - sTop) * i) / steps;
    const a = swirlAng(a0, s, cone, sw);
    if (i > 0) acc += cone.dist(prevS, prevA, s, a);
    ss.push(s);
    len.push(acc);
    prevS = s;
    prevA = a;
  }
  return { a0, ss, len };
}

/** Slant position at `along` inches down a line (clamped to the line). */
function sAtLength(line: SwirlLine, along: number): number {
  const { ss, len } = line;
  if (along <= 0) return ss[0];
  if (along >= len[len.length - 1]) return ss[ss.length - 1];
  let lo = 0;
  let hi = len.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (len[mid] < along) lo = mid;
    else hi = mid;
  }
  const f = (along - len[lo]) / (len[hi] - len[lo] || 1);
  return ss[lo] + f * (ss[hi] - ss[lo]);
}

// --- enhancers ---------------------------------------------------------------

interface EnhancerDraft {
  line: number;
  indexOnLine: number;
  centerAlong: number;
  spine: { s: number; ang: number }[];
}

/** Spread `total` over six lines: 30 -> 5 each, 20 -> 4, 4, 3, 3, 3, 3. */
export function enhancersPerLine(total: number): number[] {
  const n = Math.max(0, Math.floor(total));
  const base = Math.floor(n / 6);
  const extra = n - base * 6;
  // the extras go on opposite lines first so the tree stays balanced
  const order = [0, 3, 1, 4, 2, 5];
  const out = Array(6).fill(base);
  for (let i = 0; i < extra; i++) out[order[i]] += 1;
  return out;
}

/**
 * A and B along each line. Each line alternates; lines start on A or B so the
 * tree has as close to half A, half B as the count allows.
 */
export function enhancerLetters(perLine: number[]): ("A" | "B")[][] {
  let oddSeen = 0;
  return perLine.map((n, j) => {
    let startA: boolean;
    if (n % 2 === 1) {
      startA = oddSeen % 2 === 0;
      oddSeen++;
    } else {
      startA = j % 2 === 0;
    }
    return Array.from({ length: n }, (_, i) => ((i % 2 === 0) === startA ? "A" : "B"));
  });
}

function sprayDiscs(
  line: SwirlLine,
  centerAlong: number,
  cone: Cone,
  sw: SwirlShape,
  spineLen: number
): { s: number; ang: number }[] {
  const n = Math.max(1, Math.ceil(spineLen / SPINE_STEP_IN));
  const out: { s: number; ang: number }[] = [];
  for (let i = 0; i <= n; i++) {
    const along = centerAlong - spineLen / 2 + (spineLen * i) / n;
    const s = sAtLength(line, along);
    out.push({ s, ang: angOnLine(line, s, cone, sw) });
  }
  return out;
}

interface EnhancerPlan {
  swirl: SwirlShape;
  lines: SwirlLine[];
  drafts: EnhancerDraft[];
  ok: boolean;
  clashes: number;
}

/**
 * Line shapes tried, shortest lines first: the prototype's even 3.2 turn, more turn
 * only when the sprays need the line length. A softer bend keeps the bottom of the
 * lines from lying flat, which leaves room there for the big ornaments.
 */
const SWIRLS: SwirlShape[] = [3.2, 3.6, 4, 4.4, 4.8, 5.2, 5.6, 6, 6.6, 7.2, 8, 9, 10]
  .flatMap((turn) => [1, 0.7, 0.5].map((bend) => ({ turn, bend })))
  .sort((a, b) => a.turn - b.turn || b.bend - a.bend);
/** Plans handed to the ornament step, at most. */
const MAX_PLANS = 3;

/**
 * Ways to put the sprays on the six lines without two touching, gentlest swoop
 * first (one per swoop). Each starts from an even spacing with every other line
 * half a step lower, then slides sprays along their lines until none touch.
 * When nothing works, the single plan with the fewest clashes.
 */
function enhancerPlans(
  cone: Cone,
  perLine: number[],
  topperIn: number,
  eLen: number,
  eWid: number,
  random: () => number
): EnhancerPlan[] {
  const spineLen = Math.max(0, eLen - eWid);
  const r = eWid / 2;
  // a line runs from just under the topper to the bottom edge; a spray's ends stay on the tree
  const sTop = topperIn;
  const sBottom = cone.S - r;
  const total = perLine.reduce((a, b) => a + b, 0);
  const maxN = Math.max(...perLine, 0);
  const pitch = eLen + ENHANCER_GAP_IN;
  const plans: EnhancerPlan[] = [];
  let best: EnhancerPlan | null = null;
  for (const swirl of SWIRLS) {
    const lines = Array.from({ length: 6 }, (_, j) => buildLine((TAU * j) / 6, cone, swirl, sTop, sBottom));
    const usable = lines[0].len[lines[0].len.length - 1];
    if (maxN > 0 && maxN * eLen + (maxN - 1) * ENHANCER_GAP_IN > usable) continue;
    const lo = eLen / 2;
    const hi = usable - eLen / 2;
    // Start from an even spacing. The top is too narrow for six sprays side by side,
    // so every other line starts lower; try a few drops and keep the one with the
    // fewest clashes.
    const startPos = (evenDrop: number, oddDrop: number, evenLift: number): number[][] | null => {
      const out: number[][] = [];
      for (let j = 0; j < 6; j++) {
        const n = perLine[j];
        const odd = j % 2 === 1;
        const start = lo + (evenDrop + (odd ? oddDrop : 0)) * pitch;
        const end = hi - (odd ? 0 : evenLift) * pitch;
        const step = n > 1 ? (end - start) / (n - 1) : 0;
        if (n && (end < start || (n > 1 && step < pitch))) return null;
        out.push(Array.from({ length: n }, (_, i) => (n > 1 ? start + i * step : (start + end) / 2)));
      }
      return out;
    };
    const quickClashes = (p: number[][], cap: number): number => {
      const sp: { s: number; ang: number }[][] = [];
      p.forEach((list, j) => list.forEach((x) => sp.push(sprayDiscs(lines[j], x, cone, swirl, spineLen))));
      let c = 0;
      for (let a = 0; a < sp.length && c < cap; a++) {
        for (let b = a + 1; b < sp.length && c < cap; b++) {
          if (capsuleClearance(cone, sp[a], sp[b], r, r) < ENHANCER_GAP_IN) c++;
        }
      }
      return c;
    };
    let pos: number[][] | null = null;
    let posClashes = Infinity;
    grid: for (const evenDrop of [0, 0.25, 0.5, 0.75, 1, 1.25]) {
      for (const evenLift of [0, 0.25, 0.5]) {
        for (const oddDrop of [0.5, 0.75, 1, 0.35, 1.25, 0.2, 1.5, 0]) {
          const p = startPos(evenDrop, oddDrop, evenLift);
          if (!p) continue;
          const c = quickClashes(p, posClashes);
          if (c < posClashes) {
            pos = p;
            posClashes = c;
          }
          if (c === 0) break grid;
        }
      }
    }
    if (!pos) continue;
    const ids: { j: number; i: number }[] = [];
    perLine.forEach((n, j) => {
      for (let i = 0; i < n; i++) ids.push({ j, i });
    });
    const spines = ids.map(({ j, i }) => sprayDiscs(lines[j], pos[j][i], cone, swirl, spineLen));
    const sRange = (sp: { s: number }[]) => [Math.min(...sp.map((p) => p.s)), Math.max(...sp.map((p) => p.s))];
    const ranges = spines.map(sRange);
    const pairPen = (a: number, b: number, spA = spines[a], rA = ranges[a]): number => {
      const rB = ranges[b];
      if (rA[0] - rB[1] > 2 * r + ENHANCER_GAP_IN || rB[0] - rA[1] > 2 * r + ENHANCER_GAP_IN) return 0;
      return Math.max(0, ENHANCER_GAP_IN + 0.05 - capsuleClearance(cone, spA, spines[b], r, r));
    };
    // pair penalties: how far short of the enhancer gap each pair is
    const n = ids.length;
    const P = ids.map((_, x) => ids.map((__, y) => (x === y ? 0 : pairPen(x, y))));
    const pens = P.map((row) => row.reduce((sum, v) => sum + v, 0));
    // Slide sprays along their own lines until nothing touches: one spray at a time,
    // or a whole line at once (which keeps its spacing and changes the stagger).
    const iterations = posClashes === 0 ? 0 : 160 * Math.max(1, total);
    const lineIds = perLine.map((_, j) => ids.map((id, x) => (id.j === j ? x : -1)).filter((x) => x >= 0));
    for (let it = 0; it < iterations; it++) {
      const bad: number[] = [];
      for (let x = 0; x < n; x++) if (pens[x] > 1e-9) bad.push(x);
      if (!bad.length) break;
      const a = bad[Math.floor(random() * bad.length)];
      const { j, i } = ids[a];
      const reach = 8 * (1 - it / iterations) + 1;
      const delta = (random() * 2 - 1) * reach;
      const moved = random() < 0.3 ? lineIds[j] : [a];
      const next = new Map<number, number>();
      let ok = true;
      for (const m of moved) {
        const { i: mi } = ids[m];
        const x = pos[j][mi] + delta;
        if (x < lo || x > hi) ok = false;
        next.set(m, x);
      }
      if (!ok) continue;
      if (moved.length === 1) {
        // keep the order on the line and a full pitch between neighbours there
        const x = next.get(a)!;
        const prev = i > 0 ? pos[j][i - 1] + pitch : lo;
        const nxt = i < pos[j].length - 1 ? pos[j][i + 1] - pitch : hi;
        if (x < prev - 1e-9 || x > nxt + 1e-9) continue;
      }
      const newSp = new Map<number, { s: number; ang: number }[]>();
      const newRg = new Map<number, number[]>();
      next.forEach((x, m) => {
        const sp = sprayDiscs(lines[j], x, cone, swirl, spineLen);
        newSp.set(m, sp);
        newRg.set(m, sRange(sp));
      });
      const spOf = (y: number) => newSp.get(y) ?? spines[y];
      const rgOf = (y: number) => newRg.get(y) ?? ranges[y];
      const pen2 = (x: number, y: number) => {
        const rA = rgOf(x);
        const rB = rgOf(y);
        if (rA[0] - rB[1] > 2 * r + ENHANCER_GAP_IN || rB[0] - rA[1] > 2 * r + ENHANCER_GAP_IN) return 0;
        return Math.max(0, ENHANCER_GAP_IN + 0.05 - capsuleClearance(cone, spOf(x), spOf(y), r, r));
      };
      const changes: [number, number, number][] = [];
      let change = 0;
      for (const m of moved) {
        for (let y = 0; y < n; y++) {
          if (y === m || (next.has(y) && y < m)) continue;
          const v = pen2(m, y);
          change += v - P[m][y];
          changes.push([m, y, v]);
        }
      }
      // mostly downhill, with a little uphill early on to get out of dead ends
      const temp = 0.6 * (1 - it / iterations);
      if (change < -1e-9 || (change > 0 && temp > 0 && random() < Math.exp(-change / temp) * 0.15)) {
        next.forEach((x, m) => {
          pos[j][ids[m].i] = x;
          spines[m] = newSp.get(m)!;
          ranges[m] = newRg.get(m)!;
        });
        for (const [x, y, v] of changes) {
          pens[x] += v - P[x][y];
          pens[y] += v - P[y][x];
          P[x][y] = v;
          P[y][x] = v;
        }
      }
    }
    const clashes = pens.filter((p) => p > 1e-9).length;
    const drafts: EnhancerDraft[] = ids.map(({ j, i }, a) => ({ line: j, indexOnLine: i, centerAlong: pos[j][i], spine: spines[a] }));
    const plan = { swirl, lines, drafts, ok: clashes === 0, clashes };
    if (clashes === 0) plans.push(plan);
    else if (!best || clashes < best.clashes) best = plan;
    if (plans.length >= MAX_PLANS) break;
  }
  if (plans.length) return plans;
  if (best) return [best];
  // Even the tightest swirl can't fit the sprays end to end: place what fits.
  const swirl = SWIRLS[SWIRLS.length - 1];
  const lines = Array.from({ length: 6 }, (_, j) => buildLine((TAU * j) / 6, cone, swirl, sTop, sBottom));
  const drafts: EnhancerDraft[] = [];
  const usable = lines[0].len[lines[0].len.length - 1];
  for (let j = 0; j < 6; j++) {
    for (let i = 0; i < perLine[j]; i++) {
      const centerAlong = eLen / 2 + i * pitch;
      if (centerAlong + eLen / 2 > usable) break;
      drafts.push({ line: j, indexOnLine: i, centerAlong, spine: sprayDiscs(lines[j], centerAlong, cone, swirl, spineLen) });
    }
  }
  return [{ swirl, lines, drafts, ok: false, clashes: Infinity }];
}

function capsuleClearance(
  cone: Cone,
  A: { s: number; ang: number }[],
  B: { s: number; ang: number }[],
  ra: number,
  rb: number
): number {
  let best = Infinity;
  for (const p of A) {
    for (const q of B) {
      if (Math.abs(p.s - q.s) - ra - rb > best) continue;
      const d = cone.dist(p.s, p.ang, q.s, q.ang);
      if (d < best) best = d;
    }
  }
  return best - ra - rb - SPINE_SLACK_IN;
}

// --- ornaments ---------------------------------------------------------------

/**
 * A and B for every spray. Each line alternates A, B, A, B; which letter each line
 * starts on is chosen so the tree has half of each and sprays on neighbouring
 * lines differ as much as possible (no column or row of all A's).
 */
function pickLetters(cone: Cone, perLine: number[], drafts: EnhancerDraft[]): ("A" | "B")[][] {
  const fallback = enhancerLetters(perLine);
  if (!drafts.length) return fallback;
  const total = perLine.reduce((a, b) => a + b, 0);
  const mid = (d: EnhancerDraft) => d.spine[Math.floor(d.spine.length / 2)];
  // neighbouring sprays on different lines, closer weighs more
  const pairs: { a: EnhancerDraft; b: EnhancerDraft; w: number }[] = [];
  for (let x = 0; x < drafts.length; x++) {
    for (let y = x + 1; y < drafts.length; y++) {
      const a = drafts[x];
      const b = drafts[y];
      if (a.line === b.line) continue;
      const p = mid(a);
      const q = mid(b);
      const d = cone.dist(p.s, p.ang, q.s, q.ang);
      if (d < 40) pairs.push({ a, b, w: 1 / Math.max(6, d) });
    }
  }
  let best: { letters: ("A" | "B")[][]; cost: number } | null = null;
  for (let mask = 0; mask < 64; mask++) {
    const letters = perLine.map((n, j) =>
      Array.from({ length: n }, (_, i) => ((i % 2 === 0) === ((mask >> j) & 1) > 0 ? "A" : "B") as "A" | "B")
    );
    const a = letters.flat().filter((l) => l === "A").length;
    // as close to half and half as the count allows, A first
    if (a !== Math.ceil(total / 2)) continue;
    let cost = 0;
    for (const { a: p, b: q, w } of pairs) if (letters[p.line][p.indexOnLine] === letters[q.line][q.indexOnLine]) cost += w;
    if (!best || cost < best.cost - 1e-12) best = { letters, cost };
  }
  return best ? best.letters : fallback;
}

/** Where each size may go, as shares of the slant from the tip (centers). */
function sizeZone(size: number, sizes: number[], topShare: number): [number, number] {
  const sorted = [...sizes].sort((a, b) => b - a);
  if (size >= BIG_ORNAMENT_IN) {
    // the top size sits lowest; the next big size starts at the 40% line
    return size === sorted[0] ? [Math.max(0.45, topShare), 1] : [BIG_ORNAMENT_TOP_SHARE, 1];
  }
  if (size >= 6) return [Math.max(0.24, topShare), 1];
  return [topShare, 1];
}

/** Discs bucketed by slant position, so a lookup only visits the nearby bands. */
class DiscIndex {
  private bins: Disc[][];
  private readonly w = 3;
  constructor(slant: number) {
    this.bins = Array.from({ length: Math.ceil(slant / 3) + 2 }, () => []);
  }
  private bin(s: number) {
    return Math.min(this.bins.length - 1, Math.max(0, Math.floor(s / this.w)));
  }
  add(d: Disc) {
    this.bins[this.bin(d.s)].push(d);
  }
  remove(d: Disc) {
    const list = this.bins[this.bin(d.s)];
    const i = list.indexOf(d);
    if (i >= 0) list.splice(i, 1);
  }
  near(s: number, reach: number, visit: (d: Disc) => void) {
    const a = this.bin(s - reach);
    const b = this.bin(s + reach);
    for (let i = a; i <= b; i++) for (const d of this.bins[i]) visit(d);
  }
}

interface Pending {
  size: number;
  color: number;
}

interface PlacedDraft {
  s: number;
  ang: number;
  size: number;
  color: number;
}

/**
 * "even" puts each ornament where it has the most room (the evenest look); "dense"
 * tucks each one into the tightest spot that still clears, which fits more when a
 * tree is full. Big ornaments lean low either way.
 */
type PackMode = "even" | "dense";

interface PackResult {
  orn: PlacedDraft[];
  unplaced: Record<number, number>;
  /** Flat area (sq in) of what didn't fit: how to rank two partial results. */
  missingArea: number;
}

function packOrnaments(
  cone: Cone,
  enhancerDiscs: Disc[],
  queue: Pending[],
  sizes: number[],
  topperIn: number,
  sameColorRule: boolean,
  mode: PackMode,
  random: () => number
): PackResult {
  const index = new DiscIndex(cone.S);
  for (const d of enhancerDiscs) index.add(d);
  const orn: PlacedDraft[] = [];
  const ornDiscs: Disc[] = [];
  const unplaced: Record<number, number> = {};
  let missingArea = 0;
  const topShare = (topperIn + 2) / cone.S;
  const maxR = Math.max(enhancerDiscs[0]?.r ?? 0, ...sizes.map((x) => x / 2)) + 1;

  /** Edge-to-edge room a spot needs from a neighbour: negative means overlap is fine, up to a same-spot stack. */
  const required = (color: number, r: number, other: Disc): number => {
    if (!other.enh && sameColorRule && other.color === color) return SAME_COLOR_GAP_IN;
    return STACK_SHARE * 2 * Math.min(r, other.r) - r - other.r;
  };
  /**
   * Room left at a spot: the smallest clearance minus what each neighbour needs
   * (negative = not allowed), counted up to `cap` inches.
   */
  const slackAt = (s: number, ang: number, size: number, color: number, cap: number, skip: Disc | null = null): number => {
    const r = size / 2;
    let best = cap;
    index.near(s, r + maxR + SAME_COLOR_GAP_IN + SPINE_SLACK_IN + cap, (d) => {
      if (d === skip) return;
      const need = required(color, r, d);
      if (Math.abs(s - d.s) - r - d.r - need > best) return;
      const c = cone.dist(s, ang, d.s, d.ang) - r - d.r - need - (d.enh ? SPINE_SLACK_IN : 0);
      if (c < best) best = c;
    });
    return best;
  };
  const zoneOf = (size: number): [number, number] => {
    const [lo, hi] = sizeZone(size, sizes, topShare);
    const r = size / 2;
    // the whole ball stays on the tree and clear of the topper
    return [Math.max(lo * cone.S + 0.01, topperIn + r), Math.min(hi * cone.S, cone.S - r)];
  };
  const sampleS = (lo: number, hi: number) => Math.sqrt(lo * lo + random() * (hi * hi - lo * lo)); // even by area
  const failed = new Set<string>();
  const miss = (size: number, color: number) => {
    unplaced[size] = (unplaced[size] ?? 0) + 1;
    missingArea += Math.PI * (size / 2) ** 2;
    failed.add(`${size}:${color}`);
  };

  queue.forEach((item, qi) => {
    const [lo, hi] = zoneOf(item.size);
    if (hi <= lo) return miss(item.size, item.color);
    const big = item.size >= BIG_ORNAMENT_IN;
    let best: { s: number; ang: number; score: number } | null = null;
    // Keep looking until a few spots that fit have been compared; give up sooner
    // once the same size and color has already failed to find room.
    const want = mode === "even" ? 60 : 30;
    const budget = failed.has(`${item.size}:${item.color}`) ? 500 : 4000;
    const cap = Math.max(6, item.size);
    let found = 0;
    for (let k = 0; k < budget && found < want; k++) {
      const s = sampleS(lo, hi);
      const ang = random() * TAU;
      const slack = slackAt(s, ang, item.size, item.color, cap);
      if (slack < 0) continue;
      found++;
      // big balls lean low ("bottom row mostly large")
      const lean = big ? (s / cone.S) * item.size * 0.35 : 0;
      const score = mode === "even" ? Math.min(slack, item.size) + lean : -slack + lean;
      if (!best || score > best.score) best = { s, ang, score };
    }
    if (!best) return miss(item.size, item.color);
    const d: Disc = { s: best.s, ang: best.ang, r: item.size / 2, owner: 100000 + qi, color: item.color, enh: false };
    index.add(d);
    ornDiscs.push(d);
    orn.push({ s: best.s, ang: best.ang, size: item.size, color: item.color });
  });

  // Even out the spacing: nudge each ornament toward wherever it has more room.
  for (let pass = 0; pass < 12; pass++) {
    for (let i = 0; i < ornDiscs.length; i++) {
      const d = ornDiscs[i];
      const o = orn[i];
      const [lo, hi] = zoneOf(o.size);
      let cur = slackAt(d.s, d.ang, o.size, o.color, 6, d);
      if (cur >= 6) continue;
      const reach = Math.max(0.5, Math.min(3, cur + 1));
      for (let k = 0; k < 4; k++) {
        const ns = Math.min(hi, Math.max(lo, d.s + (random() - 0.5) * 2 * reach));
        const na = d.ang + ((random() - 0.5) * 2 * reach) / Math.max(4, ns * cone.k);
        const slack = slackAt(ns, na, o.size, o.color, 6, d);
        if (slack > cur) {
          index.remove(d);
          d.s = o.s = ns;
          d.ang = o.ang = na;
          index.add(d);
          cur = slack;
        }
      }
    }
  }
  return { orn, unplaced, missingArea };
}

/**
 * Lay out a tree. Deterministic: the same input always gives the same layout.
 */
export function buildTreeInstallLayout(input: TreeInstallLayoutInput): TreeInstallLayout {
  const heightIn = input.heightFt * 12;
  const baseRadiusIn = input.widthIn / 2;
  const cone = new Cone(heightIn, baseRadiusIn);
  const eLen = input.enhancerLengthIn ?? ENHANCER_LENGTH_IN;
  const eWid = input.enhancerWidthIn ?? ENHANCER_WIDTH_IN;
  const colorCount = clampColorCount(input.colorCount);
  const sameColorRule = colorCount > 1;
  const seed = hashInput(input);
  // The topper's spray and bow fill the very top: about a tenth of the height.
  const topperIn = Math.min(16, Math.max(8, heightIn * 0.1));
  const problems: string[] = [];

  // 1. enhancers on the six swirl lines
  const perLine = enhancersPerLine(input.enhancers);
  const plans = enhancerPlans(cone, perLine, topperIn, eLen, eWid, rng(seed + 2));

  // 2. the ornament list, biggest first, colors dealt round robin so each spreads around
  const sizes = Object.keys(input.loose)
    .map(Number)
    .filter((s) => input.loose[s] > 0)
    .sort((a, b) => b - a);
  const queue: Pending[] = [];
  let colorTurn = 0;
  for (const size of sizes) {
    const left = splitAcrossColors(input.loose[size], colorCount);
    let remaining = left.reduce((a, b) => a + b, 0);
    while (remaining > 0) {
      const c = colorTurn % colorCount;
      colorTurn++;
      if (left[c] > 0) {
        left[c]--;
        remaining--;
        queue.push({ size, color: c + 1 });
      }
    }
  }

  // 3. try each enhancer plan (gentlest swirl first), even packing then dense; keep
  // the first that fits everything, else the one that leaves the least off.
  let chosen: { plan: EnhancerPlan; drafts: EnhancerDraft[]; pack: PackResult; enhancersUnplaced: number } | null = null;
  attempts: for (const plan of plans) {
    const drafts: EnhancerDraft[] = [];
    // Enhancers may touch, so every one goes on; only a spray that would sit on the
    // same spot as another is left off.
    for (const d of plan.drafts) {
      const m = d.spine[Math.floor(d.spine.length / 2)];
      const stacked = drafts.some((e) => {
        const q = e.spine[Math.floor(e.spine.length / 2)];
        return cone.dist(m.s, m.ang, q.s, q.ang) < STACK_SHARE * eWid;
      });
      if (!stacked) drafts.push(d);
    }
    const enhancersUnplaced = Math.max(0, Math.floor(input.enhancers) - drafts.length);
    const enhancerDiscs: Disc[] = [];
    drafts.forEach((d, idx) => {
      for (const p of d.spine) enhancerDiscs.push({ s: p.s, ang: p.ang, r: eWid / 2, owner: idx, color: 0, enh: true });
    });
    for (const mode of ["even", "dense"] as PackMode[]) {
      const pack = packOrnaments(cone, enhancerDiscs, queue, sizes, topperIn, sameColorRule, mode, rng(seed + (mode === "even" ? 0 : 1)));
      // rank by how much is left off, sprays and balls alike, in square inches
      const leftOff = (e: number, p: PackResult) => e * eLen * eWid + p.missingArea;
      const better = !chosen || leftOff(enhancersUnplaced, pack) < leftOff(chosen.enhancersUnplaced, chosen.pack) - 1e-9;
      if (better) chosen = { plan, drafts, pack, enhancersUnplaced };
      if (enhancersUnplaced === 0 && pack.missingArea === 0) break attempts;
    }
  }
  const { plan, drafts: enhDrafts, pack, enhancersUnplaced } = chosen!;
  const letters = pickLetters(cone, perLine, enhDrafts);
  const orn = pack.orn;
  const unplaced = pack.unplaced;

  // 4. rows for the build slider, top down
  const rowOf = (s: number) => Math.max(0, Math.floor((s - topperIn) / ROW_STEP_IN));

  // 5. pieces inside the enhancers: biggest first, dealt round robin
  const insideSizes = Object.keys(input.inEnhancers ?? {})
    .map(Number)
    .sort((a, b) => b - a)
    .flatMap((size) => Array<number>((input.inEnhancers ?? {})[size] ?? 0).fill(size));
  const inside: number[][] = enhDrafts.map(() => []);
  if (enhDrafts.length) insideSizes.forEach((size, i) => inside[i % enhDrafts.length].push(size));

  // Turn the whole tree so the top A sits at the front, right under the topper.
  const topA = enhDrafts
    .map((d, i) => ({ d, letter: letters[d.line][d.indexOnLine], spine: d.spine, i }))
    .filter((x) => x.letter === "A")
    .sort((a, b) => a.d.centerAlong - b.d.centerAlong || a.d.line - b.d.line)[0];
  const turn = topA ? -topA.spine[Math.floor(topA.spine.length / 2)].ang : 0;

  const toPoint = (s: number, ang: number): ConePoint => ({ t: s / cone.S, ang: wrapTau(ang + turn) });
  const enhancers: PlacedEnhancer[] = enhDrafts.map((d, i) => {
    const mid = d.spine[Math.floor(d.spine.length / 2)];
    return {
      kind: "enhancer",
      id: i,
      letter: letters[d.line][d.indexOnLine],
      line: d.line,
      indexOnLine: d.indexOnLine,
      ...toPoint(mid.s, mid.ang),
      spine: d.spine.map((p) => toPoint(p.s, p.ang)),
      downhill: (() => {
        const line = plan.lines[d.line];
        const sd = sAtLength(line, d.centerAlong + 4);
        return toPoint(sd, angOnLine(line, sd, cone, plan.swirl));
      })(),
      inside: inside[i],
      row: rowOf(mid.s),
    };
  });
  const ornaments: PlacedOrnament[] = orn.map((o, i) => ({
    kind: "ornament",
    id: i,
    size: o.size,
    color: o.color,
    ...toPoint(o.s, o.ang),
    row: rowOf(o.s),
  }));
  const lineSamples = plan.lines.map((line) =>
    Array.from({ length: 61 }, (_, i) => {
      const s = line.ss[0] + ((line.ss[line.ss.length - 1] - line.ss[0]) * i) / 60;
      return toPoint(s, angOnLine(line, s, cone, plan.swirl));
    })
  );

  const rows = Math.max(1, rowOf(cone.S) + 1);
  const check = checkTreeInstallLayout(
    { heightIn, baseRadiusIn, ornaments, enhancers },
    { enhancerWidthIn: eWid, colorCount }
  );

  const missing = Object.entries(unplaced).filter(([, n]) => n > 0);
  if (enhancersUnplaced > 0) {
    problems.push(
      `${enhancersUnplaced} of ${input.enhancers} enhancers would sit on top of another one on the six swirl lines.`
    );
  }
  if (missing.length) {
    problems.push(
      `No room left for ${missing
        .sort((a, b) => Number(b[0]) - Number(a[0]))
        .map(([size, n]) => `${n} x ${size}"`)
        .join(", ")} without stacking them on top of other pieces. They are left off the mockup.`
    );
  }
  if (colorCount === 1) {
    problems.push("One color: every ornament is the same color, so the no-same-color-touching rule can't apply.");
  }

  return {
    heightIn,
    baseRadiusIn,
    slantIn: cone.S,
    swirl: plan.swirl,
    topperIn,
    lines: lineSamples,
    ornaments,
    enhancers,
    rows,
    unplaced,
    enhancersUnplaced,
    fits: enhancersUnplaced === 0 && missing.length === 0,
    problems,
    check,
  };
}

/**
 * Re-check a finished layout from scratch, in inches on the unrolled cone: overlaps,
 * enhancers touching, same colors touching, big ornaments up top, A/B alternating.
 */
export function checkTreeInstallLayout(
  layout: Pick<TreeInstallLayout, "heightIn" | "baseRadiusIn" | "ornaments" | "enhancers">,
  opts: { enhancerWidthIn?: number; colorCount: number }
): TreeInstallCheck {
  const cone = new Cone(layout.heightIn, layout.baseRadiusIn);
  const er = (opts.enhancerWidthIn ?? ENHANCER_WIDTH_IN) / 2;
  const S = cone.S;
  const enh = layout.enhancers.map((e) => e.spine.map((p) => ({ s: p.t * S, ang: p.ang })));
  const orn = layout.ornaments.map((o) => ({ s: o.t * S, ang: o.ang, r: o.size / 2, color: o.color, size: o.size, t: o.t }));
  let overlaps = 0;
  let stacks = 0;
  let enhancerTouches = 0;
  let colorTouches = 0;
  let minClear = Infinity;
  const one = (o: { s: number; ang: number }) => [o];
  // centers: an ornament's middle, a spray's middle
  const centers = [
    ...orn.map((o) => ({ s: o.s, ang: o.ang, d: o.size })),
    ...enh.map((sp) => ({ ...sp[Math.floor(sp.length / 2)], d: er * 2 })),
  ];
  for (let i = 0; i < centers.length; i++) {
    for (let j = i + 1; j < centers.length; j++) {
      const a = centers[i];
      const b = centers[j];
      if (cone.dist(a.s, a.ang, b.s, b.ang) < STACK_SHARE * Math.min(a.d, b.d) - 1e-6) stacks++;
    }
  }
  for (let i = 0; i < enh.length; i++) {
    for (let j = i + 1; j < enh.length; j++) {
      const c = capsuleClearance(cone, enh[i], enh[j], er, er);
      minClear = Math.min(minClear, c);
      if (c < 0) overlaps++;
      if (c < ENHANCER_GAP_IN - 1e-6) enhancerTouches++;
    }
  }
  for (let i = 0; i < orn.length; i++) {
    for (const e of enh) {
      const c = capsuleClearance(cone, one(orn[i]), e, orn[i].r, er);
      minClear = Math.min(minClear, c);
      if (c < 0) overlaps++;
    }
    for (let j = i + 1; j < orn.length; j++) {
      const a = orn[i];
      const b = orn[j];
      const c = cone.dist(a.s, a.ang, b.s, b.ang) - a.r - b.r;
      minClear = Math.min(minClear, c);
      if (c < 0) overlaps++;
      if (opts.colorCount > 1 && a.color === b.color && c < SAME_COLOR_GAP_IN - 1e-6) colorTouches++;
    }
  }
  const bigInTop = orn.filter((o) => o.size >= BIG_ORNAMENT_IN && o.t < BIG_ORNAMENT_TOP_SHARE).length;
  const byLine = new Map<number, PlacedEnhancer[]>();
  for (const e of layout.enhancers) byLine.set(e.line, [...(byLine.get(e.line) ?? []), e]);
  let abAlternates = true;
  byLine.forEach((list) => {
    const sorted = [...list].sort((a, b) => a.indexOnLine - b.indexOnLine);
    for (let i = 1; i < sorted.length; i++) if (sorted[i].letter === sorted[i - 1].letter) abAlternates = false;
  });
  return {
    stacks,
    overlaps,
    enhancerTouches,
    colorTouches,
    bigInTop,
    abAlternates,
    minClearanceIn: Number.isFinite(minClear) ? Math.round(minClear * 100) / 100 : 0,
  };
}
