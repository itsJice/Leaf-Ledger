// LocalStorage caches for the product library (product/supplier list and
// filter metadata) plus favourite-state merging.
// Moved verbatim out of pages/Library.tsx (WP 4.2 library-extract).
import { readJsonCache } from "utils/jsonCache";
import { readFavoriteIds } from "utils/favorites";
import { LIBRARY_CACHE_KEY, LIBRARY_METADATA_CACHE_KEY, LIBRARY_CACHE_RAW_KEYS } from "./constants";
import type { Product, Supplier, LibraryFilterMetadata } from "./types";

export function trimRawDataForCache(raw?: Record<string, any> | null) {
  if (!raw) return {};
  const trimmed: Record<string, any> = {};
  for (const key of LIBRARY_CACHE_RAW_KEYS) {
    if (raw[key] !== undefined) trimmed[key] = raw[key];
  }
  return trimmed;
}

export function trimProductForCache(product: Product): Product {
  return {
    ...product,
    raw_data: trimRawDataForCache(product.raw_data),
  };
}

export function readLibraryCache(): { suppliers: Supplier[]; products: Product[]; productTotal?: number } | null {
  const parsed = readJsonCache<any>(LIBRARY_CACHE_KEY, null);
  if (!Array.isArray(parsed?.products) || !Array.isArray(parsed?.suppliers)) return null;
  return { suppliers: parsed.suppliers, products: parsed.products, productTotal: parsed.productTotal };
}

export function writeLibraryCache(suppliers: Supplier[], products: Product[], productTotal?: number) {
  try {
    const payload = {
      suppliers,
      products: products.map(trimProductForCache),
      productTotal,
      cachedAt: Date.now(),
    };
    localStorage.setItem(LIBRARY_CACHE_KEY, JSON.stringify(payload));
  } catch {
    // Ignore cache quota/storage issues.
  }
}

export function readLibraryMetadataCache(): LibraryFilterMetadata | null {
  const parsed = readJsonCache<any>(LIBRARY_METADATA_CACHE_KEY, null);
  if (!parsed || typeof parsed !== "object") return null;
  return parsed;
}

export function writeLibraryMetadataCache(metadata: LibraryFilterMetadata) {
  try {
    localStorage.setItem(LIBRARY_METADATA_CACHE_KEY, JSON.stringify({ ...metadata, cachedAt: Date.now() }));
  } catch {
    // Ignore cache quota/storage issues.
  }
}

export function applyLocalFavoriteState(products: Product[]): Product[] {
  const favoriteIds = readFavoriteIds();
  return products.map((product) => ({
    ...product,
    is_favorited: product.is_favorited || favoriteIds.has(product.id),
  }));
}
