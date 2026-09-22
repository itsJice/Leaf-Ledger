export function formatCurrency(value: number | null | undefined): string {
  if (value == null) return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value);
}

const DATE_ONLY_RE = /^\d{4}-\d{2}-\d{2}$/;

/**
 * Parse a date input the way both formatters below need it: a bare
 * `YYYY-MM-DD` string names a calendar date, not an instant, so it's parsed
 * as local midnight — parsing it as UTC midnight (the default for a
 * date-only ISO string) renders as the previous day in any timezone west of
 * UTC. A full ISO timestamp (or a `Date`) keeps the normal `Date` parsing.
 */
function parseDateInput(value: string | Date): Date {
  if (typeof value === "string" && DATE_ONLY_RE.test(value)) {
    const [y, m, d] = value.split("-").map(Number);
    return new Date(y, m - 1, d);
  }
  return new Date(value);
}

export function formatDate(value: string | Date | null | undefined): string {
  if (!value) return "—";
  return parseDateInput(value).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function categoryLabel(cat: string): string {
  const map: Record<string, string> = {
    // New categories
    containers: "Containers",
    wood: "Wood",
    greenery: "Greenery",
    florals: "Florals",
    trees: "Trees",
    // Scraper-produced categories
    accents: "Accents",
    // Legacy (kept for backward compat)
    plant: "Plant",
    container: "Container",
    filler: "Filler",
    accent: "Accent",
    other: "Other",
    supplies: "Supplies",
    moss: "Moss",
    branches: "Branches",
    botanicals: "Botanicals",
    preserved: "Preserved",
    seasonal: "Seasonal",
    stems: "Stems",
    foliage: "Foliage",
    succulents: "Succulents",
    topiaries: "Topiaries",
    wreaths: "Wreaths",
    baskets: "Baskets",
    vases: "Vases",
    risers: "Risers",
    pedestals: "Pedestals",
    liners: "Liners",
  };
  return Object.hasOwn(map, cat) ? map[cat] : cat;
}

export function unitLabel(unit: string): string {
  const map: Record<string, string> = {
    stem: "stem",
    pot: "pot",
    flat: "flat",
    bunch: "bunch",
    each: "each",
  };
  return Object.hasOwn(map, unit) ? map[unit] : unit;
}

/**
 * Short date in the machine's default locale ("Sep 13, 2026" in en-US).
 * `""`, `null`/`undefined` and an unparseable string all return "—", matching
 * `formatDate`. Was a verbatim copy of the inline `formatDate` in
 * pages/TreeCounts.tsx; that copy is kept, unfixed, as `formatDateTreeCounts`
 * in `inline-copies.ts`.
 */
export function formatDateShortLocale(iso: string | null | undefined): string {
  // Deliberately not a blanket falsy check: `0` (a valid epoch input in the
  // historical callers) still falls through to `parseDateInput` below.
  if (iso == null || iso === "") return "—";
  const date = parseDateInput(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}
