// Ornament recipe engine — a faithful port of Vickerman's public Ornament
// Calculator (vickerman.com/ornamentcalculator). The math is reproduced exactly
// so our numbers match theirs; verified against the live site
// (7.5 ft x 55 in -> 3"x42, 4"x41, 4.75"x21, 6"x10, density 40%).
//
// Model of a tree as a cone:
//   radius = (width_in - 20) / 2
//   height = (height_ft * 12) - 20
//   surfaceArea = pi*r^2 (base) + pi*r*slant (side)
// The recipe always targets 40% coverage, picks a 4-size "family" based on the
// coverage bucket, splits coverage 20/35/25/20 across those sizes, then converts
// each size's coverage share into a whole-ornament count.

export interface OrnamentOption {
  /** Label shown in the UI (e.g. "4.75"). */
  display: string;
  /** Diameter in inches. */
  size: number;
  /** How many come in a retail pack (1 = sold individually). */
  qtyPerPack: number;
  /** Vickerman size code, kept for future catalog/SKU mapping. */
  sizeCode: string;
  /** Flat circle area of one ornament: pi*(size/2)^2. */
  planarArea: number;
}

/**
 * Ornament sizes for the N59 single-color ball line — the sizes this calculator
 * can price into real SKUs. The 12 core sizes come from Vickerman's own page
 * model; 1" (03) and 1.6" (54) were added from our scraped catalog
 * (`catalog-extraction/outputs/vickerman-full`), which are real N59 ball sizes
 * missing from Vickerman's public tool. planarArea = π·(size/2)².
 *
 * Not included: 5", 5.5", 14" ball ornaments exist in the wider catalog but have
 * no N59 size code, so they can't produce valid SKUs for this line. 20"/24" have
 * no N59 ball products but stay because Vickerman's recipe uses 20" for big trees.
 */
export const ORNAMENT_OPTIONS: OrnamentOption[] = [
  { display: "1", size: 1, qtyPerPack: 18, sizeCode: "03", planarArea: 0.7853981633974483 },
  { display: "1.6", size: 1.6, qtyPerPack: 96, sizeCode: "54", planarArea: 2.0106192982974678 },
  { display: "2.4", size: 2.4, qtyPerPack: 24, sizeCode: "06", planarArea: 4.523893421169298 },
  { display: "2.75", size: 2.75, qtyPerPack: 12, sizeCode: "07", planarArea: 5.939573610693197 },
  { display: "3", size: 3, qtyPerPack: 12, sizeCode: "08", planarArea: 7.068583470577027 },
  { display: "4", size: 4, qtyPerPack: 6, sizeCode: "10", planarArea: 12.56637061435916 },
  { display: "4.75", size: 4.75, qtyPerPack: 4, sizeCode: "12", planarArea: 17.72054606165491 },
  { display: "6", size: 6, qtyPerPack: 4, sizeCode: "15", planarArea: 28.27433388230811 },
  { display: "8", size: 8, qtyPerPack: 1, sizeCode: "20", planarArea: 50.26548245743664 },
  { display: "10", size: 10, qtyPerPack: 1, sizeCode: "25", planarArea: 78.53981633974475 },
  { display: "12", size: 12, qtyPerPack: 1, sizeCode: "30", planarArea: 113.09733552923244 },
  { display: "15.75", size: 15.75, qtyPerPack: 1, sizeCode: "40", planarArea: 194.8278319077793 },
  { display: "20", size: 20, qtyPerPack: 1, sizeCode: "45", planarArea: 314.159265358979 },
  { display: "24", size: 24, qtyPerPack: 1, sizeCode: "46", planarArea: 452.38934211692975 },
];

/**
 * Coverage buckets. Each entry: recipe applies when coverage is below `under`,
 * using the four `sizes` (smallest -> largest). The last bucket is the catch-all.
 */
const RECIPE_BUCKETS: { under: number; sizes: [number, number, number, number] }[] = [
  { under: 1000, sizes: [2.4, 3, 4, 4.75] },
  { under: 5000, sizes: [3, 4, 4.75, 6] },
  { under: 9000, sizes: [4, 4.75, 6, 8] },
  { under: 13000, sizes: [4.75, 6, 8, 10] },
  { under: 18000, sizes: [6, 8, 10, 12] },
  { under: 25000, sizes: [8, 10, 12, 15.75] },
  { under: Infinity, sizes: [10, 12, 15.75, 20] },
];

/** How the coverage is split across the four sizes (smallest -> largest). */
const COVERAGE_SPLIT: [number, number, number, number] = [0.2, 0.35, 0.25, 0.2];

/** The recipe always fills to 40% of the tree's surface area. */
export const RECIPE_TARGET_COVERAGE = 0.4;

/** Cone surface area (sq in) for a tree, or 0 when the tree is too small. */
export function treeSurfaceArea(heightFt: number, widthIn: number): number {
  const radius = (widthIn - 20) / 2;
  const adjustedHeight = heightFt * 12 - 20;
  if (radius <= 0 || adjustedHeight <= 0) return 0;
  const slant = Math.sqrt(adjustedHeight ** 2 + radius ** 2);
  return Math.PI * radius ** 2 + Math.PI * radius * slant;
}

/** Whole-ornament count for a given size's coverage share. */
function quantityForCoverage(planarArea: number, coverage: number): number {
  return Math.round((coverage / planarArea) * 0.75);
}

/** The bucket index (1-based) a coverage value lands in — handy for display. */
export function recipeBucketNumber(coverage: number): number {
  const idx = RECIPE_BUCKETS.findIndex((b) => coverage < b.under);
  return idx === -1 ? RECIPE_BUCKETS.length : idx + 1;
}

export interface RecipeLine {
  option: OrnamentOption;
  quantity: number;
}

export interface RecipeResult {
  surfaceArea: number;
  /** Coverage target = surfaceArea * 0.4. */
  recipeCoverage: number;
  bucketNumber: number;
  lines: RecipeLine[];
}

/**
 * Produce the recommended recipe for a tree. Returns an empty line list (and
 * zero areas) when the tree dimensions are too small to compute.
 */
export function buildRecipe(
  heightFt: number,
  widthIn: number,
  targetCoverage: number = RECIPE_TARGET_COVERAGE
): RecipeResult {
  const surfaceArea = treeSurfaceArea(heightFt, widthIn);
  if (!Number.isFinite(surfaceArea) || surfaceArea <= 0) {
    return { surfaceArea: 0, recipeCoverage: 0, bucketNumber: 0, lines: [] };
  }

  const recipeCoverage = surfaceArea * targetCoverage;
  const bucket = RECIPE_BUCKETS.find((b) => recipeCoverage < b.under)!;

  const lines: RecipeLine[] = bucket.sizes.map((size, i) => {
    const option = ORNAMENT_OPTIONS.find((o) => o.size === size)!;
    return {
      option,
      quantity: quantityForCoverage(option.planarArea, recipeCoverage * COVERAGE_SPLIT[i]),
    };
  });

  return {
    surfaceArea,
    recipeCoverage,
    bucketNumber: recipeBucketNumber(recipeCoverage),
    lines,
  };
}

