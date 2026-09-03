import { apiFetch } from "utils/apiFetch";
import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Calculator,
  TreePine,
  Sparkles,
  RotateCcw,
  Palette,
  Plus,
  Trash2,
  Copy,
  Download,
  Link2,
  Check,
  ArrowLeft,
  Store,
  Loader2,
  Tag,
  PackageSearch,
  X,
  Flower2,
  ListChecks,
  MessageSquareText,
  ArrowUpRight,
} from "lucide-react";
import Layout from "components/Layout";
import { toast } from "sonner";
import {
  ORNAMENT_OPTIONS,
  COLORS,
  FINISHES,
  buildRecipeFor,
  coverageDensity,
  packSummary,
  treeSurfaceArea,
  treeDensityImage,
  buildOrderLines,
  totalColorPct,
  leafLedgerSource,
  leafLedgerMinTopCount,
  widthForProfile,
  profileForWidth,
  enhancerLookup,
  enhancerAllocation,
  ENHANCER_MAX_SIZE_IN,
  WIDTH_PROFILES,
  LL_CONTEMPORARY_FILL,
  LL_DEFAULT_COLOR_COUNT,
  LL_MIN_COLOR_COUNT,
  LL_MAX_COLOR_COUNT,
  LL_SIZE_SWAP_TOLERANCE,
  treeConfigLabel,
  sizeSwapSuggestions,
  applySizeSwap,
  type SizeSwapSuggestion,
  type ColorBlock,
  type RecipeMode,
  type RecipeLine,
  type WidthProfile,
  type DesignStyle,
  type EnhancerLookup,
  type EnhancerAllocationLine,
} from "utils/ornamentRecipe";

// Exact in-app clone of Vickerman's Ornament Calculator (both steps):
//   Step 1 "Calculator" — tree dimensions -> recipe quantities, with the tree
//     photo that swaps by coverage density.
//   Step 2 "Select Colors" — split quantities across colors + finishes to
//     generate Vickerman SKUs, pack counts, thumbnails, and CSV/copy/share.

type QtyMap = Record<number, number | "">;
type Step = "calculator" | "colors";

// --- Catalog matching (real products across ALL suppliers) ---
interface CatalogMatch {
  product_id: number;
  supplier: string;
  name: string;
  sku: string | null;
  price: number | null;
  image: string | null;
  size_in: number;
  color: string | null;
  finish: string | null;
  case_qty: number;
  packs_needed: number | null;
  color_match: boolean;
  size_delta: number;
}
interface MatchLine {
  size: number;
  quantity: number;
  color: string | null;
  finish: string | null;
  match_count: number;
  matches: CatalogMatch[];
}

/** Route a supplier image through the backend proxy (dodges hotlink blocks). */
function proxied(url: string | null): string | undefined {
  if (!url) return undefined;
  return `/api/products/image-proxy?url=${encodeURIComponent(url)}`;
}

/** Stable id for a recipe line (size + color + finish) — keys the picker map + scroll anchors. */
const lineId = (size: number | string, color: string | null, finish?: string | null) =>
  `${size}-${color || "any"}-${finish || "any"}`.replace(/[^a-z0-9]+/gi, "-").toLowerCase();

async function fetchCatalogMatches(
  lines: { size: number; quantity: number; color: string | null; finish?: string | null }[],
  suppliers: string[] | null
): Promise<MatchLine[]> {
  const res = await apiFetch("/api/products/ornament-match", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    // per_line = max matches per vendor; the backend guarantees every vendor's
    // best match first, so 2 gives full vendor coverage + a runner-up each.
    body: JSON.stringify({ lines, suppliers, per_line: 2 }),
  });
  if (!res.ok) throw new Error(`match request failed (${res.status})`);
  const data = await res.json();
  return (data?.lines ?? []) as MatchLine[];
}

const emptyQuantities = (): QtyMap =>
  ORNAMENT_OPTIONS.reduce((acc, o) => ({ ...acc, [o.size]: "" }), {} as QtyMap);

function densityColor(density: number): string {
  if (density >= 70) return "rgb(var(--ll-ok-strong))";
  if (density >= 40) return "rgb(var(--ll-ok))";
  if (density >= 15) return "rgb(var(--ll-warn))";
  return "rgb(var(--nc-400))";
}
function densityLabel(density: number): string {
  if (density >= 70) return "Full / dense";
  if (density >= 40) return "Balanced (recipe target)";
  if (density >= 15) return "Light";
  return "Sparse";
}

/** The active modifiers, briefly, as " · …" suffixes (empty when the table applies as approved). */
function describeModifiers(style: DesignStyle, colorCount: number): string {
  const parts: string[] = [];
  if (style === "contemporary") parts.push(`contemporary fill ×${LL_CONTEMPORARY_FILL}`);
  if (colorCount !== LL_DEFAULT_COLOR_COUNT) parts.push(`${colorCount} color${colorCount === 1 ? "" : "s"}`);
  return parts.map((s) => ` · ${s}`).join("");
}

/** One line on where the Leaf & Ledger recipe for this height comes from, modifiers included. */
function describeLeafLedger(heightFt: number | "", style: DesignStyle, colorCount: number): string {
  const modifiers = describeModifiers(style, colorCount);
  if (typeof heightFt !== "number" || heightFt <= 0) return `Designer-approved table · interpolated between rows${modifiers}`;
  const src = leafLedgerSource(heightFt);
  if (src.kind === "table")
    return `Designer-approved recipe for ${src.heightFt} ft${modifiers || ", as signed off"}`;
  const rounding = colorCount === 1 ? "" : colorCount === 2 ? " · even counts" : ` · counts in multiples of ${colorCount}`;
  if (src.kind === "interpolated")
    return `Interpolated between the approved ${src.lowerFt} ft and ${src.upperFt} ft recipes${rounding} · at least ${leafLedgerMinTopCount(colorCount)} of the largest${modifiers}`;
  return `Beyond the approved table — top-heavy formula extrapolated from the ${src.from === "above" ? "12 ft" : "7.5 ft"} recipe${modifiers}`;
}

/** Color blocks with equal shares of the tree, for seeding Step 2 from the color count. */
function equalShareBlocks(count: number): ColorBlock[] {
  const base = Math.floor(100 / count);
  const extra = 100 - base * count; // the odd percent goes to the first block(s)
  return Array.from({ length: count }, (_, i) => ({ ...newColorBlock(), sharePct: base + (i < extra ? 1 : 0) }));
}

/** One line on which enhancer-table row the count came from. */
function describeEnhancers(lookup: EnhancerLookup | null, touched: boolean): string {
  if (!lookup) return "Enter tree dimensions to look up the enhancer table";
  const src = lookup.source;
  const from =
    src.kind === "table"
      ? `Table row ${src.row.label} → ${src.row.count}`
      : src.kind === "nearestWidth"
      ? `No width bucket fits — nearest row ${src.row.label} → ${src.row.count}`
      : src.kind === "interpolated"
      ? `Between rows ${src.lower.label} (${src.lower.count}) and ${src.upper.label} (${src.upper.count}) → ${lookup.count}`
      : `Beyond the table — row ${src.row.label} (${src.row.count}) scaled by surface area → ${lookup.count}`;
  return touched ? `Edited by hand · table says ${lookup.count}: ${from}` : from;
}

/**
 * Price of one piece from a catalog match. Catalog prices are per pack — a 4"
 * ball "6/Bag" lists at about $12, and `packs_needed` counts packs of `case_qty`
 * — so per piece = price ÷ case_qty. Null when the product has no price.
 */
const pricePerPiece = (m: CatalogMatch) => (m.price != null ? m.price / Math.max(1, m.case_qty || 1) : null);

