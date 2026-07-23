import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Search, X, SlidersHorizontal, Package, RotateCcw, Heart } from "lucide-react";
import Layout from "components/Layout";
import { ProductDetailModal } from "./Library";
import { readFavoriteIds, setLocalFavorite } from "utils/favorites";
import { metricHintText, METRIC_CHEAT } from "utils/measurements";

// Phase 3 — versatile catalog search. Purpose-built search over the whole
// catalog, driven by the normalization layer's server-side facets (color, size,
// finish, product type, supplier, availability) + keyword. Talks directly to the
// products API (/api/products/page + /filter-metadata).

interface FacetOption { value: string; count?: number; id?: number }
interface FilterMetadata {
  categories?: FacetOption[];
  colors?: FacetOption[];
  sizes?: FacetOption[];
  finishes?: FacetOption[];
  product_types?: FacetOption[];
  suppliers?: FacetOption[];
  availability?: FacetOption[];
}
interface Product {
  id: number;
  name: string;
  supplier_name?: string;
  supplier_sku?: string;
  current_price?: number | null;
  image_urls?: string[] | null;
  raw_data?: { normalized?: { color?: string; finish?: string; size_in?: number; class?: string } } | null;
}

type Selection = {
  categories: string[];
  colors: string[];
  sizes: string[];
  finishes: string[];
  product_types: string[];
  suppliers: string[]; // supplier names (mapped to ids at request time)
  availability: string[];
};
const EMPTY: Selection = { categories: [], colors: [], sizes: [], finishes: [], product_types: [], suppliers: [], availability: [] };

const PAGE_SIZE = 48;

// Map natural-language words → a Category filter value (matches our taxonomy).
const CATEGORY_HINTS: [RegExp, string][] = [
  [/\b(ornament|ornaments|bauble|baubles)\b/, "Ornaments"],
  [/\b(tree|trees)\b/, "Trees"],
  [/\b(wreath|wreaths|garland|garlands)\b/, "Wreaths & Garland"],
  [/\b(ribbon|ribbons|bow|bows)\b/, "Ribbon & Bows"],
  [/\b(light|lights|lighting|lamp|lamps|bulb|bulbs)\b/, "Lighting"],
  [/\b(candle|candles|lantern|lanterns|votive)\b/, "Candles & Lanterns"],
  [/\b(floral|florals|flower|flowers|stem|stems|spray|sprays|pick|picks|bouquet)\b/, "Florals"],
  [/\b(greenery|plant|plants|fern|ferns|foliage|succulent|succulents|palm|ivy)\b/, "Greenery & Plants"],
  [/\b(berry|berries|pod|pods|pinecone|pinecones|moss|dried|preserved|botanical|botanicals)\b/, "Botanicals & Fillers"],
  [/\b(container|containers|vase|vases|pot|pots|planter|planters|urn|basket|baskets)\b/, "Containers & Vases"],
  [/\b(rug|rugs|pillow|pillows|textile|textiles|throw|blanket)\b/, "Rugs & Textiles"],
  [/\b(rock|rocks|stone|stones|gravel|pebble|pebbles|agate|geode)\b/, "Rocks & Stone"],
  [/\b(furniture|table|tables|chair|chairs|shelf|shelves|cabinet)\b/, "Furniture & Storage"],
  [/\b(decor|figurine|figurines|sculpture|sculptures|statue|statues|mirror|mirrors|sign|signs)\b/, "Home Décor"],
];

function proxied(url?: string | null): string | undefined {
  if (!url) return undefined;
  return `/api/products/image-proxy?url=${encodeURIComponent(url)}`;
}

