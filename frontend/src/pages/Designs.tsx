import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import Arrangements from "./Arrangements";
import {
  Check,
  ChevronDown,
  CircleDashed,
  Flower2,
  Layers,
  LayoutGrid,
  Leaf,
  List,
  Minus,
  Plus,
  RotateCcw,
  Search,
  Shapes,
  Shrub,
  Sparkle,
  Spline,
  Sprout,
  TreeDeciduous,
  TreePine,
  Waves,
  X,
} from "lucide-react";
import Layout from "components/Layout";
import { ProxiedImage } from "./Library";
import { formatCurrency } from "utils/format";
import {
  Design,
  DesignFacet,
  DesignFacets,
  DesignSort,
  EMPTY_FACETS,
  fetchDesignList,
} from "utils/designs";

// The Designs tab — the shortcut to every build in the shop.
//
// Before this page a design was four-plus clicks deep (Clients → project →
// room → scope → "Open builder"). Here they're all in one grid: filter by the
// real hierarchy (Client → Project → Group) plus build type, search by name or
// material, and open the builder in one click.
//
// The card image slot renders `hero_image_url` when the design has one and
// falls back to a build-type icon. AI mockups land in that same slot later with
// no rework here.

type FilterKey = "clients" | "projects" | "groups" | "build_types";

type Selection = Record<FilterKey, string[]>;

const EMPTY_SELECTION: Selection = { clients: [], projects: [], groups: [], build_types: [] };

const PAGE_SIZE = 48;

// View + card-size preferences, persisted per browser (same pattern as
// Catalog Search, separate keys so the two pages don't fight over one setting).
type ViewMode = "grid" | "list";
type CardSize = 1 | 2 | 3 | 4; // 1 = smallest (most per row) … 4 = largest
const GRID_COLS: Record<CardSize, string> = {
  1: "grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 xl:grid-cols-8",
  2: "grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 xl:grid-cols-6",
  3: "grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5",
  4: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4",
};
const IMG_HEIGHT: Record<CardSize, string> = { 1: "h-24", 2: "h-32", 3: "h-40", 4: "h-56" };
const VIEW_KEY = "leaf-ledger:designs-view:v1";
const SIZE_KEY = "leaf-ledger:designs-size:v1";

const SORTS: { value: DesignSort; label: string }[] = [
  { value: "recent", label: "Recently updated" },
  { value: "name", label: "Name (A–Z)" },
  { value: "cost", label: "Cost (high → low)" },
  { value: "type", label: "Build type" },
];

const FILTERS: { key: FilterKey; label: string; facet: keyof DesignFacets }[] = [
  { key: "clients", label: "Client", facet: "clients" },
  { key: "projects", label: "Project", facet: "projects" },
  { key: "groups", label: "Group", facet: "groups" },
  { key: "build_types", label: "Build type", facet: "build_types" },
];

// Build-type → icon. Ordered: the first pattern that matches wins, so
// "Christmas Tree" beats the generic "tree" rule.
type IconComponent = typeof TreePine;
const BUILD_TYPE_ICONS: [RegExp, IconComponent][] = [
  [/christmas tree|holiday tree/, TreePine],
  [/wreath/, CircleDashed],
  [/garland/, Spline],
  [/swag/, Waves],
  [/spray|teardrop|door drop/, Sprout],
  [/planter|container garden/, Shrub],
  [/ornament/, Sparkle],
  [/branch|stem/, Leaf],
  [/tree|fig/, TreeDeciduous],
  [/centerpiece|arrangement|floral|orchid|succulent/, Flower2],
];

export function buildTypeIcon(buildType?: string | null): IconComponent {
  const normalized = (buildType || "").trim().toLowerCase();
  if (!normalized) return Shapes;
  for (const [pattern, Icon] of BUILD_TYPE_ICONS) {
    if (pattern.test(normalized)) return Icon;
  }
  return Shapes;
}

