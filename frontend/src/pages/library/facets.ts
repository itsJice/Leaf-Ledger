// Facet labels (country, availability, type, size) and search-entry
// builders for the product library.
// Moved verbatim out of pages/Library.tsx (WP 4.2 library-extract).
import { categoryLabel } from "utils/format";
import { PRODUCT_TYPE_RULES } from "./constants";
import { normalizeSearchText, titleCase, uniqStrings, expandSearchAliases, searchableCodeText } from "./search";
import { productColorLabels } from "./colors";
import { displayProductName, sourceBasePrice, sourceUom } from "./display";
import type { Product, ProductSearchEntry } from "./types";

export function productCountryLabel(product: Product): string | undefined {
  const raw = product.raw_data || {};
  const value = product.country_of_origin || raw["Country of Origin"] || raw.Country;
  return value ? titleCase(String(value)) : undefined;
}

export function productAvailabilityLabel(product: Product): string | undefined {
  const raw = product.raw_data || {};
  const note = normalizeSearchText(product.availability_note || raw["Avail. Qty: *"] || raw["Avail. Qty"]);
  if (note.includes("within 1 4 months")) return "Within 1-4 months";
  if (note.includes("available today") || note.includes("today")) return "Available today";
  if (note.includes("sold out") || note.includes("out of stock") || note.includes("unavailable")) {
    return "Sold out / unavailable";
  }
  if (product.availability === "in_stock") return "Available today";
  if (product.availability === "out_of_stock") return "Sold out / unavailable";
  if (product.availability === "eta") return "Future ETA";
  if (/eta|available\s+[a-z]{3,9}\s+\d{4}|expected|future/.test(note)) return "Future ETA";
  if (note.includes("over 4 months")) return "Over 4 months";
  return undefined;
}

export function productTypeLabels(product: Product): string[] {
  const raw = product.raw_data || {};
  const haystack = ` ${normalizeSearchText([
    displayProductName(product),
    raw.Description,
    raw.name,
    product.description,
    raw.allstate_subcategory,
    raw.Category,
    raw.Style,
    categoryLabel(product.category),
  ].filter(Boolean).join(" "))} `;
  return PRODUCT_TYPE_RULES
    .filter((rule) => rule.keywords.some((keyword) => haystack.includes(keyword)))
    .map((rule) => rule.label);
}

