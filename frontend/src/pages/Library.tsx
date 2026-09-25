import Layout from "components/Layout";
import { apiClient } from "app";
import { toast } from "sonner";
import { useEffect, useState, useRef, useCallback, useMemo } from "react";
import { Store, Grid3X3 } from "components/icons";
import { setLocalFavorite } from "utils/favorites";
import {
  readLibraryCache,
  writeLibraryCache,
  readLibraryMetadataCache,
  writeLibraryMetadataCache,
  applyLocalFavoriteState,
} from "./library/cache";
import { INITIAL_CARD_RENDER_LIMIT } from "./library/constants";
import { ProductModal } from "./library/ProductModal";
import { AddToProjectModal } from "./library/AddToProjectModal";
import { ProductDetailModal } from "./library/ProductDetailModal";
import { VendorView } from "./library/VendorView";
import { ProductView } from "./library/ProductView";
import type {
  Product,
  Supplier,
  ProductPage,
  LibraryFilterMetadata,
  ServerFilterSelection,
} from "./library/types";

// This page used to hold every product-library helper, type and component in
// one 3000+ line file that six other pages imported from directly. Those
// pieces now live under ./library/**; this re-export keeps every existing
// `from "./Library"` / `from "../Library"` import working unchanged.
export * from "./library/index";

