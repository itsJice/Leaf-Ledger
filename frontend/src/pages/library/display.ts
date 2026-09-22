// Display/formatting helpers for product values, source pricing, image
// status and detail status. Moved verbatim out of pages/Library.tsx
// (WP 4.2 library-extract).
import { formatCurrency, unitLabel } from "utils/format";
import { STALE_DAYS } from "./constants";
import type { Product } from "./types";

export function isPriceStale(price_updated_at?: string | null): boolean {
  if (!price_updated_at) return true;
  const diffMs = Date.now() - new Date(price_updated_at).getTime();
  return diffMs > STALE_DAYS * 24 * 60 * 60 * 1000;
}

export function formatDetailValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(2);
  return String(value);
}

export function sourceValue(product: Product, ...keys: string[]): unknown {
  const raw = product.raw_data || {};
  for (const key of keys) {
    const value = raw[key];
    if (value !== undefined && value !== null && value !== "") return value;
  }
  return undefined;
}

export function displayProductName(product: Product): string {
  // `name` holds the concise product name; `description` is marketing copy.
  // (Some legacy rows only had the readable name in raw.Description.)
  const raw = product.raw_data || {};
  const preferred = product.name || raw.Description || product.description;
  return String(preferred || "").trim();
}

export function sourceBasePrice(product: Product): string {
  const rawPrice = sourceValue(product, "BasePrice", "price");
  if (rawPrice) return String(rawPrice);
  return product.current_price != null ? formatCurrency(product.current_price) : "—";
}

export function sourceUom(product: Product): string {
  const rawUom = sourceValue(product, "Uom", "UOM", "Unit of Measure", "Unit");
  if (rawUom) return String(rawUom);
  return unitLabel(product.unit).toUpperCase();
}

export function sourceOrderContext(product: Product): Array<[string, unknown]> {
  return ([
    ["MinQty", product.moq ?? sourceValue(product, "MinQty")],
    ["BoxQty", product.box_qty ?? sourceValue(product, "BoxQty")],
    ["CaseQty", product.case_qty ?? sourceValue(product, "CaseQty")],
    ["SugRetail", sourceValue(product, "SugRetail")],
  ] as Array<[string, unknown]>).filter(([, value]) => value !== undefined && value !== null && value !== "");
}

export function hasNoSupplierImage(product: Pick<Product, "raw_data">): boolean {
  return product.raw_data?.image_status === "no_supplier_image";
}

export function hasSupplierPlaceholderImage(product: Pick<Product, "photo_url" | "raw_data">): boolean {
  const photoUrl = String(product.photo_url || "").toLowerCase();
  const sourcePhotoUrl = String(product.raw_data?.source_photo_url || "").toLowerCase();
  return photoUrl.includes("price_update.gif") || sourcePhotoUrl.includes("price_update.gif");
}

export function productDisplayImageUrl(product: Pick<Product, "photo_url" | "image_urls" | "raw_data">): string | undefined {
  if (hasNoSupplierImage(product) || hasSupplierPlaceholderImage(product)) return undefined;
  const candidates = [
    product.photo_url,
    ...(Array.isArray(product.image_urls) ? product.image_urls : []),
    product.raw_data?.source_photo_url,
  ];
  return candidates.map((value) => String(value || "").trim()).find(Boolean);
}

// All image URLs for a product, ordered: stored key first (resolves in prod),
// then the external source + gallery URLs as fallbacks. Feeds ProxiedImage so a
// missing stored image falls through to a working external one.
export function productImageSources(product: Pick<Product, "photo_url" | "image_urls" | "raw_data">): string[] {
  if (hasNoSupplierImage(product) || hasSupplierPlaceholderImage(product)) return [];
  const urls = [
    product.photo_url,
    product.raw_data?.source_photo_url,
    ...(Array.isArray(product.image_urls) ? product.image_urls : []),
  ].map((value) => String(value || "").trim()).filter(Boolean);
  return Array.from(new Set(urls));
}

export function imageStatus(product: Product): "stored" | "visible" | "pending" | "failed" | "no_supplier_image" | "placeholder" {
  const status = product.raw_data?.image_status;
  const displayImageUrl = productDisplayImageUrl(product);
  if (status === "no_supplier_image") return "no_supplier_image";
  if (hasSupplierPlaceholderImage(product)) return "placeholder";
  if (status === "stored" && displayImageUrl) return "stored";
  if (displayImageUrl) return "visible";
  if (status === "failed") return "failed";
  return "pending";
}

export function detailStatus(product: Product): "stored" | "pending" | "failed" {
  const status = product.raw_data?.detail_status;
  if (status === "failed") return "failed";
  if (status === "stored" || product.raw_data?.detail_url) return "stored";
  return "pending";
}


export function prettifyKey(key: string): string {
  return key.replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim().replace(/\b\w/g, (c) => c.toUpperCase());
}

// Append a unit to bare numeric measurements ("360" -> "360 in"). Leaves empty
// values and values that already carry a unit / are compound strings untouched.
export function withUnit(value: unknown, unit: string): unknown {
  if (value === null || value === undefined) return value;
  const s = String(value).trim();
  if (!s || s === "0") return value;
  if (/[a-zA-Z"'″×]/.test(s)) return s;
  return `${s} ${unit}`;
}
