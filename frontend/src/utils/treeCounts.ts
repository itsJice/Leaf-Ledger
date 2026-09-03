// Tree counts — the calibration loop behind the ornament calculator's golden
// table. Every install / teardown records what was ACTUALLY on the tree; this
// module averages those records per golden height and measures the drift
// against the approved row. Pure helpers only (no fetch, no React) so they can
// be unit-checked with `npx tsx`. The API calls live in pages/TreeCounts.tsx.
// See treeCounts.md for the API, storage and the drift rule.

import { GOLDEN_RECIPES, ORNAMENT_OPTIONS } from "./ornamentRecipe";
import type { GoldenRecipe, OrnamentOption } from "./ornamentRecipe";

export type TreeCountKind = "install" | "teardown";

/** One row of `ll_app.tree_counts`, as the API returns it. */
export interface TreeCountRecord {
  id: number;
  /** ISO timestamp. */
  recorded_at: string;
  kind: TreeCountKind;
  height_ft: number;
  width_in: number;
  profile: string | null;
  style: string | null;
  label: string | null;
  /** Ornament size in inches (string key, e.g. "4.75") -> pieces. Zero sizes are absent. */
  counts: Record<string, number>;
  enhancers: number;
  notes: string | null;
  created_by: string | null;
  created_name: string | null;
}

/** POST body for `/api/tree-counts`. */
export interface TreeCountInput {
  kind: TreeCountKind;
  height_ft: number;
  width_in: number;
  profile?: string | null;
  style?: string | null;
  label?: string | null;
  counts: Record<string, number>;
  enhancers: number;
  notes?: string | null;
}

/**
 * The sizes a crew counts: 3" through 15.75". Smaller balls only ever ride
 * inside enhancers (counted as enhancers, not pieces) and 20"/24" are not
 * stocked for the N59 line, so neither gets a column on the count grid.
 */
export const COUNT_SIZES: OrnamentOption[] = ORNAMENT_OPTIONS.filter(
  (o) => o.size >= 3 && o.size <= 15.75
);

/** Records within this many feet of a golden height count as "that tree size". */
export const HEIGHT_TOLERANCE_FT = 0.25;

/** A per-size difference of at least this many pieces is drift. */
export const DRIFT_MIN_PIECES = 4;
/** ...or at least this share of the approved count (0.2 = 20%). */
export const DRIFT_MIN_PCT = 0.2;

/** Total ornament pieces in a counts map (enhancers not included). */
export function totalPieces(counts: Record<string, number>): number {
  return Object.values(counts).reduce((sum, n) => sum + (Number(n) || 0), 0);
}

/**
 * Turn the count grid's raw text fields into an API counts map. Blank, zero and
 * non-numeric cells are dropped; keys are the size's display string ("4.75").
 */
export function countsFromForm(form: Record<string, string>): Record<string, number> {
  const out: Record<string, number> = {};
  Object.entries(form).forEach(([size, text]) => {
    const n = Math.round(Number(text));
    if (text.trim() === "" || !Number.isFinite(n) || n <= 0) return;
    out[size] = n;
  });
  return out;
}

/** Records whose height is within `toleranceFt` of `heightFt`. */
export function recordsNearHeight(
  records: TreeCountRecord[],
  heightFt: number,
  toleranceFt: number = HEIGHT_TOLERANCE_FT
): TreeCountRecord[] {
  return records.filter((r) => Math.abs(r.height_ft - heightFt) <= toleranceFt + 1e-9);
}

export interface CountAverage {
  /** How many records went into the average. */
  n: number;
  widthIn: number;
  enhancers: number;
  /** Size (in) -> mean pieces. A record with no entry for a size counts as 0. */
  counts: Record<number, number>;
}

/**
 * Mean per-size count across records. A size missing from a record is a real
 * zero (nothing of that size was on the tree), so every record contributes to
 * every size's denominator. Returns `null` for an empty list.
 */
export function averageCounts(records: TreeCountRecord[]): CountAverage | null {
  if (records.length === 0) return null;
  const totals: Record<number, number> = {};
  let width = 0;
  let enhancers = 0;
  records.forEach((r) => {
    width += Number(r.width_in) || 0;
    enhancers += Number(r.enhancers) || 0;
    Object.entries(r.counts).forEach(([size, n]) => {
      const key = Number(size);
      if (!Number.isFinite(key)) return;
      totals[key] = (totals[key] ?? 0) + (Number(n) || 0);
    });
  });
  const n = records.length;
  const counts: Record<number, number> = {};
  Object.entries(totals).forEach(([size, total]) => {
    counts[Number(size)] = total / n;
  });
  return { n, widthIn: width / n, enhancers: enhancers / n, counts };
}