// ---------------------------------------------------------------------------
// Leaf & Ledger recipe — the design team's rules.
//
// Source of truth is a GOLDEN TABLE: the recipes the designers signed off in the
// 2026-09-03 session, one row per tree size, at the calculator's default widths.
// Trees between rows are interpolated size-by-size; trees beyond the table use a
// top-heavy formula (the big ornaments carry ~half the coverage) on Vickerman's
// surface-area math. Every result then gets the designers' hard rules: at least 8
// of the top size, quantities in multiples of the color count (two by default),
// and no sizes below the floor for that height. See
// `Vickerman Ornament Rules/designer-recipe-plan.md`.
//
// The coverage slider scales the table: 40 (the default) is the recipe as approved.
// Three modifiers (designer rules 4, 6, 7) sit on top: the width profile (pencil /
// slim / standard / full — drives the width, and through it the enhancer count),
// the design style (traditional = the table; contemporary thins the fill sizes),
// and the color count (drives the rounding).
// ---------------------------------------------------------------------------

export type RecipeMode = "vickerman" | "leafledger";

/** Tree width profile — the designers' pencil / slim / standard / full buckets. */
export type WidthProfile = "pencil" | "slim" | "standard" | "full";

/** Design style: traditional is the golden table; contemporary is patterns, fewer pieces. */
export type DesignStyle = "traditional" | "contemporary";

/** Modifiers on the Leaf & Ledger recipe; every field defaults to the table as approved. */
export interface LeafLedgerOptions {
  /** Traditional = the table as approved; contemporary thins the fill sizes. */
  style?: DesignStyle;
  /** Colors in the design (1–4): every quantity rounds to a multiple of it. */
  colorCount?: number;
}

export interface GoldenRecipe {
  heightFt: number;
  widthIn: number;
  /** Size (in) -> pieces, as approved. */
  quantities: Record<number, number>;
}

/** Designer-approved recipes, smallest tree first. Widths = height x 6.5. */
export const GOLDEN_RECIPES: GoldenRecipe[] = [
  { heightFt: 7.5, widthIn: 49, quantities: { 3: 25, 4: 12, 4.75: 16, 6: 16, 8: 8 } },
  { heightFt: 8, widthIn: 52, quantities: { 4: 25, 4.75: 30, 6: 20, 8: 10, 10: 8 } },
  { heightFt: 10, widthIn: 65, quantities: { 4: 36, 4.75: 36, 6: 30, 8: 20, 10: 12 } },
  { heightFt: 12, widthIn: 78, quantities: { 4.75: 40, 6: 30, 8: 17, 10: 15, 12: 10 } },
];

/** Sizes the Leaf & Ledger recipe will auto-select, smallest -> largest. */
const LL_SIZE_LADDER = [2.4, 3, 4, 4.75, 6, 8, 10, 12, 15.75, 20];
/** How many sizes a formula-built recipe uses, top size included. */
const LL_SIZE_COUNT = 5;
/** Coverage share by rank from the top size down (averaged from the golden table). */
const LL_TOP_HEAVY_SHARES = [0.25, 0.25, 0.2, 0.17, 0.13];
/** Coverage the formula targets beyond the table: the 12 ft row's density. */
const LL_FORMULA_COVERAGE = 0.44;
/** Never fewer than this many of the largest size — it is the design, not an accent. */
const LL_MIN_TOP_COUNT = 8;
/** Designs are usually two colors, so quantities round to even numbers by default. */
export const LL_DEFAULT_COLOR_COUNT = 2;
/** The color counts the recipe supports. */
export const LL_MIN_COLOR_COUNT = 1;
export const LL_MAX_COLOR_COUNT = 4;
/** The top sizes a style leaves alone: they are the design, the rest is fill. */
const LL_DESIGN_SIZE_COUNT = 2;
/**
 * Contemporary multiplier on the fill sizes ("patterns, fewer ornaments"). A first
 * guess for the designers to react to — the table only has traditional recipes.
 */
export const LL_CONTEMPORARY_FILL = 0.7;
/** Largest tree a size may be used on loose ("3 inches gets lost"). */
const LL_SIZE_CEILING_FT: Record<number, number> = { 2.4: 7.5, 3: 7.5, 4: 10 };
/** The slider position that means "the recipe as approved". */
const LL_TABLE_COVERAGE = 0.4;
/** Default tree width when only height is known (12 ft -> 78 in, per the golden table). */
export const LL_WIDTH_PER_FT = 6.5;

/**
 * Width profiles as inches of width per foot of height, read off the designers'
 * enhancer table: pencil from "7.5' 30–32"", slim from "7–7.5' 40–45"", standard
 * is the golden table's ratio, full from the upper ends of "9.5–10' 60–82"" and
 * "12' 73–86"". Insertion order is narrowest first — the UI renders it as is.
 */
export const WIDTH_PROFILES: Record<WidthProfile, { label: string; inchesPerFt: number }> = {
  pencil: { label: "Pencil", inchesPerFt: 4.2 },
  slim: { label: "Slim", inchesPerFt: 5.6 },
  standard: { label: "Standard", inchesPerFt: LL_WIDTH_PER_FT },
  full: { label: "Full", inchesPerFt: 7.8 },
};
/** A width this close to a profile's ratio (either side) counts as that profile. */
const WIDTH_PROFILE_TOLERANCE = 0.06;

/** Default width (in) for a tree height when the user hasn't set one. */
export function defaultWidthForHeight(heightFt: number): number {
  return Math.round(heightFt * LL_WIDTH_PER_FT);
}

/** Width (in, rounded) of a tree of this height at a profile's ratio. */
export function widthForProfile(heightFt: number, profile: WidthProfile): number {
  return Math.round(heightFt * WIDTH_PROFILES[profile].inchesPerFt);
}

/** The profile a tree's width matches (within ±6% of the ratio), or null = custom. */
export function profileForWidth(heightFt: number, widthIn: number): WidthProfile | null {
  if (!(heightFt > 0) || !(widthIn > 0)) return null;
  const ratio = widthIn / heightFt;
  const profiles = Object.keys(WIDTH_PROFILES) as WidthProfile[];
  const distance = (p: WidthProfile) => Math.abs(ratio - WIDTH_PROFILES[p].inchesPerFt) / WIDTH_PROFILES[p].inchesPerFt;
  const nearest = profiles.reduce((best, p) => (distance(p) < distance(best) ? p : best));
  return distance(nearest) <= WIDTH_PROFILE_TOLERANCE ? nearest : null;
}

