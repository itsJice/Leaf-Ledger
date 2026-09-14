// Colour decoding helpers for the product library.
// Moved verbatim out of pages/Library.tsx (WP 4.2 library-extract).
import { KNOWN_COLOR_WORDS, ALLSTATE_COLOR_CODE_MAP } from "./constants";
import { normalizeSearchText, titleCase, uniqStrings, supplierKey } from "./search";
import { displayProductName } from "./display";
import type { Product } from "./types";

export function looksLikeSupplierColorCode(value: unknown): boolean {
  const raw = String(value ?? "").trim();
  if (!raw) return false;
  return raw
    .split(/[/,\s-]+/)
    .filter(Boolean)
    .every((token) => /^[A-Z]{1,4}$/.test(token));
}

// Matches a colour word as a whole word (or whole phrase, for multi-word
// entries like "rose gold") rather than a bare substring — otherwise "tan"
// matches inside "tangerine". `normalizeSearchText` already turns hyphens
// and other separators into spaces, so a word-boundary match against the
// space-joined phrase also catches hyphenated input (e.g. "rose-gold").
function matchesColorWord(normalized: string, word: string): boolean {
  const escaped = word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`\\b${escaped}\\b`).test(normalized);
}

export function extractKnownColorWords(value: unknown): string[] {
  const normalized = normalizeSearchText(value);
  if (!normalized) return [];
  return KNOWN_COLOR_WORDS.filter((word) => matchesColorWord(normalized, word)).map(titleCase);
}

export function decodeAllstateColorGroup(value: unknown): string[] {
  const normalized = normalizeSearchText(value).toUpperCase();
  if (!normalized) return [];
  const tokens = normalized.split(/[^A-Z0-9]+/).filter(Boolean);
  return uniqStrings(tokens.flatMap((token) => ALLSTATE_COLOR_CODE_MAP[token] || []));
}

export function metadataColorLabels(value: unknown): string[] {
  if (looksLikeSupplierColorCode(value)) return decodeAllstateColorGroup(value);
  const known = extractKnownColorWords(value);
  if (known.length) return known;
  return [];
}

export function mergeOptionLists(...lists: Array<Array<string | undefined | null>>): string[] {
  return uniqStrings(lists.flat().map((value) => (value ? String(value) : ""))).sort((a, b) =>
    a.localeCompare(b, undefined, { numeric: true })
  );
}

export function productColorLabels(product: Product): string[] {
  const raw = product.raw_data || {};
  const explicitValues = [
    product.color,
    raw.Color,
    raw["Primary Color"],
    raw.ColorGrp,
  ].filter(Boolean);

  const explicitWords = explicitValues.flatMap((value) => {
    if (looksLikeSupplierColorCode(value)) return [];
    const found = extractKnownColorWords(value);
    if (found.length) return found;
    const normalized = normalizeSearchText(value);
    if (!normalized) return [];
    return normalized
      .split(" ")
      .filter((token) => token.length >= 3)
      .map(titleCase);
  });

  const colorCodeLabels =
    supplierKey(product) === "allstate"
      ? decodeAllstateColorGroup(product.color || raw.ColorGrp || raw.Color || raw["Primary Color"])
      : [];

  const descriptionLabels = extractKnownColorWords([
    displayProductName(product),
    raw.Description,
    product.description,
  ].filter(Boolean).join(" "));

  return uniqStrings([...explicitWords, ...colorCodeLabels, ...descriptionLabels]).sort();
}

export function productColorSummary(product: Product): string {
  const labels = productColorLabels(product);
  if (labels.length) return labels.join(", ");
  const raw = product.raw_data || {};
  return String(product.color || raw.ColorGrp || raw.Color || "—");
}
