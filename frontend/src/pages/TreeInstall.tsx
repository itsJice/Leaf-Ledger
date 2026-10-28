import React, { Suspense, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  AlertTriangle,
  Calculator,
  CheckCircle2,
  Eye,
  EyeOff,
  Layers,
  ListChecks,
  Loader2,
  Palette,
  Play,
  Printer,
  Shrub,
  Spline,
  TreePine,
} from "components/icons";
import Layout from "components/Layout";
import {
  COLORS,
  LL_DEFAULT_COLOR_COUNT,
  LL_MAX_COLOR_COUNT,
  LL_MIN_COLOR_COUNT,
  WIDTH_PROFILES,
  profileForWidth,
  splitAcrossColors,
  widthForProfile,
  type DesignStyle,
  type WidthProfile,
} from "utils/ornamentRecipe";
import {
  BOW_IN,
  treeInstallCounts,
  type TreeInstallLayoutInput,
} from "utils/treeInstallLayout";
import type { TreeView } from "components/TreeInstall3D";
import { useTreeLayout } from "components/useTreeLayout";
import { treeInstallPrintUrl } from "utils/treeInstallPrint";

// Tree Install: pick a tree's size, style and colors, get the Ornament
// Calculator's counts for it, and see where every piece goes on a 3D tree you can
// spin. The counts are the calculator's engine, unchanged (utils/ornamentRecipe.ts);
// the placement is utils/treeInstallLayout.ts (designer rules of 10/27/2026).

// three.js only loads with this page, and only once the mockup is on screen.
const TreeInstall3D = React.lazy(() => import("components/TreeInstall3D"));

const INPUT_CLASS =
  "w-full rounded-lg border border-stone-300 px-3 py-2 text-sm text-stone-800 outline-none focus:border-emerald-600 focus:ring-1 focus:ring-emerald-600";
const CARD = "rounded-xl border border-stone-200 bg-white p-4 shadow-sm sm:p-6";
const CARD_TITLE = "mb-4 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-stone-600";
const SEGMENT = "flex overflow-hidden rounded-lg border border-stone-300 text-xs font-medium";
const segmentButton = (on: boolean) =>
  `flex-1 px-2 py-2 transition-colors disabled:cursor-not-allowed disabled:opacity-40 sm:px-3 ${
    on ? "bg-emerald-700 text-white" : "bg-white text-stone-600 hover:bg-stone-100"
  }`;
const pillButton = (on: boolean) =>
  `flex min-h-[40px] items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors ${
    on
      ? "border-emerald-700 bg-emerald-700 text-white"
      : "border-stone-300 bg-white text-stone-600 hover:bg-stone-100"
  }`;

/** Starting colors, all Vickerman colors (the reference tree's burgundy, gold and champagne, then blue). */
const vick = (name: string) => COLORS.find((c) => c.name === name)?.hex ?? "#888888";
const DEFAULT_COLORS = [vick("Berry Red"), vick("Gold"), vick("Champagne"), vick("Blue")];
const DEFAULT_RIBBON_A = vick("Wine");
const DEFAULT_RIBBON_B = vick("Antique Gold");
const DEFAULT_TOPPER = vick("Honey Gold");


function ColorField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (hex: string) => void;
}) {
  const named = COLORS.find((c) => c.hex.toLowerCase() === value.toLowerCase());
  return (
    <div className="flex items-center gap-2">
      <span className="w-20 shrink-0 text-xs font-semibold text-stone-600">{label}</span>
      <input
        type="color"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-label={`${label} color`}
        className="h-10 w-12 shrink-0 cursor-pointer rounded-lg border border-stone-300 bg-white p-1"
      />
      <select
        value={named ? named.hex : ""}
        onChange={(e) => e.target.value && onChange(e.target.value)}
        aria-label={`${label}: pick a Vickerman color`}
        className="min-w-0 flex-1 rounded-lg border border-stone-300 bg-white px-2 py-2 text-sm text-stone-800 outline-none focus:border-emerald-600 focus:ring-1 focus:ring-emerald-600"
      >
        <option value="">{named ? named.name : "Custom color"}</option>
        {COLORS.map((c) => (
          <option key={c.code} value={c.hex}>
            {c.name}
          </option>
        ))}
      </select>
    </div>
  );
}