/** A color count the recipe can use: an integer from 1 to 4, defaulting to 2. */
export function clampColorCount(colorCount: number | undefined): number {
  if (colorCount === undefined || !Number.isFinite(colorCount)) return LL_DEFAULT_COLOR_COUNT;
  return Math.min(LL_MAX_COLOR_COUNT, Math.max(LL_MIN_COLOR_COUNT, Math.round(colorCount)));
}

/** The minimum top-size count for a color count: 8, rounded UP to a multiple of it. */
export function leafLedgerMinTopCount(colorCount: number = LL_DEFAULT_COLOR_COUNT): number {
  const colors = clampColorCount(colorCount);
  return Math.ceil(LL_MIN_TOP_COUNT / colors) * colors;
}

/**
 * The largest ornament for a tree: height in feet as inches, rounded up to a
 * stocked size — except an 8 ft (or taller) tree never tops out at 8".
 */
export function leafLedgerTopSize(heightFt: number): number {
  const rounded = LL_SIZE_LADDER.find((s) => s >= heightFt) ?? LL_SIZE_LADDER[LL_SIZE_LADDER.length - 1];
  return rounded === 8 && heightFt >= 8 ? 10 : rounded;
}

/** The sizes (smallest -> largest) a formula-built recipe uses for a tree height. */
export function leafLedgerSizes(heightFt: number): number[] {
  const topIdx = LL_SIZE_LADDER.indexOf(leafLedgerTopSize(heightFt));
  return LL_SIZE_LADDER.slice(Math.max(0, topIdx - LL_SIZE_COUNT + 1), topIdx + 1).filter(
    (size) => (LL_SIZE_CEILING_FT[size] ?? Infinity) >= heightFt
  );
}

/** Where a tree's Leaf & Ledger recipe comes from — shown in the UI. */
export type LeafLedgerSource =
  | { kind: "table"; heightFt: number }
  | { kind: "interpolated"; lowerFt: number; upperFt: number }
  | { kind: "formula"; from: "below" | "above" };

export function leafLedgerSource(heightFt: number): LeafLedgerSource {
  const exact = GOLDEN_RECIPES.find((g) => Math.abs(g.heightFt - heightFt) < 0.01);
  if (exact) return { kind: "table", heightFt: exact.heightFt };
  const upper = GOLDEN_RECIPES.find((g) => g.heightFt > heightFt);
  const lower = [...GOLDEN_RECIPES].reverse().find((g) => g.heightFt < heightFt);
  if (lower && upper) return { kind: "interpolated", lowerFt: lower.heightFt, upperFt: upper.heightFt };
  return { kind: "formula", from: lower ? "above" : "below" };
}

/** Round to a multiple of the color count, never below `min` when the raw value is positive. */
function roundForColors(raw: number, colorCount: number, min = 0): number {
  if (raw <= 0) return 0;
  const rounded = Math.round(raw / colorCount) * colorCount;
  return Math.max(rounded, min);
}

/** Raw (unrounded) size -> pieces for a tree, before the hard rules. */
function leafLedgerRawQuantities(heightFt: number, widthIn: number, coverage: number): Map<number, number> {
  const source = leafLedgerSource(heightFt);
  const scale = coverage / LL_TABLE_COVERAGE;
  const raw = new Map<number, number>();

  if (source.kind === "table" || source.kind === "interpolated") {
    const rows =
      source.kind === "table"
        ? [GOLDEN_RECIPES.find((g) => g.heightFt === source.heightFt)!]
        : [
            GOLDEN_RECIPES.find((g) => g.heightFt === source.lowerFt)!,
            GOLDEN_RECIPES.find((g) => g.heightFt === source.upperFt)!,
          ];
    const t = rows.length === 1 ? 0 : (heightFt - rows[0].heightFt) / (rows[1].heightFt - rows[0].heightFt);
    // A wider/narrower tree than the table assumed scales with surface area.
    const tableWidth = rows.length === 1 ? rows[0].widthIn : rows[0].widthIn + t * (rows[1].widthIn - rows[0].widthIn);
    const widthScale = treeSurfaceArea(heightFt, widthIn) / treeSurfaceArea(heightFt, tableWidth) || 1;
    const sizes = new Set(rows.flatMap((r) => Object.keys(r.quantities).map(Number)));
    sizes.forEach((size) => {
      const lo = rows[0].quantities[size] ?? 0;
      const hi = rows.length === 1 ? lo : rows[1].quantities[size] ?? 0;
      raw.set(size, (lo + t * (hi - lo)) * widthScale * scale);
    });
    return raw;
  }

  // Beyond the table: top-heavy shares on Vickerman's surface-area math.
  const totalCoverage = treeSurfaceArea(heightFt, widthIn) * LL_FORMULA_COVERAGE * scale;
  const sizes = leafLedgerSizes(heightFt).reverse(); // largest first
  const shares = LL_TOP_HEAVY_SHARES.slice(0, sizes.length);
  const shareTotal = shares.reduce((a, b) => a + b, 0);
  sizes.forEach((size, i) => {
    const option = ORNAMENT_OPTIONS.find((o) => o.size === size)!;
    raw.set(size, ((totalCoverage * shares[i]) / shareTotal / option.planarArea) * 0.75);
  });
  return raw;
}

/**
 * The Leaf & Ledger recipe for a tree. `options` are the modifiers: style
 * (contemporary multiplies every size below the top two by LL_CONTEMPORARY_FILL)
 * and color count (every quantity rounds to a multiple of it; the minimum top
 * count rounds up to one). Both default to the table as approved.
 */
