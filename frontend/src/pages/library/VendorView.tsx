// Vendor-grouped catalog view: collapsible supplier sections of product
// cards. Moved verbatim out of pages/Library.tsx (WP 4.2 library-extract).
import { useState } from "react";
import { Store, ChevronRight, Package, Plus, Leaf } from "lucide-react";
import { formatCurrency } from "utils/format";
import { INITIAL_CARD_RENDER_LIMIT } from "./constants";
import { productDisplayImageUrl } from "./display";
import { ProductCard } from "./ProductCard";
import type { Product, Supplier } from "./types";

// ─── Category pill config ────────────────────────────────────────────────────
// A soft tinted chip with its own ink. Both halves resolve through `--badge-*`
// in index.css: light mode keeps the original pastels, dark mode swaps in a deep
// tint with bright ink so the row of pills doesn't glare off a dark page.
const CAT_PILL: Record<string, { bg: string; text: string; label: string }> = {
  greenery:   { bg: "rgb(var(--badge-greenery-bg))",   text: "rgb(var(--badge-greenery-fg))",   label: "Greenery" },
  florals:    { bg: "rgb(var(--badge-florals-bg))",    text: "rgb(var(--badge-florals-fg))",    label: "Florals" },
  trees:      { bg: "rgb(var(--badge-trees-bg))",      text: "rgb(var(--badge-trees-fg))",      label: "Trees" },
  wood:       { bg: "rgb(var(--badge-wood-bg))",       text: "rgb(var(--badge-wood-fg))",       label: "Wood" },
  containers: { bg: "rgb(var(--badge-containers-bg))", text: "rgb(var(--badge-containers-fg))", label: "Containers" },
  other:      { bg: "rgb(var(--badge-other-bg))",      text: "rgb(var(--badge-other-fg))",      label: "Other" },
};