/** Money for the UI: "$1,234.50". */
const money = (n: number) => `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

/** One line on a size swap: `4" ×36 → 4.75" ×26 — cheaper per coverage (−$7.40 total), bigger impact`. */
function describeSwap(s: SizeSwapSuggestion): string {
  const verdict = s.toCostPerSqIn < s.fromCostPerSqIn ? "cheaper per coverage" : "about the same cost per coverage";
  const delta =
    Math.abs(s.extraCost) < 0.005 ? "same total" : `${s.extraCost > 0 ? "+" : "−"}${money(Math.abs(s.extraCost))} total`;
  return `${s.fromSize}" ×${s.fromQty} → ${s.toSize}" ×${s.toQty} — ${verdict} (${delta}), bigger impact`;
}

let blockIdSeq = 1;
const newColorBlock = (): ColorBlock => ({
  id: blockIdSeq++,
  colorCode: "",
  finishCode: "",
  sharePct: 100,
});

export default function OrnamentCalculator() {
  const [step, setStep] = useState<Step>("calculator");

  // --- Step 1 state ---
  const [heightFt, setHeightFt] = useState<number | "">(7.5);
  const [widthIn, setWidthIn] = useState<number | "">(widthForProfile(7.5, "standard"));
  // Width follows height at this profile's ratio; null = custom, the user typed a width.
  const [widthProfile, setWidthProfile] = useState<WidthProfile | null>("standard");
  const [quantities, setQuantities] = useState<QtyMap>(emptyQuantities);
  const [coverageTarget, setCoverageTarget] = useState(40); // the slider's position
  const [recipeMode, setRecipeMode] = useState<RecipeMode>("leafledger");
  // Leaf & Ledger modifiers (ignored under the Vickerman rules).
  const [designStyle, setDesignStyle] = useState<DesignStyle>("traditional");
  const [colorCount, setColorCount] = useState(LL_DEFAULT_COLOR_COUNT);
  // Enhancer count follows the designers' table until the user edits it (like width).
  const [enhancersInput, setEnhancersInput] = useState<number | "">("");
  const [enhancersTouched, setEnhancersTouched] = useState(false);

  // --- Step 2 state ---
  const [colorBlocks, setColorBlocks] = useState<ColorBlock[]>(() => [newColorBlock()]);

  const h = typeof heightFt === "number" ? heightFt : NaN;
  const w = typeof widthIn === "number" ? widthIn : NaN;
  const dimsValid = Number.isFinite(h) && Number.isFinite(w);
  const surfaceArea = useMemo(
    () => (dimsValid ? treeSurfaceArea(h, w) : 0),
    [dimsValid, h, w]
  );
  const tooSmall = dimsValid && surfaceArea <= 0;

  const qtyNumberMap = useMemo(() => {
    const map = new Map<number, number>();
    ORNAMENT_OPTIONS.forEach((o) => {
      const v = quantities[o.size];
      if (typeof v === "number" && v > 0) map.set(o.size, v);
    });
    return map;
  }, [quantities]);

  const density = useMemo(
    () => (dimsValid ? coverageDensity(h, w, qtyNumberMap) : 0),
    [dimsValid, h, w, qtyNumberMap]
  );
  const totalOrnaments = useMemo(
    () => Array.from(qtyNumberMap.values()).reduce((a, b) => a + b, 0),
    [qtyNumberMap]
  );

  // Enhancers — only under the Leaf & Ledger rules (Vickerman's tool has none).
  const enhancerAuto = useMemo<EnhancerLookup | null>(
    () => (dimsValid && !tooSmall ? enhancerLookup(h, w, colorCount) : null),
    [dimsValid, tooSmall, h, w, colorCount]
  );
  const enhancers =
    recipeMode !== "leafledger" || !enhancerAuto
      ? 0
      : enhancersTouched
      ? typeof enhancersInput === "number"
        ? enhancersInput
        : 0
      : enhancerAuto.count;
  // Whatever is in the table right now (edits included), as recipe lines.
  const currentLines = useMemo<RecipeLine[]>(
    () =>
      ORNAMENT_OPTIONS.filter((o) => qtyNumberMap.has(o.size)).map((o) => ({
        option: o,
        quantity: qtyNumberMap.get(o.size)!,
      })),
    [qtyNumberMap]
  );
  // Loose vs in-enhancer split of the current lines.
  const enhancerLines = useMemo<EnhancerAllocationLine[]>(
    () => (dimsValid && recipeMode === "leafledger" ? enhancerAllocation(currentLines, h, enhancers, colorCount) : []),
    [dimsValid, recipeMode, currentLines, h, enhancers, colorCount]
  );

  // Quantities keyed by size CODE, for the colors step.
  const qtyByCode = useMemo(() => {
    const map = new Map<string, number>();
    ORNAMENT_OPTIONS.forEach((o) => {
      const v = quantities[o.size];
      if (typeof v === "number" && v > 0) map.set(o.sizeCode, v);
    });
    return map;
  }, [quantities]);

  // Order lines — one per (size × color × finish), from the color blocks.
  const orderLines = useMemo(
    () => buildOrderLines(qtyByCode, colorBlocks),
    [qtyByCode, colorBlocks]
  );
  const colorPctSum = totalColorPct(colorBlocks);
  const showPctWarning = colorBlocks.filter((b) => b.colorCode).length > 1 && colorPctSum !== 100;

  // The purchase list's name — what Charles reads first. Profile and style are
  // Leaf & Ledger modifiers, so under the Vickerman rules the label has neither.
  const effectiveProfile = widthProfile ?? (dimsValid ? profileForWidth(h, w) : null);
  const configLabel = useMemo(
    () =>
      treeConfigLabel({
        heightFt: dimsValid ? h : null,
        widthIn: dimsValid ? w : null,
        profile: recipeMode === "leafledger" ? effectiveProfile : null,
        style: recipeMode === "leafledger" ? designStyle : null,
        colorNames: Array.from(
          new Set(colorBlocks.map((b) => COLORS.find((c) => c.code === b.colorCode)?.name).filter((n): n is string => !!n))
        ),
      }),
    [dimsValid, h, w, recipeMode, effectiveProfile, designStyle, colorBlocks]
  );

  // Each order line is already a recipe line to match/pick against.
  const matchRequestLines = useMemo(
    () =>
      orderLines.map((l) => ({
        size: l.size,
        quantity: l.quantity,
        color: l.color,
        finish: l.finish,
      })),
    [orderLines]
  );

  const [matchLines, setMatchLines] = useState<MatchLine[]>([]);
  const [matchLoading, setMatchLoading] = useState(false);
  const [matchError, setMatchError] = useState<string | null>(null);
  const [onlyVickerman, setOnlyVickerman] = useState(false);
  const matchSeq = useRef(0);

  // Debounced fetch whenever the plan (or supplier filter) changes on the colors step.
  useEffect(() => {
    if (step !== "colors" || matchRequestLines.length === 0) {
      setMatchLines([]);
      return;
    }
    const seq = ++matchSeq.current;
    setMatchLoading(true);
    setMatchError(null);
    const t = setTimeout(() => {
      fetchCatalogMatches(matchRequestLines, onlyVickerman ? ["Vickerman"] : null)
        .then((lines) => {
          if (seq === matchSeq.current) setMatchLines(lines);
        })
        .catch((e) => {
          if (seq === matchSeq.current) setMatchError(String(e.message || e));
        })
        .finally(() => {
          if (seq === matchSeq.current) setMatchLoading(false);
        });
    }, 400);
    return () => clearTimeout(t);
  }, [step, matchRequestLines, onlyVickerman]);

  // `next` carries a setting that was just changed but hasn't landed in state yet.
  const applyRecipeAtCoverage = (
    pct: number,
    next: { mode?: RecipeMode; widthIn?: number; style?: DesignStyle; colorCount?: number } = {}
  ) => {
    const width = next.widthIn ?? w;
    if (!Number.isFinite(h) || !Number.isFinite(width) || treeSurfaceArea(h, width) <= 0) return;
    const clamped = Math.max(0, Math.min(100, pct));
    setCoverageTarget(clamped); // keep the slider exactly where it was dragged
    const recipe = buildRecipeFor(next.mode ?? recipeMode, h, width, clamped / 100, {
      style: next.style ?? designStyle,
      colorCount: next.colorCount ?? colorCount,
    });
    const nextQuantities = emptyQuantities();
    recipe.lines.forEach((line) => {
      nextQuantities[line.option.size] = line.quantity;
    });
    setQuantities(nextQuantities);
  };
  const applyRecipe = () => applyRecipeAtCoverage(40);
  const changeRecipeMode = (mode: RecipeMode) => {
    setRecipeMode(mode);
    if (totalOrnaments > 0) applyRecipeAtCoverage(coverageTarget, { mode });
  };
  const changeStyle = (style: DesignStyle) => {
    setDesignStyle(style);
    if (totalOrnaments > 0) applyRecipeAtCoverage(coverageTarget, { style });
  };
  const changeColorCount = (count: number) => {
    setColorCount(count);
    if (totalOrnaments > 0) applyRecipeAtCoverage(coverageTarget, { colorCount: count });
  };
  // Width follows height at the chosen profile's ratio until the user sets it themselves.
  const changeHeight = (v: number | "") => {
    setHeightFt(v);
    if (widthProfile && typeof v === "number" && v > 0) setWidthIn(widthForProfile(v, widthProfile));
  };
  const changeWidth = (v: number | "") => {
    setWidthProfile(null);
    setWidthIn(v);
  };
  // Picking a profile sets the width (and keeps it following height) — a modifier, so it re-populates.
  const changeWidthProfile = (profile: WidthProfile) => {
    setWidthProfile(profile);
    if (typeof heightFt !== "number" || heightFt <= 0) return;
    const width = widthForProfile(heightFt, profile);
    setWidthIn(width);
    if (totalOrnaments > 0) applyRecipeAtCoverage(coverageTarget, { widthIn: width });
  };
  // Step 2 starts with one block per color, equal shares — unless the user already set blocks up.
  const goToColors = () => {
    if (recipeMode === "leafledger") {
      setColorBlocks((blocks) => {
        const pristine = blocks.length === 1 && !blocks[0].colorCode && !blocks[0].finishCode && blocks[0].sharePct === 100;
        return pristine && colorCount !== blocks.length ? equalShareBlocks(colorCount) : blocks;
      });
    }
    setStep("colors");
  };
  const changeEnhancers = (v: number | "") => {
    setEnhancersTouched(true);
    setEnhancersInput(v);
  };
  const resetEnhancers = () => {
    setEnhancersTouched(false);
    setEnhancersInput("");
  };
  const clearAll = () => {
    setQuantities(emptyQuantities());
    setCoverageTarget(0);
  };
  const setQty = (size: number, raw: string) =>
    setQuantities((prev) => ({
      ...prev,
      [size]: raw === "" ? "" : Math.max(0, Math.floor(Number(raw))),
    }));

  // --- Step 2 mutators ---
  const addColorBlock = () => setColorBlocks((b) => [...b, newColorBlock()]);
  const removeColorBlock = (id: number) =>
    setColorBlocks((b) => (b.length > 1 ? b.filter((x) => x.id !== id) : b));
  const updateBlock = (id: number, patch: Partial<ColorBlock>) =>
    setColorBlocks((b) => b.map((x) => (x.id === id ? { ...x, ...patch } : x)));

  const pickedRows = () =>
    matchRequestLines
      .map((l) => ({ l, p: picked[lineId(l.size, l.color, l.finish)] }))
      .filter((r): r is { l: typeof matchRequestLines[number]; p: CatalogMatch } => !!r.p);
  const copyOrder = async () => {
    const rows = pickedRows();
    if (!rows.length) return toast.error("Pick a product for at least one size first.");
    const text =
      (configLabel ? `${configLabel}\n` : "") +
      "Supplier\tSKU\tItem\tPacks\tPieces\n" +
      rows.map(({ l, p }) => `${p.supplier}\t${p.sku ?? ""}\t${p.name}\t${p.packs_needed ?? ""}\t${l.quantity}`).join("\n") +
      (enhancers > 0 ? `\nEnhancers\t${enhancers}` : "");
    try {
      await navigator.clipboard.writeText(text);
      toast.success("Order copied to clipboard");
    } catch {
      toast.error("Copy failed — use Export CSV instead.");
    }
  };
  const exportCsv = () => {
    const rows = pickedRows();
    if (!rows.length) return toast.error("Pick a product for at least one size first.");
    const csv =
      (configLabel ? `# ${configLabel}\n` : "") +
      "Supplier,SKU,Item,Size,Color,Packs,Pieces\n" +
      rows
        .map(({ l, p }) => `${p.supplier},${p.sku ?? ""},"${(p.name || "").replace(/"/g, '""')}",${l.size},${l.color ?? ""},${p.packs_needed ?? ""},${l.quantity}`)
        .join("\n") +
      (enhancers > 0 ? `\nEnhancers,${enhancers}` : "");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `Ornament_Order_${new Date().toISOString().split("T")[0]}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    toast.success("CSV downloaded");
  };
  const copyShareUrl = async () => {
    const params = new URLSearchParams();
    ORNAMENT_OPTIONS.forEach((o) => {
      const v = quantities[o.size];
      if (typeof v === "number" && v > 0) params.set(o.sizeCode, String(v));
    });
    const url = `${window.location.origin}${window.location.pathname}${
      params.toString() ? "?" + params.toString() : ""
    }`;
    try {
      await navigator.clipboard.writeText(url);
      toast.success("Shareable link copied");
    } catch {
      toast.error("Copy failed.");
    }
  };

  // --- Fill-in-the-blank picker: assign a real product to each recipe line ---
  const [picked, setPicked] = useState<Record<string, CatalogMatch>>({});
  const [activeLineKey, setActiveLineKey] = useState<string | null>(null);

  const scrollTo = (id: string) =>
    requestAnimationFrame(() =>
      document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" })
    );
  // Click an order slot → jump to that size's matches to choose from.
  const openPickerFor = (key: string) => {
    setActiveLineKey(key);
    scrollTo(`match-line-${key}`);
  };
  // Click ＋ on a match → fill that line's slot and jump back to the order.
  const pickProduct = (key: string, m: CatalogMatch) => {
    setPicked((prev) => ({ ...prev, [key]: m }));
    setActiveLineKey(null);
    scrollTo("order-panel");
  };
  const clearPick = (key: string) =>
    setPicked((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });

  // Drop picks whose recipe line no longer exists (color/finish/size changed).
  useEffect(() => {
    const valid = new Set(matchRequestLines.map((l) => lineId(l.size, l.color, l.finish)));
    setPicked((prev) => {
      const next: Record<string, CatalogMatch> = {};
      let changed = false;
      for (const [k, v] of Object.entries(prev)) {
        if (valid.has(k)) next[k] = v;
        else changed = true;
      }
      return changed ? next : prev;
    });
  }, [matchRequestLines]);

  const pickedPacks = useMemo(
    () =>
      matchRequestLines.reduce((sum, l) => {
        const p = picked[lineId(l.size, l.color, l.finish)];
        return sum + (p?.packs_needed ?? 0);
      }, 0),
    [matchRequestLines, picked]
  );
  const pickedCount = matchRequestLines.filter((l) => picked[lineId(l.size, l.color, l.finish)]).length;

  // --- Purchase list (designer rules 8 and 9) ---
  // Per-piece price of each size from its picks, weighted by pieces (a size has one line per color).
  const pricePerPieceBySize = useMemo(() => {
    const totals = new Map<number, { cost: number; pieces: number }>();
    matchRequestLines.forEach((l) => {
      const p = picked[lineId(l.size, l.color, l.finish)];
      const perPiece = p ? pricePerPiece(p) : null;
      if (perPiece == null) return;
      const t = totals.get(l.size) ?? { cost: 0, pieces: 0 };
      totals.set(l.size, { cost: t.cost + perPiece * l.quantity, pieces: t.pieces + l.quantity });
    });
    const map = new Map<number, number>();
    totals.forEach((t, size) => {
      if (t.pieces > 0) map.set(size, t.cost / t.pieces);
    });
    return map;
  }, [matchRequestLines, picked]);
  // A swap rounds to the design's color count; under the Vickerman rules, to the colors chosen.
  const swapColorCount =
    recipeMode === "leafledger" ? colorCount : Math.max(1, colorBlocks.filter((b) => b.colorCode).length);
  const swapSuggestions = useMemo(
    () => sizeSwapSuggestions(currentLines, pricePerPieceBySize, LL_SIZE_SWAP_TOLERANCE, swapColorCount),
    [currentLines, pricePerPieceBySize, swapColorCount]
  );
  // Estimated cost of the picks: packs × pack price. Lines without a price are counted, not summed.
  const pickedEstimate = useMemo(() => {
    let total = 0;
    let unpriced = 0;
    matchRequestLines.forEach((l) => {
      const p = picked[lineId(l.size, l.color, l.finish)];
      if (!p) return;
      if (p.price == null || p.packs_needed == null) unpriced++;
      else total += p.price * p.packs_needed;
    });
    return { total, unpriced };
  }, [matchRequestLines, picked]);

  // One click: every line without a pick gets its best catalog match — the first
  // with the color right, else the first (the backend ranks by size closeness,
  // then color). The matches already honour the "Vickerman only" filter.
  const buildPurchaseList = () => {
    let filled = 0;
    matchLines.forEach((line) => {
      const key = lineId(line.size, line.color, line.finish);
      if (picked[key]) return;
      const best = line.matches.find((m) => m.color_match) ?? line.matches[0];
      if (!best) return;
      pickProduct(key, best);
      filled++;
    });
    if (filled) toast.success(`Filled ${filled} line${filled === 1 ? "" : "s"} from the catalog`);
    else if (matchLines.length === 0) toast.error("No catalog matches yet — pick a color and finish first.");
    else toast.success("Every line already has a pick");
  };
  // Make a swap: the calculator's quantities are the source of truth, and the
  // picks for both sizes go stale (their pack counts were for the old quantities).
  const applySwap = (swap: SizeSwapSuggestion) => {
    setQuantities((prev) => applySizeSwap(prev, swap));
    matchRequestLines.forEach((l) => {
      if (l.size === swap.fromSize || l.size === swap.toSize) clearPick(lineId(l.size, l.color, l.finish));
    });
    toast.success(`Swapped ${swap.fromQty} × ${swap.fromSize}" for ${swap.toQty} × ${swap.toSize}" — re-pick those sizes`);
  };
  // A plain-text message Charles can pull from: the label, pieces per size (with
  // the loose / in-enhancer split), enhancers, then the picked supplier SKUs.
  const copyForCharles = async () => {
    if (currentLines.length === 0) return toast.error("Populate a recipe first.");
    const sizeLines = currentLines.map((line) => {
      const split = enhancerLines.find((l) => l.option.size === line.option.size);
      const note = split && split.inEnhancers > 0 ? ` (${split.loose} loose / ${split.inEnhancers} in enhancers)` : "";
      return `${line.quantity} × ${line.option.display}"${note}`;
    });
    const pickLines = pickedRows().map(
      ({ l, p }) =>
        `${p.supplier} ${p.sku ?? "(no SKU)"} — ${l.size}" ${l.color ?? ""}${l.finish ? ` ${l.finish}` : ""} · ${
          p.packs_needed ?? "?"
        } pk (${l.quantity} pcs)`
    );
    const text = [
      ...(configLabel ? [configLabel] : []),
      ...sizeLines,
      ...(enhancers > 0 ? [`Enhancers: ${enhancers}`] : []),
      ...(pickLines.length ? ["", ...pickLines] : []),
    ].join("\n");
    try {
      await navigator.clipboard.writeText(text);
      toast.success("Copied for Charles");
    } catch {
      toast.error("Copy failed.");
    }
  };

  return (
    <Layout>
      <header
        className="sticky top-0 z-10 flex items-center justify-between border-b border-stone-200 px-10 py-4"
        style={{ backgroundColor: "rgb(var(--ll-page))" }}
      >
        <div>
          <h1
            className="flex items-center gap-2 text-xl font-semibold text-stone-800"
            style={{ fontFamily: "Georgia, serif" }}
          >
            <Calculator size={18} className="text-emerald-700" />
            Ornament Calculator
          </h1>
          <p className="mt-0.5 text-xs text-stone-500">
            Estimate ornaments by size, then split into colors &amp; finishes — a
            clone of Vickerman&apos;s tool.
          </p>
        </div>
        {/* Step switcher */}
        <div className="flex items-center gap-1 rounded-lg border border-stone-200 bg-white p-1 text-sm">
          <button
            onClick={() => setStep("calculator")}
            className={`rounded-md px-3 py-1.5 font-medium transition-colors ${
              step === "calculator" ? "bg-emerald-700 text-white" : "text-stone-600 hover:bg-stone-100"
            }`}
          >
            1 · Calculator
          </button>
          <button
            onClick={goToColors}
            className={`rounded-md px-3 py-1.5 font-medium transition-colors ${
              step === "colors" ? "bg-emerald-700 text-white" : "text-stone-600 hover:bg-stone-100"
            }`}
          >
            2 · Colors
          </button>
        </div>
      </header>

      <div className="px-10 py-8">
        {step === "calculator" ? (
          <CalculatorStep
            heightFt={heightFt}
            widthIn={widthIn}
            setHeightFt={changeHeight}
            setWidthIn={changeWidth}
            widthProfile={effectiveProfile}
            setWidthProfile={changeWidthProfile}
            recipeMode={recipeMode}
            setRecipeMode={changeRecipeMode}
            designStyle={designStyle}
            setDesignStyle={changeStyle}
            colorCount={colorCount}
            setColorCount={changeColorCount}
            quantities={quantities}
            setQty={setQty}
            applyRecipe={applyRecipe}
            onCoverageChange={applyRecipeAtCoverage}
            coverageTarget={coverageTarget}
            clearAll={clearAll}
            dimsValid={dimsValid}
            tooSmall={tooSmall}
            surfaceArea={surfaceArea}
            density={density}
            totalOrnaments={totalOrnaments}
            sizesUsed={qtyNumberMap.size}
            enhancerAuto={enhancerAuto}
            enhancers={enhancers}
            enhancersInput={enhancersInput}
            enhancersTouched={enhancersTouched}
            setEnhancers={changeEnhancers}
            resetEnhancers={resetEnhancers}
            enhancerLines={enhancerLines}
            goToColors={goToColors}
          />
        ) : (
          <ColorsStep
            colorBlocks={colorBlocks}
            addColorBlock={addColorBlock}
            removeColorBlock={removeColorBlock}
            updateBlock={updateBlock}
            colorPctSum={colorPctSum}
            showPctWarning={showPctWarning}
            hasQuantities={qtyByCode.size > 0}
            copyOrder={copyOrder}
            exportCsv={exportCsv}
            copyShareUrl={copyShareUrl}
            back={() => setStep("calculator")}
            matchLines={matchLines}
            matchLoading={matchLoading}
            matchError={matchError}
            onlyVickerman={onlyVickerman}
            setOnlyVickerman={setOnlyVickerman}
            recipeLines={matchRequestLines}
            picked={picked}
            activeLineKey={activeLineKey}
            openPickerFor={openPickerFor}
            pickProduct={pickProduct}
            clearPick={clearPick}
            pickedPacks={pickedPacks}
            pickedCount={pickedCount}
            configLabel={configLabel}
            buildPurchaseList={buildPurchaseList}
            canBuild={matchLines.length > 0 && !matchLoading}
            swapSuggestions={swapSuggestions}
            applySwap={applySwap}
            copyForCharles={copyForCharles}
            pickedEstimate={pickedEstimate}
          />
        )}
      </div>
    </Layout>
  );
}

