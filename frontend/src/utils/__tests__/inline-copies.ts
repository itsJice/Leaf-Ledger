// Verbatim copies of helpers that are duplicated inline across pages and
// components. They exist only as a test oracle: Phase 3 consolidates these into
// shared utils, and `inline-copies.test.ts` pins exactly what each copy does
// today so the consolidated version can be checked against every original.
//
// The only change from the source is `export` (and a per-site name). Do not
// "fix" anything here — if a copy looks wrong, that is the behaviour to pin.

// ─── money ───────────────────────────────────────────────────────────────────

// verbatim copy of src/components/CatalogPickPane.tsx:29
export const moneyCatalogPick = (n?: number | null) => (n == null ? "—" : `$${Number(n).toFixed(2)}`);

// verbatim copy of src/pages/Jobs.tsx:24
export const moneyJobs = (n?: number | null) => (n == null ? "—" : `$${Number(n).toFixed(2)}`);

// verbatim copy of src/pages/Sourcing.tsx:45
export const moneySourcing = (n?: number | null) => (n == null ? "—" : `$${Number(n).toFixed(2)}`);

// verbatim copy of src/pages/Orders.tsx:20
export const moneyOrders = (n?: number | null) => (n == null ? "—" : `$${Number(n).toFixed(2)}`);

// verbatim copy of src/pages/OrnamentCalculator.tsx:192
export const moneyOrnament = (n: number) => `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

// ─── proxied ─────────────────────────────────────────────────────────────────

// verbatim copy of src/components/CatalogPickPane.tsx:27
export const proxiedCatalogPick = (url?: string | null) =>
  url ? `/api/products/image-proxy?url=${encodeURIComponent(url)}` : undefined;

// verbatim copy of src/pages/Sourcing.tsx:44
export const proxiedSourcing = (url?: string | null) => (url ? `/api/products/image-proxy?url=${encodeURIComponent(url)}` : undefined);

// verbatim copy of src/pages/Orders.tsx:16
export function proxiedOrders(url?: string | null): string | undefined {
  if (!url) return undefined;
  return `/api/products/image-proxy?url=${encodeURIComponent(url)}`;
}

// verbatim copy of src/pages/OrnamentCalculator.tsx:100
export function proxiedOrnament(url: string | null): string | undefined {
  if (!url) return undefined;
  return `/api/products/image-proxy?url=${encodeURIComponent(url)}`;
}

// ─── formatDate ──────────────────────────────────────────────────────────────

// verbatim copy of src/pages/TreeCounts.tsx:38
export function formatDateTreeCounts(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}
