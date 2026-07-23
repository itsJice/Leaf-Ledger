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
  { display: "2.4", size: 2.4, qtyPerPack: 24, sizeCode: "06", planarArea: 4.5238934211692976 },
  { display: "2.75", size: 2.75, qtyPerPack: 12, sizeCode: "07", planarArea: 5.939573610693197 },
  { display: "3", size: 3, qtyPerPack: 12, sizeCode: "08", planarArea: 7.0685834705770275 },
  { display: "4", size: 4, qtyPerPack: 6, sizeCode: "10", planarArea: 12.56637061435916 },
  { display: "4.75", size: 4.75, qtyPerPack: 4, sizeCode: "12", planarArea: 17.72054606165491 },
  { display: "6", size: 6, qtyPerPack: 4, sizeCode: "15", planarArea: 28.27433388230811 },
  { display: "8", size: 8, qtyPerPack: 1, sizeCode: "20", planarArea: 50.26548245743664 },
  { display: "10", size: 10, qtyPerPack: 1, sizeCode: "25", planarArea: 78.53981633974475 },
  { display: "12", size: 12, qtyPerPack: 1, sizeCode: "30", planarArea: 113.09733552923244 },
  { display: "15.75", size: 15.75, qtyPerPack: 1, sizeCode: "40", planarArea: 194.82783190777932 },
  { display: "20", size: 20, qtyPerPack: 1, sizeCode: "45", planarArea: 314.159265358979 },
  { display: "24", size: 24, qtyPerPack: 1, sizeCode: "46", planarArea: 452.38934211692976 },
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
  if (surfaceArea <= 0) {
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
  if (!quantity) return "";
  if (option.qtyPerPack === 1) return `${quantity} each`;
  const wholePacks = Math.ceil(quantity / option.qtyPerPack);
  return `${wholePacks} pack${wholePacks === 1 ? "" : "s"} of ${option.qtyPerPack}`;
}

// ---------------------------------------------------------------------------
// Tree density image — the visual "tree representation based on the selection".
// Vickerman renders a photo per 5% coverage step (0..90). We host copies under
// /public/ornament-calculator/ so the app is self-contained.
// ---------------------------------------------------------------------------

/** Local path to the tree photo for a given coverage density (%). */
export function treeDensityImage(density: number): string {
  let step = Math.floor(density / 5) * 5;
  if (step > 90) step = 90;
  if (step < 0) step = 0;
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

/** All 58 Vickerman ornament colors (name + code exact; hex is our swatch). */
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

/**
 * Build the Vickerman product SKU for a size/color/finish combination.
 * Rules ported verbatim from the site:
 *   Clear (X):            N59{size}{color}V
 *   Sequin (Q)/Glitter(G): N59{size}{color}D{finish}
 *   everything else:      N59{size}{color}D{finish}V
 */
export function buildSku(sizeCode: string, colorCode: string, finishCode: string): string {
  if (finishCode === "X") return `N59${sizeCode}${colorCode}V`;
  if (finishCode === "Q" || finishCode === "G") return `N59${sizeCode}${colorCode}D${finishCode}`;
  return `N59${sizeCode}${colorCode}D${finishCode}V`;
}

/** Product image URL for a SKU (Vickerman CDN pattern), for thumbnails. */
export function productImageUrl(sku: string): string {
  return `https://images.vickerman.com/${sku}_1000.jpg`;
}

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