export default function Designs() {
  const navigate = useNavigate();
  const location = useLocation();
  const isNew = location.pathname.replace(/\/+$/, "").endsWith("/new");

  const [sel, setSel] = useState<Selection>(EMPTY_SELECTION);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [sort, setSort] = useState<DesignSort>("recent");
  const [items, setItems] = useState<Design[]>([]);
  const [facets, setFacets] = useState<DesignFacets>(EMPTY_FACETS);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  // Distinguishes "still fetching" from "fetched and there's nothing" so the
  // empty state never shows before the first response.
  const [loadedOnce, setLoadedOnce] = useState(false);
  const seq = useRef(0);

  const [viewMode, setViewMode] = useState<ViewMode>(() => (localStorage.getItem(VIEW_KEY) as ViewMode) || "grid");
  const [cardSize, setCardSize] = useState<CardSize>(() => (Number(localStorage.getItem(SIZE_KEY)) as CardSize) || 3);
  useEffect(() => { localStorage.setItem(VIEW_KEY, viewMode); }, [viewMode]);
  useEffect(() => { localStorage.setItem(SIZE_KEY, String(cardSize)); }, [cardSize]);

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search.trim()), 350);
    return () => clearTimeout(t);
  }, [search]);

  const load = useCallback(
    (nextOffset: number, append: boolean) => {
      const s = ++seq.current;
      setLoading(true);
      // fetchDesignList never rejects — a missing/failing API resolves to an
      // empty page, which lands us in the empty state instead of a crash.
      fetchDesignList({
        search: debouncedSearch || undefined,
        clients: sel.clients,
        projects: sel.projects,
        groups: sel.groups,
        build_types: sel.build_types,
        sort,
        limit: PAGE_SIZE,
        offset: nextOffset,
      }).then((data) => {
        if (s !== seq.current) return;
        setItems((prev) => (append ? [...prev, ...data.items] : data.items));
        setTotal(data.total);
        setOffset(nextOffset);
        if (!append) setFacets(data.facets);
        setLoading(false);
        setLoadedOnce(true);
      });
    },
    [debouncedSearch, sel, sort]
  );

  useEffect(() => { load(0, false); }, [load]);

  const toggle = (group: FilterKey, value: string) =>
    setSel((prev) => {
      const has = prev[group].includes(value);
      return { ...prev, [group]: has ? prev[group].filter((v) => v !== value) : [...prev[group], value] };
    });

  const activeCount = useMemo(
    () => Object.values(sel).reduce((n, arr) => n + arr.length, 0) + (debouncedSearch ? 1 : 0),
    [sel, debouncedSearch]
  );
  const resetAll = () => { setSel(EMPTY_SELECTION); setSearch(""); };

  // Infinite scroll + prefetch — next page starts loading ~800px early.
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

  return (
    <Layout>
      <header
        className="sticky top-0 z-20 border-b border-stone-200 px-10 py-4"
        style={{ backgroundColor: "rgb(var(--ll-page))" }}
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="flex items-center gap-2 text-xl font-semibold text-stone-800" style={{ fontFamily: "Georgia, serif" }}>
              <Shapes size={18} className="text-emerald-700" />
              Designs
            </h1>
            <p className="mt-0.5 text-xs text-stone-500">
              Every build in one place — filter by client, project, group &amp; build type.
            </p>
          </div>
          {/* All Designs ⇄ New Design */}
          <div className="flex shrink-0 items-center rounded-lg border border-stone-300 bg-white p-0.5">
            <button
              onClick={() => navigate("/designs")}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                isNew ? "text-stone-500 hover:text-stone-800" : "bg-emerald-700 text-white"
              }`}
            >
              All Designs
            </button>
            <button
              onClick={() => navigate("/designs/new")}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                isNew ? "bg-emerald-700 text-white" : "text-stone-500 hover:text-stone-800"
              }`}
            >
              New Design
            </button>
          </div>
        </div>
      </header>

      {isNew ? (
        <Arrangements embedded newDesign />
      ) : (
        <main className="px-10 py-6">
          {/* Filter chips (left) + search / sort / view controls (right) */}
          <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2">
              {FILTERS.map((f) => (
                <FilterChip
                  key={f.key}
                  label={f.label}
                  options={facets[f.facet]}
                  selected={sel[f.key]}
                  onToggle={(v) => toggle(f.key, v)}
                  onClear={() => setSel((prev) => ({ ...prev, [f.key]: [] }))}
                />
              ))}
              {activeCount > 0 && (
                <button
                  onClick={resetAll}
                  className="flex items-center gap-1 rounded-full px-2.5 py-1.5 text-xs font-medium text-emerald-700 hover:bg-emerald-50 hover:text-emerald-900"
                >
                  <RotateCcw size={12} /> Reset ({activeCount})
                </button>
              )}
            </div>

            <div className="flex items-center gap-3">
              <div className="relative w-72 max-w-[36vw]">
                <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-stone-400" />
                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search designs & materials…"
                  className="w-full rounded-lg border border-stone-300 bg-white py-2 pl-9 pr-8 text-sm text-stone-800 outline-none focus:border-emerald-600 focus:ring-1 focus:ring-emerald-600"
                />
                {search && (
                  <button
                    onClick={() => setSearch("")}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-stone-400 hover:text-stone-700"
                    aria-label="Clear search"
                  >
                    <X size={15} />
                  </button>
                )}
              </div>
              <select
                value={sort}
                onChange={(e) => setSort(e.target.value as DesignSort)}
                className="rounded-lg border border-stone-300 bg-white px-2.5 py-2 text-sm text-stone-700 outline-none focus:border-emerald-600"
                title="Sort designs"
              >
                {SORTS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
              </select>
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
              <div className="flex items-center rounded-lg border border-stone-300 bg-white">
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

          <p className="mb-3 text-xs text-stone-400">
            {total.toLocaleString()} design{total === 1 ? "" : "s"}
          </p>

          {!loadedOnce && loading ? (
            <div className="py-20 text-center text-sm text-stone-400">Loading designs…</div>
          ) : items.length === 0 ? (
            <EmptyState activeCount={activeCount} onReset={resetAll} onNew={() => navigate("/designs/new")} />
          ) : (
            <>
              <div className={viewMode === "list" ? "flex flex-col gap-2" : `grid gap-4 ${GRID_COLS[cardSize]}`}>
                {items.map((d) => (
                  <DesignCard
                    key={String(d.id)}
                    d={d}
                    view={viewMode}
                    size={cardSize}
                    // Until the design detail/builder route lands, a card opens
                    // the design's project — the builder page that exists today.
                    onOpen={() => { if (d.project_id != null) navigate(`/projects?id=${encodeURIComponent(String(d.project_id))}`); }}
                  />
                ))}
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
      )}
    </Layout>
  );
}

/**
 * A multi-select filter chip. Options and their counts come from the current
 * search's facets, so the counts stay live as other filters narrow the set.
 */
function FilterChip({ label, options, selected, onToggle, onClear }: {
  label: string;
  options: DesignFacet[];
  selected: string[];
  onToggle: (value: string) => void;
  onClear: () => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const disabled = options.length === 0 && selected.length === 0;
  const active = selected.length > 0;

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => { if (!disabled) setOpen((o) => !o); }}
        disabled={disabled}
        className={`flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
          active
            ? "border-emerald-600 bg-emerald-700 text-white"
            : "border-stone-300 bg-white text-stone-600 hover:border-stone-400 hover:text-stone-900"
        } ${disabled ? "cursor-not-allowed opacity-50" : ""}`}
        title={disabled ? `No ${label.toLowerCase()} options yet` : `Filter by ${label.toLowerCase()}`}
      >
        {label}
        {active && (
          <span className="rounded-full bg-white/25 px-1.5 text-[10px] leading-4">{selected.length}</span>
        )}
        <ChevronDown size={12} className={open ? "rotate-180 transition-transform" : "transition-transform"} />
      </button>

      {open && (
        <div className="absolute left-0 top-full z-30 mt-1.5 max-h-80 w-64 overflow-y-auto rounded-xl border border-stone-200 bg-white p-1.5 shadow-lg">
          <div className="flex items-center justify-between px-2 py-1">
            <span className="text-[10px] font-semibold uppercase tracking-widest text-stone-400">{label}</span>
            {selected.length > 0 && (
              <button onClick={onClear} className="text-[11px] font-medium text-emerald-700 hover:text-emerald-900">Clear</button>
            )}
          </div>
          {options.length === 0 ? (
            <p className="px-2 py-2 text-xs italic text-stone-400">Nothing to filter yet.</p>
          ) : (
            options.map((o) => {
              const on = selected.includes(o.value);
              return (
                <button
                  key={o.value}
                  onClick={() => onToggle(o.value)}
                  className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm hover:bg-stone-100"
                >
                  <span className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border ${
                    on ? "border-emerald-700 bg-emerald-700 text-white" : "border-stone-300"
                  }`}>
                    {on && <Check size={11} strokeWidth={3} />}
                  </span>
                  <span className={`flex-1 truncate ${on ? "font-medium text-emerald-900" : "text-stone-600"}`}>{o.value}</span>
                  <span className="shrink-0 text-xs text-stone-400">{o.count.toLocaleString()}</span>
                </button>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}

/**
 * The card's image slot. Renders the hero mockup when one exists and otherwise
 * a build-type icon — so dropping in AI mockup URLs later needs no change here.
 */
function DesignImage({ d, className }: { d: Design; className?: string }) {
  const Icon = buildTypeIcon(d.build_type);
  if (d.hero_image_url) {
    return <ProxiedImage src={d.hero_image_url} alt={d.name} className={className ?? "h-full w-full object-cover"} />;
  }
  return (
    <div className="flex h-full w-full items-center justify-center">
      <Icon className="text-emerald-700/40" size={36} strokeWidth={1.4} />
    </div>
  );
}

function hierarchy(d: Design): string {
  return [d.client_name, d.project_name, d.group_name].filter(Boolean).join(" · ") || "Unassigned";
}

function DesignCard({ d, view, size, onOpen }: {
  d: Design;
  view: ViewMode;
  size: CardSize;
  onOpen: () => void;
}) {
  const Icon = buildTypeIcon(d.build_type);
  const count = d.item_count ?? 0;
  const cost = d.total_cost != null ? formatCurrency(Number(d.total_cost)) : "—";

  if (view === "list") {
    return (
      <div
        onClick={onOpen}
        className="group flex cursor-pointer items-center gap-4 rounded-xl border border-stone-200 bg-white px-3 py-2 shadow-sm transition-shadow hover:shadow-md"
      >
        <div className="flex h-14 w-14 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-stone-50">
          <DesignImage d={d} className="h-full w-full object-cover" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-stone-800" title={d.name}>{d.name}</p>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-stone-500">
            {d.build_type && (
              <span className="flex items-center gap-1 font-medium text-emerald-800">
                <Icon size={12} /> {d.build_type}
              </span>
            )}
            <span className="truncate">{hierarchy(d)}</span>
          </div>
        </div>
        <span className="shrink-0 text-xs text-stone-500">{count} item{count === 1 ? "" : "s"}</span>
        <span className="shrink-0 text-sm font-semibold text-emerald-800">{cost}</span>
      </div>
    );
  }

  const compact = size === 1;
  return (
    <div
      onClick={onOpen}
      className="group cursor-pointer overflow-hidden rounded-xl border border-stone-200 bg-white shadow-sm transition-shadow hover:shadow-md"
    >
      <div className={`flex ${IMG_HEIGHT[size]} items-center justify-center overflow-hidden bg-stone-50`}>
        <DesignImage d={d} className="h-full w-full object-cover" />
      </div>
      <div className={compact ? "p-2" : "p-3"}>
        <p className={`truncate font-medium text-stone-800 ${compact ? "text-xs" : "text-sm"}`} title={d.name}>{d.name}</p>
        {d.build_type && (
          <p className="mt-0.5 flex items-center gap-1 truncate text-[11px] font-medium text-emerald-700">
            <Icon size={11} className="shrink-0" /> <span className="truncate">{d.build_type}</span>
          </p>
        )}
        {!compact && (
          <p className="mt-1 truncate text-xs text-stone-500" title={hierarchy(d)}>{hierarchy(d)}</p>
        )}
        <div className="mt-1.5 flex items-center justify-between gap-1">
          <span className="flex shrink-0 items-center gap-1 text-xs text-stone-400">
            <Layers size={11} /> {count}
          </span>
          <span className={`shrink-0 font-semibold text-emerald-800 ${compact ? "text-xs" : "text-sm"}`}>{cost}</span>
        </div>
      </div>
    </div>
  );
}

/**
 * A sparse grid here is expected, not a bug: there are only a handful of
 * designs so far and most have no saved parts yet. The copy says so plainly
 * rather than reading like a failure.
 */
function EmptyState({ activeCount, onReset, onNew }: {
  activeCount: number;
  onReset: () => void;
  onNew: () => void;
}) {
  if (activeCount > 0) {
    return (
      <div className="rounded-xl border border-dashed border-stone-300 py-20 text-center">
        <Shapes className="mx-auto mb-3 text-stone-300" size={32} />
        <p className="text-sm text-stone-500">No designs match these filters.</p>
        <button onClick={onReset} className="mt-3 text-sm font-medium text-emerald-700 hover:text-emerald-900">
          Clear filters
        </button>
      </div>
    );
  }
  return (
    <div className="rounded-xl border border-dashed border-stone-300 py-20 text-center">
      <Shapes className="mx-auto mb-3 text-stone-300" size={32} />
      <p className="text-sm font-medium text-stone-600">No designs yet — start one with New Design.</p>
      <p className="mx-auto mt-1 max-w-md text-xs text-stone-400">
        Designs show up here as soon as they're created. A short or empty list is normal early on —
        most builds don't have their parts saved yet.
      </p>
      <button
        onClick={onNew}
        className="mt-4 rounded-lg bg-emerald-700 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-emerald-800"
      >
        New Design
      </button>
    </div>
  );
}