export function buildLeafLedgerRecipe(
  heightFt: number,
  widthIn: number,
  targetCoverage: number = RECIPE_TARGET_COVERAGE,
  options: LeafLedgerOptions = {}
): RecipeResult {
  const surfaceArea = treeSurfaceArea(heightFt, widthIn);
  if (!Number.isFinite(surfaceArea) || surfaceArea <= 0) {
    return { surfaceArea: 0, recipeCoverage: 0, bucketNumber: 0, lines: [] };
  }

  const style = options.style ?? "traditional";
  const colorCount = clampColorCount(options.colorCount);
  const raw = leafLedgerRawQuantities(heightFt, widthIn, targetCoverage);
  const sizes = [...raw.keys()]
    .filter((size) => (LL_SIZE_CEILING_FT[size] ?? Infinity) >= heightFt)
    .sort((a, b) => a - b);
  const topSize = sizes[sizes.length - 1];
  // The top sizes are the design and stay put; a contemporary style thins the fill.
  const designSizes = new Set(sizes.slice(-LL_DESIGN_SIZE_COUNT));
  const fillScale = style === "contemporary" ? LL_CONTEMPORARY_FILL : 1;
  // An approved row, as approved: the designers' own counts win over the rounding
  // rules — but only with no modifiers, since the table is traditional, two colors.
  const source = leafLedgerSource(heightFt);
  const verbatim =
    source.kind === "table" &&
    targetCoverage === LL_TABLE_COVERAGE &&
    GOLDEN_RECIPES.find((g) => g.heightFt === source.heightFt)!.widthIn === widthIn &&
    style === "traditional" &&
    colorCount === LL_DEFAULT_COLOR_COUNT;

  const lines: RecipeLine[] = sizes
    .map((size) => {
      const scaled = raw.get(size)! * (designSizes.has(size) ? 1 : fillScale);
      return {
        option: ORNAMENT_OPTIONS.find((o) => o.size === size)!,
        quantity: verbatim
          ? Math.round(scaled)
          : roundForColors(
              scaled,
              colorCount,
              size === topSize && targetCoverage > 0 ? leafLedgerMinTopCount(colorCount) : 0
            ),
      };
    })
    .filter((line) => line.quantity > 0);

  const recipeCoverage = surfaceArea * targetCoverage;
  return {
    surfaceArea,
    recipeCoverage,
    bucketNumber: recipeBucketNumber(recipeCoverage),
    lines,
  };
}

/** Recipe for a tree under the chosen rule set (`options` only apply to Leaf & Ledger). */
export function buildRecipeFor(
  mode: RecipeMode,
  heightFt: number,
  widthIn: number,
  targetCoverage: number = RECIPE_TARGET_COVERAGE,
  options: LeafLedgerOptions = {}
): RecipeResult {
  return mode === "leafledger"
    ? buildLeafLedgerRecipe(heightFt, widthIn, targetCoverage, options)
    : buildRecipe(heightFt, widthIn, targetCoverage);
}

// ---------------------------------------------------------------------------
// Enhancers — the parallel bill of materials (designer rule 6).
//
// Enhancers (picks/sprays) are counted from the designers' card, keyed by tree
// height AND width profile (pencil / slim / standard / full). Some of the
// small ornaments live inside the enhancers rather than loose on the tree
// ("9 loose and 9 in the enhancers"), so the loose list and the enhancer list
// are produced together: `enhancerLookup` for the count, `enhancerAllocation`
// for the loose / in-enhancer split of each recipe line.
// ---------------------------------------------------------------------------

/**
 * The designers' enhancer card, verbatim: a count for every tree height and width
 * profile, confirmed by the lead designer 2026-10-01. It replaces the standard-only
 * card of 2026-09-30 and the surface-area scaling that stood in for the other
 * profiles (which gave a 9 ft slim 22 by accident and a 14 ft standard 48). Columns
 * follow `ENHANCER_CARD_HEIGHTS`.
 */
export const ENHANCER_CARD_HEIGHTS = [7, 7.5, 8, 9, 10, 12, 14, 15];
export const ENHANCER_CARD: Record<WidthProfile, number[]> = {
  pencil: [8, 10, 14, 20, 24, 28, 32, 36],
  slim: [10, 12, 16, 22, 26, 30, 34, 38],
  standard: [18, 20, 24, 30, 32, 36, 40, 44],
  full: [22, 24, 28, 34, 36, 40, 44, 48],
};

/** Profiles from narrowest to widest, for custom widths that fall between two. */
const PROFILES_BY_WIDTH = (Object.keys(WIDTH_PROFILES) as WidthProfile[]).sort(
  (a, b) => WIDTH_PROFILES[a].inchesPerFt - WIDTH_PROFILES[b].inchesPerFt
);

/** Ornaments this size and under split between the tree and the enhancers. */
export const ENHANCER_MAX_SIZE_IN = 4.75;
/** Share of an enhancer-sized quantity that goes into the enhancers ("9 and 9"). */
export const ENHANCER_SHARE = 0.5;

/** Where an enhancer count came from — shown in the UI. */
export type EnhancerSource =
  /** The tree's height and profile are on the card. */
  | { kind: "card"; profile: WidthProfile; heightFt: number }
  /** Between two card heights, same profile. */
  | { kind: "interpolated"; profile: WidthProfile; lowerFt: number; upperFt: number; lowerCount: number; upperCount: number }
  /** Shorter or taller than the card: its first or last two rows' trend, continued. */
  | { kind: "extrapolated"; profile: WidthProfile; fromFt: number; fromCount: number }
  /** A custom width: blended between the neighbouring profiles (the same one twice past either end). */
  | { kind: "customWidth"; narrower: WidthProfile; wider: WidthProfile; narrowerCount: number; widerCount: number }
  /** No usable tree dimensions. */
  | { kind: "none" };

export interface EnhancerLookup {
  count: number;
  source: EnhancerSource;
}

/** Enhancer counts round to the color count like everything else. */
function roundEnhancers(raw: number, colorCount: number): number {
  return Math.max(0, Math.round(raw / colorCount) * colorCount);
}

/** One profile's count at a height, unrounded, with where it came from. */
function cardValue(profile: WidthProfile, heightFt: number): { raw: number; source: EnhancerSource } {
  const heights = ENHANCER_CARD_HEIGHTS;
  const counts = ENHANCER_CARD[profile];
  const exact = heights.findIndex((h) => Math.abs(h - heightFt) < 1e-6);
  if (exact !== -1) return { raw: counts[exact], source: { kind: "card", profile, heightFt: heights[exact] } };

  const upperIdx = heights.findIndex((h) => h > heightFt);
  if (upperIdx > 0) {
    const [lo, hi] = [upperIdx - 1, upperIdx];
    const t = (heightFt - heights[lo]) / (heights[hi] - heights[lo]);
    return {
      raw: counts[lo] + t * (counts[hi] - counts[lo]),
      source: {
        kind: "interpolated",
        profile,
        lowerFt: heights[lo],
        upperFt: heights[hi],
        lowerCount: counts[lo],
        upperCount: counts[hi],
      },
    };
  }

  // Beyond either end: continue the trend of the two end rows (+4 per foot on every
  // profile at both ends of the card), never below 0.
  const [a, b] = upperIdx === 0 ? [0, 1] : [heights.length - 2, heights.length - 1];
  const from = upperIdx === 0 ? a : b;
  const slope = (counts[b] - counts[a]) / (heights[b] - heights[a]);
  return {
    raw: Math.max(0, counts[from] + (heightFt - heights[from]) * slope),
    source: { kind: "extrapolated", profile, fromFt: heights[from], fromCount: counts[from] },
  };
}