export default function CatalogSearch() {
  const [metadata, setMetadata] = useState<FilterMetadata>({});
  const [facets, setFacets] = useState<FilterMetadata>({});
  const [sel, setSel] = useState<Selection>(EMPTY);
  const [favOnly, setFavOnly] = useState(false);
  const [priceMin, setPriceMin] = useState<number | "">("");
  const [priceMax, setPriceMax] = useState<number | "">("");
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [items, setItems] = useState<Product[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const seq = useRef(0);
  const [detailProduct, setDetailProduct] = useState<any | null>(null);

  const openDetail = useCallback((id: number) => {
    fetch(`/api/products/detail/${id}`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setDetailProduct)
      .catch(() => {});
  }, []);

  const [favIds, setFavIds] = useState<Set<number>>(() => readFavoriteIds());
  const toggleFav = useCallback((id: number) => {
    setFavIds(setLocalFavorite(id, !readFavoriteIds().has(id)));
  }, []);

  // metadata once
  useEffect(() => {
    fetch("/api/products/filter-metadata")
      .then((r) => r.json())
      .then(setMetadata)
      .catch(() => {});
  }, []);

  // debounce keyword
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search.trim()), 350);
    return () => clearTimeout(t);
  }, [search]);

  const buildParams = useCallback(
    (nextOffset: number) => {
      const p = new URLSearchParams();
      if (sel.categories.length) p.set("categories", sel.categories.join(","));
      if (sel.colors.length) p.set("colors", sel.colors.join(","));
      if (sel.sizes.length) p.set("sizes", sel.sizes.join(","));
      if (sel.finishes.length) p.set("finishes", sel.finishes.join(","));
      if (sel.product_types.length) p.set("product_types", sel.product_types.join(","));
      if (sel.suppliers.length) p.set("supplier_ids", sel.suppliers.join(","));
      if (sel.availability.length) p.set("availability", sel.availability.join(","));
      // Favorites are client-side ids; -1 forces an empty set when nothing saved.
      if (favOnly) p.set("ids", Array.from(readFavoriteIds()).join(",") || "-1");
      if (priceMin !== "") p.set("price_min", String(priceMin));
      if (priceMax !== "") p.set("price_max", String(priceMax));
      if (debouncedSearch) p.set("search", debouncedSearch);
      p.set("limit", String(PAGE_SIZE));
      p.set("offset", String(nextOffset));
      return p.toString();
    },
    [sel, favOnly, priceMin, priceMax, debouncedSearch]
  );

  const load = useCallback(
    (nextOffset: number, append: boolean) => {
      const s = ++seq.current;
      setLoading(true);
      fetch(`/api/products/search?${buildParams(nextOffset)}`)
        .then((r) => r.json())
        .then((data) => {
          if (s !== seq.current) return;
          const rows: Product[] = data?.items ?? [];
          setItems((prev) => (append ? [...prev, ...rows] : rows));
          setTotal(data?.total ?? 0);
          setOffset(nextOffset);
          if (!append && data?.facets) setFacets(data.facets);
        })
        .catch(() => {
          if (s === seq.current) { setItems([]); setTotal(0); }
        })
        .finally(() => { if (s === seq.current) setLoading(false); });
    },
    [buildParams]
  );

  // reload from top whenever filters/search change (favIds so un-hearting an
  // item refreshes the list while "favorites only" is on)
  useEffect(() => { load(0, false); }, [sel, favOnly, favIds, priceMin, priceMax, debouncedSearch, load]);

  const toggle = (group: keyof Selection, value: string) =>
    setSel((prev) => {
      const has = prev[group].includes(value);
      return { ...prev, [group]: has ? prev[group].filter((v) => v !== value) : [...prev[group], value] };
    });

  const activeCount = useMemo(
    () => Object.values(sel).reduce((n, arr) => n + arr.length, 0)
      + (debouncedSearch ? 1 : 0) + (priceMin !== "" ? 1 : 0) + (priceMax !== "" ? 1 : 0) + (favOnly ? 1 : 0),
    [sel, debouncedSearch, priceMin, priceMax, favOnly]
  );
  const resetAll = () => { setSel(EMPTY); setSearch(""); setPriceMin(""); setPriceMax(""); setFavOnly(false); };

  // Infinite scroll + prefetch: auto-load the next page ~800px before the
  // bottom, so the next batch is ready before you reach it.
  const loadMoreStateRef = useRef({ loading, itemsLen: items.length, total, offset });
  loadMoreStateRef.current = { loading, itemsLen: items.length, total, offset };
  const scrollObsRef = useRef<IntersectionObserver | null>(null);
  const setSentinel = useCallback((node: HTMLDivElement | null) => {
    if (scrollObsRef.current) { scrollObsRef.current.disconnect(); scrollObsRef.current = null; }
    if (!node) return;
    scrollObsRef.current = new IntersectionObserver((entries) => {
      if (!entries[0].isIntersecting) return;
      const s = loadMoreStateRef.current;
      if (!s.loading && s.itemsLen < s.total) load(s.offset + PAGE_SIZE, true);
    }, { rootMargin: "800px 0px" });
    scrollObsRef.current.observe(node);
  }, [load]);

  // Natural-language query → facets. "gold matte ornaments under $5" applies
  // Color=Gold, Finish=Matte, price<5, leaving the rest as the keyword.
  const runSmartSearch = () => {
    let text = ` ${search.toLowerCase()} `;
    const add = (group: keyof Selection, val: string) =>
      setSel((prev) => (prev[group].includes(val) ? prev : { ...prev, [group]: [...prev[group], val] }));
    let m: RegExpMatchArray | null;
    if ((m = text.match(/(?:under|below|less than|cheaper than|<)\s*\$?\s*(\d+(?:\.\d+)?)/))) setPriceMax(parseFloat(m[1]));
    if ((m = text.match(/(?:over|above|more than|>)\s*\$?\s*(\d+(?:\.\d+)?)/))) setPriceMin(parseFloat(m[1]));
    if ((m = text.match(/\$?\s*(\d+(?:\.\d+)?)\s*(?:-|to)\s*\$?\s*(\d+(?:\.\d+)?)/))) { setPriceMin(parseFloat(m[1])); setPriceMax(parseFloat(m[2])); }
    text = text.replace(/(?:under|below|less than|cheaper than|over|above|more than)\s*\$?\s*\d+(?:\.\d+)?/g, " ").replace(/\$\s*\d+(?:\.\d+)?/g, " ");
    for (const sm of text.matchAll(/(\d+(?:\.\d+)?)\s*(?:inch|inches|in\b|")/g)) {
      const v = Math.round(parseFloat(sm[1]) * 2) / 2;
      add("sizes", String(v).replace(/\.0$/, ""));
    }
    text = text.replace(/(\d+(?:\.\d+)?)\s*(?:inch|inches|in\b|")/g, " ");
    // categories: "ornaments", "tree", "wreath" … → the Category filter
    for (const [re, catValue] of CATEGORY_HINTS) {
      if (re.test(text) && (metadata.categories || []).some((o) => o.value === catValue)) {
        add("categories", catValue);
        text = text.replace(new RegExp(re.source, "g"), " ");
      }
    }
    // colors: match any word of a family ("cream" → "Cream/Ivory", "gold" → "Gold")
    for (const o of metadata.colors || []) {
      const words = o.value.toLowerCase().split(/[^a-z]+/).filter((w) => w.length > 2);
      if (words.some((w) => text.includes(` ${w} `) || text.includes(` ${w}s `))) {
        add("colors", o.value);
        for (const w of words) text = text.split(w).join(" ");
      }
    }
    // drop generic filler words so the leftover keyword doesn't over-constrain
    const STOP = /\b(the|and|with|for|an?|of|in|on|my|me|some|please|show|find|all|that|are|is|me)\b/g;
    const residual = text.replace(STOP, " ").replace(/\s+/g, " ").trim();
    setSearch(residual);
  };

  // Dynamic facet groups — options come from the current search's `facets`, so
  // the sidebar reflects whatever was searched (e.g. ornament sizes/finishes).
  const FACETS: { key: keyof Selection; label: string; options?: FacetOption[]; useId?: boolean; suffix?: string }[] = [
    { key: "categories", label: "Category", options: facets.categories },
    { key: "colors", label: "Color", options: facets.colors },
    { key: "sizes", label: "Size", options: facets.sizes, suffix: '"' },
    { key: "finishes", label: "Finish", options: facets.finishes },
    { key: "availability", label: "Availability", options: facets.availability },
    { key: "suppliers", label: "Supplier", options: facets.suppliers, useId: true },
  ];

  return (
    <Layout>
      <header
        className="sticky top-0 z-10 border-b border-stone-200 px-10 py-4"
        style={{ backgroundColor: "#f7f4ef" }}
      >
        <div className="flex items-center justify-between gap-4">
          <div>
            <h1 className="flex items-center gap-2 text-xl font-semibold text-stone-800" style={{ fontFamily: "Georgia, serif" }}>
              <Search size={18} className="text-emerald-700" />
              Catalog Search
            </h1>
            <p className="mt-0.5 text-xs text-stone-500">
              {total.toLocaleString()} product{total === 1 ? "" : "s"} across every supplier — filter by color, size, finish &amp; more.
            </p>
          </div>
          <div className="relative w-96 max-w-[40vw]">
            <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-stone-400" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") runSmartSearch(); }}
              placeholder="Try: green wreaths under $20"
              className="w-full rounded-lg border border-stone-300 py-2 pl-9 pr-8 text-sm text-stone-800 outline-none focus:border-emerald-600 focus:ring-1 focus:ring-emerald-600"
            />
            {search && (
              <button onClick={() => setSearch("")} className="absolute right-2 top-1/2 -translate-y-1/2 text-stone-400 hover:text-stone-700">
                <X size={15} />
              </button>
            )}
            <p className="absolute -bottom-4 left-1 text-[10px] text-stone-400">↵ Enter to auto-apply colors, finishes, size &amp; price</p>
          </div>
        </div>
      </header>

      <div className="flex">
        {/* Facet sidebar */}
        <aside className="w-64 flex-shrink-0 border-r border-stone-200 px-5 py-6" style={{ minHeight: "calc(100vh - 65px)" }}>
          <div className="mb-4 flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-widest text-stone-500">
              <SlidersHorizontal size={13} /> Filters
            </span>
            {activeCount > 0 && (
              <button onClick={resetAll} className="flex items-center gap-1 text-xs font-medium text-emerald-700 hover:text-emerald-900">
                <RotateCcw size={12} /> Reset ({activeCount})
              </button>
            )}
          </div>
          <div className="flex flex-col gap-5">
            {/* Show favorites only */}
            <label className="flex cursor-pointer items-center gap-2 rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm hover:border-rose-300">
              <input
                type="checkbox" checked={favOnly}
                onChange={(e) => setFavOnly(e.target.checked)}
                className="accent-rose-500"
              />
              <Heart size={14} fill={favOnly ? "#c2410c" : "none"} style={{ color: favOnly ? "#c2410c" : "#a8a29e" }} />
              <span className={`flex-1 ${favOnly ? "font-medium text-rose-700" : "text-stone-600"}`}>Show favorites only</span>
            </label>

            {/* Price range */}
            <div>
              <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-stone-600">Price ($)</p>
              <div className="flex items-center gap-2">
                <input
                  type="number" min={0} placeholder="Min" value={priceMin}
                  onChange={(e) => setPriceMin(e.target.value === "" ? "" : Number(e.target.value))}
                  className="w-20 rounded-md border border-stone-300 px-2 py-1 text-sm outline-none focus:border-emerald-600"
                />
                <span className="text-stone-400">–</span>
                <input
                  type="number" min={0} placeholder="Max" value={priceMax}
                  onChange={(e) => setPriceMax(e.target.value === "" ? "" : Number(e.target.value))}
                  className="w-20 rounded-md border border-stone-300 px-2 py-1 text-sm outline-none focus:border-emerald-600"
                />
              </div>
            </div>

            {/* Dynamic facets — recomputed from the current search results */}
            {FACETS.map((f) => (
              <FacetGroup
                key={f.key}
                label={f.label}
                options={f.options || []}
                selected={sel[f.key]}
                suffix={f.suffix}
                useId={f.useId}
                onToggle={(v) => toggle(f.key, v)}
              />
            ))}
            {FACETS.every((f) => !(f.options || []).length) && (
              <p className="text-xs italic text-stone-400">No filters for this search yet.</p>
            )}
          </div>
        </aside>

        {/* Results */}
        <main className="flex-1 px-8 py-6">
          {loading && items.length === 0 ? (
            <div className="py-20 text-center text-sm text-stone-400">Searching…</div>
          ) : items.length === 0 ? (
            <div className="py-20 text-center">
              <Package className="mx-auto mb-3 text-stone-300" size={32} />
              <p className="text-sm text-stone-500">No products match these filters.</p>
              {activeCount > 0 && (
                <button onClick={resetAll} className="mt-3 text-sm font-medium text-emerald-700 hover:text-emerald-900">Clear filters</button>
              )}
            </div>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
                {items.map((p) => <ProductCard key={p.id} p={p} onOpen={openDetail} isFav={favIds.has(p.id)} onToggleFav={toggleFav} />)}
              </div>
              <div ref={setSentinel} className="h-px w-full" aria-hidden />
              {items.length < total && (
                <div className="mt-8 flex justify-center">
                  {loading ? (
                    <div className="flex items-center gap-2 text-sm text-stone-400">
                      <div className="h-4 w-4 animate-spin rounded-full border-2 border-emerald-500 border-t-transparent" />
                      Loading more…
                    </div>
                  ) : (
                    <button
                      onClick={() => load(offset + PAGE_SIZE, true)}
                      className="rounded-lg border border-stone-300 px-5 py-2 text-sm font-medium text-stone-700 transition-colors hover:bg-stone-100"
                    >
                      Load more ({(total - items.length).toLocaleString()} left)
                    </button>
                  )}
                </div>
              )}
            </>
          )}
        </main>
      </div>
      {detailProduct && (
        <ProductDetailModal product={detailProduct} onClose={() => setDetailProduct(null)} />
      )}
    </Layout>
  );
}

