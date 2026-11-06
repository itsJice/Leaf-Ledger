import React, { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowLeft, Loader2, Printer } from "components/icons";
import { useTreeLayout } from "components/useTreeLayout";
import { clampColorCount, type DesignStyle } from "utils/ornamentRecipe";
import type { TreeSheet as Sheet } from "utils/treeInstallPrint";
import {
  treeInstallCounts,
  type LayoutItem,
  type TreeInstallLayout,
  type TreeInstallLayoutInput,
} from "utils/treeInstallLayout";

// The Tree Install printouts, for the tree picked on /tree-install:
//   ?sheet=design  the 2-page Tree Design Map (front view + all the way around)
//   ?sheet=cone    the paper cone model (one cut, glue flap, marks 1-5)
// Ported from tree-design-map/oneway/print.html and cone.html (git d0e15dd). No
// app chrome around it, so the browser's print prints just the sheet.

const INK = "#17241c";
const MUTED = "#5b675f";
const PINE = "#2f5d43";
const TREEFILL = "#e9f1ea";
const ENH = "#4b2f6b";

const hex = (v: string | null, fallback: string) => (v && /^[0-9a-f]{6}$/i.test(v) ? `#${v}` : fallback);

/** A darker shade of a color, for outlines. */
function darken(color: string, k = 0.45): string {
  const n = parseInt(color.slice(1), 16);
  const ch = (shift: number) => Math.round(((n >> shift) & 255) * (1 - k));
  return `rgb(${ch(16)}, ${ch(8)}, ${ch(0)})`;
}

/** Light or dark text on a color. */
function textOn(color: string): string {
  const n = parseInt(color.slice(1), 16);
  const l = 0.299 * ((n >> 16) & 255) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255);
  return l > 170 ? INK : "#fff";
}

interface Palette {
  colors: string[];
  A: string;
  B: string;
  topper: string;
}

// --- the drawings (print.html / cone.html) ---------------------------------------

function Orn({ x, y, r, c, pal }: { x: number; y: number; r: number; c: number; pal: Palette }) {
  const fill = pal.colors[c - 1] ?? "#999";
  return (
    <g>
      <circle cx={x} cy={y} r={r} fill={fill} stroke={INK} strokeWidth={1.2} />
      <text x={x} y={y + r * 0.36} textAnchor="middle" fontSize={r * 1.05} fontWeight={800} fill={textOn(fill)}>
        {c}
      </text>
    </g>
  );
}

/**
 * An enhancer: a layered ribbon bow with tails, a ball in the middle, a pick and
 * small balls tucked in. s0 = half its width; rot = degrees it hangs off vertical.
 */
function Bow({ x, y, s0, letter, rot = 0, pal }: { x: number; y: number; s0: number; letter: string; rot?: number; pal: Palette }) {
  const fill = letter === "B" ? pal.B : pal.A;
  const c = { fill, dark: darken(fill), ribbon: letter === "B" ? pal.A : pal.B };
  const s = s0 * 0.74; // the whole drawing (wings, tails) fits inside its real footprint
  const kb = Math.max(7, s * 0.3);
  return (
    <g transform={`translate(${x} ${y}) rotate(${rot}) translate(0 ${-s * 0.12})`}>
      {[-1, 1].map((sx) => (
        <g key={`t${sx}`}>
          <path
            d={`M${sx * s * 0.06} ${s * 0.05} L${sx * s * 0.5} ${s * 1.25} L${sx * s * 0.3} ${s * 1.08} L${sx * s * 0.18} ${s * 1.3} Z`}
            fill={c.fill}
            stroke={c.dark}
            strokeWidth={1}
          />
          <path d={`M${sx * s * 0.05} ${s * 0.05} L${sx * s * 0.16} ${s * 1.15}`} stroke={c.ribbon} strokeWidth={Math.max(1, s * 0.07)} fill="none" />
        </g>
      ))}
      {[-150, -30, -95].map((a) => {
        const r = (a * Math.PI) / 180;
        const cx = Math.cos(r) * s * 0.62;
        const cy = Math.sin(r) * s * 0.5;
        return <ellipse key={a} cx={cx} cy={cy} rx={s * 0.32} ry={s * 0.11} transform={`rotate(${a} ${cx} ${cy})`} fill="#b9a26a" stroke="#7d6a3a" strokeWidth={0.8} />;
      })}
      {[-1, 1].map((sx) => (
        <g key={`l${sx}`}>
          <ellipse cx={sx * s * 0.5} cy={-s * 0.08} rx={s * 0.5} ry={s * 0.3} transform={`rotate(${sx * -18} ${sx * s * 0.5} ${-s * 0.08})`} fill={c.fill} stroke={c.dark} strokeWidth={1.1} />
          <ellipse
            cx={sx * s * 0.42}
            cy={-s * 0.05}
            rx={s * 0.3}
            ry={s * 0.15}
            transform={`rotate(${sx * -18} ${sx * s * 0.42} ${-s * 0.05})`}
            fill="none"
            stroke={c.ribbon}
            strokeWidth={Math.max(1, s * 0.08)}
          />
        </g>
      ))}
      <circle cx={-s * 0.3} cy={s * 0.3} r={s * 0.14} fill="#e8dcc0" stroke="#8a7a50" strokeWidth={0.8} />
      <circle cx={s * 0.32} cy={s * 0.28} r={s * 0.12} fill="#e8dcc0" stroke="#8a7a50" strokeWidth={0.8} />
      <circle cx={0} cy={s * 0.02} r={kb} fill="#f3ecdc" stroke={c.dark} strokeWidth={1.4} />
      <circle cx={-kb * 0.35} cy={s * 0.02 - kb * 0.35} r={kb * 0.25} fill="#fff" opacity={0.7} />
      {/* the letter stays upright */}
      <text x={0} y={s * 0.02 + kb * 0.38} textAnchor="middle" fontSize={kb * 1.1} fontWeight={800} fill={c.dark} transform={`rotate(${-rot} 0 ${s * 0.02})`}>
        {letter}
      </text>
    </g>
  );
}

