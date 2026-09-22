// Full product detail modal: image gallery + lightbox, supplier link bar,
// pinning/favouriting, and the attribute detail sections.
// Moved verbatim out of pages/Library.tsx (WP 4.2 library-extract).
import { useMemo, useState, useEffect } from "react";
import { X, Heart, ZoomIn } from "lucide-react";
import { formatDate, categoryLabel } from "utils/format";
import { readFavoriteIds, setLocalFavorite } from "utils/favorites";
import { metricHintText, METRIC_CHEAT } from "utils/measurements";
import WorkingJobBar from "components/WorkingJobBar";
import PinToggle from "components/PinToggle";
import { readWorkingJob, type WorkingJob, type PinGroup } from "utils/jobs";
import { loadPins, getCachedPins, setCachedPins } from "utils/pinsCache";
import { RAW_ATTRS_HIDE } from "./constants";
import {
  formatDetailValue,
  displayProductName,
  sourceBasePrice,
  sourceUom,
  detailStatus,
  imageStatus,
  productDisplayImageUrl,
  prettifyKey,
  withUnit,
} from "./display";
import { productColorSummary } from "./colors";
import { ProxiedImage, ImagePending } from "./ProxiedImage";
import { ImageLightbox } from "./ImageLightbox";
import { SupplierLinkBar } from "./SupplierLinkBar";
import type { Product } from "./types";

function ProductDetailSection({ title, rows }: { title: string; rows: Array<[string, unknown]> }) {
  return (
    <section>
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-stone-400">{title}</p>
      <div className="rounded-lg border border-stone-100 bg-white px-3">
        {rows.map(([label, value]) => (
          <ProductDetailRow key={`${title}-${label}`} label={label} value={value} />
        ))}
      </div>
    </section>
  );
}

function ProductDetailRow({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="grid grid-cols-[132px_minmax(0,1fr)] gap-3 border-b border-stone-100 py-2 last:border-b-0">
      <dt className="text-xs font-semibold text-stone-500">{label}</dt>
      <dd className="text-xs text-stone-800 break-words">{formatDetailValue(value)}</dd>
    </div>
  );
}

