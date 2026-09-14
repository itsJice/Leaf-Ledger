import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CheckCircle2, LayoutGrid, List, Maximize2, Minimize2, Minus, Package, Plus, Search, X } from "lucide-react";
import { apiFetch } from "utils/apiFetch";
import { formatCurrency } from "utils/format";
import {
  hasNoSupplierImage,
  hasSupplierPlaceholderImage,
  productDisplayImageUrl,
  type Product as LibraryProduct,
} from "../Library";
import type { ScopeFilterSlot, BuilderCardSize, CatalogSelection } from "./types";
import {
  BUILDER_CATALOG_VIEW_KEY,
  BUILDER_CATALOG_SIZE_KEY,
  BUILDER_CATALOG_PAGE_SIZE,
  EMPTY_CATALOG_SELECTION,
} from "./constants";
import { sortedScopeTerms } from "./builderTypes";
import { builderProductName } from "./parts";

// Same card/size vocabulary as Catalog Search, tuned one step tighter because
// the builder's catalog lives in a pane rather than a full page.
const BUILDER_GRID_COLS: Record<BuilderCardSize, string> = {
  1: "grid-cols-3 sm:grid-cols-4 xl:grid-cols-6",
  2: "grid-cols-2 sm:grid-cols-3 xl:grid-cols-5",
  3: "grid-cols-2 sm:grid-cols-3 xl:grid-cols-4",
  4: "grid-cols-1 sm:grid-cols-2 xl:grid-cols-3",
};
const BUILDER_IMG_HEIGHT: Record<BuilderCardSize, string> = { 1: "h-20", 2: "h-28", 3: "h-36", 4: "h-48" };

/**
 * Choose Parts, on the same index the Catalog Search page uses.
 *
 * It talks to `/api/products/search` - the warm in-memory index that answers
 * without touching the database - instead of paging the whole catalog into the
 * browser first, so it is as responsive as `/search` and the user can page
 * through everything rather than a preloaded slice.
 *
 * When a scope slot is active its measured vocabulary is pre-applied: choosing
 * Container asks for Containers & Vases (so containers come first and dried
 * botanicals never do), choosing Top Dressing asks for foam / moss / rocks.
 * Every one of those is a removable chip - the API's contract is
 * `mandatory: false`.
 */
