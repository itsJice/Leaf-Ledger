// Single product card shown in both the vendor and product catalog views.
// Moved verbatim out of pages/Library.tsx (WP 4.2 library-extract).
import { Heart, Plus, AlertTriangle } from "components/icons";
import { formatCurrency, formatDate, categoryLabel, unitLabel } from "utils/format";
import { metricHintText, METRIC_CHEAT } from "utils/measurements";
import { CATEGORY_COLORS } from "./constants";
import {
  isPriceStale,
  imageStatus,
  productDisplayImageUrl,
  productImageSources,
  sourceOrderContext,
  sourceValue,
  displayProductName,
  sourceBasePrice,
  sourceUom,
  formatDetailValue,
} from "./display";
import { ProxiedImage, ImagePending } from "./ProxiedImage";
import { InlinePriceEditor } from "./InlinePriceEditor";
import type { Product } from "./types";

// ─── Single product card ──────────────────────────────────────────────────────
export function ProductCard({
  p,
  animating,
  onFavorite,
  onProjectAdd,
  onPriceUpdated,
  onOpen,
}: {
  p: Product;
  animating: boolean;
  onFavorite: (id: number) => void;
  onProjectAdd?: (product: Product) => void;
  onPriceUpdated?: (id: number, price: number, ts: string) => void;
  onOpen: (p: Product) => void;
}) {
  const stale = isPriceStale(p.price_updated_at);
  const status = imageStatus(p);
  const isResolvedNoImage = status === "no_supplier_image";
  const isSupplierPlaceholder = status === "placeholder";
  const displayImageUrl = productDisplayImageUrl(p);
  const orderContext = sourceOrderContext(p);
  const hasSourcePrice = !!sourceValue(p, "BasePrice", "price", "Uom", "UOM", "Unit of Measure", "Unit");
  const displayName = displayProductName(p);
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onOpen(p)}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") onOpen(p); }}
      className="bg-white rounded-xl border border-stone-200 overflow-hidden group hover:shadow-md transition cursor-pointer focus:outline-none focus:ring-2 focus:ring-emerald-300"
    >
      {/* Image */}
      <div className="relative h-56 bg-stone-100 overflow-hidden">
        {displayImageUrl && !isSupplierPlaceholder ? (
          <ProxiedImage src={displayImageUrl} fallbacks={productImageSources(p)} alt={displayName} />
        ) : (
          <ImagePending label={isResolvedNoImage ? "No supplier image" : isSupplierPlaceholder ? "Supplier placeholder" : "Image pending"} />
        )}
        {isResolvedNoImage && (
          <div className="absolute top-2 left-2 rounded-full bg-white/90 px-2 py-0.5 text-[10px] font-semibold text-stone-600 shadow-sm ring-1 ring-stone-200">
            No supplier image
          </div>
        )}
        {isSupplierPlaceholder && (
          <div className="absolute top-2 left-2 rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-700 shadow-sm ring-1 ring-amber-200">
            Supplier placeholder
          </div>
        )}
        {status === "pending" && (
          <div className="absolute top-2 left-2 rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-700 shadow-sm ring-1 ring-amber-200">
            Finding image
          </div>
        )}
        {status === "failed" && (
          <div className="absolute top-2 left-2 rounded-full bg-red-50 px-2 py-0.5 text-[10px] font-semibold text-red-700 shadow-sm ring-1 ring-red-200">
            Image retry needed
          </div>
        )}
        {status === "stored" && (
          <div className="absolute top-2 left-2 rounded-full bg-white/90 px-2 py-0.5 text-[10px] font-medium text-emerald-700 shadow-sm">
            Image stored
          </div>
        )}
        {onProjectAdd && (
          <button
            onClick={(e) => { e.stopPropagation(); onProjectAdd(p); }}
            className="absolute top-2 right-2 flex h-8 w-8 items-center justify-center rounded-full bg-emerald-700 text-white shadow-sm transition-colors hover:bg-emerald-800"
            title="Add to project"
          >
            <Plus size={16} strokeWidth={2.4} />
          </button>
        )}
        {/* Favorite */}
        <button
          onClick={(e) => { e.stopPropagation(); onFavorite(p.id); }}
          className={`absolute right-2 w-8 h-8 flex items-center justify-center rounded-full bg-white/80 backdrop-blur-sm hover:bg-white transition-colors ${onProjectAdd ? "top-12" : "top-2"}`}
          style={{ transform: animating ? "scale(1.4)" : "scale(1)", transition: "transform 0.2s cubic-bezier(0.34,1.56,0.64,1)" }}
        >
          <Heart
            size={15}
            className="transition-colors"
            style={{ color: p.is_favorited ? "rgb(var(--ll-fav))" : "rgb(var(--nc-400))" }}
            fill={p.is_favorited ? "rgb(var(--ll-fav))" : "none"}
          />
        </button>
        {/* Category badge */}
        <div className="absolute bottom-2 left-2">
          <span
            className="text-xs font-medium px-2 py-0.5 rounded-full bg-white/80 backdrop-blur-sm"
            style={{ color: CATEGORY_COLORS[p.category] || "rgb(var(--cat-decor))" }}
          >
            {categoryLabel(p.category)}
          </span>
        </div>
      </div>
      {/* Info */}
      <div className="p-4">
        {p.supplier_name && (
          <p className="text-[10px] font-semibold uppercase tracking-wide text-emerald-700 truncate mb-0.5" title={p.supplier_name}>
            {p.supplier_name}
          </p>
        )}
        <p className="font-semibold text-stone-800 text-sm leading-tight truncate mb-1">{displayName}</p>
        {metricHintText(p.name) && (
          <p className="text-[11px] font-medium text-emerald-700 mb-1 truncate" title={METRIC_CHEAT}>{metricHintText(p.name)}</p>
        )}
        {p.supplier_sku && <p className="text-xs text-stone-400 mb-2 truncate">{p.supplier_sku}</p>}
        <div>
          {hasSourcePrice ? (
            <>
              <p className="text-[11px] font-semibold uppercase tracking-wide text-stone-400">Base price</p>
              <p className="text-base font-bold text-stone-800">
                {sourceBasePrice(p)} <span className="text-xs font-semibold text-stone-400">/ {sourceUom(p)}</span>
              </p>
            </>
          ) : (
            <>
              <InlinePriceEditor
                p={p}
                onUpdated={(price, ts) => onPriceUpdated?.(p.id, price, ts)}
              />
              <p className="text-xs text-stone-400">per {unitLabel(p.unit)}</p>
            </>
          )}
          {orderContext.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {orderContext.map(([label, value]) => (
                <span key={label} className="rounded-full bg-stone-100 px-2 py-0.5 text-[10px] font-medium text-stone-600">
                  {label} {formatDetailValue(value)}
                </span>
              ))}
            </div>
          )}
        </div>
        {/* Stale price warning */}
        {stale && (
          <div className="flex items-center gap-1 mt-1.5">
            <AlertTriangle size={10} className="text-amber-400 flex-shrink-0" />
            <p className="text-[10px] text-amber-600">Supplier price may be outdated</p>
          </div>
        )}
        {!stale && p.price_updated_at && (
          <p className="text-[10px] text-stone-300 mt-1">Supplier price updated {formatDate(p.price_updated_at)}</p>
        )}
      </div>
    </div>
  );
}
