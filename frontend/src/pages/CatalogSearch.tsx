import { apiFetch } from "utils/apiFetch";
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Search, X, SlidersHorizontal, Package, RotateCcw, Heart, LayoutGrid, List, Minus, Plus } from "lucide-react";
import Layout from "components/Layout";
import { ProductDetailModal, ProxiedImage } from "./Library";
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

// A style number close to the one typed. Offered for a person to pick, never
// folded into the results: N592522DCV and N592522DA are different colours of
// one item and score within a hair of each other.
interface IdentSuggestion { id: number; supplier_sku: string; name: string; similarity: number }
// The second ring of results, from /api/products/similar: near spellings of the
// query, fetched only once the exact matches have been shown or ran out.
interface SimilarResult { items: Product[]; identifier_suggestions: IdentSuggestion[]; searched_for: string | null }
const SIMILAR_LIMIT = 24;
// exclude_ids keeps the band from repeating what's already on screen; cap it so
// a long exact list never turns into an unbounded query string.
const SIMILAR_EXCLUDE_CAP = 500;

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

// View + card-size preferences (persisted per browser).
type ViewMode = "grid" | "list";
type CardSize = 1 | 2 | 3 | 4; // 1 = smallest (most per row) … 4 = largest
const GRID_COLS: Record<CardSize, string> = {
  1: "grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 xl:grid-cols-8",
  2: "grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 xl:grid-cols-6",
  3: "grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5",
  4: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4",
};
const IMG_HEIGHT: Record<CardSize, string> = { 1: "h-24", 2: "h-32", 3: "h-40", 4: "h-56" };
const VIEW_KEY = "leaf-ledger:catalog-view:v1";
const SIZE_KEY = "leaf-ledger:catalog-size:v1";
// sessionStorage, not localStorage: this is "where was I", not a lasting
// preference like view/size above - it should survive clicking away to
// another tab and back, but not resurrect a random product days later.
const OPEN_PRODUCT_KEY = "leaf-ledger:catalog-open-product:v1";
// Filters + scroll position, restored when navigating back to this page
// (e.g. Catalog Search -> Suppliers -> back). sessionStorage, not
// localStorage: this is "where I was in this browsing session," not a
// permanent saved search -- it should fall away once the tab closes.
const SEARCH_STATE_KEY = "leaf-ledger:catalog-search-state:v1";
type SavedSearchState = {
  sel: Selection; favOnly: boolean; priceMin: number | ""; priceMax: number | "";
  search: string; scrollTop?: number;
};
function readSavedSearchState(): SavedSearchState | null {
  try {
    const raw = sessionStorage.getItem(SEARCH_STATE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch { return null; }
}

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

export default function CatalogSearch() {
  // Lazy initializers so this only ever reads sessionStorage once, on the
  // very first render -- not on every render, and not fighting the effect
  // below that writes back out whenever these change.
  const [metadata, setMetadata] = useState<FilterMetadata>({});
  const [facets, setFacets] = useState<FilterMetadata>({});
  const [sel, setSel] = useState<Selection>(() => readSavedSearchState()?.sel || EMPTY);
  const [favOnly, setFavOnly] = useState(() => readSavedSearchState()?.favOnly || false);
  const [priceMin, setPriceMin] = useState<number | "">(() => readSavedSearchState()?.priceMin ?? "");
  const [priceMax, setPriceMax] = useState<number | "">(() => readSavedSearchState()?.priceMax ?? "");
  const [search, setSearch] = useState(() => readSavedSearchState()?.search || "");
  // Restoring a saved keyword shouldn't wait through the debounce below --
  // the very first query fires with it immediately.
  const [debouncedSearch, setDebouncedSearch] = useState(() => (readSavedSearchState()?.search || "").trim());
  // What the LAST smart-search parse itself checked/set, as opposed to
  // anything the user clicked by hand in the sidebar. Search text is meant to
  // behave like a search bar -- each parse should replace what the previous
  // one applied, not pile on top of it, and clearing the box should undo it
  // entirely. Without this, "green" then "blue" left both boxes checked
  // (facet values only ever got added, never removed), and clearing the text
  // back to empty didn't touch the sidebar at all.
  const autoAppliedRef = useRef<{
    categories: string[]; colors: string[]; sizes: string[];
    priceMin: number | null; priceMax: number | null;
  }>({ categories: [], colors: [], sizes: [], priceMin: null, priceMax: null });
  const revertAutoApplied = useCallback(() => {
    const applied = autoAppliedRef.current;
    if (!applied.categories.length && !applied.colors.length && !applied.sizes.length
        && applied.priceMin === null && applied.priceMax === null) return;
    setSel((prev) => ({
      ...prev,
      categories: prev.categories.filter((v) => !applied.categories.includes(v)),
      colors: prev.colors.filter((v) => !applied.colors.includes(v)),
      sizes: prev.sizes.filter((v) => !applied.sizes.includes(v)),
    }));
    // Only clear a price bound if it still holds the value THIS parse set --
    // if the user has since typed their own min/max by hand, leave it alone.
    setPriceMin((prev) => (prev === applied.priceMin ? "" : prev));
    setPriceMax((prev) => (prev === applied.priceMax ? "" : prev));
    autoAppliedRef.current = { categories: [], colors: [], sizes: [], priceMin: null, priceMax: null };
  }, []);
  const [items, setItems] = useState<Product[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const seq = useRef(0);
  // What /search actually matched when it had to reinterpret a spelling
  // ("wreathe" -> "wreath"). Shown so the user knows why they're looking at
  // results for a word they did not type.
  const [searchedFor, setSearchedFor] = useState<string | null>(null);
  const [similar, setSimilar] = useState<SimilarResult | null>(null);
  const [similarLoading, setSimilarLoading] = useState(false);
  // One /similar call per query, fired when the exact results run out -- on a
  // short first page, or when the last page of a longer list lands. Counted
  // per query (not per page) so an in-flight band isn't dropped by a page
  // load, and never fetched twice for the same query.
  const queryGen = useRef(0);
  const similarFetched = useRef(false);
  const seenIds = useRef<number[]>([]);
  const [detailProduct, setDetailProduct] = useState<any | null>(null);

  // Clicking a sidebar tab unmounts this whole page - plain component state
  // can't survive that. Persisting which product was open (and restoring it
  // below on mount) is what makes "expand a product, check Install Schedule,
  // come back" land you exactly where you left off instead of a blank search.
  const openDetail = useCallback((id: number) => {
    apiFetch(`/api/products/detail/${id}`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((p) => {
        setDetailProduct(p);
        try { sessionStorage.setItem(OPEN_PRODUCT_KEY, String(id)); } catch { /* private mode etc. */ }
      })
      .catch(() => {
        // The remembered product no longer resolves (deleted, bad id from a
        // stale session) - drop the breadcrumb so we don't retry forever.
        try { sessionStorage.removeItem(OPEN_PRODUCT_KEY); } catch { /* noop */ }
      });
  }, []);

  const closeDetail = useCallback(() => {
    setDetailProduct(null);
    try { sessionStorage.removeItem(OPEN_PRODUCT_KEY); } catch { /* noop */ }
  }, []);

  // Restore on mount: if a product was open when this page was last torn
  // down, reopen it - runs once, before the user has clicked anything.
  useEffect(() => {
    const saved = sessionStorage.getItem(OPEN_PRODUCT_KEY);
    const id = saved ? Number(saved) : NaN;
    if (Number.isFinite(id)) openDetail(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const [favIds, setFavIds] = useState<Set<number>>(() => readFavoriteIds());
  const toggleFav = useCallback((id: number) => {
    setFavIds(setLocalFavorite(id, !readFavoriteIds().has(id)));
  }, []);

  const [viewMode, setViewMode] = useState<ViewMode>(() => (localStorage.getItem(VIEW_KEY) as ViewMode) || "grid");
  const [cardSize, setCardSize] = useState<CardSize>(() => (Number(localStorage.getItem(SIZE_KEY)) as CardSize) || 3);
  useEffect(() => { localStorage.setItem(VIEW_KEY, viewMode); }, [viewMode]);
  useEffect(() => { localStorage.setItem(SIZE_KEY, String(cardSize)); }, [cardSize]);

  // metadata once
  useEffect(() => {
    apiFetch("/api/products/filter-metadata")
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

  const loadSimilar = useCallback(
    (excludeIds: number[]) => {
      const g = queryGen.current;
      setSimilarLoading(true);
      const p = new URLSearchParams(buildParams(0));
      p.delete("ids");
      p.delete("offset");
      p.set("limit", String(SIMILAR_LIMIT));
      if (excludeIds.length) p.set("exclude_ids", excludeIds.slice(0, SIMILAR_EXCLUDE_CAP).join(","));
      apiFetch(`/api/products/similar?${p.toString()}`)
        .then((r) => r.json())
        .then((data) => {
          if (g !== queryGen.current) return;
          // Neither list should repeat a product already on screen: a style
          // number the exact pass found is not a "did you mean".
          const seen = new Set(excludeIds);
          setSimilar({
            items: ((data?.items ?? []) as Product[]).filter((x) => !seen.has(x.id)),
            identifier_suggestions: ((data?.identifier_suggestions ?? []) as IdentSuggestion[]).filter((x) => !seen.has(x.id)),
            searched_for: data?.searched_for ?? null,
          });
        })
        .catch(() => { /* the band is optional; the exact results stand on their own */ })
        .finally(() => { if (g === queryGen.current) setSimilarLoading(false); });
    },
    [buildParams]
  );

  const load = useCallback(
    (nextOffset: number, append: boolean) => {
      const s = ++seq.current;
      setLoading(true);
      if (!append) {
        queryGen.current++;
        similarFetched.current = false;
        seenIds.current = [];
        setSimilar(null);
        setSearchedFor(null);
      }
      apiFetch(`/api/products/search?${buildParams(nextOffset)}`)
        .then((r) => r.json())
        .then((data) => {
          if (s !== seq.current) return;
          const rows: Product[] = data?.items ?? [];
          const nextTotal: number = data?.total ?? 0;
          setItems((prev) => (append ? [...prev, ...rows] : rows));
          setTotal(nextTotal);
          setOffset(nextOffset);
          if (!append && data?.facets) setFacets(data.facets);
          if (!append) setSearchedFor(data?.corrected && data?.searched_for ? String(data.searched_for) : null);
          seenIds.current = append ? [...seenIds.current, ...rows.map((x) => x.id)] : rows.map((x) => x.id);
          // Exact results exhausted: a short first page, or the final page of
          // a longer list. Only a keyword query has near spellings to offer,
          // and the favorites view is a fixed id set with nothing to approximate.
          const exhausted = rows.length < PAGE_SIZE || seenIds.current.length >= nextTotal;
          if (debouncedSearch && !favOnly && exhausted && !similarFetched.current) {
            similarFetched.current = true;
            loadSimilar(seenIds.current);
          }
        })
        .catch(() => {
          if (s === seq.current) { setItems([]); setTotal(0); }
        })
        .finally(() => { if (s === seq.current) setLoading(false); });
    },
    [buildParams, debouncedSearch, favOnly, loadSimilar]
  );

  // reload from top whenever filters/search change (favIds so un-hearting an
  // item refreshes the list while "favorites only" is on)
  useEffect(() => { load(0, false); }, [sel, favOnly, favIds, priceMin, priceMax, debouncedSearch, load]);

  // Persist filters/search whenever they change, merging over rather than
  // clobbering the scroll position the listener below writes independently.
  useEffect(() => {
    try {
      const prev = readSavedSearchState();
      const next: SavedSearchState = { sel, favOnly, priceMin, priceMax, search, scrollTop: prev?.scrollTop };
      sessionStorage.setItem(SEARCH_STATE_KEY, JSON.stringify(next));
    } catch { /* sessionStorage unavailable (private mode, quota) -- fine to skip */ }
  }, [sel, favOnly, priceMin, priceMax, search]);

  // Scroll lives on Layout's own scrolling div, not the window (see
  // data-scroll-root in components/Layout.tsx) -- restore it once, after
  // the first page of results has actually rendered (restoring against an
  // empty list is a no-op that then gets clobbered by the real content's
  // height), and keep saving it as the user scrolls so leaving for another
  // tab and coming back lands in the same spot.
  const scrollRestored = useRef(false);
  useEffect(() => {
    const root = document.querySelector<HTMLElement>("[data-scroll-root]");
    if (!root) return;
    let raf = 0;
    const onScroll = () => {
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        try {
          const prev = readSavedSearchState();
          sessionStorage.setItem(SEARCH_STATE_KEY, JSON.stringify({ ...prev, scrollTop: root.scrollTop }));
        } catch { /* ignore */ }
      });
    };
    root.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      root.removeEventListener("scroll", onScroll);
      if (raf) cancelAnimationFrame(raf);
    };
  }, []);
  useEffect(() => {
    if (scrollRestored.current || items.length === 0) return;
    const saved = readSavedSearchState();
    const root = document.querySelector<HTMLElement>("[data-scroll-root]");
    if (root && saved?.scrollTop) root.scrollTop = saved.scrollTop;
    scrollRestored.current = true;
  }, [items.length]);

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
  const hasSimilar = !!similar && (similar.items.length > 0 || similar.identifier_suggestions.length > 0);

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
  // A product number is passed through untouched. Smart parsing would read
  // "N590321-2" as a price range (min 590321, max 2) and "P2856-44" the same
  // way, wrecking the query — so anything that looks like an item number skips
  // parsing entirely. The backend already matches SKUs, including partials.
  const looksLikeProductNumber = (raw: string) => {
    const q = raw.trim();
    if (q.length < 3 || /\s/.test(q)) return false;
    return /\d/.test(q) && /^[A-Za-z0-9][A-Za-z0-9._/-]*$/.test(q);
  };

  const runSmartSearch = () => {
    // Undo whatever the PREVIOUS parse checked before this one applies
    // anything -- a search bar shows the result of what's in it now, not an
    // accumulation of everything ever typed into it.
    revertAutoApplied();

    if (looksLikeProductNumber(search)) {
      setSearch(search.trim());
      return;
    }
    let text = ` ${search.toLowerCase()} `;
    const justApplied: { categories: string[]; colors: string[]; sizes: string[] } =
      { categories: [], colors: [], sizes: [] };
    const add = (group: "categories" | "colors" | "sizes", val: string) => {
      setSel((prev) => (prev[group].includes(val) ? prev : { ...prev, [group]: [...prev[group], val] }));
      justApplied[group].push(val);
    };
    let appliedPriceMin: number | null = null;
    let appliedPriceMax: number | null = null;
    let m: RegExpMatchArray | null;
    if ((m = text.match(/(?:under|below|less than|cheaper than|<)\s*\$?\s*(\d+(?:\.\d+)?)/)))
      { appliedPriceMax = parseFloat(m[1]); setPriceMax(appliedPriceMax); }
    if ((m = text.match(/(?:over|above|more than|>)\s*\$?\s*(\d+(?:\.\d+)?)/)))
      { appliedPriceMin = parseFloat(m[1]); setPriceMin(appliedPriceMin); }
    if ((m = text.match(/\$?\s*(\d+(?:\.\d+)?)\s*(?:-|to)\s*\$?\s*(\d+(?:\.\d+)?)/)))
      { appliedPriceMin = parseFloat(m[1]); appliedPriceMax = parseFloat(m[2]); setPriceMin(appliedPriceMin); setPriceMax(appliedPriceMax); }
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
    autoAppliedRef.current = { ...justApplied, priceMin: appliedPriceMin, priceMax: appliedPriceMax };
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
        style={{ backgroundColor: "rgb(var(--ll-page))" }}
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
              onChange={(e) => {
                const next = e.target.value;
                setSearch(next);
                // Reaching empty by backspacing is the same "clear it" intent
                // as the X button below -- undo what the last search applied
                // right away, don't wait for another Enter.
                if (!next) revertAutoApplied();
              }}
              onKeyDown={(e) => { if (e.key === "Enter") runSmartSearch(); }}
              placeholder="Item number, or: green wreaths under $20"
              className="w-full rounded-lg border border-stone-300 py-2 pl-9 pr-8 text-sm text-stone-800 outline-none focus:border-emerald-600 focus:ring-1 focus:ring-emerald-600"
            />
            {search && (
              <button
                onClick={() => { setSearch(""); revertAutoApplied(); }}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-stone-400 hover:text-stone-700"
              >
                <X size={15} />
              </button>
            )}
            <p className="absolute -bottom-4 left-1 text-[10px] text-stone-400">↵ Enter to auto-apply colors, size &amp; price · item numbers search as-is</p>
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
              <Heart size={14} fill={favOnly ? "rgb(var(--ll-fav))" : "none"} style={{ color: favOnly ? "rgb(var(--ll-fav))" : "rgb(var(--nc-400))" }} />
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
          {/* View + size toolbar */}
          <div className="mb-4 flex items-center justify-between">
            <p className="text-xs text-stone-400">
              {total.toLocaleString()} result{total === 1 ? "" : "s"}
            </p>
            <div className="flex items-center gap-3">
              {viewMode === "grid" && (
                <div className="flex items-center gap-1">
                  <span className="mr-1 text-xs text-stone-400">Size</span>
                  <button
                    onClick={() => setCardSize((s) => (Math.max(1, s - 1) as CardSize))}
                    disabled={cardSize === 1}
                    className="rounded-md border border-stone-300 p-1 text-stone-500 hover:text-stone-800 disabled:opacity-40"
                    title="Smaller cards (more per row)"
                  ><Minus size={14} /></button>
                  <button
                    onClick={() => setCardSize((s) => (Math.min(4, s + 1) as CardSize))}
                    disabled={cardSize === 4}
                    className="rounded-md border border-stone-300 p-1 text-stone-500 hover:text-stone-800 disabled:opacity-40"
                    title="Bigger cards (fewer per row)"
                  ><Plus size={14} /></button>
                </div>
              )}
              <div className="flex items-center rounded-lg border border-stone-300">
                <button
                  onClick={() => setViewMode("grid")}
                  className={`rounded-l-md p-1.5 ${viewMode === "grid" ? "bg-emerald-700 text-white" : "text-stone-500 hover:text-stone-800"}`}
                  title="Card view"
                ><LayoutGrid size={15} /></button>
                <button
                  onClick={() => setViewMode("list")}
                  className={`rounded-r-md p-1.5 ${viewMode === "list" ? "bg-emerald-700 text-white" : "text-stone-500 hover:text-stone-800"}`}
                  title="List view"
                ><List size={15} /></button>
              </div>
            </div>
          </div>

          {searchedFor && (
            <p className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
              Few exact matches for <span className="font-semibold">“{debouncedSearch}”</span> — also showing results for <span className="font-semibold">“{searchedFor}”</span>.
            </p>
          )}

          {loading && items.length === 0 ? (
            <div className="py-20 text-center text-sm text-stone-400">Searching…</div>
          ) : items.length === 0 ? (
            <div className={hasSimilar || similarLoading ? "py-8 text-center" : "py-20 text-center"}>
              <Package className="mx-auto mb-3 text-stone-300" size={32} />
              <p className="text-sm text-stone-500">
                {debouncedSearch ? <>No exact matches for <span className="font-medium text-stone-700">“{debouncedSearch}”</span>.</> : "No products match these filters."}
              </p>
              {activeCount > 0 && !(hasSimilar || similarLoading) && (
                <button onClick={resetAll} className="mt-3 text-sm font-medium text-emerald-700 hover:text-emerald-900">Clear filters</button>
              )}
            </div>
          ) : (
            <>
              <div className={viewMode === "list" ? "flex flex-col gap-2" : `grid gap-4 ${GRID_COLS[cardSize]}`}>
                {items.map((p) => <ProductCard key={p.id} p={p} onOpen={openDetail} isFav={favIds.has(p.id)} onToggleFav={toggleFav} view={viewMode} size={cardSize} />)}
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

          {/* Approximate matches -- a second ring, after the exact ones */}
          {debouncedSearch && (similarLoading || hasSimilar) && (
            <section className={items.length > 0 ? "mt-10 border-t border-stone-200 pt-6" : "pt-2"}>
              <div className="mb-3">
                <h2 className="text-sm font-semibold text-stone-700">Close matches</h2>
                <p className="text-xs text-stone-400">
                  {similar?.searched_for
                    ? <>Results for <span className="font-medium text-stone-600">“{similar.searched_for}”</span>, a near spelling of “{debouncedSearch}”.</>
                    : <>Not exact matches for “{debouncedSearch}” — check the style number before ordering.</>}
                </p>
              </div>
              {similarLoading && !similar && (
                <div className="flex items-center gap-2 py-4 text-sm text-stone-400">
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-emerald-500 border-t-transparent" />
                  Looking for close matches…
                </div>
              )}
              {(similar?.identifier_suggestions.length ?? 0) > 0 && (
                <div className="mb-4">
                  <p className="mb-1.5 text-xs font-medium text-stone-500">Did you mean one of these style numbers?</p>
                  <div className="flex flex-wrap gap-2">
                    {similar!.identifier_suggestions.map((s) => (
                      <button
                        key={`${s.id}-${s.supplier_sku}`}
                        onClick={() => openDetail(s.id)}
                        title={s.name}
                        className="inline-flex max-w-full items-center gap-2 rounded-lg border border-stone-300 bg-white px-2.5 py-1.5 text-xs hover:border-emerald-400 hover:bg-emerald-50"
                      >
                        <span className="font-mono font-semibold text-stone-800">{s.supplier_sku}</span>
                        <span className="truncate text-stone-500">{s.name}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {(similar?.items.length ?? 0) > 0 && (
                <div className={viewMode === "list" ? "flex flex-col gap-2" : `grid gap-4 ${GRID_COLS[cardSize]}`}>
                  {similar!.items.map((p) => <ProductCard key={p.id} p={p} onOpen={openDetail} isFav={favIds.has(p.id)} onToggleFav={toggleFav} view={viewMode} size={cardSize} />)}
                </div>
              )}
            </section>
          )}
        </main>
      </div>
      {detailProduct && (
        <ProductDetailModal product={detailProduct} onClose={closeDetail} />
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

function CardImage({ imgs, alt, cls }: { imgs: string[]; alt: string; cls: string }) {
  if (!imgs.length) {
    return <div className="flex h-full w-full items-center justify-center"><Package className="text-stone-300" size={24} /></div>;
  }
  // ProxiedImage walks the candidate URLs (direct → proxy) and shows a clean
  // placeholder only if every one fails — so a card is never a broken tile.
  return <ProxiedImage src={imgs[0]} fallbacks={imgs.slice(1)} alt={alt} className={cls} />;
}

function ProductCard({ p, onOpen, isFav, onToggleFav, view, size }: {
  p: Product;
  onOpen: (id: number) => void;
  isFav: boolean;
  onToggleFav: (id: number) => void;
  view: ViewMode;
  size: CardSize;
}) {
  const n = p.raw_data?.normalized || {};
  const tags = [n.size_in != null ? `${n.size_in}"` : null, n.color, n.finish].filter(Boolean) as string[];
  const metric = metricHintText(p.name);
  const imgs = (p.image_urls || []).filter(Boolean) as string[];
  const price = p.current_price != null ? `$${Number(p.current_price).toFixed(2)}` : "";

  if (view === "list") {
    return (
      <div
        onClick={() => onOpen(p.id)}
        className="group relative flex cursor-pointer items-center gap-4 rounded-xl border border-stone-200 bg-white px-3 py-2 shadow-sm transition-shadow hover:shadow-md"
      >
        <div className="flex h-16 w-16 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-stone-50">
          <CardImage imgs={imgs} alt={p.name} cls="max-h-full max-w-full object-contain" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-stone-800" title={p.name}>{p.name}</p>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-stone-500">
            <span className="truncate">{p.supplier_name || "—"}</span>
            {p.supplier_sku && <span className="font-mono text-stone-400">{p.supplier_sku}</span>}
            {metric && <span className="font-medium text-emerald-700" title={METRIC_CHEAT}>{metric}</span>}
            {tags.map((t, i) => <span key={i} className="rounded bg-emerald-50 px-1.5 py-0.5 text-[10px] font-medium text-emerald-800">{t}</span>)}
          </div>
        </div>
        <span className="shrink-0 text-sm font-semibold text-emerald-800">{price}</span>
        <button
          onClick={(e) => { e.stopPropagation(); onToggleFav(p.id); }}
          title={isFav ? "Remove favorite" : "Add to favorites"}
          className="shrink-0"
        >
          <Heart size={16} fill={isFav ? "rgb(var(--ll-fav))" : "none"} style={{ color: isFav ? "rgb(var(--ll-fav))" : "rgb(var(--nc-400))" }} />
        </button>
      </div>
    );
  }

  const compact = size === 1;
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
        <Heart size={14} fill={isFav ? "rgb(var(--ll-fav))" : "none"} style={{ color: isFav ? "rgb(var(--ll-fav))" : "rgb(var(--nc-400))" }} />
      </button>
      <div className={`flex ${IMG_HEIGHT[size]} items-center justify-center overflow-hidden bg-stone-50`}>
        <CardImage imgs={imgs} alt={p.name} cls="h-full w-full object-contain" />
      </div>
      <div className={compact ? "p-2" : "p-3"}>
        <p className={`truncate font-medium text-stone-800 ${compact ? "text-xs" : "text-sm"}`} title={p.name}>{p.name}</p>
        {!compact && metric && (
          <p className="mt-0.5 truncate text-[11px] font-medium text-emerald-700" title={METRIC_CHEAT}>{metric}</p>
        )}
        <div className="mt-1 flex items-center justify-between gap-1">
          <span className="truncate text-xs text-stone-500">{p.supplier_name || "—"}</span>
          <span className={`shrink-0 font-semibold text-emerald-800 ${compact ? "text-xs" : "text-sm"}`}>{price}</span>
        </div>
        {!compact && <p className="mt-0.5 truncate font-mono text-[11px] text-stone-400">{p.supplier_sku || ""}</p>}
        {!compact && tags.length > 0 && (
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