export function BuilderProductPicker({
  activePartLabel,
  initialQuery = "",
  scopeFilters,
  selectedProductIds,
  selectedProductItemIds,
  onAdd,
  onRemove,
  onOpenProduct,
  onContinue,
  expanded = false,
  onToggleExpanded,
}: {
  activePartLabel: string;
  initialQuery?: string;
  scopeFilters?: ScopeFilterSlot | null;
  selectedProductIds: Set<number>;
  selectedProductItemIds: Map<number, number>;
  onAdd: (product: LibraryProduct) => void;
  onRemove: (itemId: number) => void;
  onOpenProduct: (product: LibraryProduct) => void;
  onContinue: () => void;
  expanded?: boolean;
  onToggleExpanded?: () => void;
}) {
  const [query, setQuery] = useState("");
  const [activeQuery, setActiveQuery] = useState("");
  const [sel, setSel] = useState<CatalogSelection>(EMPTY_CATALOG_SELECTION);
  const [items, setItems] = useState<LibraryProduct[]>([]);
  const [facets, setFacets] = useState<{ categories?: { value: string; count?: number }[]; colors?: { value: string; count?: number }[] }>({});
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const seq = useRef(0);
  const suggestedQuery = initialQuery.trim();

  const [viewMode, setViewMode] = useState<"grid" | "list">(
    () => (window.localStorage.getItem(BUILDER_CATALOG_VIEW_KEY) as "grid" | "list") || "grid"
  );
  const [cardSize, setCardSize] = useState<BuilderCardSize>(
    () => (Number(window.localStorage.getItem(BUILDER_CATALOG_SIZE_KEY)) as BuilderCardSize) || 2
  );
  useEffect(() => { window.localStorage.setItem(BUILDER_CATALOG_VIEW_KEY, viewMode); }, [viewMode]);
  useEffect(() => { window.localStorage.setItem(BUILDER_CATALOG_SIZE_KEY, String(cardSize)); }, [cardSize]);

  // The slot's vocabulary, ranked so a pre-applied term always returns results:
  // a term the catalog cannot match is demoted, never dropped.
  const scopeTerms = useMemo(() => sortedScopeTerms(scopeFilters?.search_terms || []), [scopeFilters]);
  const scopeCategories = useMemo(
    () => (scopeFilters?.filters?.categories || []).map((row) => row.value),
    [scopeFilters]
  );
  const scopeColors = useMemo(() => (scopeFilters?.filters?.colors || []).map((row) => row.value), [scopeFilters]);
  const scopeProductTypes = useMemo(
    () => (scopeFilters?.filters?.product_types || []).map((row) => row.value),
    [scopeFilters]
  );
  const excludeCategories = scopeFilters?.exclude_categories || [];

  // Pre-apply on slot change: the slot's categories, colors and product types,
  // plus its single strongest catalog-verified term as the keyword. Only one
  // term goes into the box because the search ANDs its words - stacking the whole
  // vocabulary would match nothing.
  useEffect(() => {
    if (!scopeFilters) {
      setSel(EMPTY_CATALOG_SELECTION);
      setQuery(suggestedQuery);
      setActiveQuery(suggestedQuery);
      return;
    }
    setSel({ categories: scopeCategories, colors: scopeColors, product_types: scopeProductTypes });
    const topTerm = scopeTerms.find((term) => term.catalog_verified !== false)?.term || "";
    setQuery(topTerm);
    setActiveQuery(topTerm);
    // Deliberately keyed to the slot only. The derived arrays below are all
    // computed from `scopeFilters`, so listing them would just re-apply the
    // filters and overwrite whatever the designer removed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scopeFilters, activePartLabel]);

  useEffect(() => {
    const handle = window.setTimeout(() => setActiveQuery(query.trim()), 250);
    return () => window.clearTimeout(handle);
  }, [query]);

  const load = useCallback(
    (nextOffset: number, append: boolean) => {
      const s = ++seq.current;
      setLoading(true);
      const params = new URLSearchParams();
      if (sel.categories.length) params.set("categories", sel.categories.join(","));
      if (sel.colors.length) params.set("colors", sel.colors.join(","));
      if (sel.product_types.length) params.set("product_types", sel.product_types.join(","));
      if (activeQuery) params.set("search", activeQuery);
      params.set("limit", String(BUILDER_CATALOG_PAGE_SIZE));
      params.set("offset", String(nextOffset));
      apiFetch(`/api/products/search?${params.toString()}`)
        .then((response) => (response.ok ? response.json() : Promise.reject(new Error("search failed"))))
        .then((data) => {
          if (s !== seq.current) return;
          const rows = (Array.isArray(data?.items) ? data.items : []) as LibraryProduct[];
          setItems((prev) => (append ? [...prev, ...rows] : rows));
          setTotal(Number(data?.total) || 0);
          setOffset(nextOffset);
          if (!append && data?.facets) setFacets(data.facets);
        })
        .catch(() => {
          if (s !== seq.current) return;
          if (!append) { setItems([]); setTotal(0); }
        })
        .finally(() => { if (s === seq.current) setLoading(false); });
    },
    [sel, activeQuery]
  );

  useEffect(() => { load(0, false); }, [load]);

  const clearSmartFilters = () => {
    setSel(EMPTY_CATALOG_SELECTION);
    setQuery("");
  };

  const removeChip = (group: keyof CatalogSelection, value: string) =>
    setSel((prev) => ({ ...prev, [group]: prev[group].filter((item) => item !== value) }));

  const toggleFacet = (group: keyof CatalogSelection, value: string) =>
    setSel((prev) => ({
      ...prev,
      [group]: prev[group].includes(value) ? prev[group].filter((item) => item !== value) : [...prev[group], value],
    }));

  const activeChipCount = sel.categories.length + sel.colors.length + sel.product_types.length + (activeQuery ? 1 : 0);
  // A slot's excludes are enforced by asking for its own categories instead:
  // Container asks for Containers & Vases, so dried botanicals cannot surface.
  const excludesEnforced = excludeCategories.length > 0 && sel.categories.length > 0;
  const visible = items;

  return (
    <div className="flex h-full flex-col">
      <div className="space-y-3 border-b border-stone-100 p-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-400" size={16} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={suggestedQuery ? `Search the catalog, or try "${suggestedQuery}"` : "Search the catalog"}
            className="w-full rounded-xl border border-stone-200 py-2.5 pl-9 pr-9 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
          />
          {query && (
            <button
              type="button"
              onClick={() => setQuery("")}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-stone-400 hover:text-stone-700"
            >
              <X size={15} />
            </button>
          )}
        </div>

        {/* Pre-applied smart filters. Removable, one by one or all at once. */}
        {(sel.categories.length > 0 || sel.colors.length > 0 || sel.product_types.length > 0) && (
          <div className="rounded-xl border border-emerald-100 bg-emerald-50/50 p-2.5">
            <div className="mb-1.5 flex items-center justify-between gap-2">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-emerald-800">
                {scopeFilters?.label || activePartLabel} filters
                {scopeFilters?.recipe_lines ? ` · from ${scopeFilters.recipe_lines} past lines` : ""}
              </span>
              <button
                type="button"
                onClick={clearSmartFilters}
                className="flex shrink-0 items-center gap-1 rounded-full bg-white px-2 py-0.5 text-[11px] font-semibold text-stone-600 ring-1 ring-stone-200 hover:text-stone-900"
              >
                <X size={11} /> Clear all
              </button>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {(["categories", "product_types", "colors"] as (keyof CatalogSelection)[]).flatMap((group) =>
                sel[group].map((value) => (
                  <button
                    key={`${group}-${value}`}
                    type="button"
                    onClick={() => removeChip(group, value)}
                    title="Remove this filter"
                    className="flex items-center gap-1 rounded-full bg-white px-2.5 py-1 text-[11px] font-semibold text-emerald-900 ring-1 ring-emerald-200 hover:bg-emerald-100"
                  >
                    {value}
                    <X size={11} className="text-emerald-600" />
                  </button>
                ))
              )}
            </div>
            {excludesEnforced && (
              <p className="mt-1.5 text-[10px] leading-relaxed text-emerald-900/70">
                Held back for this slot: {excludeCategories.join(", ")}. Remove the category chip above to see them.
              </p>
            )}
          </div>
        )}

        {/* The slot's real vocabulary. Unverified terms sort last, so the first
            suggestions always return products. */}
        {scopeTerms.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {scopeTerms.slice(0, 10).map((term) => (
              <button
                key={term.term}
                type="button"
                onClick={() => setQuery(activeQuery === term.term ? "" : term.term)}
                title={
                  term.catalog_verified === false
                    ? "Used in past builds — no catalog match for this wording"
                    : "Used in past builds"
                }
                className={`rounded-full px-2.5 py-1 text-[11px] font-medium transition-colors ${
                  activeQuery === term.term
                    ? "bg-stone-900 text-white"
                    : term.catalog_verified === false
                      ? "bg-stone-100 text-stone-400 hover:bg-stone-200"
                      : "bg-stone-100 text-stone-600 hover:bg-stone-200"
                }`}
              >
                {term.term}
              </button>
            ))}
          </div>
        )}

        {/* Facets from this very search, so the groups reflect what was searched. */}
        {(facets.categories?.length || facets.colors?.length) && sel.categories.length === 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {(facets.categories || []).slice(0, 8).map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => toggleFacet("categories", option.value)}
                className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${
                  sel.categories.includes(option.value) ? "bg-stone-900 text-white" : "bg-stone-100 text-stone-600 hover:bg-stone-200"
                }`}
              >
                {option.value}
                {option.count != null ? ` ${option.count.toLocaleString()}` : ""}
              </button>
            ))}
          </div>
        ) : null}

        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs text-stone-400">
            {loading && items.length === 0
              ? "Searching..."
              : `${items.length.toLocaleString()} of ${total.toLocaleString()} match${total === 1 ? "" : "es"}`}
            {activeChipCount > 0 ? ` · ${activeChipCount} filter${activeChipCount === 1 ? "" : "s"}` : " · whole catalog"}
          </p>
          <div className="flex items-center gap-2">
            {viewMode === "grid" && (
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => setCardSize((size) => (Math.max(1, size - 1) as BuilderCardSize))}
                  disabled={cardSize === 1}
                  title="Smaller cards (more per row)"
                  className="rounded-md border border-stone-300 p-1 text-stone-500 hover:text-stone-800 disabled:opacity-40"
                ><Minus size={13} /></button>
                <button
                  type="button"
                  onClick={() => setCardSize((size) => (Math.min(4, size + 1) as BuilderCardSize))}
                  disabled={cardSize === 4}
                  title="Bigger cards (fewer per row)"
                  className="rounded-md border border-stone-300 p-1 text-stone-500 hover:text-stone-800 disabled:opacity-40"
                ><Plus size={13} /></button>
              </div>
            )}
            <div className="flex items-center rounded-lg border border-stone-300">
              <button
                type="button"
                onClick={() => setViewMode("grid")}
                title="Card view"
                className={`rounded-l-md p-1.5 ${viewMode === "grid" ? "bg-emerald-700 text-white" : "text-stone-500 hover:text-stone-800"}`}
              ><LayoutGrid size={14} /></button>
              <button
                type="button"
                onClick={() => setViewMode("list")}
                title="List view"
                className={`rounded-r-md p-1.5 ${viewMode === "list" ? "bg-emerald-700 text-white" : "text-stone-500 hover:text-stone-800"}`}
              ><List size={14} /></button>
            </div>
            {onToggleExpanded && (
              <button
                type="button"
                onClick={onToggleExpanded}
                title={expanded ? "Shrink the catalog" : "Expand the catalog full width"}
                className="rounded-lg border border-stone-300 p-1.5 text-stone-500 hover:text-stone-800"
              >
                {expanded ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
              </button>
            )}
          </div>
        </div>

        <button
          type="button"
          onClick={onContinue}
          className="w-full rounded-xl bg-stone-900 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-40"
          disabled={selectedProductIds.size === 0}
        >
          Continue to mockup →
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-auto p-4">
        {loading && items.length === 0 ? (
          <div className="flex min-h-[280px] items-center justify-center rounded-2xl border border-dashed border-stone-300 bg-stone-50 text-center">
            <div>
              <div className="mx-auto h-8 w-8 animate-spin rounded-full border-2 border-emerald-700 border-t-transparent" />
              <p className="mt-4 font-semibold text-stone-800">Searching the catalog</p>
            </div>
          </div>
        ) : visible.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-stone-300 p-8 text-center">
            <p className="font-semibold text-stone-800">No matching products</p>
            <p className="mt-1 text-sm text-stone-400">Try a broader word, or clear the pre-applied filters above.</p>
            {activeChipCount > 0 && (
              <button
                type="button"
                onClick={clearSmartFilters}
                className="mt-3 text-sm font-semibold text-emerald-700 hover:text-emerald-900"
              >
                Clear filters
              </button>
            )}
          </div>
        ) : (
          <div className={viewMode === "list" ? "flex flex-col gap-2" : `grid gap-3 ${BUILDER_GRID_COLS[cardSize]}`}>
            {visible.map((product) => {
              const selectedItemId = selectedProductItemIds.get(product.id);
              const added = selectedItemId != null;
              const name = builderProductName(product) || product.name;
              const price = product.current_price != null ? formatCurrency(product.current_price) : "No price";
              const displayImageUrl = productDisplayImageUrl(product);
              const toggleAdd = (event: React.MouseEvent) => {
                event.preventDefault();
                event.stopPropagation();
                if (added && selectedItemId != null) onRemove(selectedItemId);
                else onAdd(product);
              };

              if (viewMode === "list") {
                return (
                  <div
                    key={product.id}
                    className={`flex items-center gap-3 rounded-xl border bg-white px-3 py-2 shadow-sm transition-all ${
                      added ? "border-emerald-700 ring-1 ring-emerald-100" : "border-stone-200 hover:border-stone-300"
                    }`}
                  >
                    <button type="button" onClick={() => onOpenProduct(product)} className="flex min-w-0 flex-1 items-center gap-3 text-left">
                      <span className="flex h-12 w-12 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-stone-50">
                        {displayImageUrl && !hasSupplierPlaceholderImage(product) ? (
                          <img src={displayImageUrl} alt={name} className="h-full w-full object-contain" />
                        ) : (
                          <Package className="text-stone-300" size={18} />
                        )}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-semibold text-stone-900">{name}</span>
                        <span className="block truncate text-xs text-stone-400">{product.supplier_sku || product.supplier_name}</span>
                      </span>
                      <span className="shrink-0 text-sm font-bold text-stone-900">{price}</span>
                    </button>
                    <button
                      type="button"
                      onClick={toggleAdd}
                      className={`shrink-0 rounded-lg px-3 py-1.5 text-xs font-semibold ${
                        added ? "bg-emerald-900 text-white" : "border border-stone-200 bg-white text-stone-800 hover:bg-stone-50"
                      }`}
                    >
                      {added ? "Added" : "Add"}
                    </button>
                  </div>
                );
              }

              return (
                <div
                  key={product.id}
                  className={`rounded-2xl border bg-white p-2.5 shadow-sm transition-all ${
                    added ? "border-emerald-700 ring-1 ring-emerald-100" : "border-stone-200 hover:border-stone-300"
                  }`}
                >
                  <button type="button" onClick={() => onOpenProduct(product)} className="block w-full text-left">
                    <div className={`mb-2 flex ${BUILDER_IMG_HEIGHT[cardSize]} items-center justify-center rounded-xl bg-stone-50`}>
                      {displayImageUrl && !hasSupplierPlaceholderImage(product) ? (
                        <img src={displayImageUrl} alt={name} className="h-full w-full object-contain" />
                      ) : (
                        <span className="px-2 text-center text-[10px] font-semibold text-stone-400">
                          {hasNoSupplierImage(product) ? "No supplier image" : hasSupplierPlaceholderImage(product) ? "Supplier placeholder" : "Image pending"}
                        </span>
                      )}
                    </div>
                    <p className={`line-clamp-2 font-semibold leading-snug text-stone-900 ${cardSize === 1 ? "text-[11px]" : "text-sm"}`}>{name}</p>
                    {cardSize > 1 && <p className="mt-1 truncate text-xs text-stone-400">{product.supplier_sku || product.supplier_name}</p>}
                    <p className={`mt-1.5 font-bold text-stone-900 ${cardSize === 1 ? "text-xs" : "text-sm"}`}>{price}</p>
                  </button>
                  <button
                    type="button"
                    onClick={toggleAdd}
                    className={`mt-2 flex w-full items-center justify-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-semibold ${
                      added ? "bg-emerald-900 text-white" : "border border-stone-200 bg-white text-stone-800 hover:bg-stone-50"
                    }`}
                  >
                    {added ? <CheckCircle2 size={14} /> : <Plus size={14} />}
                    {added ? "Added" : "Add"}
                  </button>
                </div>
              );
            })}
          </div>
        )}

        {items.length < total && (
          <div className="mt-6 flex justify-center">
            {loading ? (
              <div className="flex items-center gap-2 text-sm text-stone-400">
                <div className="h-4 w-4 animate-spin rounded-full border-2 border-emerald-500 border-t-transparent" />
                Loading more...
              </div>
            ) : (
              <button
                type="button"
                onClick={() => load(offset + BUILDER_CATALOG_PAGE_SIZE, true)}
                className="rounded-lg border border-stone-300 px-5 py-2 text-sm font-medium text-stone-700 transition-colors hover:bg-stone-100"
              >
                Load more ({(total - items.length).toLocaleString()} left)
              </button>
            )}
          </div>
        )}
      </div>

      <div className="flex items-center justify-between gap-3 border-t border-stone-100 bg-white px-4 py-3 text-xs text-stone-500">
        <span className="flex items-center gap-1 font-semibold text-emerald-800">
          <CheckCircle2 size={14} />
          {selectedProductIds.size} saved to this part
        </span>
        <span>{total.toLocaleString()} product{total === 1 ? "" : "s"} searchable</span>
      </div>
    </div>
  );
}