export function productSizeLabels(product: Product, cachedTypeLabels?: string[]): string[] {
  const raw = product.raw_data || {};
  const sourceText = [
    displayProductName(product),
    raw.Description,
    raw.name,
    product.description,
    raw.ProdLength,
    raw.Height,
    raw.Width,
    raw.Diameter,
    raw.Length,
    raw["Box LxWxH"],
    raw["Case LxWxH"],
  ].filter(Boolean).join(" ");
  const sourceLower = sourceText.toLowerCase();
  if (!sourceText) return [];

  const labels: string[] = [];
  const add = (label: string) => labels.push(label);
  const normalizedUnit = (unit: string) => {
    const lower = unit.toLowerCase();
    if (lower === "yard" || lower === "yards") return "yd";
    if (lower === "foot" || lower === "feet") return "ft";
    if (lower === "inch" || lower === "inches") return "in";
    return lower;
  };

  const hasRibbonType = (cachedTypeLabels || productTypeLabels(product)).includes("Ribbon");
  if (hasRibbonType) {
    for (const match of sourceText.matchAll(/(\d+(?:\.\d+)?)\s*(?:"|in|inch|inches)?\s*w?\s*x\s*(\d+(?:\.\d+)?)\s*(yd|yard|yards|ft|foot|feet|in|inch|inches)\b/gi)) {
      const width = match[1];
      const length = match[2];
      const unit = normalizedUnit(match[3]);
      add(`${width} in x ${length} ${unit}`);
      add(`${width} in`);
      add(`${length} ${unit}`);
    }
  }

  for (const match of sourceLower.matchAll(/(\d+(?:\.\d+)?)\s*(yd|yard|yards|ft|foot|feet|in|inch|inches)\b/g)) {
    const unit = normalizedUnit(match[2]);
    add(`${match[1]} ${unit}`);
  }

  return uniqStrings(labels).sort((a, b) => {
    const aNum = parseFloat(a);
    const bNum = parseFloat(b);
    if (!Number.isNaN(aNum) && !Number.isNaN(bNum) && aNum !== bNum) return aNum - bNum;
    return a.localeCompare(b, undefined, { numeric: true });
  });
}

export function buildProductSearchEntry(product: Product): ProductSearchEntry {
  const raw = product.raw_data || {};
  const displayName = displayProductName(product);
  const productTypes = productTypeLabels(product);
  const colors = productColorLabels(product);
  const sizes = productSizeLabels(product, productTypes);
  const country = productCountryLabel(product);
  const availability = productAvailabilityLabel(product);
  const categoryText = categoryLabel(product.category);
  const supplierName = product.supplier_name || "";
  const searchText = expandSearchAliases([
    displayName,
    product.description,
    product.color,
    product.material,
    product.country_of_origin,
    supplierName,
    categoryText,
    sourceBasePrice(product),
    sourceUom(product),
    raw.Description,
    raw.name,
    raw.sku,
    raw.price,
    raw.Category,
    raw.Material,
    raw.Materials,
    raw.Finish,
    raw.Style,
    raw["Unit of Measure"],
    raw.Unit,
    raw.Country,
    raw.Color,
    raw["Primary Color"],
    raw.Height,
    raw.Width,
    raw.Diameter,
    raw.Length,
    raw.Availability,
    raw.ColorGrp,
    raw.Season,
    raw.Class,
    raw["Material Breakdown"],
    raw["Country of Origin"],
    raw["Avail. Qty"],
    raw["Avail. Qty: *"],
    raw["ProdLength"],
    raw["ProdWeight"],
    raw["BoxWeight"],
    raw["CsWeight"],
    raw["Box LxWxH"],
    raw["Case LxWxH"],
    raw["CaseCube"],
    raw["Oversize"],
    raw["SugRetail"],
    raw["UPC"],
    raw["MinQty"],
    raw["BoxQty"],
    raw["CaseQty"],
    raw["CatalogVol"],
    raw["CatPage"],
    raw["P-CatVol"],
    raw["P-CatPage"],
    raw["allstate_subcategory"],
    ...productTypes,
    ...colors,
    country,
    availability,
    ...sizes,
  ].filter(Boolean).join(" "));

  return {
    product,
    category: product.category,
    categoryLabel: categoryText,
    supplierName,
    productTypes,
    colors,
    sizes,
    availability,
    country,
    searchText,
    codeText: searchableCodeText(product),
    sortName: displayName || product.name,
    isFavorited: product.is_favorited,
  };
}

export function searchableVisibleText(product: Product): string {
  const raw = product.raw_data || {};
  return expandSearchAliases([
    displayProductName(product),
    product.description,
    product.color,
    product.material,
    product.country_of_origin,
    product.supplier_name,
    categoryLabel(product.category),
    sourceBasePrice(product),
    sourceUom(product),
    raw.Description,
    raw.name,
    raw.sku,
    raw.price,
    raw.Category,
    raw.Material,
    raw.Materials,
    raw.Finish,
    raw.Style,
    raw["Unit of Measure"],
    raw.Unit,
    raw.Country,
    raw.Color,
    raw["Primary Color"],
    raw.Height,
    raw.Width,
    raw.Diameter,
    raw.Length,
    raw.Availability,
    raw.ColorGrp,
    raw.Season,
    raw.Class,
    raw["Material Breakdown"],
    raw["Country of Origin"],
    raw["Avail. Qty"],
    raw["Avail. Qty: *"],
    raw["ProdLength"],
    raw["ProdWeight"],
    raw["BoxWeight"],
    raw["CsWeight"],
    raw["Box LxWxH"],
    raw["Case LxWxH"],
    raw["CaseCube"],
    raw["Oversize"],
    raw["SugRetail"],
    raw["UPC"],
    raw["MinQty"],
    raw["BoxQty"],
    raw["CaseQty"],
    raw["CatalogVol"],
    raw["CatPage"],
    raw["P-CatVol"],
    raw["P-CatPage"],
    raw["ColorGrp"],
    raw["allstate_subcategory"],
    ...productTypeLabels(product),
    ...productColorLabels(product),
    productCountryLabel(product),
    productAvailabilityLabel(product),
    ...productSizeLabels(product),
  ]
    .filter(Boolean)
    .join(" "));
}