/* -------------------------------------------------------------------------- */
/* Step 1: Calculator                                                         */
/* -------------------------------------------------------------------------- */

interface CalcProps {
  heightFt: number | "";
  widthIn: number | "";
  setHeightFt: (v: number | "") => void;
  setWidthIn: (v: number | "") => void;
  /** The profile the width matches (null = custom). Leaf & Ledger only. */
  widthProfile: WidthProfile | null;
  setWidthProfile: (p: WidthProfile) => void;
  recipeMode: RecipeMode;
  setRecipeMode: (m: RecipeMode) => void;
  /** Leaf & Ledger modifiers — hidden under the Vickerman rules. */
  designStyle: DesignStyle;
  setDesignStyle: (s: DesignStyle) => void;
  colorCount: number;
  setColorCount: (n: number) => void;
  quantities: QtyMap;
  setQty: (size: number, raw: string) => void;
  applyRecipe: () => void;
  onCoverageChange: (pct: number) => void;
  coverageTarget: number;
  clearAll: () => void;
  dimsValid: boolean;
  tooSmall: boolean;
  surfaceArea: number;
  density: number;
  totalOrnaments: number;
  sizesUsed: number;
  /** Table lookup for the current tree (null when dimensions are missing/too small). */
  enhancerAuto: EnhancerLookup | null;
  /** Effective enhancer count: the table's, or the user's once edited. */
  enhancers: number;
  enhancersInput: number | "";
  enhancersTouched: boolean;
  setEnhancers: (v: number | "") => void;
  resetEnhancers: () => void;
  enhancerLines: EnhancerAllocationLine[];
  goToColors: () => void;
}