/**
 * Round to the nearest even integer — golden quantities are per-color pairs.
 * An odd whole number sits exactly between two evens and rounds UP (25 -> 26),
 * matching `Math.round`; a few extra pieces beats a thin tree.
 */
export function roundToEven(value: number): number {
  return Math.round(value / 2) * 2;
}

export interface DriftCell {
  approved: number;
  actual: number;
  /** actual − approved. */
  diff: number;
  /** diff / approved, or null when nothing was approved for the size. */
  pct: number | null;
  flagged: boolean;
}

/**
 * The drift rule: a size is flagged when |actual − approved| is at least
 * DRIFT_MIN_PIECES pieces OR at least DRIFT_MIN_PCT of the approved count. A
 * size the table does not use at all (approved 0) is flagged as soon as the
 * average is non-zero — the crews are hanging something the recipe never asked
 * for, which is exactly what a designer should look at.
 */
export function driftCell(approved: number, actual: number): DriftCell {
  const diff = actual - approved;
  const abs = Math.abs(diff);
  const pct = approved > 0 ? diff / approved : null;
  const flagged =
    abs >= DRIFT_MIN_PIECES ||
    (pct !== null && Math.abs(pct) >= DRIFT_MIN_PCT) ||
    (approved === 0 && actual > 0);
  return { approved, actual, diff, pct, flagged };
}

/**
 * A `GOLDEN_RECIPES` entry as TypeScript source, ready to paste. Sizes are
 * sorted ascending, zero quantities are dropped, and quantities are rounded to
 * even (`roundToEven`) so a pasted average keeps the two-color pairing.
 */
export function goldenRowSnippet(
  heightFt: number,
  widthIn: number,
  quantities: Record<number, number>
): string {
  const parts = Object.entries(quantities)
    .map(([size, qty]) => [Number(size), roundToEven(qty)] as const)
    .filter(([, qty]) => qty > 0)
    .sort((a, b) => a[0] - b[0])
    .map(([size, qty]) => `${size}: ${qty}`);
  return `{ heightFt: ${heightFt}, widthIn: ${Math.round(widthIn)}, quantities: { ${parts.join(", ")} } },`;
}

export interface TableComparisonRow {
  heightFt: number;
  /** The approved row. */
  approved: GoldenRecipe;
  /** Records within HEIGHT_TOLERANCE_FT of this height, newest first as given. */
  records: TreeCountRecord[];
  /** null when nothing has been recorded at this height yet. */
  average: CountAverage | null;
  /** Every size in either the approved row or the average, ascending. */
  sizes: number[];
  /** Per-size drift, keyed by size. Present only when there is an average. */
  cells: Record<number, DriftCell>;
  /** True when any size is flagged. */
  drifted: boolean;
  /** Paste-ready golden row built from the average (approved width kept). Empty without records. */
  snippet: string;
}

/**
 * The "table vs reality" view: one row per golden height, the approved
 * quantities beside the average of everything counted at that height.
 */
export function compareToTable(
  records: TreeCountRecord[],
  golden: GoldenRecipe[] = GOLDEN_RECIPES,
  toleranceFt: number = HEIGHT_TOLERANCE_FT
): TableComparisonRow[] {
  return golden.map((approved) => {
    const near = recordsNearHeight(records, approved.heightFt, toleranceFt);
    const average = averageCounts(near);
    const sizeSet = new Set<number>(Object.keys(approved.quantities).map(Number));
    if (average) Object.keys(average.counts).forEach((s) => sizeSet.add(Number(s)));
    const sizes = [...sizeSet].sort((a, b) => a - b);
    const cells: Record<number, DriftCell> = {};
    if (average) {
      sizes.forEach((size) => {
        cells[size] = driftCell(approved.quantities[size] ?? 0, average.counts[size] ?? 0);
      });
    }
    return {
      heightFt: approved.heightFt,
      approved,
      records: near,
      average,
      sizes,
      cells,
      drifted: Object.values(cells).some((c) => c.flagged),
      snippet: average ? goldenRowSnippet(approved.heightFt, approved.widthIn, average.counts) : "",
    };
  });
}

/** "4 (12)" style summary of a record's counts, largest size first. */
export function summariseCounts(counts: Record<string, number>): string {
  return Object.entries(counts)
    .map(([size, n]) => [Number(size), n] as const)
    .filter(([, n]) => n > 0)
    .sort((a, b) => b[0] - a[0])
    .map(([size, n]) => `${size}"×${n}`)
    .join(" · ");
}
