import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { LucideIcon } from "components/icons";
import {
  AlertCircle,
  ArrowRight,
  CalendarDays,
  Check,
  CheckCircle2,
  Clock,
  Loader2,
  Lock,
  Plus,
  Search,
  SlidersHorizontal,
  Users,
  X,
} from "components/icons";
import Layout from "components/Layout";
import { apiFetch } from "utils/apiFetch";
import { currentMe } from "utils/me";
import {
  CHANGES_SEEN_EVENT,
  EMPTY_FILTERS,
  TYPE_FILTERS,
  changesQuery,
  groupByDay,
  hasFilters,
  mergePages,
  toggleType,
  typeLabel,
} from "utils/scheduleChanges";
import type { ChangeEvent, ChangeFilters, ChangeType, ChangesPage } from "utils/scheduleChanges";

const TYPE_ICON: Record<ChangeType, LucideIcon> = {
  moves: ArrowRight,
  adds: Plus,
  holds: AlertCircle,
  approvals: CheckCircle2,
  staffing: Users,
  locks: Lock,
  dates: CalendarDays,
};

const TYPE_TONE: Record<ChangeType, string> = {
  moves: "bg-emerald-50 text-emerald-700",
  adds: "bg-emerald-50 text-emerald-700",
  holds: "bg-amber-50 text-amber-700",
  approvals: "bg-emerald-50 text-emerald-700",
  staffing: "bg-stone-100 text-stone-600",
  locks: "bg-stone-100 text-stone-600",
  dates: "bg-stone-100 text-stone-600",
};

function announceSeen() {
  window.dispatchEvent(new Event(CHANGES_SEEN_EVENT));
}

/**
 * Install Changes: every change to the Install Schedule, in words, newest
 * first and grouped by day (Comment #19). Following it marks what's new
 * since your last visit; the count shows on the menu entry.
 */