/** The topper: a spray with a ribbon bow. */
function Topper({ x, y, r, pal }: { x: number; y: number; r: number; pal: Palette }) {
  return (
    <g transform={`translate(${x} ${y})`}>
      {[-90, -62, -118, -40, -140, -76, -104].map((a) => {
        const rr = (a * Math.PI) / 180;
        const len = r * (Math.abs(a + 90) < 20 ? 1.25 : 0.95);
        const cx = Math.cos(rr) * len * 0.5;
        const cy = Math.sin(rr) * len * 0.5;
        return <ellipse key={a} cx={cx} cy={cy} rx={len * 0.5} ry={r * 0.09} transform={`rotate(${a} ${cx} ${cy})`} fill={pal.topper} stroke={darken(pal.topper)} strokeWidth={0.9} />;
      })}
      <Bow x={0} y={r * 0.1} s0={r * 0.55} letter="A" pal={pal} />
    </g>
  );
}

const LINK = { stroke: ENH, strokeWidth: 2, strokeOpacity: 0.45, strokeDasharray: "5 5", fill: "none" } as const;

// --- page 1 and 2: the Tree Design Map -------------------------------------------

function FrontView({ L, pal }: { L: TreeInstallLayout; pal: Palette }) {
  const H = 560;
  const top = 56;
  const cx = 260;
  const R = L.R * H;
  const pos = (it: { t: number; ang: number }) => [cx + it.t * R * Math.sin(it.ang), top + it.t * H];
  const show = (it: LayoutItem) => Math.cos(it.ang) > 0.62;
  const vis = L.items.filter(show).sort((a, b) => Math.cos(a.ang) - Math.cos(b.ang));
  const lineSegs: string[] = [];
  for (const ln of L.lines) {
    let seg: string[] = [];
    const flush = () => {
      if (seg.length > 1) lineSegs.push(seg.join(" "));
      seg = [];
    };
    for (const [t, ang] of ln.pts) {
      if (Math.cos(ang) > 0.2) {
        const q = pos({ t, ang });
        seg.push(`${q[0].toFixed(1)},${q[1].toFixed(1)}`);
      } else flush();
    }
    flush();
  }
  return (
    <svg viewBox="0 0 520 640" preserveAspectRatio="xMidYMid meet" style={{ width: "100%", height: "100%" }}>
      <path d={`M${cx} ${top} L${cx + R * 1.08} ${top + H} L${cx - R * 1.08} ${top + H} Z`} fill={TREEFILL} stroke={PINE} strokeWidth={2} strokeLinejoin="round" />
      <rect x={cx - 20} y={top + H} width={40} height={26} fill="#8a6a4a" />
      {lineSegs.map((p, i) => (
        <polyline key={i} points={p} {...LINK} />
      ))}
      {vis.map((it, i) => {
        if (it.kind !== "orn") return null;
        const [x, y] = pos(it);
        return <Orn key={`o${i}`} x={x} y={y} r={(it.gap * H) / 2} c={it.color} pal={pal} />;
      })}
      {vis.map((it, i) => {
        if (it.kind !== "enh") return null;
        const [x, y] = pos(it);
        return <Bow key={`e${i}`} x={x} y={y} s0={(it.gap * H) / 2} letter={it.letter} rot={-(it.tilt || 0)} pal={pal} />;
      })}
      <Topper x={cx} y={top - 2} r={30} pal={pal} />
      <text x={cx + 34} y={top - 2} fontSize={13} fontWeight={700} fill={MUTED}>
        Topper
      </text>
    </svg>
  );
}