// ─── Main page ────────────────────────────────────────────────────────────────
export default function Library() {
  const cachedLibrary = useMemo(() => readLibraryCache(), []);
  const cachedMetadata = useMemo(() => readLibraryMetadataCache(), []);
  const [products, setProducts] = useState<Product[]>(applyLocalFavoriteState(cachedLibrary?.products || []));
  const [suppliers, setSuppliers] = useState<Supplier[]>(cachedLibrary?.suppliers || []);
  const [productTotal, setProductTotal] = useState<number | undefined>(cachedLibrary?.productTotal);
  const [filterMetadata, setFilterMetadata] = useState<LibraryFilterMetadata | null>(cachedMetadata);
  const [librarySearch, setLibrarySearch] = useState("");
  const [serverSupplierFilter, setServerSupplierFilter] = useState<string[]>([]);
  const [serverFilters, setServerFilters] = useState<{ categories: string[]; productTypes: string[]; colors: string[]; availability: string[] }>({ categories: [], productTypes: [], colors: [], availability: [] });
  const [pageOffset, setPageOffset] = useState(0);
  const [loading, setLoading] = useState(!cachedLibrary);
  const [refreshing, setRefreshing] = useState(false);
  const [view, setView] = useState<"vendor" | "product">("product");
  const [showModal, setShowModal] = useState(false);
  const [editProduct, setEditProduct] = useState<Partial<Product> | null>(null);
  const [detailProduct, setDetailProduct] = useState<Product | null>(null);
  const [projectAddProduct, setProjectAddProduct] = useState<Product | null>(null);
  const [animatingIds, setAnimatingIds] = useState<Set<number>>(new Set());
  const [presetSupplierId, setPresetSupplierId] = useState<number | null>(null);

  const productsRef = useRef(products);
  const suppliersRef = useRef(suppliers);
  const productTotalRef = useRef(productTotal);
  const librarySearchRef = useRef(librarySearch);
  const serverSupplierFilterRef = useRef(serverSupplierFilter);
  const serverFiltersRef = useRef(serverFilters);
  const pageOffsetRef = useRef(pageOffset);
  const loadRequestIdRef = useRef(0);

  useEffect(() => { productsRef.current = products; }, [products]);
  useEffect(() => { suppliersRef.current = suppliers; }, [suppliers]);
  useEffect(() => { productTotalRef.current = productTotal; }, [productTotal]);
  useEffect(() => { librarySearchRef.current = librarySearch; }, [librarySearch]);
  useEffect(() => { serverSupplierFilterRef.current = serverSupplierFilter; }, [serverSupplierFilter]);
  useEffect(() => { serverFiltersRef.current = serverFilters; }, [serverFilters]);
  useEffect(() => { pageOffsetRef.current = pageOffset; }, [pageOffset]);

  const load = useCallback(async (opts?: { search?: string; supplierFilter?: string[]; append?: boolean }) => {
    const requestId = ++loadRequestIdRef.current;
    const currentProducts = productsRef.current;
    const currentSuppliers = suppliersRef.current;
    if (currentProducts.length === 0 && currentSuppliers.length === 0) setLoading(true);
    else setRefreshing(true);
    try {
      const search = opts?.search ?? librarySearchRef.current;
      const supplierFilter = opts?.supplierFilter ?? serverSupplierFilterRef.current;
      const supplierIds = supplierFilter
        .map((supplierName) => suppliersRef.current.find((supplier) => supplier.name === supplierName)?.id)
        .filter((id): id is number => typeof id === "number");
      const offset = opts?.append ? pageOffsetRef.current + INITIAL_CARD_RENDER_LIMIT : 0;
      const [ssRes, psRes, metaRes] = await Promise.allSettled([
        apiClient.list_suppliers().then((r) => r.json()),
        apiClient.request<ProductPage>({
          path: "/routes/products/page",
          method: "GET",
          query: {
            favorites_only: false,
            search: search || undefined,
            supplier_ids: supplierIds.length > 0 ? supplierIds.join(",") : undefined,
            categories: serverFiltersRef.current.categories.length ? serverFiltersRef.current.categories.join(",") : undefined,
            product_types: serverFiltersRef.current.productTypes.length ? serverFiltersRef.current.productTypes.join(",") : undefined,
            colors: serverFiltersRef.current.colors.length ? serverFiltersRef.current.colors.join(",") : undefined,
            availability: serverFiltersRef.current.availability.length ? serverFiltersRef.current.availability.join(",") : undefined,
            limit: INITIAL_CARD_RENDER_LIMIT,
            offset,
          },
        }).then((r) => r.json()),
        apiClient.request<LibraryFilterMetadata>({
          path: "/routes/products/filter-metadata",
          method: "GET",
        }).then((r) => r.json()),
      ]);
      if (requestId !== loadRequestIdRef.current) return;
      let nextSuppliers = suppliersRef.current;
      let nextProducts = productsRef.current;
      let nextTotal = productTotalRef.current;
      if (ssRes.status === "fulfilled") {
        nextSuppliers = ssRes.value as unknown as Supplier[];
        setSuppliers(nextSuppliers);
        suppliersRef.current = nextSuppliers;
      }
      if (psRes.status === "fulfilled") {
        const page = psRes.value;
        const pageItems = applyLocalFavoriteState(page.items || []);
        nextProducts = opts?.append
          ? [
              ...productsRef.current,
              ...pageItems.filter((item) => !productsRef.current.some((existing) => existing.id === item.id)),
            ]
          : pageItems;
        nextTotal = page.total;
        setProducts(nextProducts);
        setProductTotal(page.total);
        setPageOffset(offset);
        productsRef.current = nextProducts;
        productTotalRef.current = page.total;
        pageOffsetRef.current = offset;
      }
      if (metaRes.status === "fulfilled") {
        setFilterMetadata(metaRes.value);
        writeLibraryMetadataCache(metaRes.value);
      }
      if (ssRes.status === "fulfilled" || psRes.status === "fulfilled") {
        writeLibraryCache(nextSuppliers, nextProducts, nextTotal);
      } else {
        console.error("Products load failed:", (psRes as PromiseRejectedResult).reason);
        toast.error("Failed to load products — please sign in");
      }
    } catch {
      if (requestId === loadRequestIdRef.current) toast.error("Failed to load library");
    } finally {
      if (requestId === loadRequestIdRef.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const searchLibraryPage = useCallback((search: string) => {
    setLibrarySearch(search);
    librarySearchRef.current = search;
    load({ search, supplierFilter: serverSupplierFilterRef.current, append: false });
  }, [load]);

  const applyServerFilters = useCallback((f: ServerFilterSelection) => {
    setServerSupplierFilter(f.suppliers);
    serverSupplierFilterRef.current = f.suppliers;
    const next = { categories: f.categories, productTypes: f.productTypes, colors: f.colors, availability: f.availability };
    setServerFilters(next);
    serverFiltersRef.current = next;
    setProducts([]);
    productsRef.current = [];
    setProductTotal(undefined);
    productTotalRef.current = undefined;
    setPageOffset(0);
    pageOffsetRef.current = 0;
    load({ search: librarySearchRef.current, supplierFilter: f.suppliers, append: false });
  }, [load]);

  const loadMoreProducts = useCallback(() => {
    load({ supplierFilter: serverSupplierFilterRef.current, append: true });
  }, [load]);

  const toggleFavorite = async (id: number) => {
    setAnimatingIds((prev) => new Set(prev).add(id));
    setTimeout(() => {
      setAnimatingIds((prev) => { const next = new Set(prev); next.delete(id); return next; });
    }, 350);
    const target = products.find((p) => p.id === id);
    const nextFavorited = !target?.is_favorited;
    setLocalFavorite(id, nextFavorited);
    setProducts((prev) => {
      const next = prev.map((p) => p.id === id ? { ...p, is_favorited: nextFavorited } : p);
      writeLibraryCache(suppliers, next, productTotal);
      return next;
    });
    try {
      await apiClient.toggle_favorite({ productId: id });
    } catch {
      toast.info("Saved locally. Favorites will stay on this device.");
    }
  };

  const deleteProduct = async (id: number) => {
    if (!confirm("Delete this product?")) return;
    try {
      await apiClient.delete_product({ productId: id });
      setProducts((prev) => prev.filter((p) => p.id !== id));
      toast.success("Product deleted");
    } catch {
      toast.error("Failed to delete");
    }
  };

  const updateProductPrice = (id: number, price: number, ts: string) => {
    setProducts((prev) =>
      prev.map((p) => p.id === id ? { ...p, current_price: price, price_updated_at: ts } : p)
    );
  };

  const syncAllPrices = async () => {
    const supplierIds = suppliers.map((supplier) => supplier.id);
    if (supplierIds.length === 0) return;
    try {
      await apiClient.sync_prices_bulk({ supplier_ids: supplierIds });
      toast.success("Prices synced");
      await load({ search: librarySearch, append: false });
    } catch {
      toast.error("Price sync failed");
    }
  };

  const openAddProduct = (supplierId?: number) => {
    setPresetSupplierId(supplierId ?? null);
    setEditProduct(supplierId ? { supplier_id: supplierId } : null);
    setShowModal(true);
  };
  const libraryScopeLabel = serverSupplierFilter.length === 1
    ? `from ${serverSupplierFilter[0]}`
    : serverSupplierFilter.length > 1
      ? `from ${serverSupplierFilter.length} suppliers`
      : `across ${suppliers.length} suppliers`;

  return (
    <Layout>
      {/* Header */}
      <header className="sticky top-0 z-10 flex flex-wrap items-center justify-between gap-3 px-4 sm:px-10 py-4 border-b border-stone-200" style={{ backgroundColor: "rgb(var(--ll-page))" }}>
        <div>
          <h1 className="text-xl font-semibold text-stone-800" style={{ fontFamily: "'Sora', system-ui, sans-serif" }}>Product Library</h1>
          <p className="text-xs text-stone-500 mt-0.5">
            {loading && products.length === 0 && suppliers.length === 0
              ? "Checking product library..."
              : `${(productTotal ?? products.length).toLocaleString()} products ${libraryScopeLabel}`}
            {refreshing && <span className="ml-2 text-emerald-700">Refreshing…</span>}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* View toggle */}
          <div className="flex items-center rounded-lg border border-stone-200 bg-white overflow-hidden">
            <button
              onClick={() => setView("vendor")}
              className={`flex items-center gap-1.5 px-3.5 py-2 text-sm font-medium transition-colors ${
                view === "vendor" ? "bg-emerald-700 text-white" : "text-stone-500 hover:text-stone-700 hover:bg-stone-50"
              }`}
            >
              <Store size={14} />
              Vendor View
            </button>
            <button
              onClick={() => setView("product")}
              className={`flex items-center gap-1.5 px-3.5 py-2 text-sm font-medium transition-colors ${
                view === "product" ? "bg-emerald-700 text-white" : "text-stone-500 hover:text-stone-700 hover:bg-stone-50"
              }`}
            >
              <Grid3X3 size={14} />
              Product View
            </button>
          </div>
        </div>
      </header>

      <div className="px-4 sm:px-10 py-6">
        {view === "vendor" ? (
          loading && products.length === 0 && suppliers.length === 0 ? (
            <div className="flex min-h-[360px] flex-col items-center justify-center rounded-xl border border-stone-200 bg-white text-center">
              <div className="mb-4 h-8 w-8 animate-spin rounded-full border-2 border-emerald-600 border-t-transparent" />
              <p className="text-sm font-semibold text-stone-700">Loading vendor catalog</p>
            </div>
          ) : (
          <VendorView
            suppliers={suppliers}
            products={products}
            animatingIds={animatingIds}
            onFavorite={toggleFavorite}
            onProjectAdd={setProjectAddProduct}
            onAddProduct={(sid) => openAddProduct(sid)}
            onPriceUpdated={updateProductPrice}
            onOpenProduct={setDetailProduct}
          />
          )
        ) : (
          <ProductView
            products={products}
            animatingIds={animatingIds}
            onFavorite={toggleFavorite}
            onProjectAdd={setProjectAddProduct}
            onAddProduct={() => openAddProduct()}
            onPriceUpdated={updateProductPrice}
            onSyncAll={syncAllPrices}
            onOpenProduct={setDetailProduct}
            hideCategoryTabs
            totalProductCount={productTotal}
            filterMetadata={filterMetadata}
            isPagePartial={(productTotal ?? products.length) > products.length}
            pageLoading={refreshing}
            initialLoading={loading && products.length === 0}
            onSearchChange={searchLibraryPage}
            onServerFiltersChange={applyServerFilters}
            onLoadMore={loadMoreProducts}
            canLoadMore={(productTotal ?? products.length) > products.length}
          />
        )}
      </div>

      {detailProduct && (
        <ProductDetailModal product={detailProduct} onClose={() => setDetailProduct(null)} />
      )}

      {projectAddProduct && (
        <AddToProjectModal product={projectAddProduct} onClose={() => setProjectAddProduct(null)} />
      )}

      {showModal && (
        <ProductModal
          product={editProduct}
          suppliers={suppliers}
          onClose={() => { setShowModal(false); setEditProduct(null); setPresetSupplierId(null); }}
          onSave={(p) => {
            setProducts((prev) =>
              prev.some((x) => x.id === p.id)
                ? prev.map((x) => (x.id === p.id ? p : x))
                : [p, ...prev]
            );
          }}
        />
      )}
    </Layout>
  );
}