/**
 * Enhancer count for a tree, with where it came from. The tree's profile comes
 * from its width (`profileForWidth`); the count is then, in order:
 *   1. card         — the height and profile are on the card: the designer's count, verbatim;
 *   2. interpolated — between two card heights: a straight line between them;
 *   3. extrapolated — shorter than 7 ft or taller than 15 ft: the card's end trend continued;
 *   4. customWidth  — a width that matches no profile: blended between the two
 *                     profiles either side of it by inches per foot (past pencil or
 *                     full, that end profile's count).
 * Everything except a direct card hit rounds to a multiple of the color count.
 * Non-finite or non-positive height/width give 0 enhancers.
 */
export function enhancerLookup(
  heightFt: number,
  widthIn: number,
  colorCount: number = LL_DEFAULT_COLOR_COUNT
): EnhancerLookup {
  const colors = clampColorCount(colorCount);
  const height = Number.isFinite(heightFt) ? heightFt : 0;
  const width = Number.isFinite(widthIn) ? widthIn : 0;
  if (height <= 0 || width <= 0) return { count: 0, source: { kind: "none" } };

  const profile = profileForWidth(height, width);
  if (profile) {
    const { raw, source } = cardValue(profile, height);
    return { count: source.kind === "card" ? raw : roundEnhancers(raw, colors), source };
  }

  const ratio = width / height;
  const widerIdx = PROFILES_BY_WIDTH.findIndex((p) => WIDTH_PROFILES[p].inchesPerFt > ratio);
  const narrower = widerIdx === 0 ? PROFILES_BY_WIDTH[0] : PROFILES_BY_WIDTH[widerIdx === -1 ? PROFILES_BY_WIDTH.length - 1 : widerIdx - 1];
  const wider = widerIdx === -1 ? narrower : PROFILES_BY_WIDTH[widerIdx];
  const lo = cardValue(narrower, height).raw;
  const hi = cardValue(wider, height).raw;
  const span = WIDTH_PROFILES[wider].inchesPerFt - WIDTH_PROFILES[narrower].inchesPerFt;
  const t = span > 0 ? Math.min(1, Math.max(0, (ratio - WIDTH_PROFILES[narrower].inchesPerFt) / span)) : 0;
  return {
    count: roundEnhancers(lo + t * (hi - lo), colors),
    source: { kind: "customWidth", narrower, wider, narrowerCount: roundEnhancers(lo, colors), widerCount: roundEnhancers(hi, colors) },
  };
}

/** Enhancer count for a tree — see `enhancerLookup` for the order of rules. */
export function enhancerCount(
  heightFt: number,
  widthIn: number,
  colorCount: number = LL_DEFAULT_COLOR_COUNT
): number {
  return enhancerLookup(heightFt, widthIn, colorCount).count;
}

/**
 * Split one size's quantity across the design's colors, as evenly as possible:
 * 30 over 3 colors -> [10, 10, 10]; a hand-edited 31 -> [11, 10, 10] (any
 * remainder goes to the first colors). One color, or none, returns the quantity whole.
 */
export function splitAcrossColors(quantity: number, colorCount: number): number[] {
  const colors = Math.max(1, Math.floor(colorCount) || 1);
  const qty = Math.max(0, Math.floor(quantity) || 0);
  const each = Math.floor(qty / colors);
  const remainder = qty - each * colors;
  return Array.from({ length: colors }, (_, i) => each + (i < remainder ? 1 : 0));
}

/** A recipe line split between the tree and the enhancers. */
export interface EnhancerAllocationLine extends RecipeLine {
  loose: number;
  inEnhancers: number;
}

/**
 * Split each recipe line into loose-on-the-tree vs inside-the-enhancers.
 *
 * First guess for the designers to react to: sizes up to ENHANCER_MAX_SIZE_IN
 * put ENHANCER_SHARE of their count into the enhancers, rounded down to the
 * color count so the enhancer half is even and any odd piece stays loose
 * (18 -> 8 in enhancers / 10 loose; 25 -> 12 / 13). Larger sizes are all loose,
 * and so is everything when the tree has no enhancers. `enhancers` defaults to
 * the table count for the height at its default width; pass the user's edited
 * count to respect it. `colorCount` is the design's color count (the rounding step).
 */
export function enhancerAllocation(
  lines: RecipeLine[],
  heightFt: number,
  enhancers: number = enhancerCount(heightFt, defaultWidthForHeight(heightFt)),
  colorCount: number = LL_DEFAULT_COLOR_COUNT
): EnhancerAllocationLine[] {
  const colors = clampColorCount(colorCount);
  return lines.map((line) => {
    const eligible = enhancers > 0 && line.option.size <= ENHANCER_MAX_SIZE_IN;
    const inEnhancers = eligible ? Math.floor((line.quantity * ENHANCER_SHARE) / colors) * colors : 0;
    return { ...line, loose: line.quantity - inEnhancers, inEnhancers };
  });
}

/**
 * Coverage density (%) for an arbitrary set of quantities on a tree — mirrors
 * the calculator's live meter. Capped at 100. Quantities keyed by size.
 */
export function coverageDensity(
  heightFt: number,
  widthIn: number,
  quantities: Map<number, number>
): number {
  const surfaceArea = treeSurfaceArea(heightFt, widthIn);
  if (surfaceArea <= 0) return 0;
  let totalOrnamentArea = 0;
  quantities.forEach((qty, size) => {
    if (qty) totalOrnamentArea += Math.PI * (size / 2) ** 2 * qty;
  });
  const density = (totalOrnamentArea / surfaceArea / 0.75) * 100;
  return Math.min(100, Math.round(density));
}

/** Retail packs needed to cover a quantity (rounds up; "each" for singles). */
export function packSummary(option: OrnamentOption, quantity: number): string {
  if (!(quantity > 0)) return "";
  if (option.qtyPerPack === 1) return `${quantity} each`;
  const wholePacks = Math.ceil(quantity / option.qtyPerPack);
  return `${wholePacks} pack${wholePacks === 1 ? "" : "s"} of ${option.qtyPerPack}`;
}

// ---------------------------------------------------------------------------
// Whole packs — quantities purchasing can actually order.
//
// Ornaments come in packs (3" 12, 4" 6, 4.75" and 6" 4, 8" and up single —
// Vickerman's packs, checked against vickerman.com) and each color is ordered
// separately, so a size only orders cleanly in steps of one pack per color. With
// two colors: 3" in 24s, 4" in 12s, 4.75" and 6" in 8s. A recipe that ignores
// this turns 25 x 3" into 48 on the order (13 a color, two 12-packs each).
// `roundToWholePacks` moves a recipe onto those steps, staying as close to it as
// it can; `packOrder` says what ordering a quantity really brings in.
// ---------------------------------------------------------------------------