function AroundView({ L, pal }: { L: TreeInstallLayout; pal: Palette }) {
  const W = 660;
  const x0 = 74;
  const y0 = 40;
  const Hh = 640;
  const T0 = 0.1;
  const T1 = 0.97;
  const ft = L.tree.heightFt;
  const yOfT = (t: number) => y0 + ((t - T0) / (T1 - T0)) * Hh;
  const xOf = (ang: number) => x0 + ((((ang + Math.PI) % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI)) / (2 * Math.PI) * W;
  const feet: number[] = [];
  for (let f = Math.ceil(ft * (1 - T1)); f <= Math.floor(ft * (1 - T0)); f++) feet.push(f);
  const labels: [string, number][] = [
    ["Back", 0],
    ["Left side", 0.25],
    ["FRONT", 0.5],
    ["Right side", 0.75],
    ["Back", 1],
  ];
  const lineSegs: string[] = [];
  for (const ln of L.lines) {
    let seg: string[] = [];
    let px: number | null = null;
    const flush = () => {
      if (seg.length > 1) lineSegs.push(seg.join(" "));
      seg = [];
    };
    for (const [t, ang] of ln.pts) {
      const x = xOf(ang);
      const y = yOfT(t);
      if (px !== null && Math.abs(x - px) > W / 2) flush();
      px = x;
      seg.push(`${x.toFixed(1)},${y.toFixed(1)}`);
    }
    flush();
  }
  // ball sizes on the unrolled map (print.html's, plus the sizes other trees use)
  const RS: Record<number, number> = { 15.75: 18, 12: 15.5, 10: 14, 8: 12, 6: 10, 4.75: 8.5, 4: 7.5, 3: 6.5 };
  return (
    <svg viewBox="0 0 760 680" preserveAspectRatio="xMidYMin meet" style={{ width: "100%", flex: 1, minHeight: 0 }}>
      {feet.map((f) => {
        const y = yOfT(1 - f / ft);
        return (
          <g key={f}>
            <line x1={x0} y1={y} x2={x0 + W} y2={y} stroke="#dfe7e1" />
            <text x={x0 - 10} y={y + 4} textAnchor="end" fontSize={11} fontWeight={700} fill={MUTED}>
              {f} ft
            </text>
          </g>
        );
      })}
      {labels.map(([t, f], i) => (
        <g key={i}>
          <text x={x0 + f * W} y={22} textAnchor="middle" fontSize={12} fontWeight={800} fill={t === "FRONT" ? PINE : MUTED}>
            {t}
          </text>
          <line x1={x0 + f * W} y1={28} x2={x0 + f * W} y2={y0 + Hh} stroke="#d5ddd7" strokeDasharray="3 4" />
        </g>
      ))}
      {lineSegs.map((p, i) => (
        <polyline key={i} points={p} {...LINK} />
      ))}
      {L.items.map((it, i) =>
        it.kind === "orn" ? <Orn key={`o${i}`} x={xOf(it.ang)} y={yOfT(it.t)} r={RS[it.inch] ?? 5 + it.inch * 0.9} c={it.color} pal={pal} /> : null
      )}
      {L.items.map((it, i) =>
        it.kind === "enh" ? <Bow key={`e${i}`} x={xOf(it.ang)} y={yOfT(it.t)} s0={17} letter={it.letter} rot={-(it.tilt || 0)} pal={pal} /> : null
      )}
    </svg>
  );
}

const pageStyle: React.CSSProperties = {
  width: "7.6in",
  height: "10.05in",
  display: "flex",
  flexDirection: "column",
  gap: 10,
  overflow: "hidden",
  background: "#fff",
  color: INK,
  fontFamily: '"Nunito Sans", Arial, sans-serif',
};
const h1Style: React.CSSProperties = { fontFamily: "Sora, Arial, sans-serif", fontSize: "22pt", margin: 0, letterSpacing: "-0.01em", color: INK };
const box: React.CSSProperties = { border: "1px solid #cfd8d1", borderRadius: 6, padding: "6px 8px" };

function SheetHeader({ title, sub }: { title: string; sub: string }) {
  return (
    <header style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", borderBottom: `2px solid ${PINE}`, paddingBottom: 6 }}>
      <div>
        <h1 style={h1Style}>{title}</h1>
        <div style={{ color: MUTED, fontSize: "10pt" }}>{sub}</div>
      </div>
      <div style={{ fontFamily: "Sora, Arial, sans-serif", fontSize: "9pt", color: PINE, textAlign: "right", lineHeight: 1.3 }}>
        The Branch Design Group
        <br />
        Christmas design training
      </div>
    </header>
  );
}

function DesignSheet({ L, pal, label, sizes, counts }: { L: TreeInstallLayout; pal: Palette; label: string; sizes: number[]; counts: ReturnType<typeof treeInstallCounts> }) {
  const orn = L.items.filter((i) => i.kind === "orn");
  const inside = Object.entries(counts.inEnhancers).sort((a, b) => Number(b[0]) - Number(a[0]));
  const fillRows: [string, string][] = Array.from({ length: Math.max(3, counts.colorCount) }, (_, i) => [
    i < counts.colorCount ? `Color ${i + 1}:` : "",
    ["Enhancer A:", "Enhancer B:", "Topper:", ""][i] ?? "",
  ]);
  return (
    <>
      <section className="tree-sheet-page" style={pageStyle}>
        <SheetHeader title="Tree Design Map: One-Way Swirl" sub="Where every ornament, enhancer and the topper goes · front view" />
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8, fontSize: "9pt" }}>
          <div style={{ ...box, display: "flex", flexDirection: "column", gap: 4 }}>
            <b>Numbers = ornament colors</b>
            <svg width={28 * counts.colorCount} height={28}>
              {Array.from({ length: counts.colorCount }, (_, i) => (
                <Orn key={i} x={14 + i * 28} y={14} r={11} c={i + 1} pal={pal} />
              ))}
            </svg>
          </div>
          <div style={{ ...box, display: "flex", flexDirection: "column", gap: 4 }}>
            <b>Circle size = ornament size</b>
            <div style={{ display: "flex", alignItems: "center", gap: "2px 4px", flexWrap: "wrap" }}>
              {sizes.map((k) => (
                <span key={k} style={{ display: "inline-flex", alignItems: "center", gap: 2 }}>
                  <svg width={28} height={28}>
                    <circle cx={14} cy={14} r={Math.min(13, k * 1.2)} fill="#fff" stroke={INK} strokeWidth={1.2} />
                  </svg>
                  {k}&quot;
                </span>
              ))}
            </div>
          </div>
          <div style={{ ...box, display: "flex", flexDirection: "column", gap: 4 }}>
            <b>Bows = enhancers</b>
            <svg width={80} height={28}>
              <Bow x={20} y={12} s0={15} letter="A" pal={pal} />
              <Bow x={60} y={12} s0={15} letter="B" pal={pal} />
            </svg>
            <span style={{ fontSize: "8pt" }}>bow + pick + small balls · dashed = swirl line</span>
          </div>
          <div style={{ ...box, display: "flex", flexDirection: "column", gap: 4 }}>
            <b>Spray = tree topper</b>
            <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <svg width={32} height={28}>
                <Topper x={16} y={20} r={14} pal={pal} />
              </svg>
              at the very tip
            </span>
          </div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px 18px", fontSize: "9.5pt" }}>
          <div>
            Client / tree: <span style={{ borderBottom: "1px solid #999", display: "block", paddingTop: 10 }} />
          </div>
          <div>Tree: {label}</div>
          {fillRows.map(([l, r], i) => (
            <React.Fragment key={i}>
              <div>{l && <>{l} <span style={{ borderBottom: "1px solid #999", display: "block", paddingTop: 10 }} /></>}</div>
              <div>{r && <>{r} <span style={{ borderBottom: "1px solid #999", display: "block", paddingTop: 10 }} /></>}</div>
            </React.Fragment>
          ))}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 2.25in", gridTemplateRows: "minmax(0, 1fr)", gap: 12, flex: 1, minHeight: 0, overflow: "hidden" }}>
          <FrontView L={L} pal={pal} />
          <div style={{ fontSize: "9pt", lineHeight: 1.3, minHeight: 0, overflow: "hidden" }}>
            <div style={{ ...box, marginBottom: 8, fontSize: "8.5pt" }}>
              <b>For this tree</b> (Ornament Calculator, {counts.colorCount} {counts.colorCount === 1 ? "color" : "colors"})
              <br />
              <b>{L.check.A + L.check.B} enhancers</b>: {L.check.A} A, {L.check.B} B
              <br />
              <b>{orn.length} ornaments</b> on the tree
              {counts.colorCount > 1
                ? L.check.colors.every((n) => n === L.check.colors[0])
                  ? `, ${L.check.colors[0]} of each color`
                  : `, by color ${L.check.colors.join(" / ")}`
                : ""}
              :
              <br />
              {sizes.map((s) => `${s}" × ${counts.loose[s] ?? 0}`).join(" · ")}
              {inside.length > 0 && (
                <>
                  <br />
                  <span style={{ color: MUTED }}>Plus {inside.map(([s, n]) => `${n} × ${s}"`).join(" and ")} inside the enhancers.</span>
                </>
              )}
            </div>
            <h2 style={{ fontFamily: "Sora, Arial, sans-serif", fontSize: "11pt", margin: "0 0 6px" }}>How to place it</h2>
            <ol style={{ margin: 0, paddingLeft: 18, display: "flex", flexDirection: "column", gap: 4 }}>
              <li>
                <b>Topper first.</b> Its spray and bow fill the top and come down. No bows up there; the tree is too skinny.
              </li>
              <li>
                <b>Six swirl lines</b> (dashed) all turn the same way, evenly spaced like a candy cane.
              </li>
              <li>
                <b>Every other line sits half a step lower,</b> so bows on neighboring lines make triangles.
              </li>
              <li>
                <b>Ornaments fill in between the bows,</b> set <i>into</i> the branches. Touching is fine; never two on one spot.
              </li>
              <li>
                <b>Bows sit on the lines: A, B, A, B,</b> hung on a diagonal, tails trailing down the line. Half are A, half B.
              </li>
              <li>
                <b>Never two of the same color touching.</b>
              </li>
              <li>
                <b>Large ornaments middle and bottom only,</b> never in the top third.
              </li>
              <li>
                <b>Keep going around the back.</b> Page 2 shows the whole way around.
              </li>
            </ol>
          </div>
        </div>
        <div style={{ fontSize: "8pt", color: MUTED, display: "flex", justifyContent: "space-between" }}>
          <span>The front face of the tree. Everything around the sides and back is on page 2.</span>
          <span>Page 1 of 2</span>
        </div>
      </section>
      <section className="tree-sheet-page" style={pageStyle}>
        <SheetHeader title="All the Way Around" sub="The same pattern unrolled: read each row left to right as you walk around the tree" />
        <AroundView L={L} pal={pal} />
        <div style={{ fontSize: "9.5pt", lineHeight: 1.35 }}>
          <b>How to read it:</b> the whole tree unrolled flat, tip at the top, floor at the bottom, heights in feet. The middle is the front. Walk right
          and you reach the right side, then the back, then come around the left side to the front again. The right edge of a row joins the left edge,
          so the pattern never breaks.
        </div>
        <div style={{ fontSize: "8pt", color: MUTED, display: "flex", justifyContent: "space-between" }}>
          <span>Dashed lines are the enhancer swirl lines. The top has fewer pieces because the tree is narrower there.</span>
          <span>Page 2 of 2</span>
        </div>
      </section>
    </>
  );
}