export function ProductDetailModal({ product, onClose }: { product: Product; onClose: () => void }) {
  // "Pinning to" mirrors Catalog Search's header widget so the same job/group
  // picker, heart and + work wherever this modal is opened from — the modal
  // never buys anything, it only saves a candidate onto a job's board.
  const [working, setWorking] = useState<WorkingJob>(() => readWorkingJob());
  const [pinGroups, setPinGroups] = useState<PinGroup[]>([]);
  const [pinnedIds, setPinnedIds] = useState<Set<number>>(new Set());
  // False until this job's real pins/groups have loaded at least once — see
  // components/PinToggle.tsx for why a click can't be live before that.
  const [pinsReady, setPinsReady] = useState(false);
  // Reload only when the working JOB changes, not on every product this
  // modal happens to be showing — opening a different card's detail used to
  // refetch on every single open, which is both the visible lag and the
  // window where a fast click raced ahead of empty just-mounted state.
  useEffect(() => {
    const jobId = working.jobId;
    if (!jobId) { setPinGroups([]); setPinnedIds(new Set()); setPinsReady(false); return; }
    const cached = getCachedPins(jobId);
    if (cached) {
      setPinGroups(cached.groups);
      setPinnedIds(new Set(cached.pins.map((x) => x.product_id)));
      setPinsReady(true);
    } else {
      setPinsReady(false);
    }
    let alive = true;
    loadPins(jobId).then((r) => {
      if (!alive || working.jobId !== jobId) return;
      setPinGroups(r.groups);
      setPinnedIds(new Set(r.pins.map((x) => x.product_id)));
      setPinsReady(true);
    }).catch(() => { if (alive) setPinsReady(false); });
    return () => { alive = false; };
  }, [working.jobId]);
  const pinned = pinnedIds.has(product.id);
  const [isFav, setIsFav] = useState(() => product.is_favorited || readFavoriteIds().has(product.id));
  const toggleFav = () => {
    const next = !isFav;
    setLocalFavorite(product.id, next);
    setIsFav(next);
  };

  const raw = product.raw_data || {};
  const productUrl = String(raw.product_url || raw.detail_url || raw.url || raw.source_url || "").trim() || undefined;
  const displayName = displayProductName(product);
  const detailPending = detailStatus(product) !== "stored";
  const status = imageStatus(product);
  const isResolvedNoImage = status === "no_supplier_image";
  const isSupplierPlaceholder = status === "placeholder";
  const displayImageUrl = productDisplayImageUrl(product);
  const pricingRows: Array<[string, unknown]> = [
    ["Base Price", sourceBasePrice(product)],
    ["UOM", sourceUom(product)],
    ["Minimum Quantity", product.moq ?? raw.MinQty],
    ["Box Quantity", product.box_qty ?? raw.BoxQty],
    ["Case Quantity", product.case_qty ?? raw.CaseQty],
    ["Suggested Retail", raw.SugRetail],
    ["Price Updated", product.price_updated_at ? formatDate(product.price_updated_at) : "—"],
  ];
  const coreRows: Array<[string, unknown]> = [
    ["Item Number", product.supplier_sku || raw["Item No"] || raw.sku],
    ["Name", displayName],
    ["Description", raw.Description || raw.name || product.description],
    ["Supplier", product.supplier_name],
    ["Category", raw.allstate_subcategory || raw.Category || categoryLabel(product.category)],
    ["UPC", product.upc || raw.UPC],
  ];
  const availabilityRows: Array<[string, unknown]> = [
    ["Availability", product.availability_note || raw["Avail. Qty: *"] || raw["Avail. Qty"] || raw.Availability || product.availability],
  ];
  const dimensionRows: Array<[string, unknown]> = [
    ["Product Length", withUnit(raw.ProdLength || raw.Length || product.length_in, "in")],
    ["Product Height", withUnit(raw.Height || product.height_in, "in")],
    ["Product Width", withUnit(raw.Width || product.width_in, "in")],
    ["Product Diameter", withUnit(raw.Diameter || product.diameter_in, "in")],
    ["Product Weight", withUnit(raw.ProdWeight || product.weight_lb, "lb")],
    ["Box Weight", withUnit(raw.BoxWeight, "lb")],
    ["Case Weight", withUnit(raw.CsWeight, "lb")],
    ["Box LxWxH", raw["Box LxWxH"]],
    ["Case LxWxH", raw["Case LxWxH"]],
    ["Case Cube", withUnit(raw.CaseCube, "ft³")],
  ];
  const supplierRows: Array<[string, unknown]> = [
    ["Class", raw.Class],
    ["Color Group", productColorSummary(product)],
    ["Season", raw.Season],
    ["Style", raw.Style || product.style],
    ["Finish", raw.Finish || product.finish],
    ["Oversize", raw.Oversize],
    ["Poly Bag", raw.PolyBag],
    ["Fragile", raw.Fragile],
    ["Catalog Volume", raw.CatalogVol],
    ["Catalog Page", raw.CatPage],
  ];
  const materialRows: Array<[string, unknown]> = [
    ["Country of Origin", product.country_of_origin || raw["Country of Origin"] || raw.Country],
    ["Material Breakdown", product.material || raw["Material Breakdown"] || raw.Material || raw.Materials],
  ];

  // Full gallery: every distinct image we captured for this product.
  const galleryImages = useMemo(() => {
    const urls = [
      product.photo_url,
      ...(Array.isArray(product.image_urls) ? product.image_urls : []),
      raw.source_photo_url,
    ].map((u) => String(u || "").trim()).filter(Boolean);
    return Array.from(new Set(urls));
  }, [product]);
  const [activeImage, setActiveImage] = useState(0);
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const activeImageUrl = galleryImages[activeImage] || galleryImages[0] || displayImageUrl;
  const canExpand = galleryImages.length > 0 && !isSupplierPlaceholder && !isResolvedNoImage;

  // Catch-all: every non-empty captured field not already shown above, so
  // nothing we scraped is ever hidden.
  const attributeRows: Array<[string, unknown]> = Object.entries(raw)
    .filter(([k, v]) => !RAW_ATTRS_HIDE.has(k) && v !== null && v !== undefined && String(v).trim() !== "")
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([k, v]) => [prettifyKey(k), v]);
  const reviewNote = raw.needs_review ? String(raw.needs_review) : null;

  // The sidebar is `fixed ... z-20` (Layout.tsx); a backdrop spanning
  // `inset-0` at z-50 sat on top of it across its full width, so clicking a
  // nav tab while this modal was open just hit the backdrop and closed the
  // modal instead of navigating - the sidebar was never actually reachable.
  // Starting the backdrop at the sidebar's right edge (w-60 = 15rem) leaves
  // that strip fully interactive; everything to its right still dims and
  // still closes on an outside click. The sidebar has no responsive variant
  // (always `fixed left-0`, no mobile collapse), so this offset applies
  // unconditionally rather than only above a breakpoint.
  return (
    <div className="fixed inset-y-0 left-60 right-0 z-50 flex items-center justify-center bg-black/40 px-4" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="w-full max-w-5xl max-h-[90vh] overflow-hidden rounded-xl bg-white shadow-2xl">
        <div className="flex items-start justify-between gap-4 border-b border-stone-100 px-5 py-4">
          <div>
            <p className="text-xs uppercase tracking-wide text-stone-400">{product.supplier_name}</p>
            <h2 className="text-lg font-semibold text-stone-800" style={{ fontFamily: "Georgia, serif" }}>{displayName}</h2>
            <p className="text-xs text-stone-500">{product.supplier_sku || raw["Item No"]}</p>
            {metricHintText(`${displayName} ${product.name || ""}`) && (
              <p className="mt-1 text-xs font-medium text-emerald-700" title={METRIC_CHEAT}>
                Metric → imperial: {metricHintText(`${displayName} ${product.name || ""}`)}
              </p>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <WorkingJobBar value={working} onChange={setWorking} />
            <button onClick={toggleFav} title={isFav ? "Remove favorite" : "Add to favorites"}
              className="flex h-9 w-9 items-center justify-center rounded-full bg-white ring-1 ring-stone-200 hover:ring-rose-300">
              <Heart size={16} fill={isFav ? "rgb(var(--ll-fav))" : "none"} style={{ color: isFav ? "rgb(var(--ll-fav))" : "rgb(var(--nc-400))" }} />
            </button>
            <PinToggle productId={product.id} jobId={working.jobId} groupId={working.groupId} groups={pinGroups} isPinned={pinned} ready={pinsReady}
              onPinsChanged={(pins) => { setPinnedIds(new Set(pins.map((x) => x.product_id))); if (working.jobId) setCachedPins(working.jobId, pins); }}
              iconSize={16}
              className={`flex h-9 w-9 items-center justify-center rounded-full ring-1 ${pinned ? "bg-emerald-700 ring-emerald-700" : "bg-white ring-stone-200 hover:ring-emerald-400"}`} />
            <button onClick={onClose} className="rounded-lg p-2 text-stone-400 hover:bg-stone-100 hover:text-stone-700">
              <X size={18} />
            </button>
          </div>
        </div>
        <SupplierLinkBar supplierId={product.supplier_id} supplierName={product.supplier_name} productUrl={productUrl} />
        <div className="grid gap-0 overflow-y-auto md:grid-cols-[340px_minmax(0,1fr)]" style={{ maxHeight: "calc(90vh - 82px)" }}>
          <div className="border-b border-stone-100 bg-stone-50 p-5 md:border-b-0 md:border-r">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-stone-400">
              Images{galleryImages.length > 0 ? ` (${galleryImages.length})` : ""}
            </p>
            <div
              className={`group relative aspect-square overflow-hidden rounded-lg border border-stone-200 bg-white ${canExpand ? "cursor-zoom-in" : ""}`}
              onClick={() => { if (canExpand) setLightboxOpen(true); }}
            >
              {activeImageUrl && !isSupplierPlaceholder ? (
                <>
                  <ProxiedImage src={activeImageUrl} fallbacks={galleryImages} alt={displayName} />
                  {canExpand && (
                    <span className="pointer-events-none absolute bottom-2 right-2 flex items-center gap-1 rounded-md bg-black/55 px-1.5 py-1 text-[10px] font-medium text-white opacity-0 transition-opacity group-hover:opacity-100">
                      <ZoomIn size={11} /> Expand
                    </span>
                  )}
                </>
              ) : (
                <ImagePending label={isResolvedNoImage ? "No supplier image" : isSupplierPlaceholder ? "Supplier placeholder" : "Image pending"} />
              )}
            </div>
            {galleryImages.length > 1 && !isSupplierPlaceholder && (
              <div className="mt-2 flex flex-wrap gap-2">
                {galleryImages.map((url, i) => (
                  <button
                    key={url}
                    type="button"
                    onClick={() => setActiveImage(i)}
                    className={`h-12 w-12 overflow-hidden rounded-md border ${i === activeImage ? "border-emerald-400 ring-2 ring-emerald-200" : "border-stone-200 hover:border-stone-300"}`}
                  >
                    <ProxiedImage src={url} alt={`${displayName} ${i + 1}`} />
                  </button>
                ))}
              </div>
            )}
            {lightboxOpen && canExpand && (
              <ImageLightbox
                images={galleryImages}
                index={activeImage}
                onIndex={setActiveImage}
                onClose={() => setLightboxOpen(false)}
              />
            )}
            {isResolvedNoImage && (
              <div className="mt-3 rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs font-medium text-stone-600">
                Supplier did not provide a product photo.
              </div>
            )}
            {isSupplierPlaceholder && (
              <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-medium text-amber-700">
                Supplier returned a placeholder image instead of a product photo.
              </div>
            )}
            {status === "pending" && (
              <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-medium text-amber-700">
                Image lookup in progress
              </div>
            )}
            {status === "failed" && (
              <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs font-medium text-red-700">
                Image retry needed
              </div>
            )}
            <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
              <div className="rounded-lg bg-white p-3">
                <p className="text-stone-400">Category</p>
                <p className="font-semibold text-stone-800">{categoryLabel(product.category)}</p>
              </div>
              <div className="rounded-lg bg-white p-3">
                <p className="text-stone-400">Source UOM</p>
                <p className="font-semibold text-stone-800">{sourceUom(product)}</p>
              </div>
            </div>
            <div className="mt-2 rounded-lg bg-white p-3 text-xs">
              <p className="text-stone-400">Source price</p>
              <p className="text-lg font-semibold text-stone-800">{sourceBasePrice(product)} <span className="text-xs font-medium text-stone-400">/ {sourceUom(product)}</span></p>
            </div>
          </div>
          <div className="space-y-5 bg-stone-50/40 p-5">
            {detailPending && (
              <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-medium text-amber-700">
                Pending detail backfill: source-page fields may be incomplete.
              </div>
            )}
            <ProductDetailSection title="Core Product" rows={coreRows} />
            <ProductDetailSection title="Pricing & Ordering" rows={pricingRows} />
            <ProductDetailSection title="Availability" rows={availabilityRows} />
            <ProductDetailSection title="Dimensions & Weights" rows={dimensionRows} />
            <ProductDetailSection title="Supplier Details" rows={supplierRows} />
            <ProductDetailSection title="Material & Origin" rows={materialRows} />
            {reviewNote && (
              <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-medium text-amber-700">
                Flagged for review: {reviewNote}
              </div>
            )}
            {attributeRows.length > 0 && (
              <ProductDetailSection title={`All Captured Attributes (${attributeRows.length})`} rows={attributeRows} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