/** Pieces in one pack of a size (Vickerman's pack; 1 for a size not listed). */
export function packSizeFor(size: number): number {
  return ORNAMENT_OPTIONS.find((o) => o.size === size)?.qtyPerPack ?? 1;
}

/** The step a size orders in: one pack for every color. */
export function orderUnit(size: number, colorCount = 1): number {
  return packSizeFor(size) * Math.max(1, Math.floor(colorCount) || 1);
}

/** What ordering a quantity of one size, color by color, really brings in. */
export interface PackOrder {
  packSize: number;
  /** Pieces of each color (the design's even split). */
  perColor: number[];
  /** Whole packs each color needs. */
  packsPerColor: number[];
  /** Pieces that arrive: every color's packs, full. */
  ordered: number;
  /** Pieces left over after the recipe is hung: ordered − quantity. */
  spare: number;
}

/**
 * Packs and pieces for `quantity` of a size split evenly across `colorCount`
 * colors, each color rounded up to whole packs of `packSize` (Vickerman's pack for
 * the size unless a product says otherwise). 25 x 3" over 2 colors -> 13 + 12
 * pieces -> 2 + 1 packs of 12 -> 36 ordered, 11 spare.
 */
export function packOrder(size: number, quantity: number, colorCount = 1, packSize = packSizeFor(size)): PackOrder {
  const pack = Math.max(1, Math.floor(packSize) || 1);
  const perColor = splitAcrossColors(quantity, colorCount);
  const packsPerColor = perColor.map((n) => Math.ceil(n / pack));
  const ordered = packsPerColor.reduce((sum, k) => sum + k * pack, 0);
  const pieces = perColor.reduce((sum, n) => sum + n, 0);
  return { packSize: pack, perColor, packsPerColor, ordered, spare: ordered - pieces };
}

/** One size moved onto whole packs. */
export interface PackRounding {
  size: number;
  from: number;
  to: number;
}

export interface WholePackResult {
  /** Size (in) -> pieces, every size on whole packs for every color. */
  quantities: Map<number, number>;
  /** The sizes that moved, smallest first. */
  changes: PackRounding[];
  /** Change in total ornament coverage as a fraction of the original (−0.004 = −0.4%). */
  coverageChange: number;
}

/**
 * Move quantities onto whole packs for every color, as close to the original as
 * possible. Each size may go to the whole-pack quantity just below or just above
 * its own — never to 0 for a size in use, and the largest size keeps at least
 * `minTopCount`. Of every combination it keeps the one that changes the least
 * ornament area (the net change in coverage plus the area moved between sizes);
 * on a tie, the one with more ornaments. Sizes already on whole packs stay put.
 * The designers' 12 ft recipe at two colors: 6" 30 -> 32, 8" 17 -> 18,
 * 10" 15 -> 14, coverage +0.6%, nothing spare.
 */
export function roundToWholePacks(
  quantities: Map<number, number>,
  colorCount = 1,
  minTopCount = 0
): WholePackResult {
  const sizes = Array.from(quantities.keys())
    .filter((size) => (quantities.get(size) ?? 0) > 0)
    .sort((a, b) => a - b);
  const result = new Map(quantities);
  if (!sizes.length) return { quantities: result, changes: [], coverageChange: 0 };

  const area = (size: number) => ORNAMENT_OPTIONS.find((o) => o.size === size)?.planarArea ?? Math.PI * (size / 2) ** 2;
  const original = sizes.map((size) => quantities.get(size)!);
  const total = sizes.reduce((sum, size, i) => sum + area(size) * original[i], 0);
  const top = sizes.length - 1;
  const options = sizes.map((size, i) => {
    const unit = orderUnit(size, colorCount);
    let candidates = [Math.floor(original[i] / unit) * unit, Math.ceil(original[i] / unit) * unit].filter((n) => n > 0);
    if (i === top && minTopCount > 0) {
      const floor = Math.ceil(minTopCount / unit) * unit;
      candidates = candidates.map((n) => Math.max(n, floor));
    }
    return Array.from(new Set(candidates));
  });

  // At most two choices a size, so trying every combination is cheap.
  let best: number[] = original;
  let bestCost = Infinity;
  let bestPieces = -1;
  const pick: number[] = new Array(sizes.length);
  const walk = (i: number): void => {
    if (i === sizes.length) {
      let net = 0;
      let moved = 0;
      let pieces = 0;
      sizes.forEach((size, k) => {
        const delta = (pick[k] - original[k]) * area(size);
        net += delta;
        moved += Math.abs(delta);
        pieces += pick[k];
      });
      const cost = (Math.abs(net) + moved) / total;
      if (cost < bestCost - 1e-9 || (Math.abs(cost - bestCost) <= 1e-9 && pieces > bestPieces)) {
        best = [...pick];
        bestCost = cost;
        bestPieces = pieces;
      }
      return;
    }
    for (const n of options[i]) {
      pick[i] = n;
      walk(i + 1);
    }
  };
  walk(0);

  const changes: PackRounding[] = [];
  let net = 0;
  sizes.forEach((size, i) => {
    result.set(size, best[i]);
    net += (best[i] - original[i]) * area(size);
    if (best[i] !== original[i]) changes.push({ size, from: original[i], to: best[i] });
  });
  return { quantities: result, changes, coverageChange: net / total };
}

// ---------------------------------------------------------------------------
// Purchase list — what Charles pulls (designer rules 8 and 9).
//
// "I need a tree of 9 feet ornaments and Charles can just pull it out": the
// output is a bill of materials named by its tree configuration, not a coverage
// meter. And "I'd rather have the 5¢ more than this little one": when two
// adjacent sizes cost about the same per square inch of coverage, the bigger
// one wins. `treeConfigLabel` names the list; `sizeSwapSuggestions` finds the
// swaps worth making from real catalog prices; `applySizeSwap` makes one.
// ---------------------------------------------------------------------------

/** The parts of a tree configuration that name a purchase list; unknown parts are omitted. */
export interface TreeConfig {
  heightFt?: number | null;
  widthIn?: number | null;
  /** Width profile; null = custom width (shown as the width) or not applicable (Vickerman). */
  profile?: WidthProfile | null;
  style?: DesignStyle | null;
  /** Color names in design order, e.g. ["Red", "Gold"]. */
  colorNames?: string[];
}