// --- the paper cone model (cone.html + fan-geo.js) ----------------------------------

/** Glue flap (13°), tuck line, marks 1-5 and the approved 9 ft page geometry (fan-geo.js). */
const FLAP = (13 * Math.PI) / 180;
const ALPHA = FLAP / 2;
const MARKS = [0.3, 0.45, 0.6, 0.75, 0.9];

function ConeSheet({ L, pal, label, sizes }: { L: TreeInstallLayout; pal: Palette; label: string; sizes: number[] }) {
  // The tree's side unrolls into a fan this many radians wide: about 90° for the
  // approved 9 ft x 56 in (fan-geo.js's TH), narrower for slim trees, wider for full.
  const TH = (2 * Math.PI * L.R) / Math.hypot(1, L.R);
  // fan-geo.js's page placement (tip at 84,84, 7.12 in slant) whenever it fits the
  // page; otherwise the fan is shrunk and moved to fit.
  const fitsAt = (tip: [number, number], len: number) => {
    for (let i = 0; i <= 40; i++) {
      const a = ALPHA - FLAP + ((TH + FLAP) * i) / 40;
      const x = tip[0] + len * Math.cos(a);
      const y = tip[1] + len * Math.sin(a);
      // fan-geo.js's own 9 ft fan reaches a hair past the left edge, into the margin
      if (x < -12 || x > 800 || y < 0 || y > 820) return false;
    }
    return true;
  };
  let TIP: [number, number] = [84, 84];
  let LEN = 712;
  if (!fitsAt(TIP, LEN)) {
    // bounding box of the fan (tip included) at a 1-unit radius
    let minX = 0;
    let maxX = 0;
    let minY = 0;
    let maxY = 0;
    for (let i = 0; i <= 80; i++) {
      const a = ALPHA - FLAP + ((TH + FLAP) * i) / 80;
      minX = Math.min(minX, Math.cos(a));
      maxX = Math.max(maxX, Math.cos(a));
      minY = Math.min(minY, Math.sin(a));
      maxY = Math.max(maxY, Math.sin(a));
    }
    // room for the cut label outside the curve
    LEN = Math.min(712, 740 / (maxX - minX), 760 / (maxY - minY));
    TIP = [20 - minX * LEN, 30 - minY * LEN];
  }
  const P = (s: number, a: number): [number, number] => [TIP[0] + s * Math.cos(a), TIP[1] + s * Math.sin(a)];
  const f2 = (v: [number, number]) => v.map((x) => x.toFixed(1)).join(" ");
  const fan = `M${TIP[0]} ${TIP[1]} L${f2(P(LEN, ALPHA - FLAP))} A${LEN} ${LEN} 0 0 1 ${f2(P(LEN, ALPHA + TH))} Z`;
  const trueR = (it: LayoutItem) => (it.gap * LEN) / Math.hypot(1, L.R) / 2; // true size on the fan
  const around = (ang: number) => ((((ang + Math.PI) % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI)) / (2 * Math.PI);
  // rolled print side out, going around runs the other way across the paper: mirrored
  const fanAng = (ang: number) => ALPHA + (1 - around(ang)) * TH;
  const perp = (a: number) => [-Math.sin(a), Math.cos(a)];
  const rot = (a: number) => ((a * 180) / Math.PI - 90).toFixed(1);

  const lineEls: React.ReactNode[] = [];
  L.lines.forEach((ln, li) => {
    for (const sh of [0, TH, -TH]) {
      let seg: string[] = [];
      let prev: number | null = null;
      const flush = () => {
        if (seg.length > 1)
          lineEls.push(<polyline key={`${li}-${sh}-${lineEls.length}`} points={seg.join(" ")} fill="none" stroke={ENH} strokeWidth={2} strokeOpacity={0.5} strokeDasharray="6 5" />);
        seg = [];
      };
      for (const [t, ang] of ln.pts) {
        const a = fanAng(ang);
        if (prev !== null && Math.abs(a - prev) > TH / 2) flush();
        prev = a;
        const p = P(t * LEN, a + sh);
        seg.push(`${p[0].toFixed(1)},${p[1].toFixed(1)}`);
      }
      flush();
    }
  });
  const pieceEls: React.ReactNode[] = [];
  const draw = (it: LayoutItem, a: number, key: string) => {
    const [x, y] = P(it.t * LEN, a);
    const r = trueR(it);
    pieceEls.push(
      <g key={key} transform={`translate(${x.toFixed(1)} ${y.toFixed(1)}) rotate(${((a * 180) / Math.PI - 90).toFixed(1)})`}>
        {it.kind === "orn" ? (
          <>
            <circle r={r} fill={pal.colors[it.color - 1] ?? "#999"} stroke={INK} strokeWidth={1.2} />
            <text y={r * 0.38} textAnchor="middle" fontSize={Math.max(13, r * 1.1)} fontWeight={800} fill={textOn(pal.colors[it.color - 1] ?? "#999999")}>
              {it.color}
            </text>
          </>
        ) : (
          <Bow x={0} y={0} s0={r} letter={it.letter} rot={-(it.tilt || 0)} pal={pal} />
        )}
      </g>
    );
  };
  [...L.items]
    .sort((a, b) => Number(a.kind === "enh") - Number(b.kind === "enh"))
    .forEach((it, i) => {
      const a = fanAng(it.ang);
      const m = (1.3 * trueR(it)) / Math.max(20, it.t * LEN);
      draw(it, a, `p${i}`);
      if (a < ALPHA + m) draw(it, a + TH, `p${i}+`); // half pieces at the outside edge
      if (a > ALPHA + TH - FLAP - m) draw(it, a - TH, `p${i}-`); // the glue flap repeats the start of the pattern
    });
  const mid = ALPHA + TH / 2;
  const sc = P(LEN + 16, mid - 0.09);
  const fr = P(LEN + 40, mid + 0.09);
  const flapLabel = P(LEN * 0.16, ALPHA - FLAP * 0.5);
  const tuck = P(LEN, ALPHA);
  const o = perp(ALPHA);
  const tuckLabel = P(LEN * 0.33, ALPHA);
  const scale = (L.slantIn / (LEN / 100)).toFixed(1);
  return (
    <section className="tree-sheet-page tree-sheet-cone" style={{ background: "#fff", color: INK, fontFamily: '"Nunito Sans", Arial, sans-serif' }}>
      <svg viewBox="0 0 800 1045" style={{ display: "block", width: "8in", height: "10.45in" }}>
        <defs>
          <clipPath id="tree-fan-clip">
            <path d={fan} />
          </clipPath>
        </defs>
        <path d={fan} fill="#e3eee5" />
        <g clipPath="url(#tree-fan-clip)">
          {lineEls}
          {pieceEls}
        </g>
        {/* glue flap: shaded, with its label */}
        <path d={`M${TIP[0]} ${TIP[1]} L${f2(P(LEN, ALPHA - FLAP))} A${LEN} ${LEN} 0 0 1 ${f2(P(LEN, ALPHA))} Z`} fill="#fff" fillOpacity={0.5} />
        <text
          x={flapLabel[0]}
          y={flapLabel[1] + 4}
          textAnchor="middle"
          fontSize={11}
          fontWeight={800}
          fill={INK}
          fillOpacity={0.8}
          transform={`rotate(${(((ALPHA - FLAP * 0.5) * 180) / Math.PI).toFixed(1)} ${flapLabel[0]} ${flapLabel[1]})`}
        >
          GLUE FLAP (goes under)
        </text>
        {/* the tuck line: the other straight edge comes to rest exactly here */}
        <line x1={TIP[0] - o[0] * 0.9} y1={TIP[1] - o[1] * 0.9} x2={tuck[0] - o[0] * 0.9} y2={tuck[1] - o[1] * 0.9} stroke={INK} strokeWidth={1.6} strokeDasharray="9 6" />
        <text x={tuckLabel[0] + 8} y={tuckLabel[1] - 5} fontSize={12} fontWeight={800} fill={INK} transform={`rotate(${((ALPHA * 180) / Math.PI).toFixed(1)} ${tuckLabel[0]} ${tuckLabel[1]})`}>
          tuck to here ▸
        </text>
        {/* numbered alignment marks, the same distance from the tip on both edges */}
        {MARKS.map((m, i) => {
          const s = m * LEN;
          const n = String(i + 1);
          const a1 = ALPHA;
          const o1 = P(s, a1);
          const d1 = perp(a1);
          const c1 = [o1[0] - d1[0] * 30, o1[1] - d1[1] * 30];
          const a2 = ALPHA + TH;
          const o2 = P(s, a2);
          const d2 = perp(a2);
          const c2 = [o2[0] - d2[0] * 28, o2[1] - d2[1] * 28];
          return (
            <g key={n}>
              <line x1={o1[0] - d1[0] * 16} y1={o1[1] - d1[1] * 16} x2={o1[0] + d1[0] * 12} y2={o1[1] + d1[1] * 12} stroke={INK} strokeWidth={2.4} />
              <circle cx={c1[0]} cy={c1[1]} r={10} fill="#fff" stroke={INK} strokeWidth={1.4} />
              <text x={c1[0]} y={c1[1] + 4.5} textAnchor="middle" fontSize={13} fontWeight={800} fill={INK}>
                {n}
              </text>
              <line x1={o2[0]} y1={o2[1]} x2={o2[0] - d2[0] * 14} y2={o2[1] - d2[1] * 14} stroke={INK} strokeWidth={2.4} />
              <circle cx={c2[0]} cy={c2[1]} r={10} fill="#fff" stroke={INK} strokeWidth={1.4} />
              <text x={c2[0]} y={c2[1] + 4.5} textAnchor="middle" fontSize={13} fontWeight={800} fill={INK}>
                {n}
              </text>
            </g>
          );
        })}
        {/* the cut line: one cut all the way around */}
        <path d={fan} fill="none" stroke={INK} strokeWidth={2.4} strokeLinejoin="round" />
        <text x={sc[0]} y={sc[1]} textAnchor="middle" fontSize={16} fontWeight={800} fill={INK} transform={`rotate(${rot(mid - 0.09)} ${sc[0]} ${sc[1]})`}>
          ✂ cut on the solid line
        </text>
        <text x={fr[0]} y={fr[1]} textAnchor="middle" fontSize={14} fontWeight={800} fill={PINE} transform={`rotate(${rot(mid + 0.09)} ${fr[0]} ${fr[1]})`}>
          FRONT of the tree
        </text>
        <g transform="translate(0 838)">
          <text x={0} y={0} fontFamily="Sora, Arial" fontSize={26} fontWeight={700} fill={INK}>
            Paper Tree Model: one-way swirl
          </text>
          {[
            "1  Cut on the solid line: one cut all the way around",
            "    (down the straight edge, around the curve, up the flap).",
            "2  Roll it into a cone, printed side out, shaded flap underneath.",
            "3  Slide the shaded flap under the other edge until the edge",
            "    sits on the dashed line and marks 1 to 5 line up. Tape.",
            "4  Stand it up. The tip is where the topper goes.",
          ].map((t, i) => (
            <text key={i} x={0} y={30 + i * 21} fontSize={15} fontWeight={i < 2 ? 800 : 600} fill={INK} style={{ whiteSpace: "pre" }}>
              {t}
            </text>
          ))}
        </g>
        <g transform="translate(590 838)">
          <text x={0} y={0} fontSize={14} fontWeight={800} fill={INK}>
            Key
          </text>
          {pal.colors.map((c, i) => (
            <g key={i}>
              <circle cx={14 + i * 30} cy={26} r={12} fill={c} stroke={INK} />
              <text x={14 + i * 30} y={31} textAnchor="middle" fontSize={13} fontWeight={800} fill={textOn(c)}>
                {i + 1}
              </text>
            </g>
          ))}
          <text x={18 + pal.colors.length * 30} y={31} fontSize={13} fill={INK}>
            colors
          </text>
          <Bow x={18} y={62} s0={16} letter="A" pal={pal} />
          <Bow x={62} y={62} s0={16} letter="B" pal={pal} />
          <text x={82} y={69} fontSize={13} fill={INK}>
            enhancer bows
          </text>
          <line x1={0} y1={92} x2={40} y2={92} stroke={ENH} strokeWidth={2} strokeOpacity={0.6} strokeDasharray="5 5" />
          <text x={48} y={96} fontSize={13} fill={INK}>
            enhancer swirl line
          </text>
          <text x={0} y={120} fontSize={13} fill={INK}>
            Circle size = {sizes[sizes.length - 1]}&quot; to {sizes[0]}&quot;
          </text>
          <text x={0} y={137} fontSize={13} fill={INK}>
            {label}
          </text>
          <text x={0} y={158} fontSize={11} fill={MUTED}>
            Print at actual size (100%).
          </text>
          <text x={0} y={173} fontSize={11} fill={MUTED}>
            Model scale about 1:{scale}.
          </text>
        </g>
      </svg>
    </section>
  );
}

// --- the page --------------------------------------------------------------------------

export default function TreeInstallPrint() {
  const [q] = useSearchParams();
  const sheet: Sheet = q.get("sheet") === "cone" ? "cone" : "design";
  const heightFt = Number(q.get("h")) || 9;
  const widthIn = Number(q.get("w")) || 59;
  const colorCount = clampColorCount(Number(q.get("n")) || 2);
  const style: DesignStyle = q.get("style") === "contemporary" ? "contemporary" : "traditional";
  const wholePacks = q.get("packs") !== "0";
  const fallback = ["#9e1b32", "#d4af37", "#e8dcc0", "#2f5fa8"];
  const given = (q.get("c") ?? "").split(",");
  const pal: Palette = {
    colors: Array.from({ length: colorCount }, (_, i) => hex(given[i] ?? null, fallback[i])),
    A: hex(q.get("a"), "#722f37"),
    B: hex(q.get("b"), "#b8933b"),
    topper: hex(q.get("t"), "#e0a83b"),
  };
  const counts = useMemo(() => treeInstallCounts(heightFt, widthIn, { style, colorCount, wholePacks }), [heightFt, widthIn, style, colorCount, wholePacks]);
  const input = useMemo<TreeInstallLayoutInput>(
    () => ({ heightFt, widthIn, colorCount, enhancers: counts.enhancers, loose: counts.loose, inEnhancers: counts.inEnhancers }),
    [heightFt, widthIn, colorCount, counts]
  );
  const { layout } = useTreeLayout(input);
  const sizes = Object.keys(counts.loose)
    .map(Number)
    .sort((a, b) => b - a);
  const label = `${heightFt} ft × ${widthIn} in tree, ${style}`;
  const back = (() => {
    const b = new URLSearchParams(q);
    b.delete("sheet");
    return `/tree-install?${b.toString()}`;
  })();

  return (
    <div className="min-h-screen bg-stone-100 print:bg-white">
      <style>{`@page { size: letter; margin: ${sheet === "cone" ? "0.25in" : "0.45in"}; }
        @media print { .tree-sheet-page { page-break-after: always; box-shadow: none !important; margin: 0 !important; }
          .tree-sheet-page:last-child { page-break-after: auto; }
          body { -webkit-print-color-adjust: exact; print-color-adjust: exact; } }`}</style>
      <div className="sticky top-0 z-10 flex flex-wrap items-center justify-between gap-3 border-b border-stone-200 bg-white px-4 py-3 print:hidden sm:px-8">
        <Link to={back} className="flex min-h-[40px] items-center gap-2 text-sm font-medium text-stone-600 hover:text-emerald-700">
          <ArrowLeft size={15} />
          Back to Tree Install
        </Link>
        <span className="text-sm font-semibold text-stone-700">
          {sheet === "cone" ? "Paper model" : "Tree Design Map"} · {label}
        </span>
        <button
          type="button"
          onClick={() => window.print()}
          disabled={!layout}
          className="flex min-h-[40px] items-center gap-2 rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-800 disabled:opacity-40"
        >
          <Printer size={15} />
          Print
        </button>
      </div>
      <div className="flex flex-col items-center gap-6 overflow-x-auto px-2 py-6 print:block print:p-0">
        {!layout ? (
          <p className="flex items-center gap-2 py-20 text-sm text-stone-600">
            <Loader2 size={15} className="animate-spin" />
            Placing every piece...
          </p>
        ) : sheet === "cone" ? (
          <div className="bg-white p-[0.25in] shadow-md print:p-0 print:shadow-none">
            <ConeSheet L={layout} pal={pal} label={label} sizes={sizes} />
          </div>
        ) : (
          <div className="flex flex-col gap-[0.9in] bg-white p-[0.45in] shadow-md print:block print:p-0 print:shadow-none">
            <DesignSheet L={layout} pal={pal} label={label} sizes={sizes} counts={counts} />
          </div>
        )}
      </div>
    </div>
  );
}
