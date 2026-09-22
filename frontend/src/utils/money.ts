// Shared money formatters. Both are verbatim copies of inline page helpers;
// `src/utils/__tests__/money.test.ts` proves them identical to every original.

/**
 * `toFixed(2)` money: no thousands separators, "$" before the minus sign,
 * "—" for null/undefined/non-finite. Was a verbatim copy of the identical
 * inline `money` helpers in CatalogPickPane.tsx, Jobs.tsx, Sourcing.tsx and
 * Orders.tsx; those originals (kept unfixed as test oracles in
 * `inline-copies.ts`) still return "$NaN" for a non-finite value.
 */
export const formatMoney = (n?: number | null) =>
  n == null || !Number.isFinite(Number(n)) ? "—" : `$${Number(n).toFixed(2)}`;

/**
 * Grouped money (`$1,234.50`). Uses the machine default locale, "—" for
 * null/undefined/non-finite. Was a verbatim copy of the inline `money` in
 * OrnamentCalculator.tsx (kept unfixed as `moneyOrnament` in
 * `inline-copies.ts`, which still throws on null/undefined and returns
 * "$NaN"/"$∞" for a non-finite value).
 */
export const formatMoneyGrouped = (n?: number | null) =>
  n == null || !Number.isFinite(Number(n))
    ? "—"
    : `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
