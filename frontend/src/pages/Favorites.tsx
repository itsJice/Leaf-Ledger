import { apiFetch } from "utils/apiFetch";
import React, { useEffect, useMemo, useState } from "react";
import { Heart } from "lucide-react";
import Layout from "components/Layout";
import { apiClient } from "app";
import { toast } from "sonner";
import { ProductDetailModal, ProductView, type Product } from "./Library";
import { readFavoriteIds, setLocalFavorite } from "utils/favorites";

const FAVORITES_CACHE_KEY = "leaf-ledger:favorites-cache:v1";
const LIBRARY_CACHE_KEY = "leaf-ledger:library-cache:v1";

function readFavoritesCache(): Product[] | null {
  try {
    const raw = localStorage.getItem(FAVORITES_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed?.products) ? parsed.products : null;
  } catch {
    return null;
  }
}

function writeFavoritesCache(products: Product[]) {
  try {
    localStorage.setItem(
      FAVORITES_CACHE_KEY,
      JSON.stringify({ products, cachedAt: Date.now() })
    );
  } catch {
    // Ignore storage issues.
  }
}

function readLibraryProductsFromCache(): Product[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(LIBRARY_CACHE_KEY) || "{}");
    return Array.isArray(parsed?.products) ? parsed.products : [];
  } catch {
    return [];
  }
}

function localFavoriteProducts(): Product[] {
  const favoriteIds = readFavoriteIds();
  return readLibraryProductsFromCache()
    .filter((product) => favoriteIds.has(product.id))
    .map((product) => ({ ...product, is_favorited: true }));
}

export default function Favorites() {
  const cachedFavorites = useMemo(() => readFavoritesCache(), []);
  const initialFavorites = useMemo(
    () => cachedFavorites?.length ? cachedFavorites : localFavoriteProducts(),
    [cachedFavorites]
  );
  const [products, setProducts] = useState<Product[]>(initialFavorites);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [detailProduct, setDetailProduct] = useState<Product | null>(null);
  const [animatingIds, setAnimatingIds] = useState<Set<number>>(new Set());

  const favoritedCount = useMemo(
    () => products.filter((product) => product.is_favorited).length,
    [products]
  );

  const load = async () => {
    setRefreshing(true);
    try {
      const favoriteIds = Array.from(readFavoriteIds());
      if (favoriteIds.length === 0) {
        setProducts([]);
        writeFavoritesCache([]);
        return;
      }
      // Fetch full data for every favorited id, so items favorited anywhere
      // (Catalog Search, Product Library) show up — not just cached ones.
      const res = await apiFetch(`/api/products/by-ids?ids=${favoriteIds.join(",")}`, { credentials: "include" });
      const data = await res.json();
      const nextProducts = (Array.isArray(data) ? data : []).map((product: Product) => ({ ...product, is_favorited: true }));
      setProducts(nextProducts);
      writeFavoritesCache(nextProducts);
    } catch {
      const local = localFavoriteProducts();
      if (local.length) setProducts(local);
      else toast.error("Failed to load favorites");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => { load(); }, []);

  const toggleFavorite = async (id: number) => {
    setAnimatingIds((prev) => new Set(prev).add(id));
    setTimeout(() => {
      setAnimatingIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }, 350);

    try {
      setLocalFavorite(id, false);
      await apiClient.toggle_favorite({ productId: id });
      setProducts((prev) => {
        const next = prev.filter((product) => product.id !== id);
        writeFavoritesCache(next);
        return next;
      });
      setDetailProduct((prev) => (prev?.id === id ? null : prev));
      toast.success("Removed from favorites");
    } catch {
      toast.error("Failed to update favorite");
    }
  };

  return (
    <Layout>
      <header
        className="sticky top-0 z-10 flex items-center justify-between border-b border-stone-200 px-10 py-4"
        style={{ backgroundColor: "rgb(var(--ll-page))" }}
      >
        <div>
          <h1
            className="text-xl font-semibold text-stone-800"
            style={{ fontFamily: "Georgia, serif" }}
          >
            Favorites
          </h1>
          <p className="mt-0.5 text-xs text-stone-500">
            {favoritedCount} saved product{favoritedCount !== 1 ? "s" : ""}
            {refreshing && <span className="ml-2 text-emerald-700">Refreshing…</span>}
          </p>
        </div>
      </header>

      <div className="px-10 py-6">
        {loading ? (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <div
              className="mb-4 flex h-16 w-16 items-center justify-center rounded-full"
              style={{ backgroundColor: "rgb(var(--ll-brand-soft))" }}
            >
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-emerald-600 border-t-transparent" />
            </div>
            <p className="mb-1 text-base font-medium text-stone-600">Checking saved favorites</p>
            <p className="max-w-xs text-sm leading-relaxed text-stone-400">
              We&apos;re loading your hearted products.
            </p>
          </div>
        ) : products.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <div
              className="mb-4 flex h-16 w-16 items-center justify-center rounded-full"
              style={{ backgroundColor: "rgb(var(--ll-danger-soft))" }}
            >
              <Heart size={28} className="text-rose-400" strokeWidth={1.5} />
            </div>
            <p className="mb-1 text-base font-medium text-stone-600">No favorites yet</p>
            <p className="max-w-xs text-sm leading-relaxed text-stone-400">
              Heart products in Product Library to save them here.
            </p>
          </div>
        ) : (
          <ProductView
            products={products}
            animatingIds={animatingIds}
            onFavorite={toggleFavorite}
            onOpenProduct={setDetailProduct}
            hideSyncAll
            hideFavoritesToggle
            emptyTitle="No favorites match"
            emptyDescription="Try adjusting your search or filters."
          />
        )}
      </div>

      {detailProduct && (
        <ProductDetailModal product={detailProduct} onClose={() => setDetailProduct(null)} />
      )}
    </Layout>
  );
}