function FacetGroup(p: {
  label: string;
  options: FacetOption[];
  selected: string[];
  onToggle: (v: string) => void;
  useId?: boolean;
  suffix?: string;
}) {
  const [expanded, setExpanded] = useState(false);
  if (!p.options.length) return null;
  // Keep checked options visible even when collapsed, so a selection never hides.
  const selectedFirst = [
    ...p.options.filter((o) => p.selected.includes(p.useId && o.id != null ? String(o.id) : o.value)),
    ...p.options.filter((o) => !p.selected.includes(p.useId && o.id != null ? String(o.id) : o.value)),
  ];
  const shown = expanded ? selectedFirst : selectedFirst.slice(0, 8);
  return (
    <div>
      <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-stone-600">{p.label}</p>
      <div className="flex flex-col gap-0.5">
        {shown.map((o) => {
          const val = p.useId && o.id != null ? String(o.id) : o.value;
          const on = p.selected.includes(val);
          return (
            <label key={val} className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 text-sm hover:bg-stone-100">
              <input type="checkbox" checked={on} onChange={() => p.onToggle(val)} className="accent-emerald-700" />
              <span className={`flex-1 truncate ${on ? "font-medium text-emerald-900" : "text-stone-600"}`}>{o.value}{p.suffix || ""}</span>
              {o.count != null && <span className="text-xs text-stone-400">{o.count.toLocaleString()}</span>}
            </label>
          );
        })}
      </div>
      {p.options.length > 8 && (
        <button onClick={() => setExpanded((e) => !e)} className="mt-1 text-xs font-medium text-emerald-700 hover:text-emerald-900">
          {expanded ? "Show less" : `Show all ${p.options.length}`}
        </button>
      )}
    </div>
  );
}