function CalculatorStep(p: CalcProps) {
  const showTree = p.dimsValid && !p.tooSmall;
  const inEnhancerLines = p.enhancerLines.filter((l) => l.inEnhancers > 0);
  const inEnhancerTotal = inEnhancerLines.reduce((sum, l) => sum + l.inEnhancers, 0);
  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_380px]">
      {/* Left: inputs + table */}
      <div className="flex flex-col gap-6">
        <section className="rounded-xl border border-stone-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-stone-600">
            <TreePine size={15} className="text-emerald-700" />
            Tree Dimensions
          </h2>
          <div className="flex flex-wrap items-end gap-4">
            <label className="flex flex-col gap-1">
              <span className="text-xs font-medium text-stone-500">Tree Height (ft)</span>
              <input
                type="number"
                min={0}
                step={0.5}
                value={p.heightFt}
                onChange={(e) => p.setHeightFt(e.target.value === "" ? "" : Number(e.target.value))}
                className="w-32 rounded-lg border border-stone-300 px-3 py-2 text-sm text-stone-800 outline-none focus:border-emerald-600 focus:ring-1 focus:ring-emerald-600"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs font-medium text-stone-500">Tree Width (in)</span>
              <input
                type="number"
                min={0}
                step={1}
                value={p.widthIn}
                onChange={(e) => p.setWidthIn(e.target.value === "" ? "" : Number(e.target.value))}
                className="w-32 rounded-lg border border-stone-300 px-3 py-2 text-sm text-stone-800 outline-none focus:border-emerald-600 focus:ring-1 focus:ring-emerald-600"
              />
            </label>
            {/* Width profile — sets the width from the height and keeps it following (Leaf & Ledger only) */}
            {p.recipeMode === "leafledger" && (
              <div className="flex flex-col gap-1">
                <span className="text-xs font-medium text-stone-500">Profile</span>
                <div className="flex overflow-hidden rounded-lg border border-stone-300 text-xs font-medium">
                  {(Object.keys(WIDTH_PROFILES) as WidthProfile[]).map((profile) => (
                    <button
                      key={profile}
                      onClick={() => p.setWidthProfile(profile)}
                      disabled={!p.dimsValid}
                      className={`px-3 py-1.5 transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
                        p.widthProfile === profile
                          ? "bg-emerald-700 text-white"
                          : "bg-white text-stone-600 hover:bg-stone-100"
                      }`}
                    >
                      {WIDTH_PROFILES[profile].label}
                    </button>
                  ))}
                  <span
                    className={`px-3 py-1.5 ${
                      p.widthProfile === null && p.dimsValid ? "bg-emerald-700 text-white" : "bg-white text-stone-400"
                    }`}
                  >
                    Custom
                  </span>
                </div>
              </div>
            )}
            <button
              onClick={p.applyRecipe}
              disabled={!p.dimsValid || p.tooSmall}
              className="flex items-center gap-2 rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-emerald-800 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Sparkles size={15} />
              Populate Using Recipe
            </button>
            <button
              onClick={p.clearAll}
              className="flex items-center gap-2 rounded-lg border border-stone-300 px-3 py-2 text-sm font-medium text-stone-600 transition-colors hover:bg-stone-100"
            >
              <RotateCcw size={14} />
              Clear
            </button>
          </div>
          {p.tooSmall && (
            <p className="mt-3 text-xs text-amber-700">
              Tree is too small to calculate — width must be over 20&quot; and height over 1.7 ft.
            </p>
          )}
          <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-stone-100 pt-4">
            <span className="text-xs font-medium text-stone-500">Recipe rules</span>
            <div className="flex overflow-hidden rounded-lg border border-stone-300 text-xs font-medium">
              {(
                [
                  ["leafledger", "Leaf & Ledger"],
                  ["vickerman", "Vickerman"],
                ] as [RecipeMode, string][]
              ).map(([mode, label]) => (
                <button
                  key={mode}
                  onClick={() => p.setRecipeMode(mode)}
                  className={`px-3 py-1.5 transition-colors ${
                    p.recipeMode === mode
                      ? "bg-emerald-700 text-white"
                      : "bg-white text-stone-600 hover:bg-stone-100"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            {/* Modifiers — style and color count (Leaf & Ledger only) */}
            {p.recipeMode === "leafledger" && (
              <>
                <div className="flex overflow-hidden rounded-lg border border-stone-300 text-xs font-medium">
                  {(
                    [
                      ["traditional", "Traditional"],
                      ["contemporary", "Contemporary"],
                    ] as [DesignStyle, string][]
                  ).map(([style, label]) => (
                    <button
                      key={style}
                      onClick={() => p.setDesignStyle(style)}
                      className={`px-3 py-1.5 transition-colors ${
                        p.designStyle === style
                          ? "bg-emerald-700 text-white"
                          : "bg-white text-stone-600 hover:bg-stone-100"
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                <label className="flex items-center gap-1.5 text-xs font-medium text-stone-500">
                  Colors
                  <select
                    value={p.colorCount}
                    onChange={(e) => p.setColorCount(Number(e.target.value))}
                    className="rounded-lg border border-stone-300 px-2 py-1.5 text-xs text-stone-800 outline-none focus:border-emerald-600 focus:ring-1 focus:ring-emerald-600"
                  >
                    {Array.from({ length: LL_MAX_COLOR_COUNT - LL_MIN_COLOR_COUNT + 1 }, (_, i) => LL_MIN_COLOR_COUNT + i).map((n) => (
                      <option key={n} value={n}>
                        {n}
                      </option>
                    ))}
                  </select>
                </label>
              </>
            )}
            <span className="text-xs text-stone-500">
              {p.recipeMode === "leafledger"
                ? describeLeafLedger(p.heightFt, p.designStyle, p.colorCount)
                : "Vickerman's size family by coverage bucket · 4 sizes · 20/35/25/20 split"}
            </span>
          </div>
        </section>

        <section className="overflow-hidden rounded-xl border border-stone-200 bg-white shadow-sm">
          <div className="flex items-center justify-between border-b border-stone-200 px-6 py-4">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-stone-600">Ornaments</h2>
            <span className="text-xs text-stone-500">{p.totalOrnaments.toLocaleString()} total</span>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-stone-200 text-left text-xs uppercase tracking-wide text-stone-500">
                <th className="px-6 py-2 font-medium">Size (in)</th>
                <th className="px-6 py-2 font-medium">Quantity</th>
                <th className="px-6 py-2 font-medium">To Order</th>
              </tr>
            </thead>
            <tbody>
              {ORNAMENT_OPTIONS.map((o) => {
                const v = p.quantities[o.size];
                const numeric = typeof v === "number" ? v : 0;
                const active = numeric > 0;
                // Leaf & Ledger only — enhancerLines is empty under the Vickerman rules.
                const split = p.enhancerLines.find((l) => l.option.size === o.size);
                return (
                  <tr
                    key={o.size}
                    className={`border-b border-stone-100 last:border-0 ${active ? "bg-emerald-50/40" : ""}`}
                  >
                    <td className="px-6 py-2.5">
                      <span className={`font-medium ${active ? "text-emerald-900" : "text-stone-700"}`}>
                        {o.display}&quot;
                      </span>
                    </td>
                    <td className="px-6 py-2">
                      <input
                        type="number"
                        min={0}
                        value={v}
                        onChange={(e) => p.setQty(o.size, e.target.value)}
                        className="w-24 rounded-md border border-stone-300 px-2 py-1.5 text-sm text-stone-800 outline-none focus:border-emerald-600 focus:ring-1 focus:ring-emerald-600"
                      />
                    </td>
                    <td className="px-6 py-2 text-xs text-stone-500">
                      {active ? packSummary(o, numeric) : "—"}
                      {split && split.inEnhancers > 0 && (
                        <span className="text-stone-400">
                          {" "}· {split.loose} loose / {split.inEnhancers} in enhancers
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="flex justify-end border-t border-stone-200 px-6 py-4">
            <button
              onClick={p.goToColors}
              disabled={p.totalOrnaments === 0}
              className="flex items-center gap-2 rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-emerald-800 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Palette size={15} />
              Select Colors
            </button>
          </div>
        </section>

        {/* Enhancers — the parallel bill of materials (Leaf & Ledger rules only) */}
        {p.recipeMode === "leafledger" && (
          <section className="rounded-xl border border-stone-200 bg-white p-6 shadow-sm">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-stone-600">
                <Flower2 size={15} className="text-emerald-700" />
                Enhancers
              </h2>
              <span className="text-xs text-stone-500">
                {inEnhancerTotal.toLocaleString()} ornament{inEnhancerTotal === 1 ? "" : "s"} in enhancers
              </span>
            </div>
            <div className="flex flex-wrap items-end gap-4">
              <label className="flex flex-col gap-1">
                <span className="text-xs font-medium text-stone-500">Enhancer count</span>
                <input
                  type="number"
                  min={0}
                  step={2}
                  value={p.enhancersTouched ? p.enhancersInput : showTree ? p.enhancers : ""}
                  disabled={!showTree}
                  onChange={(e) =>
                    p.setEnhancers(e.target.value === "" ? "" : Math.max(0, Math.floor(Number(e.target.value))))
                  }
                  className="w-32 rounded-lg border border-stone-300 px-3 py-2 text-sm text-stone-800 outline-none focus:border-emerald-600 focus:ring-1 focus:ring-emerald-600 disabled:bg-stone-50 disabled:text-stone-400"
                />
              </label>
              {p.enhancersTouched && (
                <button
                  onClick={p.resetEnhancers}
                  className="flex items-center gap-2 rounded-lg border border-stone-300 px-3 py-2 text-sm font-medium text-stone-600 transition-colors hover:bg-stone-100"
                >
                  <RotateCcw size={14} />
                  Use table
                </button>
              )}
            </div>
            <p className="mt-3 text-xs text-stone-500">{describeEnhancers(p.enhancerAuto, p.enhancersTouched)}</p>

            <div className="mt-4 border-t border-stone-100 pt-4">
              <p className="text-xs font-medium uppercase tracking-wide text-stone-500">Ornaments going into enhancers</p>
              {inEnhancerLines.length > 0 ? (
                <ul className="mt-2 flex flex-col gap-1.5 text-sm">
                  {inEnhancerLines.map((l) => (
                    <li key={l.option.size} className="flex items-center justify-between">
                      <span className="font-medium text-emerald-900">{l.option.display}&quot;</span>
                      <span className="text-stone-500">
                        <span className="font-medium text-stone-800">{l.inEnhancers}</span> in enhancers · {l.loose} loose on the tree
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-xs text-stone-400">
                  {p.enhancers > 0
                    ? `Populate a recipe — sizes up to ${ENHANCER_MAX_SIZE_IN}" split half and half between the tree and the enhancers.`
                    : "No enhancers on this tree — every ornament stays loose."}
                </p>
              )}
            </div>
          </section>
        )}
      </div>

      {/* Right: tree visualization + coverage */}
      <aside className="flex flex-col gap-6">
        <section className="rounded-xl border border-stone-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-center text-sm font-semibold uppercase tracking-wide text-stone-600">
            Ornament Density
          </h2>
          <div className="flex justify-center">
            {showTree ? (
              <img
                src={treeDensityImage(p.density)}
                alt={`Tree with ${p.density}% ornament coverage`}
                className="h-80 w-auto rounded-lg object-contain"
              />
            ) : (
              <div className="flex h-80 w-52 items-center justify-center rounded-lg bg-stone-100 text-center text-xs text-stone-400">
                Enter tree dimensions to preview coverage
              </div>
            )}
          </div>
          {/* Draggable coverage slider — sliding scales the ornament counts. */}
          <input
            type="range"
            min={0}
            max={100}
            step={1}
            value={p.coverageTarget}
            disabled={!showTree}
            onChange={(e) => p.onCoverageChange(Number(e.target.value))}
            aria-label="Ornament coverage"
            title="Drag to set coverage — scales the ornament counts"
            className="ornament-slider mt-4 w-full"
            style={{
              background: `linear-gradient(to right, ${densityColor(p.coverageTarget)} ${p.coverageTarget}%, rgb(var(--ns-200)) ${p.coverageTarget}%)`,
            }}
          />
          <div className="mt-2 flex items-center justify-between">
            <span className="text-xs" style={{ color: densityColor(p.density) }}>
              {showTree ? `${densityLabel(p.density)} · drag to adjust` : "—"}
            </span>
            <span
              className="text-lg font-bold"
              style={{ fontFamily: "Georgia, serif", color: densityColor(p.density) }}
            >
              Total Coverage: {p.density}%
            </span>
          </div>

          <dl className="mt-5 flex flex-col gap-2 border-t border-stone-100 pt-4 text-sm">
            <div className="flex items-center justify-between">
              <dt className="text-stone-500">Tree surface area</dt>
              <dd className="font-medium text-stone-800">
                {p.surfaceArea > 0 ? `${Math.round(p.surfaceArea).toLocaleString()} sq in` : "—"}
              </dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-stone-500">Total ornaments</dt>
              <dd className="font-medium text-stone-800">{p.totalOrnaments.toLocaleString()}</dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-stone-500">Sizes used</dt>
              <dd className="font-medium text-stone-800">{p.sizesUsed}</dd>
            </div>
          </dl>
        </section>

        <section className="rounded-xl border border-stone-200 bg-stone-50 p-5">
          <p className="text-xs leading-relaxed text-stone-500">
            <strong className="text-stone-600">Disclaimer:</strong> the tree image
            illustrates approximate coverage based on the number and size of ornaments
            you enter. It doesn&apos;t represent exact dimensions or specific models — use
            it as a planning guide, not an exact representation.
          </p>
        </section>
      </aside>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Step 2: Select Colors                                                      */
/* -------------------------------------------------------------------------- */

interface ColorsProps {
  colorBlocks: ColorBlock[];
  addColorBlock: () => void;
  removeColorBlock: (id: number) => void;
  updateBlock: (id: number, patch: Partial<ColorBlock>) => void;
  colorPctSum: number;
  showPctWarning: boolean;
  hasQuantities: boolean;
  copyOrder: () => void;
  exportCsv: () => void;
  copyShareUrl: () => void;
  back: () => void;
  matchLines: MatchLine[];
  matchLoading: boolean;
  matchError: string | null;
  onlyVickerman: boolean;
  setOnlyVickerman: (v: boolean) => void;
  recipeLines: { size: number; quantity: number; color: string | null; finish: string | null }[];
  picked: Record<string, CatalogMatch>;
  activeLineKey: string | null;
  openPickerFor: (key: string) => void;
  pickProduct: (key: string, m: CatalogMatch) => void;
  clearPick: (key: string) => void;
  pickedPacks: number;
  pickedCount: number;
  /** The tree configuration the list is for, e.g. "9 ft standard · traditional · Red + Gold". */
  configLabel: string;
  buildPurchaseList: () => void;
  /** Matches are in and not loading, so there is something to fill from. */
  canBuild: boolean;
  swapSuggestions: SizeSwapSuggestion[];
  applySwap: (swap: SizeSwapSuggestion) => void;
  copyForCharles: () => void;
  /** Packs × pack price over the picks, plus how many picks have no price. */
  pickedEstimate: { total: number; unpriced: number };
}

function ColorsStep(p: ColorsProps) {
  return (
    <div className="flex flex-col gap-6">
    {/* Purchase list header — the configuration Charles reads first, and one click to fill it */}
    <section className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-stone-200 bg-white px-6 py-4 shadow-sm">
      <div>
        <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-stone-500">
          <ListChecks size={14} className="text-emerald-700" />
          Purchase list
        </p>
        <h2 className="mt-0.5 text-lg font-semibold text-stone-800" style={{ fontFamily: "Georgia, serif" }}>
          {p.configLabel || "Enter tree dimensions and choose colors"}
        </h2>
      </div>
      <button
        onClick={p.buildPurchaseList}
        disabled={!p.canBuild}
        title="Fill every size that has no pick with its best catalog match"
        className="flex items-center gap-2 rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-emerald-800 disabled:cursor-not-allowed disabled:opacity-40"
      >
        <ListChecks size={15} />
        Build purchase list
      </button>
    </section>
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_420px]">
      {/* Left: color blocks */}
      <div className="flex flex-col gap-6">
        <button
          onClick={p.back}
          className="flex w-fit items-center gap-2 text-sm font-medium text-stone-500 hover:text-stone-800"
        >
          <ArrowLeft size={15} /> Back to calculator
        </button>

        {!p.hasQuantities && (
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
            No ornament quantities yet. Go back to the calculator and populate a recipe first.
          </div>
        )}

        {p.colorBlocks.map((block, idx) => {
          const color = COLORS.find((c) => c.code === block.colorCode);
          return (
            <section key={block.id} className="rounded-xl border border-stone-200 bg-white p-6 shadow-sm">
              <div className="mb-4 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span
                    className="h-5 w-5 rounded-full border border-stone-300"
                    style={{ backgroundColor: color?.hex ?? "rgb(var(--ns-200))" }}
                  />
                  <h3 className="text-sm font-semibold text-stone-700">Color {idx + 1}</h3>
                </div>
                {p.colorBlocks.length > 1 && (
                  <button
                    onClick={() => p.removeColorBlock(block.id)}
                    className="flex items-center gap-1 text-xs font-medium text-rose-600 hover:text-rose-700"
                  >
                    <Trash2 size={13} /> Remove
                  </button>
                )}
              </div>

              <div className="flex flex-wrap items-end gap-4">
                <label className="flex flex-col gap-1">
                  <span className="text-xs font-medium text-stone-500">Color</span>
                  <select
                    value={block.colorCode}
                    onChange={(e) => p.updateBlock(block.id, { colorCode: e.target.value })}
                    className="w-52 rounded-lg border border-stone-300 px-3 py-2 text-sm text-stone-800 outline-none focus:border-emerald-600 focus:ring-1 focus:ring-emerald-600"
                  >
                    <option value="">Select a color…</option>
                    {COLORS.map((c) => (
                      <option key={c.code} value={c.code}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-xs font-medium text-stone-500">Finish</span>
                  <select
                    value={block.finishCode}
                    onChange={(e) => p.updateBlock(block.id, { finishCode: e.target.value })}
                    className="w-44 rounded-lg border border-stone-300 px-3 py-2 text-sm text-stone-800 outline-none focus:border-emerald-600 focus:ring-1 focus:ring-emerald-600"
                  >
                    <option value="">Select a finish…</option>
                    {FINISHES.map((f) => (
                      <option key={f.code} value={f.code}>
                        {f.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-xs font-medium text-stone-500">Share of tree (%)</span>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    value={block.sharePct}
                    onChange={(e) =>
                      p.updateBlock(block.id, { sharePct: Math.max(0, Math.min(100, Number(e.target.value) || 0)) })
                    }
                    className="w-24 rounded-lg border border-stone-300 px-3 py-2 text-sm text-stone-800 outline-none focus:border-emerald-600 focus:ring-1 focus:ring-emerald-600"
                  />
                </label>
              </div>
              <p className="mt-3 text-xs text-stone-400">
                One color + one finish per box. Need another? <span className="font-medium text-emerald-700">Add Color</span> for
                e.g. Blue&nbsp;Glitter&nbsp;50% + Blue&nbsp;Matte&nbsp;10% + Green&nbsp;Matte&nbsp;40%.
              </p>
            </section>
          );
        })}

        <div className="flex items-center gap-3">
          <button
            onClick={p.addColorBlock}
            className="flex items-center gap-2 rounded-lg border border-emerald-600 px-4 py-2 text-sm font-semibold text-emerald-700 transition-colors hover:bg-emerald-50"
          >
            <Plus size={15} /> Add Color
          </button>
          {p.showPctWarning && (
            <span className="text-xs text-amber-700">
              ⚠️ Color shares total {p.colorPctSum}% (should equal 100%)
            </span>
          )}
        </div>
      </div>

      {/* Right: fill-in-the-blank order — pick a real product per size */}
      <aside className="flex flex-col gap-4">
        <section id="order-panel" className="rounded-xl border border-stone-200 bg-white shadow-sm">
          <div className="flex items-center justify-between border-b border-stone-200 px-5 py-4">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-stone-600">Order</h2>
            <span className="text-xs text-stone-500">
              {p.pickedCount}/{p.recipeLines.length} picked · {p.pickedPacks.toLocaleString()} packs
            </span>
          </div>

          {p.recipeLines.length === 0 ? (
            <div className="px-5 py-10 text-center text-sm text-stone-400">
              Pick a color and at least one finish to build your order.
            </div>
          ) : (
            <div className="max-h-[560px] divide-y divide-stone-100 overflow-y-auto">
              {p.recipeLines.map((ln) => {
                const key = lineId(ln.size, ln.color, ln.finish);
                const pick = p.picked[key];
                const hex = COLORS.find((c) => c.name === ln.color)?.hex ?? "rgb(var(--ns-200))";
                const active = p.activeLineKey === key;
                return (
                  <div key={key} className={`px-4 py-3 ${active ? "bg-emerald-50/50" : ""}`}>
                    <div className="mb-2 flex items-center gap-2 text-sm">
                      <span className="h-4 w-4 flex-shrink-0 rounded-full border border-stone-300" style={{ backgroundColor: hex }} />
                      <span className="font-semibold text-stone-800">{ln.size}&quot;</span>
                      <span className="text-stone-500">· {ln.color}{ln.finish ? ` · ${ln.finish}` : ""}</span>
                      <span className="ml-auto text-xs text-stone-400">need {ln.quantity.toLocaleString()} pcs</span>
                    </div>
                    {pick ? (
                      <div className={`flex items-center gap-3 rounded-lg border p-2 ${active ? "border-emerald-400" : "border-stone-200"}`}>
                        <div className="h-11 w-11 flex-shrink-0 overflow-hidden rounded border border-stone-200 bg-stone-50">
                          {pick.image ? (
                            <img src={proxied(pick.image)} alt="" className="h-full w-full object-contain" />
                          ) : (
                            <div className="flex h-full w-full items-center justify-center text-stone-300"><PackageSearch size={16} /></div>
                          )}
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-xs font-medium text-stone-800" title={pick.name}>{pick.name}</p>
                          <p className="truncate text-[11px] text-stone-500">
                            {pick.supplier} · {pick.sku || "—"}{pick.price != null ? ` · $${pick.price.toFixed(2)}` : ""}
                          </p>
                        </div>
                        <div className="flex flex-col items-end gap-1">
                          <span className="whitespace-nowrap text-sm font-bold text-emerald-800">{pick.packs_needed ?? "—"} pk</span>
                          <div className="flex items-center gap-1.5">
                            <button onClick={() => p.openPickerFor(key)} className="text-[10px] font-medium text-emerald-700 hover:underline">change</button>
                            <button onClick={() => p.clearPick(key)} className="text-stone-300 hover:text-rose-500" title="Clear"><X size={13} /></button>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <button
                        onClick={() => p.openPickerFor(key)}
                        className={`flex w-full items-center justify-center gap-2 rounded-lg border-2 border-dashed py-3 text-sm font-medium transition-colors ${
                          active ? "border-emerald-500 bg-emerald-50 text-emerald-700" : "border-stone-300 text-stone-500 hover:border-emerald-400 hover:text-emerald-700"
                        }`}
                      >
                        <Plus size={15} /> Pick a {ln.size}&quot; {ln.color}{ln.finish ? ` ${ln.finish}` : ""} product
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {p.pickedCount > 0 && (
            <div className="flex items-center justify-between gap-3 border-t border-stone-200 px-5 py-3 text-sm">
              <span className="text-stone-500">
                Estimate
                <span className="text-xs text-stone-400">
                  {" "}· packs × pack price
                  {p.pickedEstimate.unpriced > 0 && ` · ${p.pickedEstimate.unpriced} without a price left out`}
                </span>
              </span>
              <span className="font-semibold text-stone-800">{money(p.pickedEstimate.total)}</span>
            </div>
          )}

          <div className="flex flex-wrap gap-2 border-t border-stone-200 px-5 py-4">
            <button
              onClick={p.copyOrder}
              className="flex items-center gap-2 rounded-lg bg-emerald-700 px-3 py-2 text-sm font-semibold text-white transition-colors hover:bg-emerald-800"
            >
              <Copy size={14} /> Copy
            </button>
            <button
              onClick={p.copyForCharles}
              title="Plain text: the tree, pieces per size, enhancers, then the picked SKUs"
              className="flex items-center gap-2 rounded-lg border border-emerald-600 px-3 py-2 text-sm font-medium text-emerald-700 transition-colors hover:bg-emerald-50"
            >
              <MessageSquareText size={14} /> Copy for Charles
            </button>
            <button
              onClick={p.exportCsv}
              className="flex items-center gap-2 rounded-lg border border-stone-300 px-3 py-2 text-sm font-medium text-stone-700 transition-colors hover:bg-stone-100"
            >
              <Download size={14} /> Export CSV
            </button>
            <button
              onClick={p.copyShareUrl}
              className="flex items-center gap-2 rounded-lg border border-stone-300 px-3 py-2 text-sm font-medium text-stone-700 transition-colors hover:bg-stone-100"
            >
              <Link2 size={14} /> Share link
            </button>
          </div>
        </section>

        {/* Price-aware size swaps (designer rule 8) — only when the picks' prices make one worth it */}
        {p.swapSuggestions.length > 0 && (
          <section className="rounded-xl border border-emerald-200 bg-emerald-50/40 p-5">
            <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-stone-600">
              <ArrowUpRight size={15} className="text-emerald-700" />
              Size swaps worth making
            </h2>
            <p className="mt-1 text-xs text-stone-500">
              The same coverage from the next size up, at no more than {Math.round(LL_SIZE_SWAP_TOLERANCE * 100)}% more per
              square inch — the designers take the bigger ornament every time.
            </p>
            <ul className="mt-3 flex flex-col gap-2 text-sm">
              {p.swapSuggestions.map((s) => (
                <li key={`${s.fromSize}-${s.toSize}`} className="flex items-center justify-between gap-3">
                  <span
                    className="text-stone-700"
                    title={`${money(s.fromCostPerSqIn)}/sq in → ${money(s.toCostPerSqIn)}/sq in`}
                  >
                    {describeSwap(s)}
                  </span>
                  <button
                    onClick={() => p.applySwap(s)}
                    className="flex-shrink-0 rounded-lg border border-emerald-600 px-3 py-1.5 text-xs font-semibold text-emerald-700 transition-colors hover:bg-emerald-100"
                  >
                    Apply
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        <section className="rounded-xl border border-stone-200 bg-stone-50 p-5">
          <p className="text-xs leading-relaxed text-stone-500">
            Click a size to <strong className="text-stone-600">pick a real product</strong> from the catalog
            below, or <strong className="text-stone-600">Build purchase list</strong> to fill every size with its
            best match. Each size fills in with your chosen ornament and the packs you need — from
            <strong className="text-stone-600"> every supplier</strong> in your catalog.
          </p>
        </section>
      </aside>
    </div>

      {/* Full-width: real catalog matches across all suppliers */}
      <CatalogMatches
        matchLines={p.matchLines}
        loading={p.matchLoading}
        error={p.matchError}
        onlyVickerman={p.onlyVickerman}
        setOnlyVickerman={p.setOnlyVickerman}
        hasQuantities={p.hasQuantities}
        picked={p.picked}
        activeLineKey={p.activeLineKey}
        onPick={p.pickProduct}
      />
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Catalog matches — real products across every supplier                      */
/* -------------------------------------------------------------------------- */

interface CatalogMatchesProps {
  matchLines: MatchLine[];
  loading: boolean;
  error: string | null;
  onlyVickerman: boolean;
  setOnlyVickerman: (v: boolean) => void;
  hasQuantities: boolean;
  picked: Record<string, CatalogMatch>;
  activeLineKey: string | null;
  onPick: (key: string, m: CatalogMatch) => void;
}

function CatalogMatches(p: CatalogMatchesProps) {
  const suppliers = useMemo(() => {
    const s = new Set<string>();
    p.matchLines.forEach((l) => l.matches.forEach((m) => s.add(m.supplier)));
    return Array.from(s).sort();
  }, [p.matchLines]);

  if (!p.hasQuantities) return null;

  return (
    <section className="rounded-xl border border-stone-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-stone-200 px-6 py-4">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-stone-600">
            <PackageSearch size={16} className="text-emerald-700" />
            Catalog Matches
          </h2>
          <p className="mt-0.5 text-xs text-stone-500">
            Real, orderable products matched to your recipe by size &amp; color — across{" "}
            {suppliers.length || "all"} supplier{suppliers.length === 1 ? "" : "s"}.
          </p>
        </div>
        <label className="flex items-center gap-2 text-xs font-medium text-stone-600">
          <input
            type="checkbox"
            checked={p.onlyVickerman}
            onChange={(e) => p.setOnlyVickerman(e.target.checked)}
            className="accent-emerald-700"
          />
          Vickerman only
        </label>
      </div>

      {p.error ? (
        <div className="px-6 py-8 text-center text-sm text-rose-600">
          Couldn&apos;t load catalog matches ({p.error}).
        </div>
      ) : p.loading && p.matchLines.length === 0 ? (
        <div className="flex items-center justify-center gap-2 px-6 py-10 text-sm text-stone-400">
          <Loader2 size={16} className="animate-spin" /> Searching the catalog…
        </div>
      ) : p.matchLines.length === 0 ? (
        <div className="px-6 py-10 text-center text-sm text-stone-400">
          Pick a color and finish to see matching products.
        </div>
      ) : (
        <div className="flex flex-col divide-y divide-stone-100">
          {p.matchLines.map((line) => {
            const key = lineId(line.size, line.color, line.finish);
            const active = p.activeLineKey === key;
            const chosenId = p.picked[key]?.product_id;
            return (
              <div
                key={key}
                id={`match-line-${key}`}
                className={`scroll-mt-4 px-6 py-4 ${active ? "bg-emerald-50/40 ring-1 ring-inset ring-emerald-400" : ""}`}
              >
                <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
                  <span className="font-semibold text-stone-800">{line.size}&quot;</span>
                  {line.color && <span className="text-stone-500">· {line.color}</span>}
                  {line.finish && <span className="text-stone-500">· {line.finish}</span>}
                  <span className="text-stone-400">· need {line.quantity.toLocaleString()} pcs</span>
                  {active && (
                    <span className="rounded bg-emerald-600 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-white">
                      Choosing — tap ＋
                    </span>
                  )}
                  {chosenId != null && !active && (
                    <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700">
                      ✓ picked
                    </span>
                  )}
                  <span className="ml-auto text-xs text-stone-400">
                    {line.match_count.toLocaleString()} in catalog
                  </span>
                </div>
                {line.matches.length === 0 ? (
                  <p className="text-xs text-stone-400">No close match in the catalog for this size/color.</p>
                ) : (
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
                    {line.matches.map((m, i) => (
                      <MatchCard
                        key={`${m.product_id}-${i}`}
                        m={m}
                        best={i === 0}
                        chosen={m.product_id === chosenId}
                        onPick={() => p.onPick(key, m)}
                      />
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

function MatchCard({
  m, best, chosen, onPick,
}: { m: CatalogMatch; best: boolean; chosen?: boolean; onPick?: () => void }) {
  const [broken, setBroken] = useState(false);
  return (
    <button
      type="button"
      onClick={onPick}
      title="Add this to your order"
      className={`group relative flex flex-col overflow-hidden rounded-lg border bg-white text-left transition-shadow hover:shadow-md ${
        chosen
          ? "border-emerald-600 ring-2 ring-emerald-500"
          : best
          ? "border-emerald-500 ring-1 ring-emerald-500/30"
          : "border-stone-200"
      }`}
    >
      <div className="relative aspect-square bg-stone-50">
        {m.image && !broken ? (
          <img
            src={proxied(m.image)}
            alt={m.name}
            className="h-full w-full object-contain"
            onError={() => setBroken(true)}
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-stone-300">
            <PackageSearch size={22} />
          </div>
        )}
        {best && (
          <span className="absolute left-1 top-1 rounded bg-emerald-600 px-1.5 py-0.5 text-[9px] font-semibold uppercase text-white">
            Best
          </span>
        )}
        {m.color_match && (
          <span className="absolute right-1 top-1 rounded bg-white/90 px-1 py-0.5 text-[9px] font-medium text-emerald-700">
            color ✓
          </span>
        )}
        {/* add-to-order affordance */}
        <span
          className={`absolute bottom-1 right-1 flex h-7 w-7 items-center justify-center rounded-full shadow transition-colors ${
            chosen
              ? "bg-emerald-600 text-white"
              : "bg-white text-emerald-700 group-hover:bg-emerald-600 group-hover:text-white"
          }`}
        >
          {chosen ? <Check size={15} /> : <Plus size={15} />}
        </span>
      </div>
      <div className="flex flex-1 flex-col gap-1 p-2">
        <p className="line-clamp-2 text-[11px] font-medium leading-tight text-stone-700" title={m.name}>
          {m.name}
        </p>
        <p className="flex items-center gap-1 text-[10px] text-stone-400">
          <Store size={10} /> {m.supplier}
        </p>
        <p className="truncate font-mono text-[10px] text-stone-500">{m.sku || "—"}</p>
        <div className="mt-auto flex items-center justify-between pt-1">
          <span className="flex items-center gap-0.5 text-xs font-semibold text-stone-800">
            {m.price != null ? (
              <>
                <Tag size={11} className="text-emerald-700" />${m.price.toFixed(2)}
              </>
            ) : (
              <span className="text-stone-400">no price</span>
            )}
          </span>
          {m.packs_needed != null && (
            <span className={`text-[10px] font-medium ${chosen ? "text-emerald-700" : "text-stone-500"}`}>
              {m.packs_needed} pk
            </span>
          )}
        </div>
      </div>
    </button>
  );
}