/**
 * One-line name for a tree configuration — what Charles reads first, e.g.
 * "9 ft standard · traditional · Red + Gold". Parts are joined by " · " and
 * unknown parts are left out: with no profile the width shows instead
 * ("7.5 ft × 55 in · Red"), and the Vickerman rules pass no profile or style.
 * Returns "" when nothing is known.
 */
export function treeConfigLabel(config: TreeConfig): string {
  const { heightFt, widthIn, profile, style, colorNames = [] } = config;
  const parts: string[] = [];
  const hasHeight = typeof heightFt === "number" && heightFt > 0;
  const hasWidth = typeof widthIn === "number" && widthIn > 0;
  if (hasHeight && profile) parts.push(`${heightFt} ft ${WIDTH_PROFILES[profile].label.toLowerCase()}`);
  else if (hasHeight && hasWidth) parts.push(`${heightFt} ft × ${widthIn} in`);
  else if (hasHeight) parts.push(`${heightFt} ft`);
  else if (hasWidth) parts.push(`${widthIn} in wide`);
  if (style) parts.push(style);
  const colors = colorNames.filter((name) => name && name.trim());
  if (colors.length) parts.push(colors.join(" + "));
  return parts.join(" · ");
}

/**
 * A larger size wins when its cost per square inch of coverage is within this
 * much of the smaller size's (15% = "5¢ more"). A first guess for the
 * designers to react to.
 */
export const LL_SIZE_SWAP_TOLERANCE = 0.15;

/** A size swap worth making: move `fromQty` of the smaller size up to `toQty` of the next size. */
export interface SizeSwapSuggestion {
  fromSize: number;
  toSize: number;
  fromQty: number;
  /** Pieces of the larger size that keep the same coverage, rounded to the color count. */
  toQty: number;
  /** Price per piece ÷ planar area, in $ per sq in. */
  fromCostPerSqIn: number;
  toCostPerSqIn: number;
  /** Cost of the swap: toQty × larger price − fromQty × smaller price (negative = saves money). */
  extraCost: number;
}

/**
 * Price-aware size swaps (designer rule 8). For every pair of ADJACENT sizes in
 * the recipe (smaller → next larger present), compare cost per square inch of
 * coverage = price per piece ÷ planarArea. When the larger size costs no more
 * than the smaller × (1 + tolerance) per square inch, suggest moving the
 * smaller size's quantity up, keeping the same coverage:
 *
 *   toQty = round( fromQty × smallerArea ÷ largerArea )  to a multiple of colorCount
 *
 * (never below one set of colorCount pieces). `pricePerPieceBySize` is keyed by
 * size in inches; sizes without a price are skipped, and the top size is never
 * the one swapped away. Suggestions are independent — apply one, then recompute.
 */
export function sizeSwapSuggestions(
  lines: RecipeLine[],
  pricePerPieceBySize: Map<number, number>,
  tolerance: number = LL_SIZE_SWAP_TOLERANCE,
  colorCount: number = LL_DEFAULT_COLOR_COUNT
): SizeSwapSuggestion[] {
  const colors = clampColorCount(colorCount);
  const present = lines.filter((line) => line.quantity > 0).sort((a, b) => a.option.size - b.option.size);
  const suggestions: SizeSwapSuggestion[] = [];
  for (let i = 0; i < present.length - 1; i++) {
    const from = present[i];
    const to = present[i + 1];
    const fromPrice = pricePerPieceBySize.get(from.option.size);
    const toPrice = pricePerPieceBySize.get(to.option.size);
    if (fromPrice === undefined || toPrice === undefined || !(fromPrice > 0) || !(toPrice > 0)) continue;
    const fromCostPerSqIn = fromPrice / from.option.planarArea;
    const toCostPerSqIn = toPrice / to.option.planarArea;
    if (toCostPerSqIn > fromCostPerSqIn * (1 + tolerance)) continue;
    const toQty = roundForColors((from.quantity * from.option.planarArea) / to.option.planarArea, colors, colors);
    suggestions.push({
      fromSize: from.option.size,
      toSize: to.option.size,
      fromQty: from.quantity,
      toQty,
      fromCostPerSqIn,
      toCostPerSqIn,
      extraCost: toQty * toPrice - from.quantity * fromPrice,
    });
  }
  return suggestions;
}

/**
 * Make a size swap: a new quantities map (size → pieces) with the smaller size
 * zeroed and the larger size increased by `toQty`. Works on the calculator's
 * own map, where an untouched size is "" — that counts as 0.
 */
export function applySizeSwap<Q extends Record<number, number | "">>(quantities: Q, swap: SizeSwapSuggestion): Q {
  const current = quantities[swap.toSize];
  return {
    ...quantities,
    [swap.fromSize]: 0,
    [swap.toSize]: (typeof current === "number" ? current : 0) + swap.toQty,
  };
}

// ---------------------------------------------------------------------------
// Tree density image — the visual "tree representation based on the selection".
// Vickerman renders a photo per 5% coverage step (0..90). We host copies under
// /public/ornament-calculator/ so the app is self-contained.
// ---------------------------------------------------------------------------

/** Local path to the tree photo for a given coverage density (%). Out-of-range
 * (including non-finite) values clamp the same way as a too-low density: 0. */
export function treeDensityImage(density: number): string {
  let step = Math.floor(density / 5) * 5;
  if (!Number.isFinite(step) || step < 0) step = 0;
  if (step > 90) step = 90;
  return `/ornament-calculator/tree_density_${step}.jpg`;
}

// ---------------------------------------------------------------------------
// Colors, finishes & SKU building — the "Select Colors" step, ported exactly
// from Vickerman's /Tools/OrnamentRecipe page.
// ---------------------------------------------------------------------------

export interface OrnamentColor {
  name: string;
  code: string;
  /** Best-effort swatch hex for the UI (Vickerman ships names only). */
  hex: string;
}

export interface OrnamentFinish {
  name: string;
  code: string;
}