function ProductCard({ p, onOpen, isFav, onToggleFav }: {
  p: Product;
  onOpen: (id: number) => void;
  isFav: boolean;
  onToggleFav: (id: number) => void;
}) {
  const [imgOk, setImgOk] = useState(true);
  const img = proxied(p.image_urls?.[0]);
  const n = p.raw_data?.normalized || {};
  const tags = [n.size_in != null ? `${n.size_in}"` : null, n.color, n.finish].filter(Boolean) as string[];
  const metric = metricHintText(p.name);
  return (
    <div
      onClick={() => onOpen(p.id)}
      className="group relative cursor-pointer overflow-hidden rounded-xl border border-stone-200 bg-white shadow-sm transition-shadow hover:shadow-md"
    >
      <button
        onClick={(e) => { e.stopPropagation(); onToggleFav(p.id); }}
        title={isFav ? "Remove favorite" : "Add to favorites"}
        className="absolute right-2 top-2 z-10 flex h-7 w-7 items-center justify-center rounded-full bg-white/85 shadow-sm ring-1 ring-stone-200 backdrop-blur-sm hover:bg-white"
      >
        <Heart size={14} fill={isFav ? "#c2410c" : "none"} style={{ color: isFav ? "#c2410c" : "#a8a29e" }} />
      </button>
      <div className="flex h-40 items-center justify-center bg-stone-50">
        {img && imgOk ? (
          <img src={img} alt={p.name} className="h-full w-full object-contain" onError={() => setImgOk(false)} />
        ) : (
          <Package className="text-stone-300" size={28} />
        )}
      </div>
      <div className="p-3">
        <p className="truncate text-sm font-medium text-stone-800" title={p.name}>{p.name}</p>
        {metric && (
          <p className="mt-0.5 truncate text-[11px] font-medium text-emerald-700" title={METRIC_CHEAT}>{metric}</p>
        )}
        <div className="mt-1 flex items-center justify-between">
          <span className="truncate text-xs text-stone-500">{p.supplier_name || "—"}</span>
          <span className="text-sm font-semibold text-emerald-800">
            {p.current_price != null ? `$${Number(p.current_price).toFixed(2)}` : ""}
          </span>
        </div>
        <p className="mt-0.5 truncate font-mono text-[11px] text-stone-400">{p.supplier_sku || ""}</p>
        {tags.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {tags.map((t, i) => (
              <span key={i} className="rounded bg-emerald-50 px-1.5 py-0.5 text-[10px] font-medium text-emerald-800">{t}</span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