// ─── Vendor View ─────────────────────────────────────────────────────────────
export function VendorView({
  suppliers,
  products,
  animatingIds,
  onFavorite,
  onProjectAdd,
  onAddProduct,
  onPriceUpdated,
  onOpenProduct,
}: {
  suppliers: Supplier[];
  products: Product[];
  animatingIds: Set<number>;
  onFavorite: (id: number) => void;
  onProjectAdd?: (product: Product) => void;
  onAddProduct: (supplierId: number) => void;
  onPriceUpdated?: (id: number, price: number, ts: string) => void;
  onOpenProduct: (p: Product) => void;
}) {
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [filterCat, setFilterCat] = useState("");
  const [visibleBySupplier, setVisibleBySupplier] = useState<Record<number, number>>({});

  const allCats = Array.from(new Set(suppliers.flatMap((s) => s.categories || []))).sort();
  const visibleSuppliers = filterCat
    ? suppliers.filter((s) => (s.categories || []).includes(filterCat))
    : suppliers;

  return (
    <div>
      {/* Category filter pills */}
      {allCats.length > 0 && (
        <div className="flex items-center gap-2 mb-5 flex-wrap">
          <span className="text-xs text-stone-400 font-medium mr-1">Filter by type:</span>
          <button
            onClick={() => setFilterCat("")}
            className={`px-3 py-1 rounded-full text-xs font-medium border transition ${
              filterCat === ""
                ? "bg-emerald-700 text-white border-emerald-700"
                : "border-stone-200 text-stone-500 hover:border-stone-300 bg-white"
            }`}
          >
            All vendors
          </button>
          {allCats.map((cat) => {
            const cfg = CAT_PILL[cat] || CAT_PILL.other;
            const active = filterCat === cat;
            return (
              <button
                key={cat}
                onClick={() => setFilterCat(active ? "" : cat)}
                className="px-3 py-1 rounded-full text-xs font-medium border transition"
                style={active
                  // Selected: the pill's own ink becomes the fill. `--ll-on-bright`
                  // is white in light mode and near-black in dark, where the inks
                  // are the bright end of their ramps.
                  ? { backgroundColor: cfg.text, color: "rgb(var(--ll-on-bright))", borderColor: cfg.text }
                  : { backgroundColor: cfg.bg, color: cfg.text, borderColor: "transparent" }
                }
              >
                {cfg.label}
              </button>
            );
          })}
        </div>
      )}
      <div className="space-y-4">
      {visibleSuppliers.length === 0 && (
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <div className="w-16 h-16 rounded-full flex items-center justify-center mb-4" style={{ backgroundColor: "rgb(var(--ll-brand-soft))" }}>
            <Store size={28} className="text-emerald-600" strokeWidth={1.5} />
          </div>
          <p className="text-base font-medium text-stone-600 mb-1">No suppliers yet</p>
          <p className="text-sm text-stone-400 max-w-xs leading-relaxed">Add suppliers from the Suppliers page to get started.</p>
        </div>
      )}
      {visibleSuppliers.map((s) => {
        const vendorProducts = products
          .filter((p) => p.supplier_id === s.id)
          .sort((a, b) => {
            if (a.is_favorited && !b.is_favorited) return -1;
            if (!a.is_favorited && b.is_favorited) return 1;
            return a.name.localeCompare(b.name);
          });
        const isExpanded = expandedId === s.id;
        const favCount = vendorProducts.filter((p) => p.is_favorited).length;
        const visibleCount = visibleBySupplier[s.id] ?? INITIAL_CARD_RENDER_LIMIT;
        const visibleVendorProducts = vendorProducts.slice(0, visibleCount);

        return (
          <div key={s.id} className="bg-white rounded-2xl border border-stone-200 overflow-hidden">
            {/* Supplier header */}
            <button
              className="w-full flex items-center justify-between px-6 py-4 hover:bg-stone-50 transition-colors text-left"
              onClick={() => setExpandedId(isExpanded ? null : s.id)}
            >
              <div className="flex items-center gap-3">
                <div
                  className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
                  style={{ backgroundColor: "rgb(var(--ll-brand-soft))" }}
                >
                  <Store size={18} className="text-emerald-700" strokeWidth={1.5} />
                </div>
                <div>
                  <p className="font-semibold text-stone-800" style={{ fontFamily: "Georgia, serif" }}>{s.name}</p>
                  <div className="flex items-center gap-1.5 flex-wrap mt-0.5">
                    {(s.categories || []).map((cat) => {
                      const cfg = CAT_PILL[cat] || CAT_PILL.other;
                      return (
                        <span
                          key={cat}
                          className="text-xs font-medium px-2 py-0.5 rounded-full"
                          style={{ backgroundColor: cfg.bg, color: cfg.text }}
                        >
                          {cfg.label}
                        </span>
                      );
                    })}
                    <span className="text-xs text-stone-400">
                      · {vendorProducts.length} product{vendorProducts.length !== 1 ? "s" : ""}
                      {favCount > 0 && <span className="text-orange-500"> · {favCount} ♥</span>}
                    </span>
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-3">
                {vendorProducts.length > 0 && (
                  <div className="flex -space-x-1">
                    {vendorProducts.slice(0, 4).map((p) => {
                      const displayImageUrl = productDisplayImageUrl(p);
                      return (
                        <div key={p.id} className="w-7 h-7 rounded-full border-2 border-white bg-stone-100 overflow-hidden flex-shrink-0">
                          {displayImageUrl ? (
                            <img src={displayImageUrl} alt={p.name} className="w-full h-full object-cover" />
                          ) : (
                            <div className="w-full h-full flex items-center justify-center">
                              <Leaf size={10} className="text-stone-300" />
                            </div>
                          )}
                        </div>
                      );
                    })}
                    {vendorProducts.length > 4 && (
                      <div className="w-7 h-7 rounded-full border-2 border-white bg-stone-200 flex items-center justify-center">
                        <span className="text-xs text-stone-500">+{vendorProducts.length - 4}</span>
                      </div>
                    )}
                  </div>
                )}
                <ChevronRight
                  size={16}
                  className="text-stone-400 transition-transform duration-200"
                  style={{ transform: isExpanded ? "rotate(90deg)" : "rotate(0deg)" }}
                />
              </div>
            </button>

            {/* Products panel */}
            {isExpanded && (
              <div className="border-t border-stone-100 px-6 py-5">
                {vendorProducts.length === 0 ? (
                  <div className="flex flex-col items-center py-8 text-center">
                    <Package size={24} className="text-stone-300 mb-2" strokeWidth={1.5} />
                    <p className="text-sm text-stone-400 mb-3">No products from this supplier yet</p>
                    <button
                      onClick={() => onAddProduct(s.id)}
                      className="text-xs font-semibold text-emerald-700 hover:text-emerald-800 flex items-center gap-1"
                    >
                      <Plus size={13} /> Add first product
                    </button>
                  </div>
                ) : (
                  <>
                    <div className="grid grid-cols-2 gap-4 xl:grid-cols-3 2xl:grid-cols-4">
                      {visibleVendorProducts.map((p) => (
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
                    {visibleCount < vendorProducts.length && (
                      <div className="mt-4 flex justify-center">
                        <button
                          onClick={() =>
                            setVisibleBySupplier((prev) => ({
                              ...prev,
                              [s.id]: (prev[s.id] ?? INITIAL_CARD_RENDER_LIMIT) + INITIAL_CARD_RENDER_LIMIT,
                            }))
                          }
                          className="rounded-lg border border-stone-200 bg-white px-4 py-2 text-sm font-semibold text-stone-600 hover:border-emerald-300 hover:text-emerald-700"
                        >
                          Show more products ({Math.min(visibleCount, vendorProducts.length)} of {vendorProducts.length})
                        </button>
                      </div>
                    )}
                    <div className="mt-4 pt-4 border-t border-stone-100 flex justify-between items-center">
                      <p className="text-xs text-stone-400">
                        Avg price: {formatCurrency(
                          vendorProducts.reduce((s, p) => s + (p.current_price || 0), 0) / (vendorProducts.filter(p => p.current_price).length || 1)
                        )}
                      </p>
                      <button
                        onClick={() => onAddProduct(s.id)}
                        className="text-xs font-semibold text-emerald-700 hover:text-emerald-800 flex items-center gap-1"
                      >
                        <Plus size={13} /> Add product
                      </button>
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        );
      })}
      </div>
    </div>
  );
}