export default function TreeInstall() {
  // Same inputs and defaults as the Ornament Calculator.
  // Same inputs and defaults as the Ornament Calculator; coming back from a printout
  // (?h=&w=&n=...) picks up the tree that was printed.
  const [q] = useSearchParams();
  const init = useMemo(() => {
    const h0 = Number(q.get("h"));
    const w0 = Number(q.get("w"));
    const n0 = Number(q.get("n"));
    const hexOf = (v: string | null, d: string) => (v && /^[0-9a-f]{6}$/i.test(v) ? `#${v}` : d);
    const given = (q.get("c") ?? "").split(",");
    const heightFt = h0 > 0 ? h0 : 7.5;
    return {
      heightFt,
      widthIn: w0 > 0 ? w0 : widthForProfile(heightFt, "standard"),
      profile: w0 > 0 ? profileForWidth(heightFt, w0) : ("standard" as WidthProfile),
      colorCount: n0 > 0 ? n0 : LL_DEFAULT_COLOR_COUNT,
      style: (q.get("style") === "contemporary" ? "contemporary" : "traditional") as DesignStyle,
      wholePacks: q.get("packs") !== "0",
      colors: DEFAULT_COLORS.map((d, i) => hexOf(given[i] ?? null, d)),
      ribbonA: hexOf(q.get("a"), DEFAULT_RIBBON_A),
      ribbonB: hexOf(q.get("b"), DEFAULT_RIBBON_B),
      topper: hexOf(q.get("t"), DEFAULT_TOPPER),
    };
    // read once, on arrival
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const [heightFt, setHeightFt] = useState<number | "">(init.heightFt);
  const [widthIn, setWidthIn] = useState<number | "">(init.widthIn);
  const [widthProfile, setWidthProfile] = useState<WidthProfile | null>(init.profile);
  const [style, setStyle] = useState<DesignStyle>(init.style);
  const [colorCount, setColorCount] = useState(init.colorCount);
  const [wholePacks, setWholePacks] = useState(init.wholePacks);
  const [colors, setColors] = useState<string[]>(init.colors);
  const [ribbonA, setRibbonA] = useState(init.ribbonA);
  const [ribbonB, setRibbonB] = useState(init.ribbonB);
  const [topper, setTopper] = useState(init.topper);
  const [showLabels, setShowLabels] = useState(true);
  const [showLines, setShowLines] = useState(true);
  const [spin, setSpin] = useState(true);
  const [view, setView] = useState<{ name: TreeView; nonce: number } | null>(null);
  const [rows, setRows] = useState<number | null>(null); // null = every row

  const h = typeof heightFt === "number" ? heightFt : NaN;
  const w = typeof widthIn === "number" ? widthIn : NaN;
  // A tree the layout can draw: a sensible size for a real install.
  const dimsValid = Number.isFinite(h) && Number.isFinite(w) && h >= 4 && h <= 30 && w >= 20 && w <= 240;
  const effectiveProfile = widthProfile ?? (dimsValid ? profileForWidth(h, w) : null);

  const counts = useMemo(
    () => (dimsValid ? treeInstallCounts(h, w, { style, colorCount, wholePacks }) : null),
    [dimsValid, h, w, style, colorCount, wholePacks]
  );
  const layoutInput = useMemo<TreeInstallLayoutInput | null>(
    () =>
      counts
        ? {
            heightFt: h,
            widthIn: w,
            colorCount,
            enhancers: counts.enhancers,
            loose: counts.loose,
            inEnhancers: counts.inEnhancers,
          }
        : null,
    [counts, h, w, colorCount]
  );
  const { layout, busy } = useTreeLayout(layoutInput);
  const stale = busy || !layout;

  useEffect(() => setRows(null), [layout]);
  const rowsShown = layout ? Math.min(rows ?? layout.rows, layout.rows) : 0;

  const changeHeight = (v: number | "") => {
    setHeightFt(v);
    if (widthProfile && typeof v === "number" && v > 0) setWidthIn(widthForProfile(v, widthProfile));
  };
  const changeWidth = (v: number | "") => {
    setWidthProfile(null);
    setWidthIn(v);
  };
  const changeProfile = (profile: WidthProfile) => {
    setWidthProfile(profile);
    if (typeof heightFt === "number" && heightFt > 0) setWidthIn(widthForProfile(heightFt, profile));
  };
  const printUrl = (sheet: "design" | "cone") =>
    treeInstallPrintUrl(sheet, {
      heightFt: dimsValid ? h : 9,
      widthIn: dimsValid ? w : 59,
      colorCount,
      style,
      wholePacks,
      colors: usedColors,
      ribbonA,
      ribbonB,
      topper,
    });
  const jump = (name: TreeView) => {
    setSpin(false);
    setView((v) => ({ name, nonce: (v?.nonce ?? 0) + 1 }));
  };

  const placedBySize = useMemo(() => {
    const map = new Map<number, number>();
    layout?.items.forEach((o) => {
      if (o.kind === "orn") map.set(o.inch, (map.get(o.inch) ?? 0) + 1);
    });
    return map;
  }, [layout]);
  // A and B as placed (half and half; an odd count differs by one)
  const enhancersA = layout && !stale ? layout.check.A : counts ? Math.ceil(counts.enhancers / 2) : 0;
  const enhancersB = layout && !stale ? layout.check.B : counts ? counts.enhancers - enhancersA : 0;
  const placedBows = layout ? layout.check.A + layout.check.B : 0;
  const looseTotal = counts ? Object.values(counts.loose).reduce((a, b) => a + b, 0) : 0;
  const insideTotal = counts ? Object.values(counts.inEnhancers).reduce((a, b) => a + b, 0) : 0;
  const usedColors = colors.slice(0, colorCount);
  const treeLabel = dimsValid
    ? `${h} ft ${effectiveProfile ? WIDTH_PROFILES[effectiveProfile].label.toLowerCase() : `x ${w} in`}`
    : "";

  return (
    <Layout>
      <header
        className="sticky top-0 z-10 flex flex-wrap items-center justify-between gap-3 border-b border-stone-200 px-4 py-4 sm:px-10"
        style={{ backgroundColor: "rgb(var(--ll-page))" }}
      >
        <div className="min-w-0">
          <h1
            className="flex items-center gap-2 text-xl font-semibold text-stone-800"
            style={{ fontFamily: "'Sora', system-ui, sans-serif" }}
          >
            <Shrub size={18} className="text-emerald-700" />
            Tree Install
          </h1>
          <p className="mt-0.5 text-xs text-stone-500">
            Pick the tree and its colors, then spin the 3D mockup to see where every ornament, enhancer and the topper
            goes.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
        <Link
          to={printUrl("design")}
          aria-disabled={!dimsValid}
          className={`flex min-h-[40px] items-center gap-2 rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm font-medium text-stone-600 transition-colors hover:border-emerald-400 hover:text-emerald-700 ${dimsValid ? "" : "pointer-events-none opacity-40"}`}
        >
          <Printer size={14} />
          Print sheet
        </Link>
        <Link
          to={printUrl("cone")}
          aria-disabled={!dimsValid}
          className={`flex min-h-[40px] items-center gap-2 rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm font-medium text-stone-600 transition-colors hover:border-emerald-400 hover:text-emerald-700 ${dimsValid ? "" : "pointer-events-none opacity-40"}`}
        >
          <Layers size={14} />
          Paper model
        </Link>
        <Link
          to="/ornament-calculator"
          className="flex min-h-[40px] items-center gap-2 rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm font-medium text-stone-600 transition-colors hover:border-emerald-400 hover:text-emerald-700"
        >
          <Calculator size={14} />
          Ornament Calculator
        </Link>
        </div>
      </header>

      <div className="max-w-[1600px] px-4 py-6 sm:px-10 sm:py-8">
        {/* Phones and tablets: one column (tree, mockup, colors, counts, how to). From
            xl: the inputs and counts on the left, the mockup on the right. */}
        <div className="flex flex-col gap-6 xl:grid xl:grid-cols-[360px_minmax(0,1fr)] xl:items-start">
          <div className="contents xl:flex xl:flex-col xl:gap-6">
          {/* The tree */}
          <section className={`${CARD} order-1`}>
            <h2 className={CARD_TITLE}>
              <TreePine size={15} className="text-emerald-700" />
              The tree
            </h2>
            <div className="grid grid-cols-2 gap-3">
              <label className="flex flex-col gap-1">
                <span className="text-xs font-medium text-stone-500">Tree Height (ft)</span>
                <input
                  type="number"
                  inputMode="decimal"
                  min={4}
                  max={30}
                  step={0.5}
                  value={heightFt}
                  onChange={(e) => changeHeight(e.target.value === "" ? "" : Number(e.target.value))}
                  className={INPUT_CLASS}
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs font-medium text-stone-500">Tree Width (in)</span>
                <input
                  type="number"
                  inputMode="numeric"
                  min={20}
                  max={240}
                  step={1}
                  value={widthIn}
                  onChange={(e) => changeWidth(e.target.value === "" ? "" : Number(e.target.value))}
                  className={INPUT_CLASS}
                />
              </label>
            </div>
            {!dimsValid && (
              <p className="mt-2 text-xs text-amber-700">
                Enter a height from 4 to 30 ft and a width from 20 to 240 in.
              </p>
            )}
            <div className="mt-4 flex flex-col gap-1">
              <span className="text-xs font-medium text-stone-500">Profile</span>
              <div className={SEGMENT}>
                {(Object.keys(WIDTH_PROFILES) as WidthProfile[]).map((profile) => (
                  <button
                    key={profile}
                    type="button"
                    onClick={() => changeProfile(profile)}
                    disabled={!(typeof heightFt === "number" && heightFt > 0)}
                    aria-pressed={effectiveProfile === profile}
                    className={segmentButton(effectiveProfile === profile)}
                  >
                    {WIDTH_PROFILES[profile].label}
                  </button>
                ))}
                <span
                  className={`flex-1 px-2 py-2 text-center sm:px-3 ${
                    effectiveProfile === null && dimsValid ? "bg-emerald-700 text-white" : "bg-white text-stone-400"
                  }`}
                >
                  Custom
                </span>
              </div>
            </div>
            <div className="mt-4 flex flex-col gap-1">
              <span className="text-xs font-medium text-stone-500">Style</span>
              <div className={SEGMENT}>
                {(
                  [
                    ["traditional", "Traditional"],
                    ["contemporary", "Contemporary"],
                  ] as [DesignStyle, string][]
                ).map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setStyle(value)}
                    aria-pressed={style === value}
                    className={segmentButton(style === value)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            <div className="mt-4 flex flex-wrap items-end gap-3">
              <label className="flex flex-col gap-1">
                <span className="text-xs font-medium text-stone-500">Colors</span>
                <select
                  value={colorCount}
                  onChange={(e) => setColorCount(Number(e.target.value))}
                  className="min-h-[40px] rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm text-stone-800 outline-none focus:border-emerald-600 focus:ring-1 focus:ring-emerald-600"
                >
                  {Array.from({ length: LL_MAX_COLOR_COUNT - LL_MIN_COLOR_COUNT + 1 }, (_, i) => LL_MIN_COLOR_COUNT + i).map(
                    (n) => (
                      <option key={n} value={n}>
                        {n}
                      </option>
                    )
                  )}
                </select>
              </label>
              <button
                type="button"
                onClick={() => setWholePacks(!wholePacks)}
                aria-pressed={wholePacks}
                title="Round every size to whole packs for each color, like the Ornament Calculator does"
                className={pillButton(wholePacks)}
              >
                Whole packs
              </button>
            </div>
          </section>

          {/* Colors */}
          <section className={`${CARD} order-3`}>
            <h2 className={CARD_TITLE}>
              <Palette size={15} className="text-emerald-700" />
              Colors
            </h2>
            <div className="flex flex-col gap-2.5">
              <p className="text-xs text-stone-500">Ornaments, by number on the mockup</p>
              {usedColors.map((c, i) => (
                <ColorField
                  key={i}
                  label={`Color ${i + 1}`}
                  value={c}
                  onChange={(hex) => setColors((list) => list.map((x, j) => (j === i ? hex : x)))}
                />
              ))}
              <p className="mt-2 text-xs text-stone-500">Enhancer ribbons and the topper</p>
              <ColorField label="Ribbon A" value={ribbonA} onChange={setRibbonA} />
              <ColorField label="Ribbon B" value={ribbonB} onChange={setRibbonB} />
              <ColorField label="Topper" value={topper} onChange={setTopper} />
            </div>
          </section>

          {/* Counts */}
          <section className={`${CARD} order-4`}>
            <h2 className={CARD_TITLE}>
              <ListChecks size={15} className="text-emerald-700" />
              Counts
            </h2>
            {!counts ? (
              <p className="text-sm text-stone-500">Enter the tree size to get its counts.</p>
            ) : (
              <>
                <p className="mb-3 text-xs text-stone-500">
                  From the Ornament Calculator&apos;s Leaf &amp; Ledger rules for a {treeLabel} {style} tree with{" "}
                  {colorCount} {colorCount === 1 ? "color" : "colors"}
                  {wholePacks ? ", rounded to whole packs" : ""}.
                </p>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-stone-200 text-left text-[11px] uppercase tracking-wide text-stone-500">
                        <th className="py-2 pr-2 font-semibold">Piece</th>
                        <th className="whitespace-nowrap px-2 py-2 text-right font-semibold">On tree</th>
                        <th className="whitespace-nowrap px-2 py-2 text-right font-semibold">In bows</th>
                        <th className="py-2 pl-2 text-right font-semibold">Total</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr className="border-b border-stone-100 align-top">
                        <td className="py-2 pr-2">
                          <div className="font-semibold text-stone-800">Enhancers</div>
                          <div className="text-xs text-stone-500">
                            {BOW_IN}&quot; ribbon bows: {enhancersA} A, {enhancersB} B
                          </div>
                        </td>
                        <td className="px-2 py-2 text-right tabular-nums text-stone-700">{counts.enhancers}</td>
                        <td className="px-2 py-2 text-right text-stone-400"> </td>
                        <td className="py-2 pl-2 text-right font-bold tabular-nums text-stone-800">{counts.enhancers}</td>
                      </tr>
                      {[...counts.lines]
                        .sort((a, b) => b.option.size - a.option.size)
                        .map((line) => {
                          const split = colorCount > 1 ? splitAcrossColors(line.loose, colorCount) : [];
                          const placed = placedBySize.get(line.option.size) ?? 0;
                          const short = layout && !stale && placed < line.loose;
                          return (
                            <tr key={line.option.size} className="border-b border-stone-100 align-top">
                              <td className="py-2 pr-2">
                                <div className="font-semibold text-stone-800">{line.option.display}&quot; ornaments</div>
                                {split.length > 0 && (
                                  <div className="flex flex-wrap gap-1 pt-0.5">
                                    {split.map((n, i) => (
                                      <span
                                        key={i}
                                        className="inline-flex items-center gap-1 rounded bg-stone-100 px-1.5 text-[11px] text-stone-500"
                                      >
                                        <span
                                          className="inline-block h-2 w-2 rounded-full border border-stone-300"
                                          style={{ backgroundColor: usedColors[i] }}
                                        />
                                        {i + 1}: {n}
                                      </span>
                                    ))}
                                  </div>
                                )}
                                {short && (
                                  <div className="pt-0.5 text-[11px] font-semibold text-amber-700">
                                    {placed} of {line.loose} fit on the mockup
                                  </div>
                                )}
                              </td>
                              <td className="px-2 py-2 text-right tabular-nums text-stone-700">{line.loose}</td>
                              <td className="px-2 py-2 text-right tabular-nums text-stone-500">{line.inEnhancers || ""}</td>
                              <td className="py-2 pl-2 text-right font-bold tabular-nums text-stone-800">{line.quantity}</td>
                            </tr>
                          );
                        })}
                      <tr className="text-stone-800">
                        <td className="py-2 pr-2 font-semibold">All ornaments</td>
                        <td className="px-2 py-2 text-right font-semibold tabular-nums">{looseTotal}</td>
                        <td className="px-2 py-2 text-right font-semibold tabular-nums">{insideTotal || ""}</td>
                        <td className="py-2 pl-2 text-right font-bold tabular-nums">{counts.totalOrnaments}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                {layout && !stale && (
                  <div
                    className={`mt-4 rounded-lg border px-3 py-2.5 text-sm ${
                      layout.fits
                        ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                        : "border-amber-200 bg-amber-50 text-amber-800"
                    }`}
                  >
                    {layout.fits ? (
                      <div className="flex items-start gap-2">
                        <CheckCircle2 size={15} className="mt-0.5 shrink-0" />
                        <div className="space-y-1">
                          <p>
                            Everything fits: {placedBows} bows and {layout.check.placed} loose ornaments at true size,
                            nestled into the branches, none on the same spot and no color touching itself.
                          </p>
                          {layout.note && <p className="text-xs">{layout.note}</p>}
                        </div>
                      </div>
                    ) : (
                      <div className="flex items-start gap-2">
                        <AlertTriangle size={15} className="mt-0.5 shrink-0" />
                        <div className="space-y-1">
                          <p className="font-semibold">This tree can&apos;t show everything by the rules.</p>
                          {layout.problems.map((p) => (
                            <p key={p}>{p}</p>
                          ))}
                          {layout.note && <p className="text-xs">{layout.note}</p>}
                          <p className="text-xs">
                            The counts above are still the calculator&apos;s. The mockup only shows what fits on the
                            tree&apos;s surface.
                          </p>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </>
            )}
          </section>

          </div>
          <div className="contents xl:flex xl:flex-col xl:gap-6">
          {/* The 3D mockup */}
          <section className={`${CARD} order-2 !p-0 overflow-hidden xl:sticky xl:top-[96px]`}>
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-stone-200 px-4 py-3 sm:px-5">
              <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-stone-600">
                <Shrub size={15} className="text-emerald-700" />
                3D mockup{treeLabel ? `: ${treeLabel}` : ""}
              </h2>
              <div className="flex flex-wrap gap-1.5" role="group" aria-label="Camera views">
                {(["front", "side", "back", "top"] as TreeView[]).map((name) => (
                  <button
                    key={name}
                    type="button"
                    onClick={() => jump(name)}
                    disabled={!layout}
                    className="min-h-[36px] rounded-lg border border-stone-300 bg-white px-3 text-xs font-semibold capitalize text-stone-600 transition-colors hover:bg-stone-100 disabled:opacity-40"
                  >
                    {name}
                  </button>
                ))}
                <button
                  type="button"
                  onClick={() => setSpin(!spin)}
                  aria-pressed={spin}
                  disabled={!layout}
                  className={`${pillButton(spin)} !min-h-[36px]`}
                >
                  <Play size={12} />
                  Spin
                </button>
              </div>
            </div>
            <div className="relative h-[460px] bg-stone-100 sm:h-[560px] xl:h-[min(72vh,760px)]">
              {layout && (
                <Suspense fallback={null}>
                  <TreeInstall3D
                    layout={layout}
                    colors={usedColors}
                    ribbonA={ribbonA}
                    ribbonB={ribbonB}
                    topper={topper}
                    showLabels={showLabels}
                    showLines={showLines}
                    rowsShown={rowsShown}
                    spin={spin}
                    onSpinChange={setSpin}
                    view={view}
                  />
                </Suspense>
              )}
              {(stale || !dimsValid) && (
                <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
                  <span className="flex items-center gap-2 rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm text-stone-600 shadow-sm">
                    {dimsValid ? (
                      <>
                        <Loader2 size={14} className="animate-spin" />
                        Placing every piece...
                      </>
                    ) : (
                      "Enter the tree size to see it."
                    )}
                  </span>
                </div>
              )}
              <p className="pointer-events-none absolute bottom-2 left-3 rounded-md bg-white/80 px-2 py-1 text-[11px] text-stone-500">
                Drag to turn. Pinch or scroll to zoom.
              </p>
            </div>
            <div className="grid gap-4 border-t border-stone-200 px-4 py-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:px-5">
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-semibold text-stone-600">Build it row by row</span>
                <input
                  type="range"
                  min={0}
                  max={layout?.rows ?? 1}
                  value={rowsShown}
                  disabled={!layout}
                  onChange={(e) => setRows(Number(e.target.value))}
                  className="h-10 w-full accent-emerald-700"
                  aria-valuetext={
                    layout ? (rowsShown === 0 ? "Topper only" : `Rows 1 to ${rowsShown} of ${layout.rows}`) : undefined
                  }
                />
                <span className="text-xs text-stone-500">
                  {!layout
                    ? " "
                    : rowsShown === 0
                    ? "Topper only"
                    : rowsShown >= layout.rows
                    ? `All ${layout.rows} rows and the topper, top down`
                    : `Topper and rows 1 to ${rowsShown} of ${layout.rows} (6 in each)`}
                </span>
              </label>
              <div className="flex flex-wrap items-start gap-2">
                <button
                  type="button"
                  onClick={() => setShowLabels(!showLabels)}
                  aria-pressed={showLabels}
                  className={pillButton(showLabels)}
                >
                  {showLabels ? <Eye size={13} /> : <EyeOff size={13} />}
                  Numbers and letters
                </button>
                <button
                  type="button"
                  onClick={() => setShowLines(!showLines)}
                  aria-pressed={showLines}
                  className={pillButton(showLines)}
                >
                  <Spline size={13} />
                  Swirl lines
                </button>
              </div>
            </div>
          </section>

          {/* How to place it */}
          <section className={`${CARD} order-5`}>
            <h2 className={CARD_TITLE}>
              <ListChecks size={15} className="text-emerald-700" />
              How to place it
            </h2>
            <ol className="list-decimal space-y-1.5 pl-5 text-sm text-stone-700">
              <li>Topper first. Its spray and bow fill the top and come down; no bows up there, the tree is too skinny.</li>
              <li>Six swirl lines start at the tip, all turning the same way, evenly spaced.</li>
              <li>Bows sit on the lines, hanging diagonally down them: A, B, A, B. Every other line sits half a step lower.</li>
              <li>Ornaments fill in around them, nestled into the branches. Touching is fine; two on the same spot is not.</li>
              <li>No color touches itself.</li>
              <li>Big ornaments (8&quot; and up) go in the middle and bottom only, never the top third.</li>
              <li>Every side looks the same. Spin it to check.</li>
            </ol>
          </section>
          </div>
        </div>
      </div>
    </Layout>
  );
}
