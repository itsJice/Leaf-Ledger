// Flat product catalog view: search, dropdown filters, category tabs,
// infinite scroll and the product grid.
// Moved verbatim out of pages/Library.tsx (WP 4.2 library-extract).
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Search, Heart, RefreshCw, RotateCcw, X, Leaf } from "lucide-react";
import { categoryLabel } from "utils/format";
import { useInfiniteScroll } from "../../hooks/useInfiniteScroll";
import { INITIAL_CARD_RENDER_LIMIT } from "./constants";
import { normalizeSearchText, looksLikeCodeQuery, matchesNormalizedTokens } from "./search";
import { buildProductSearchEntry } from "./facets";
import { MultiSelectFilter } from "./MultiSelectFilter";
import { ProductCard } from "./ProductCard";
import type { Product, LibraryFilterMetadata, ServerFilterSelection, ProductSearchEntry } from "./types";

// ─── Product View ────────────────────────────────────────────────────────────
export function ProductView({
  products,
  animatingIds,
  onFavorite,
  onProjectAdd,
  onAddProduct,
  onPriceUpdated,
  onSyncAll,
  onOpenProduct,
  hideSyncAll = false,
  hideFavoritesToggle = false,
  hideCategoryTabs = false,
  emptyTitle = "No products found",
  emptyDescription,
  totalProductCount,
  filterMetadata,
  isPagePartial = false,
  pageLoading = false,
  initialLoading = false,
  onSearchChange,
  onServerFiltersChange,
  onLoadMore,
  canLoadMore = false,
}: {
  products: Product[];
  animatingIds: Set<number>;
  onFavorite: (id: number) => void;
  onProjectAdd?: (product: Product) => void;
  onAddProduct?: () => void;
  onPriceUpdated?: (id: number, price: number, ts: string) => void;
  onSyncAll?: () => Promise<void>;
  onOpenProduct: (p: Product) => void;
  hideSyncAll?: boolean;
  hideFavoritesToggle?: boolean;
  hideCategoryTabs?: boolean;
  emptyTitle?: string;
  emptyDescription?: string;
  totalProductCount?: number;
  filterMetadata?: LibraryFilterMetadata | null;
  isPagePartial?: boolean;
  pageLoading?: boolean;
  initialLoading?: boolean;
  onSearchChange?: (search: string) => void;
  onServerFiltersChange?: (filters: ServerFilterSelection) => void;
  onLoadMore?: () => void;
  canLoadMore?: boolean;
}) {
  const [syncing, setSyncing] = useState(false);

  const handleSyncAll = async () => {
    if (!onSyncAll) return;
    setSyncing(true);
    try {
      await onSyncAll();
    } finally {
      setSyncing(false);
    }
  };
  const [activeCategory, setActiveCategory] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [activeSearch, setActiveSearch] = useState("");
  const [favoritesOnly, setFavoritesOnly] = useState(false);
  const [categoryFilter, setCategoryFilter] = useState<string[]>([]);
  const [productTypeFilter, setProductTypeFilter] = useState<string[]>([]);
  const [supplierFilter, setSupplierFilter] = useState<string[]>([]);
  const [colorFilter, setColorFilter] = useState<string[]>([]);
  const [sizeFilter, setSizeFilter] = useState<string[]>([]);
  const [availabilityFilter, setAvailabilityFilter] = useState<string[]>([]);
  const [countryFilter, setCountryFilter] = useState<string[]>([]);
  const [visibleLimit, setVisibleLimit] = useState(INITIAL_CARD_RENDER_LIMIT);
  const didNotifySearchMount = useRef(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setActiveSearch(searchInput), 200);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  useEffect(() => {
    if (!didNotifySearchMount.current) {
      didNotifySearchMount.current = true;
      return;
    }
    onSearchChange?.(activeSearch);
  }, [activeSearch, onSearchChange]);

  // Kept in refs (not effect deps) so a fresh filterMetadata or callback
  // reference does NOT re-fire the filter effect — that caused a reload loop.
  const categoryValueByLabelRef = useRef<Record<string, string>>({});
  useEffect(() => {
    const map: Record<string, string> = {};
    for (const option of filterMetadata?.categories || []) {
      if (option.value) map[categoryLabel(option.value)] = option.value;
    }
    categoryValueByLabelRef.current = map;
  }, [filterMetadata]);

  const onServerFiltersChangeRef = useRef(onServerFiltersChange);
  useEffect(() => { onServerFiltersChangeRef.current = onServerFiltersChange; }, [onServerFiltersChange]);

  const didNotifyFiltersMount = useRef(false);
  useEffect(() => {
    if (!didNotifyFiltersMount.current) {
      didNotifyFiltersMount.current = true;
      return;
    }
    onServerFiltersChangeRef.current?.({
      suppliers: supplierFilter,
      categories: categoryFilter.map((label) => categoryValueByLabelRef.current[label] ?? label),
      productTypes: productTypeFilter,
      colors: colorFilter,
      availability: availabilityFilter,
    });
  }, [supplierFilter, categoryFilter, productTypeFilter, colorFilter, availabilityFilter]);

  const productIndex = useMemo(() => products.map(buildProductSearchEntry), [products]);

  const categoryCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const entry of productIndex) {
      counts.set(entry.category, (counts.get(entry.category) || 0) + 1);
    }
    return counts;
  }, [productIndex]);

  const metadataCategoryCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const option of filterMetadata?.categories || []) {
      if (option.value) counts.set(option.value, option.count || 0);
    }
    return counts;
  }, [filterMetadata]);

  const dynamicCategories = useMemo(
    () => {
      const metadataCategories = filterMetadata?.categories?.map((option) => option.value).filter(Boolean);
      if (metadataCategories?.length) return metadataCategories;
      return Array.from(categoryCounts.keys()).sort((a, b) => (categoryCounts.get(b) || 0) - (categoryCounts.get(a) || 0));
    },
    [categoryCounts, filterMetadata]
  );

  const normalizedSearch = useMemo(() => normalizeSearchText(activeSearch), [activeSearch]);
  const searchTokens = useMemo(() => normalizedSearch.split(" ").filter(Boolean), [normalizedSearch]);
  const rawSearch = activeSearch.trim().toLowerCase();
  const shouldSearchCodes = rawSearch.length >= 4 || looksLikeCodeQuery(rawSearch);

  const baseFiltered = useMemo(() => productIndex.filter((entry) => {
    if (favoritesOnly && !entry.isFavorited) return false;
    if (activeCategory && entry.category !== activeCategory) return false;
    return true;
  }), [productIndex, favoritesOnly, activeCategory]);

  const matchesTextFilters = useCallback((entry: ProductSearchEntry) => {
    if (!normalizedSearch) return true;
    const matchesVisibleText = matchesNormalizedTokens(entry.searchText, searchTokens);
    const matchesCodeText =
      shouldSearchCodes &&
      (entry.codeText.includes(rawSearch) || matchesNormalizedTokens(entry.codeText, searchTokens));
    return matchesVisibleText || matchesCodeText;
  }, [normalizedSearch, rawSearch, searchTokens, shouldSearchCodes]);

  const matchesStructuredFilters = useCallback((entry: ProductSearchEntry, exclude?: {
    category?: boolean;
    productType?: boolean;
    supplier?: boolean;
    color?: boolean;
    size?: boolean;
    availability?: boolean;
    country?: boolean;
  }) => {
    if (!exclude?.category && categoryFilter.length > 0 && !categoryFilter.includes(entry.categoryLabel)) return false;
    if (!exclude?.productType && productTypeFilter.length > 0 && !productTypeFilter.some((type) => entry.productTypes.includes(type))) return false;
    if (!exclude?.supplier && supplierFilter.length > 0 && !supplierFilter.includes(entry.supplierName)) return false;
    if (!exclude?.color && colorFilter.length > 0 && !colorFilter.some((color) => entry.colors.includes(color))) return false;
    if (!exclude?.size && sizeFilter.length > 0 && !sizeFilter.some((size) => entry.sizes.includes(size))) return false;
    if (!exclude?.availability && availabilityFilter.length > 0 && !availabilityFilter.includes(entry.availability || "")) return false;
    if (!exclude?.country && countryFilter.length > 0 && !countryFilter.includes(entry.country || "")) return false;
    return true;
  }, [categoryFilter, productTypeFilter, supplierFilter, colorFilter, sizeFilter, availabilityFilter, countryFilter]);

  const optionBase = useMemo(
    () => baseFiltered.filter((entry) => matchesTextFilters(entry)),
    [baseFiltered, matchesTextFilters]
  );

  // Options come straight from server metadata (full catalog, not just the
  // loaded page). Sizes & countries are omitted — no reliable data yet.
  const supplierOptions = useMemo(() => (filterMetadata?.suppliers || []).map((o) => o.value).filter(Boolean), [filterMetadata]);
  const categoryOptions = useMemo(() => (filterMetadata?.categories || []).map((o) => categoryLabel(o.value)).filter(Boolean), [filterMetadata]);
  const productTypeOptions = useMemo(() => (filterMetadata?.product_types || []).map((o) => o.value).filter(Boolean), [filterMetadata]);
  const colorOptions = useMemo(() => (filterMetadata?.colors || []).map((o) => o.value).filter(Boolean), [filterMetadata]);
  const availabilityOptions = useMemo(() => (filterMetadata?.availability || []).map((o) => o.value).filter(Boolean), [filterMetadata]);

  // The server already applied search + all dropdown filters, so the loaded
  // products are the result set. The client only narrows by the favorites
  // toggle + active category tab (handled in baseFiltered).
  const filtered = baseFiltered;
  void matchesStructuredFilters;
  void matchesTextFilters;
  void optionBase;

  const sortedEntries = useMemo(() => [...filtered].sort((a, b) => {
    if (a.isFavorited && !b.isFavorited) return -1;
    if (!a.isFavorited && b.isFavorited) return 1;
    return a.sortName.localeCompare(b.sortName);
  }), [filtered]);
  const sorted = useMemo(() => sortedEntries.map((entry) => entry.product), [sortedEntries]);
  const visibleProducts = sorted.slice(0, visibleLimit);
  const shownResultCount = totalProductCount ?? sorted.length;
  const countLabel = initialLoading ? "…" : (totalProductCount ?? products.length).toLocaleString();

  useEffect(() => {
    setVisibleLimit(INITIAL_CARD_RENDER_LIMIT);
  }, [activeCategory, activeSearch, favoritesOnly, categoryFilter, productTypeFilter, supplierFilter, colorFilter, sizeFilter, availabilityFilter, countryFilter]);

  const hasActiveDropdownFilters =
    categoryFilter.length > 0 || productTypeFilter.length > 0 || supplierFilter.length > 0 ||
    colorFilter.length > 0 || availabilityFilter.length > 0;

  const resetFilters = () => {
    setCategoryFilter([]);
    setProductTypeFilter([]);
    setSupplierFilter([]);
    setColorFilter([]);
    setSizeFilter([]);
    setAvailabilityFilter([]);
    setCountryFilter([]);
  };

  // ── Infinite scroll + prefetch ──────────────────────────────────────────────
  // Reveal more cards as you scroll, and keep the NEXT server page loaded one
  // step ahead so reaching the bottom feels instant instead of blocking.
  const setInfiniteScrollSentinel = useInfiniteScroll({
    enabled: !pageLoading,
    onLoadMore: () => {
      if (visibleLimit < sorted.length) {
        setVisibleLimit((limit) => limit + INITIAL_CARD_RENDER_LIMIT);
      } else if (canLoadMore) {
        onLoadMore?.();
      }
    },
    rootMargin: "800px 0px", // trigger ~800px early so the next batch is ready
  });

  // Keep ~one rendered page of buffer ahead by prefetching the next server page.
  useEffect(() => {
    if (!pageLoading && canLoadMore && sorted.length - visibleLimit < INITIAL_CARD_RENDER_LIMIT) {
      onLoadMore?.();
    }
  }, [visibleLimit, sorted.length, canLoadMore, pageLoading, onLoadMore]);

  return (
    <div>
      {!hideCategoryTabs && (
        <div className="flex items-center gap-1 mb-5 border-b border-stone-200 pb-0 overflow-x-auto">
          <button
            onClick={() => setActiveCategory("")}
            className={`flex-shrink-0 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px ${
              activeCategory === ""
                ? "border-emerald-600 text-emerald-700"
                : "border-transparent text-stone-500 hover:text-stone-700"
            }`}
          >
            All <span className="text-xs text-stone-400 ml-1">({countLabel})</span>
          </button>
          {dynamicCategories.map((cat) => (
            <button
              key={cat}
              onClick={() => setActiveCategory(activeCategory === cat ? "" : cat)}
              className={`flex-shrink-0 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px ${
                activeCategory === cat
                  ? "border-emerald-600 text-emerald-700"
                  : "border-transparent text-stone-500 hover:text-stone-700"
              }`}
            >
              {categoryLabel(cat)}
              <span className="text-xs text-stone-400 ml-1">({(metadataCategoryCounts.get(cat) ?? categoryCounts.get(cat) ?? 0).toLocaleString()})</span>
            </button>
          ))}
        </div>
      )}

      {/* Search + favorites row */}
      <div className="flex items-center gap-3 mb-5 flex-wrap">
        <div className="relative flex-1 max-w-xs">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-400" />
          <input
            className="w-full pl-9 pr-3 py-2 text-sm border border-stone-200 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-emerald-300"
            placeholder="Search products..."
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
          />
        </div>
        <div className="text-sm font-medium text-stone-500 tabular-nums">
          {initialLoading
            ? "Loading products..."
            : pageLoading
              ? "Searching..."
              : `${shownResultCount.toLocaleString()} ${shownResultCount === 1 ? "result" : "results"}`}
          {isPagePartial && !pageLoading && <span className="ml-1 font-normal text-stone-400">({products.length.toLocaleString()} loaded)</span>}
        </div>
        {!hideFavoritesToggle && (
          <button
            onClick={() => setFavoritesOnly((v) => !v)}
            className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm border transition-all ${
              favoritesOnly
                ? "border-orange-300 bg-orange-50 text-orange-700"
                : "border-stone-200 bg-white text-stone-500 hover:text-stone-700"
            }`}
          >
            <Heart
              size={13}
              fill={favoritesOnly ? "rgb(var(--ll-fav))" : "none"}
              style={{ color: favoritesOnly ? "rgb(var(--ll-fav))" : "rgb(var(--nc-400))" }}
            />
            Favorites
          </button>
        )}
        {(searchInput || activeSearch || favoritesOnly || activeCategory || categoryFilter.length > 0 || productTypeFilter.length > 0 || supplierFilter.length > 0 || colorFilter.length > 0 || sizeFilter.length > 0 || availabilityFilter.length > 0 || countryFilter.length > 0) && (
          <button
            onClick={() => {
              setSearchInput("");
              setActiveSearch("");
              setFavoritesOnly(false);
              setActiveCategory("");
              setCategoryFilter([]);
              setProductTypeFilter([]);
              setSupplierFilter([]);
              setColorFilter([]);
              setSizeFilter([]);
              setAvailabilityFilter([]);
              setCountryFilter([]);
            }}
            className="text-xs text-stone-500 hover:text-stone-700 flex items-center gap-1"
          >
            <X size={12} /> Clear
          </button>
        )}
        {!hideSyncAll && (
          <div className="ml-auto">
            <button
              onClick={handleSyncAll}
              disabled={syncing || products.length === 0}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm border border-stone-200 bg-white text-stone-600 hover:text-emerald-700 hover:border-emerald-300 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <RefreshCw size={13} className={syncing ? "animate-spin" : ""} />
              {syncing ? "Syncing…" : "Sync Prices"}
            </button>
          </div>
        )}
      </div>

      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wide text-stone-400">Filters</span>
        <button
          onClick={resetFilters}
          disabled={!hasActiveDropdownFilters}
          className="flex items-center gap-1 rounded-lg border border-stone-200 bg-white px-2.5 py-1.5 text-xs font-medium text-stone-500 transition-all hover:border-emerald-300 hover:text-emerald-700 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-stone-200 disabled:hover:text-stone-500"
        >
          <RotateCcw size={12} /> Reset filters
        </button>
      </div>
      <div className="mb-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        <MultiSelectFilter
          label="All categories"
          options={categoryOptions}
          selected={categoryFilter}
          onChange={setCategoryFilter}
        />
        <MultiSelectFilter
          label="All suppliers"
          options={supplierOptions}
          selected={supplierFilter}
          onChange={setSupplierFilter}
        />
        <MultiSelectFilter
          label="All colors"
          options={colorOptions}
          selected={colorFilter}
          onChange={setColorFilter}
        />
      </div>

      {/* Grid */}
      {initialLoading || (pageLoading && sorted.length === 0) ? (
        <div className="flex min-h-[360px] flex-col items-center justify-center rounded-xl border border-stone-200 bg-white text-center">
          <div className="mb-4 h-8 w-8 animate-spin rounded-full border-2 border-emerald-600 border-t-transparent" />
          <p className="text-sm font-semibold text-stone-700">{initialLoading ? "Loading product catalog" : "Loading filtered products"}</p>
          <p className="mt-1 max-w-xs text-xs text-stone-400">
            Product cards will appear here as soon as the matching catalog page is loaded.
          </p>
        </div>
      ) : sorted.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <div className="w-16 h-16 rounded-full flex items-center justify-center mb-4" style={{ backgroundColor: "rgb(var(--ll-brand-soft))" }}>
            <Leaf size={28} className="text-emerald-600" strokeWidth={1.5} />
          </div>
          <p className="text-base font-medium text-stone-600 mb-1">{emptyTitle}</p>
          <p className="text-sm text-stone-400 max-w-xs leading-relaxed mb-4">
            {emptyDescription || (products.length === 0
              ? "Add your first plant, container, or accent to start building projects."
              : "Try adjusting your filters.")}
          </p>
          {products.length === 0 && onAddProduct && (
            <button
              onClick={onAddProduct}
              className="px-4 py-2 text-sm font-semibold text-white rounded-lg hover:opacity-90"
              style={{ backgroundColor: "rgb(var(--ll-brand))" }}
            >
              Add First Product
            </button>
          )}
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 xl:grid-cols-3 2xl:grid-cols-4">
            {visibleProducts.map((p) => (
              <ProductCard
                key={p.id}
                p={p}
                animating={animatingIds.has(p.id)}
                onFavorite={onFavorite}
                onProjectAdd={onProjectAdd}
                onPriceUpdated={onPriceUpdated}
                onOpen={onOpenProduct}
              />
            ))}
          </div>
          {/* Infinite-scroll sentinel — auto-loads the next batch as you approach it */}
          <div ref={setInfiniteScrollSentinel} className="h-px w-full" aria-hidden />
          {(visibleLimit < sorted.length || canLoadMore) && (
            <div className="mt-5 flex justify-center">
              {pageLoading ? (
                <div className="flex items-center gap-2 text-sm text-stone-400">
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-emerald-500 border-t-transparent" />
                  Loading more…
                </div>
              ) : (
                <button
                  onClick={() => {
                    if (visibleLimit < sorted.length) setVisibleLimit((limit) => limit + INITIAL_CARD_RENDER_LIMIT);
                    else onLoadMore?.();
                  }}
                  className="rounded-lg border border-stone-200 bg-white px-4 py-2 text-sm font-semibold text-stone-600 hover:border-emerald-300 hover:text-emerald-700"
                >
                  Show more products ({Math.min(products.length, shownResultCount).toLocaleString()} of {shownResultCount.toLocaleString()})
                </button>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
