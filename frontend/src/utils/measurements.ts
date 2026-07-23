// Metric → imperial conversions for DISPLAY ONLY. Never mutates product data —
// used to annotate a product's name/size with the imperial equivalent shown
// right next to the metric value.
//
// Ornament/décor mm sizes use the trade-standard chart (80mm≈3″, 100mm≈4″,
// 120mm≈4.75″ …) rather than a raw 25.4 divide, matching how these are sold.
// Other values are computed and rounded to a clean fraction.

const MM_TO_IN: Record<number, number> = {
  40: 1.5, 50: 2, 60: 2.5, 70: 2.75, 76: 3, 80: 3, 90: 3.5, 100: 4, 110: 4.25,
  120: 4.75, 130: 5, 140: 5.5, 150: 6, 160: 6.25, 170: 6.75, 180: 7, 200: 8,
  210: 8.25, 250: 10, 300: 12,
};

const roundTo = (n: number, step: number) => Math.round(n / step) * step;
const trim = (n: number) => Math.round(n * 100) / 100;

export function mmToInches(mm: number): number {
  if (MM_TO_IN[mm] != null) return MM_TO_IN[mm];
  if (mm < 25) return Math.round((mm / 25.4) * 10) / 10; // finer for tiny gauges
  return roundTo(mm / 25.4, 0.25);
}
const cmToInches = (cm: number) => roundTo(cm / 2.54, 0.25);

function metersToImperial(m: number): string {
  const totalIn = m * 39.3701;
  const ft = Math.floor(totalIn / 12);
  const inch = Math.round(totalIn - ft * 12);
  if (ft <= 0) return `${trim(totalIn)}″`;
  return inch ? `${ft}′${inch}″` : `${ft}′`;
}

export interface Conversion { raw: string; imperial: string }

// number + optional space + a metric unit at a word boundary. Longer units are
// listed first so "mm"/"cm"/"ml"/"kg" win over "m"/"g". Bare litres ("l") are
// deliberately excluded — in this catalog "100 L" means 100 lights, not liters.
const RE = /(\d+(?:\.\d+)?)\s?(mm|cm|kg|ml|m|g)\b/gi;

export function findMetricConversions(text?: string | null): Conversion[] {
  if (!text) return [];
  const out: Conversion[] = [];
  const seen = new Set<string>();
  let m: RegExpExecArray | null;
  RE.lastIndex = 0;
  while ((m = RE.exec(text)) !== null) {
    const value = parseFloat(m[1]);
    if (!isFinite(value)) continue;
    const unit = m[2].toLowerCase();
    let imperial: string | null = null;
    if (unit === "mm") imperial = `${trim(mmToInches(value))}″`;
    else if (unit === "cm") imperial = `${trim(cmToInches(value))}″`;
    else if (unit === "m") imperial = metersToImperial(value);
    else if (unit === "g") imperial = `${trim(value / 28.35)} oz`;
    else if (unit === "kg") imperial = `${trim(value / 0.45359)} lb`;
    else if (unit === "ml") imperial = `${trim(value / 29.5735)} fl oz`;
    if (!imperial) continue;
    const key = `${m[1]}${unit}`.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({ raw: `${m[1]}${unit}`, imperial });
  }
  return out;
}

// One compact string: "100mm ≈ 4″ · 5mm ≈ 0.2″" (or null when no metric found).
export function metricHintText(text?: string | null, max = 3): string | null {
  const conv = findMetricConversions(text);
  if (!conv.length) return null;
  return conv.slice(0, max).map((c) => `${c.raw} ≈ ${c.imperial}`).join(" · ");
}

// Shown as a hover title — doubles as the quick cheat sheet.
export const METRIC_CHEAT = "Ornament sizes — 80mm≈3″ · 100mm≈4″ · 120mm≈4.75″ · 150mm≈6″ · 200mm≈8″";
