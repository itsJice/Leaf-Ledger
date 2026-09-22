// Search text normalisation and token matching helpers for the product
// library. Moved verbatim out of pages/Library.tsx (WP 4.2 library-extract).
import type { Product } from "./types";

export function normalizeSearchText(value: unknown): string {
  return String(value ?? "")
    .toLowerCase()
    .replace(/["'`]/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function titleCase(value: string): string {
  return value.replace(/\b\w+/g, (part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase());
}

export function expandSearchAliases(value: unknown): string {
  const normalized = normalizeSearchText(value);
  if (!normalized) return "";

  let expanded = ` ${normalized} `;

  const unitPatterns: Array<[RegExp, string]> = [
    [/\b(\d+(?:\.\d+)?)\s*yd\b/g, "$1 yd $1 yard $1 yards"],
    [/\b(\d+(?:\.\d+)?)\s*in\b/g, "$1 in $1 inch $1 inches"],
    [/\b(\d+(?:\.\d+)?)\s*ft\b/g, "$1 ft $1 foot $1 feet"],
    [/\b(\d+(?:\.\d+)?)\s*ea\b/g, "$1 ea $1 each"],
    [/\b(\d+(?:\.\d+)?)\s*cs\b/g, "$1 cs $1 case"],
    [/\b(\d+(?:\.\d+)?)\s*bx\b/g, "$1 bx $1 box"],
    [/\b(\d+(?:\.\d+)?)\s*st\b/g, "$1 st $1 set"],
  ];

  for (const [pattern, replacement] of unitPatterns) {
    expanded = expanded.replace(pattern, ` ${replacement} `);
  }

  const tokenAliases: Array<[RegExp, string]> = [
    [/\byd\b/g, "yd yard yards"],
    [/\byard\b/g, "yard yd yards"],
    [/\byards\b/g, "yards yd yard"],
    [/\bin\b/g, "in inch inches"],
    [/\binch\b/g, "inch in inches"],
    [/\binches\b/g, "inches in inch"],
    [/\bft\b/g, "ft foot feet"],
    [/\bfoot\b/g, "foot ft feet"],
    [/\bfeet\b/g, "feet ft foot"],
    [/\bea\b/g, "ea each"],
    [/\beach\b/g, "each ea"],
    [/\bcs\b/g, "cs case"],
    [/\bcase\b/g, "case cs"],
    [/\bbx\b/g, "bx box"],
    [/\bbox\b/g, "box bx"],
    [/\bst\b/g, "st set"],
    [/\bset\b/g, "set st"],
    [/\bqty\b/g, "qty quantity"],
    [/\bquantity\b/g, "quantity qty"],
    [/\bw\b/g, "w width"],
    [/\bwidth\b/g, "width w"],
  ];

  for (const [pattern, replacement] of tokenAliases) {
    expanded = expanded.replace(pattern, ` ${replacement} `);
  }

  return expanded.replace(/\s+/g, " ").trim();
}

export function looksLikeCodeQuery(query: string): boolean {
  return /[\d/-]/.test(query) || /^[a-z]{1,3}$/.test(query);
}

export function matchesSearchTokens(haystack: string, query: string): boolean {
  const tokens = normalizeSearchText(query).split(" ").filter(Boolean);
  if (!tokens.length) return true;
  return matchesNormalizedTokens(haystack, tokens);
}

export function matchesNormalizedTokens(haystack: string, tokens: string[]): boolean {
  if (!tokens.length) return true;
  return tokens.every((token) => haystack.includes(token));
}

export function supplierKey(product: Product): string {
  return normalizeSearchText(product.supplier_name || "");
}

export function uniqStrings(values: Array<string | undefined | null>): string[] {
  return Array.from(new Set(values.map((value) => (value || "").trim()).filter(Boolean)));
}

export function searchableCodeText(product: Product): string {
  const rawCodeText = [
    product.supplier_sku,
    product.upc,
    product.raw_data?.["Item No"],
    product.raw_data?.sku,
    product.name,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return `${rawCodeText} ${expandSearchAliases(rawCodeText)}`.trim();
}