/** All 57 Vickerman ornament colors (name + code exact; hex is our swatch). */
export const COLORS: OrnamentColor[] = [
  { name: "Clear Iridescent", code: "00", hex: "#e8f0f2" },
  { name: "Blue", code: "02", hex: "#2f5fa8" },
  { name: "Red", code: "03", hex: "#c0392b" },
  { name: "Green", code: "04", hex: "#2e7d32" },
  { name: "Silver", code: "07", hex: "#c0c4c8" },
  { name: "Gold", code: "08", hex: "#d4af37" },
  { name: "White", code: "11", hex: "#f5f5f0" },
  { name: "Turquoise", code: "12", hex: "#30bfbf" },
  { name: "Olive", code: "14", hex: "#808000" },
  { name: "Black", code: "17", hex: "#1c1c1c" },
  { name: "Burnished Orange", code: "18", hex: "#b5651d" },
  { name: "Wine", code: "19", hex: "#722f37" },
  { name: "Berry Red", code: "21", hex: "#9e1b32" },
  { name: "Cobalt Blue", code: "22", hex: "#1f3a93" },
  { name: "Wrought Iron", code: "23", hex: "#3a3a3a" },
  { name: "Emerald", code: "24", hex: "#0d6b4f" },
  { name: "Limestone", code: "25", hex: "#c9c2b0" },
  { name: "Plum", code: "26", hex: "#6d3a5d" },
  { name: "Periwinkle", code: "29", hex: "#8f9fe0" },
  { name: "Antique Gold", code: "30", hex: "#b8933b" },
  { name: "Midnight Blue", code: "31", hex: "#182848" },
  { name: "Baby Blue", code: "32", hex: "#a9d0f5" },
  { name: "Copper Gold", code: "33", hex: "#b87333" },
  { name: "Juniper", code: "34", hex: "#3d5e50" },
  { name: "Honey Gold", code: "37", hex: "#e0a83b" },
  { name: "Champagne", code: "38", hex: "#e8dcc0" },
  { name: "Bittersweet", code: "39", hex: "#c65d3b" },
  { name: "Frosty Mint", code: "40", hex: "#c8e6d4" },
  { name: "Dark Teal", code: "41", hex: "#0f5e5e" },
  { name: "Teal", code: "42", hex: "#1b8a8a" },
  { name: "Oat", code: "43", hex: "#ded3b8" },
  { name: "Seafoam", code: "44", hex: "#9fe0c0" },
  { name: "Mauve", code: "45", hex: "#b784a7" },
  { name: "Medallion", code: "46", hex: "#c9a24b" },
  { name: "Denim Blue", code: "52", hex: "#3b5c8a" },
  { name: "Celadon", code: "54", hex: "#aecaad" },
  { name: "Rose Gold", code: "58", hex: "#e0bfb8" },
  { name: "Hot Pink", code: "59", hex: "#ff3d8b" },
  { name: "Sea Blue", code: "62", hex: "#2d7fb0" },
  { name: "Crimson Red", code: "63", hex: "#a01828" },
  { name: "Moss Green", code: "64", hex: "#5a6f2a" },
  { name: "Burgundy", code: "65", hex: "#5e1a2b" },
  { name: "Purple", code: "66", hex: "#6a2a8c" },
  { name: "Orchid", code: "69", hex: "#b452cd" },
  { name: "Fuchsia", code: "70", hex: "#c71585" },
  { name: "Coral", code: "71", hex: "#ff7f50" },
  { name: "Lime", code: "73", hex: "#9acd32" },
  { name: "Midnight Green", code: "74", hex: "#0f3b34" },
  { name: "Chocolate", code: "75", hex: "#4b2e2a" },
  { name: "Mocha", code: "76", hex: "#7b5b43" },
  { name: "Yellow", code: "78", hex: "#f2c94c" },
  { name: "Pink", code: "79", hex: "#f5a9c4" },
  { name: "Café Latte", code: "80", hex: "#c4a484" },
  { name: "Gunmetal", code: "84", hex: "#5a5f66" },
  { name: "Lavender", code: "86", hex: "#b19cd9" },
  { name: "Pewter", code: "87", hex: "#8f8f8f" },
  { name: "Copper", code: "88", hex: "#b87333" },
];

/**
 * Finishes — the 7 from Vickerman's tool plus the finishes that actually appear
 * across the full ornament catalog (all suppliers), verified against the data,
 * so the picker's options are representative of what you can really buy.
 * The first 7 codes double as Vickerman SKU finish codes; the rest are internal.
 */
export const FINISHES: OrnamentFinish[] = [
  { name: "Shiny", code: "S" },
  { name: "Matte", code: "M" },
  { name: "Glitter", code: "G" },
  { name: "Pearl", code: "P" },
  { name: "Sequin", code: "Q" },
  { name: "Candy", code: "C" },
  { name: "Clear", code: "X" },
  { name: "Frosted", code: "F" },
  { name: "Iridescent", code: "I" },
  { name: "Mercury", code: "R" },
  { name: "Velvet", code: "V" },
  { name: "Flocked", code: "L" },
  { name: "Beaded", code: "B" },
  { name: "Metallic", code: "T" },
];


/** A color block: exactly one color + one finish + its share of the tree (%). */
export interface ColorBlock {
  id: number;
  colorCode: string;
  finishCode: string;
  /** Share of the whole tree this color+finish covers, in percent. */
  sharePct: number;
}

/** A resolved order line — one product to source, per size × color × finish. */
export interface OrderLine {
  size: number;
  sizeCode: string;
  color: string;
  colorCode: string;
  finish: string;
  finishCode: string;
  quantity: number;
}

/**
 * Expand the color blocks into order lines — one per (size × color × finish).
 * quantity = round(recipe pieces for that size × the block's tree share).
 * Blocks that resolve to the same size+color+finish are summed.
 */
export function buildOrderLines(
  sizeQuantities: Map<string, number>,
  colorBlocks: ColorBlock[]
): OrderLine[] {
  const map = new Map<string, OrderLine>();
  colorBlocks.forEach((block) => {
    if (!block.colorCode || !block.finishCode) return;
    const share = (block.sharePct || 0) / 100;
    if (share <= 0) return;
    const colorObj = COLORS.find((c) => c.code === block.colorCode);
    const finishObj = FINISHES.find((f) => f.code === block.finishCode);
    ORNAMENT_OPTIONS.forEach((size) => {
      const total = sizeQuantities.get(size.sizeCode) || 0;
      const qty = Math.round(total * share);
      if (qty <= 0) return;
      const key = `${size.sizeCode}|${block.colorCode}|${block.finishCode}`;
      const existing = map.get(key);
      if (existing) existing.quantity += qty;
      else
        map.set(key, {
          size: size.size,
          sizeCode: size.sizeCode,
          color: colorObj?.name || block.colorCode,
          colorCode: block.colorCode,
          finish: finishObj?.name || block.finishCode,
          finishCode: block.finishCode,
          quantity: qty,
        });
    });
  });
  return Array.from(map.values()).sort(
    (a, b) => a.size - b.size || a.color.localeCompare(b.color) || a.finish.localeCompare(b.finish)
  );
}

/** Total tree-share across blocks — used to warn when it isn't 100%. */
export function totalColorPct(colorBlocks: ColorBlock[]): number {
  return colorBlocks.reduce((sum, b) => sum + (b.sharePct || 0), 0);
}