export default function InstallChanges() {
  const [filters, setFilters] = useState<ChangeFilters>(EMPTY_FILTERS);
  const [query, setQuery] = useState("");
  const [data, setData] = useState<ChangesPage | null>(null);
  const [events, setEvents] = useState<ChangeEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [filtersOpen, setFiltersOpen] = useState(() =>
    typeof window !== "undefined" ? window.innerWidth >= 640 : true,
  );
  const canFollow = !currentMe()?.viewOnly;
  // The newest change this visit showed: leaving the page marks up to it as
  // seen, so anything saved while you were here is still NEW next time.
  const newestShown = useRef<string | null>(null);
  const following = useRef(false);

  // Debounce the search box into the filters.
  useEffect(() => {
    const t = window.setTimeout(() => setFilters((f) => (f.q === query ? f : { ...f, q: query })), 250);
    return () => window.clearTimeout(t);
  }, [query]);

  const load = useCallback(async (f: ChangeFilters) => {
    setLoading(true);
    setError(null);
    try {
      const r = await apiFetch(`/api/schedule-changes?${changesQuery(f)}`);
      if (!r.ok) throw new Error(r.status === 403 ? "You don't have access to the changes list." : "Couldn't load changes.");
      const page: ChangesPage = await r.json();
      setData(page);
      setEvents(page.events);
      following.current = page.following;
      if (page.newest && (!newestShown.current || page.newest > newestShown.current)) {
        newestShown.current = page.newest;
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(filters);
  }, [filters, load]);

  useEffect(() => () => {
    if (!following.current || !newestShown.current || !canFollow) return;
    apiFetch("/api/schedule-changes/seen", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ upTo: newestShown.current }),
    }).then(announceSeen).catch(() => {});
  }, [canFollow]);

  const loadMore = async () => {
    if (!data?.next) return;
    setLoadingMore(true);
    try {
      const r = await apiFetch(`/api/schedule-changes?${changesQuery(filters, data.next)}`);
      if (!r.ok) throw new Error();
      const page: ChangesPage = await r.json();
      setEvents((shown) => mergePages(shown, page.events));
      setData((d) => (d ? { ...d, next: page.next } : page));
    } catch {
      setError("Couldn't load more changes.");
    } finally {
      setLoadingMore(false);
    }
  };

  const setFollow = async (on: boolean) => {
    setBusy(true);
    try {
      const r = await apiFetch("/api/schedule-changes/follow", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ following: on }),
      });
      if (r.ok) {
        following.current = on;
        announceSeen();
        await load(filters);
      }
    } finally {
      setBusy(false);
    }
  };

  const markAllSeen = async () => {
    setBusy(true);
    try {
      const r = await apiFetch("/api/schedule-changes/seen", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ upTo: data?.newest ?? null }),
      });
      if (r.ok) {
        setEvents((shown) => shown.map((e) => ({ ...e, isNew: false })));
        setData((d) => (d ? { ...d, unseen: 0 } : d));
        announceSeen();
      }
    } finally {
      setBusy(false);
    }
  };

  const groups = useMemo(() => groupByDay(events), [events]);
  const activeFilterCount =
    (filters.q.trim() ? 1 : 0) + (filters.from || filters.to ? 1 : 0) + filters.types.length;
  const unseen = data?.unseen ?? 0;

  return (
    <Layout>
      <header
        className="sticky top-0 z-10 border-b border-stone-200 px-4 py-3 sm:px-10 sm:py-5"
        style={{ backgroundColor: "rgb(var(--ll-page))" }}
      >
        <div className="flex items-center gap-2">
          <h1
            className="flex min-w-0 flex-1 items-center gap-2 text-lg font-semibold text-stone-800 sm:text-xl"
            style={{ fontFamily: "'Sora', system-ui, sans-serif" }}
          >
            <Clock size={18} className="flex-none text-emerald-700" />
            <span className="truncate sm:hidden">Changes</span>
            <span className="hidden truncate sm:inline">Install Changes</span>
          </h1>
          {canFollow && data && (
            data.following ? (
              <>
                {unseen > 0 && (
                  <button
                    type="button"
                    onClick={markAllSeen}
                    disabled={busy}
                    className="min-h-10 flex-none rounded-lg bg-emerald-700 px-3 text-xs font-semibold text-white hover:bg-emerald-800 disabled:opacity-50 sm:min-h-9"
                  >
                    Mark all seen<span className="hidden sm:inline"> ({unseen})</span>
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setFollow(false)}
                  disabled={busy}
                  title="Stop following changes"
                  className="flex min-h-10 flex-none items-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-50 px-3 text-xs font-semibold text-emerald-800 hover:border-emerald-300 disabled:opacity-50 sm:min-h-9"
                >
                  <Check size={14} /> Following
                </button>
              </>
            ) : (
              <button
                type="button"
                onClick={() => setFollow(true)}
                disabled={busy}
                className="min-h-10 flex-none rounded-lg border border-stone-300 bg-white px-3 text-xs font-semibold text-stone-700 hover:border-stone-400 disabled:opacity-50 sm:min-h-9"
              >
                Follow changes
              </button>
            )
          )}
        </div>
        <p className="mt-0.5 hidden text-xs text-stone-500 sm:block">
          Every change to the Install Schedule, newest first. Follow it to see what's new since you last looked.
        </p>
      </header>

      <div className="mx-auto max-w-3xl px-4 pb-24 pt-3 sm:px-6 sm:pt-5">
        {/* Search + filters */}
        <div className="mb-3 flex items-center gap-2">
          <label className="relative min-w-0 flex-1">
            <span className="sr-only">Search changes</span>
            <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-stone-400" />
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search a client or person"
              className="h-10 w-full rounded-lg border border-stone-200 bg-white pl-9 pr-3 text-base text-stone-800 placeholder:text-stone-400 focus:border-emerald-500 focus:outline-none sm:text-sm"
            />
          </label>
          <button
            type="button"
            onClick={() => setFiltersOpen((o) => !o)}
            aria-expanded={filtersOpen}
            className={`flex h-10 flex-none items-center gap-1.5 rounded-lg border px-3 text-xs font-semibold ${
              filtersOpen || activeFilterCount > 0
                ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                : "border-stone-200 bg-white text-stone-600"
            }`}
          >
            <SlidersHorizontal size={14} />
            Filters
            {activeFilterCount > 0 && <span className="text-emerald-600">{activeFilterCount}</span>}
          </button>
        </div>

        {filtersOpen && (
          <div className="mb-4 rounded-xl border border-stone-200 bg-stone-50/60 p-3">
            <div className="flex flex-wrap gap-1.5">
              {TYPE_FILTERS.map(({ type, label }) => {
                const on = filters.types.includes(type);
                return (
                  <button
                    key={type}
                    type="button"
                    onClick={() => setFilters((f) => ({ ...f, types: toggleType(f.types, type) }))}
                    aria-pressed={on}
                    className={`min-h-9 rounded-full border px-3 text-xs font-medium transition-colors ${
                      on
                        ? "border-emerald-600 bg-emerald-50 text-emerald-800"
                        : "border-stone-200 bg-white text-stone-600 hover:border-stone-300"
                    }`}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2 sm:flex sm:items-end">
              <label className="block text-[11px] font-semibold uppercase tracking-wide text-stone-500">
                Changed from
                <input
                  type="date"
                  value={filters.from}
                  onChange={(e) => setFilters((f) => ({ ...f, from: e.target.value }))}
                  className="mt-1 block h-10 w-full rounded-lg border border-stone-200 bg-white px-2 text-base font-normal normal-case tracking-normal text-stone-800 focus:border-emerald-500 focus:outline-none sm:w-40 sm:text-sm"
                />
              </label>
              <label className="block text-[11px] font-semibold uppercase tracking-wide text-stone-500">
                To
                <input
                  type="date"
                  value={filters.to}
                  onChange={(e) => setFilters((f) => ({ ...f, to: e.target.value }))}
                  className="mt-1 block h-10 w-full rounded-lg border border-stone-200 bg-white px-2 text-base font-normal normal-case tracking-normal text-stone-800 focus:border-emerald-500 focus:outline-none sm:w-40 sm:text-sm"
                />
              </label>
              {hasFilters(filters) && (
                <button
                  type="button"
                  onClick={() => {
                    setQuery("");
                    setFilters(EMPTY_FILTERS);
                  }}
                  className="col-span-2 flex h-10 items-center justify-center gap-1 rounded-lg px-2 text-xs font-medium text-stone-500 hover:text-stone-800 sm:ml-auto"
                >
                  <X size={13} /> Clear filters
                </button>
              )}
            </div>
          </div>
        )}

        {data && !data.following && canFollow && !loading && (
          <p className="mb-3 rounded-lg bg-stone-100/70 px-3 py-2 text-xs text-stone-600">
            Follow changes to get a NEW marker on anything changed since your last visit, and a count on the menu.
          </p>
        )}

        {loading && events.length === 0 ? (
          <div className="flex justify-center py-16 text-stone-400">
            <Loader2 size={22} className="animate-spin" />
          </div>
        ) : error ? (
          <p className="py-12 text-center text-sm text-stone-500">{error}</p>
        ) : events.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-stone-200 py-14 text-center">
            <Clock size={26} className="mb-3 text-stone-300" strokeWidth={1.5} />
            <p className="text-sm text-stone-500">
              {hasFilters(filters) ? "No changes match these filters." : "No schedule changes yet."}
            </p>
          </div>
        ) : (
          <div className={`flex flex-col gap-5 ${loading ? "opacity-60" : ""}`}>
            {groups.map((g) => (
              <section key={g.day} aria-label={g.heading}>
                <h2 className="mb-1.5 flex items-baseline gap-2 px-1 text-xs font-semibold uppercase tracking-wide text-stone-500">
                  {g.heading}
                  {g.newCount > 0 && <span className="normal-case tracking-normal text-emerald-700">{g.newCount} new</span>}
                </h2>
                <ul className="overflow-hidden rounded-xl border border-stone-200 bg-white">
                  {g.events.map((e) => (
                    <ChangeRow key={e.id} e={e} />
                  ))}
                </ul>
              </section>
            ))}
            {data?.next && (
              <button
                type="button"
                onClick={loadMore}
                disabled={loadingMore}
                className="mx-auto flex min-h-10 items-center gap-2 rounded-lg border border-stone-200 bg-white px-4 text-xs font-semibold text-stone-600 hover:border-stone-300 disabled:opacity-50"
              >
                {loadingMore && <Loader2 size={13} className="animate-spin" />}
                Show older changes
              </button>
            )}
          </div>
        )}
      </div>
    </Layout>
  );
}

function ChangeRow({ e }: { e: ChangeEvent }) {
  const Icon = TYPE_ICON[e.type] ?? ArrowRight;
  return (
    <li
      className={`flex gap-3 border-b border-stone-100 px-3 py-2.5 last:border-b-0 sm:px-4 ${
        e.isNew ? "bg-emerald-50/50" : ""
      }`}
    >
      <span
        className={`mt-0.5 flex h-7 w-7 flex-none items-center justify-center rounded-full ${TYPE_TONE[e.type] ?? TYPE_TONE.dates}`}
        title={typeLabel(e.type)}
        aria-hidden="true"
      >
        <Icon size={14} />
      </span>
      <div className="min-w-0 flex-1">
        <p className="break-words text-sm leading-snug text-stone-800">
          {e.isNew && (
            <span className="mr-1.5 inline-block rounded bg-emerald-600 px-1.5 py-px align-[1px] text-[10px] font-bold uppercase tracking-wide text-white">
              New
            </span>
          )}
          {e.text}
        </p>
        <p className="mt-0.5 text-xs text-stone-500">
          {e.time} CT · {e.mine ? "You" : e.by}
        </p>
      </div>
    </li>
  );
}
