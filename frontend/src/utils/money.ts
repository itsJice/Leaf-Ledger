// Shared money formatters. Both are verbatim copies of inline page helpers;
// `src/utils/__tests__/money.test.ts` proves them identical to every original.

/**
 * `toFixed(2)` money: no thousands separators, "$" before the minus sign,
 * "—" for null/undefined. Verbatim copy of the identical inline `money` helpers
 * in CatalogPickPane.tsx, Jobs.tsx, Sourcing.tsx and Orders.tsx.
 */
export const formatMoney = (n?: number | null) => (n == null ? "—" : `$${Number(n).toFixed(2)}`);

/**
 * Grouped money (`$1,234.50`). Uses the machine default locale, throws on
 * null/undefined. Verbatim copy of the inline `money` in OrnamentCalculator.tsx.
 */
export const formatMoneyGrouped = (n: number) => `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
