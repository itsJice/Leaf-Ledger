/**
 * Home ("/"): a "Today" strip (today's or the next install day, from
 * /api/lead/today-summary) over an app-icon grid of every page, install
 * season first (utils/homeTiles.ts). Replaced the catalog-era dashboard
 * (stats + action cards) on 2026-10-08.
 */
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ChevronRight, TreePine } from "components/icons";
import Layout from "components/Layout";
import { apiFetch } from "utils/apiFetch";
import { currentMe } from "utils/me";
import {
  GROUP_LABELS,
  type HomeTile,
  type TileGroup,
  type TodaySummary,
  openCommentCount,
  visibleTiles,
} from "utils/homeTiles";

const SORA = { fontFamily: "'Sora', system-ui, sans-serif" };

async function getJson<T>(path: string): Promise<T | null> {
  try {
    const res = await apiFetch(path);
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

function greeting(d: Date) {
  const h = d.getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

function prettyDate(iso: string, opts: Intl.DateTimeFormatOptions) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-US", opts);
}

function Tile({ tile, badge }: { tile: HomeTile; badge?: number }) {
  const Icon = tile.icon;
  return (
    <Link
      to={tile.path}
      className="group flex min-w-0 flex-col items-center gap-1.5 rounded-2xl px-1 py-2 outline-none focus-visible:ring-2 focus-visible:ring-emerald-600"
    >
      <span
        className="relative flex aspect-square w-full max-w-[64px] items-center justify-center rounded-[22%] shadow-sm transition-transform duration-150 ease-out group-hover:-translate-y-0.5 group-active:scale-95 sm:max-w-[72px]"
        style={{
          backgroundColor: tile.tone,
          backgroundImage: "linear-gradient(160deg, rgba(255,255,255,0.18), rgba(255,255,255,0) 55%)",
        }}
      >
        <Icon className="h-[46%] w-[46%] text-white" strokeWidth={1.8} />
        {badge ? (
          <span
            className="absolute -right-1.5 -top-1.5 flex h-5 min-w-[20px] items-center justify-center rounded-full bg-red-600 px-1 text-[11px] font-bold leading-none text-white ring-2"
            style={{ ["--tw-ring-color" as string]: "rgb(var(--ll-page))" }}
            aria-label={`${badge} open`}
          >
            {badge > 99 ? "99+" : badge}
          </span>
        ) : null}
      </span>
      <span className="w-full truncate text-center text-[11px] font-semibold tracking-tight text-stone-700 min-[360px]:text-xs sm:text-[13px]">
        {tile.label}
      </span>
    </Link>
  );
}

function TodayStrip({ summary, loading }: { summary: TodaySummary | null; loading: boolean }) {
  const when = summary
    ? summary.isToday
      ? "Today"
      : prettyDate(summary.date, { weekday: "short", month: "short", day: "numeric" })
    : "";
  return (
    <Link
      to="/install-schedule"
      className="mb-6 flex items-center gap-3 rounded-2xl border border-stone-200 bg-white px-4 py-3 transition-colors hover:border-stone-300 sm:mb-8 sm:px-5"
    >
      <span
        className="flex h-11 w-11 flex-none items-center justify-center rounded-xl"
        style={{ backgroundColor: "rgb(var(--ll-brand-soft))" }}
      >
        <TreePine size={22} className="text-emerald-700" strokeWidth={1.8} />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-[11px] font-bold uppercase tracking-wide text-stone-500">
          {summary?.isToday ? "Installing today" : "Next install day"}
        </p>
        {loading && !summary ? (
          <p className="text-sm text-stone-500">Loading the schedule…</p>
        ) : summary ? (
          <>
            <p className="truncate text-base font-semibold text-stone-800" style={SORA}>
              {summary.isToday ? "" : `${when} · `}
              {summary.crews.length} {summary.crews.length === 1 ? "crew" : "crews"} · {summary.jobs}{" "}
              {summary.jobs === 1 ? "job" : "jobs"}
            </p>
            <p className="truncate text-xs text-stone-500">
              {summary.people} people ·{" "}
              {summary.crews.map((c) => `${c.label}: ${c.jobs} ${c.jobs === 1 ? "job" : "jobs"}`).join(" · ")}
            </p>
          </>
        ) : (
          <p className="text-sm text-stone-600">No install days left on the board</p>
        )}
      </div>
      <ChevronRight size={18} className="flex-none text-stone-400" />
    </Link>
  );
}

export default function App() {
  const tiles = useMemo(() => visibleTiles(currentMe()), []);
  const [openComments, setOpenComments] = useState(0);
  const [today, setToday] = useState<TodaySummary | null>(null);
  const [loadingToday, setLoadingToday] = useState(true);

  useEffect(() => {
    let alive = true;
    if (tiles.some((t) => t.id === "comments")) {
      getJson<unknown[]>("/api/feedback?limit=200").then((rows) => alive && setOpenComments(openCommentCount(rows)));
    }
    getJson<{ day?: TodaySummary | null }>("/api/lead/today-summary")
      .then((r) => alive && setToday(r?.day ?? null))
      .finally(() => alive && setLoadingToday(false));
    return () => {
      alive = false;
    };
  }, [tiles]);

  const groups = (["season", "catalog", "more"] as TileGroup[])
    .map((g) => ({ g, items: tiles.filter((t) => t.group === g) }))
    .filter((x) => x.items.length);
  const now = new Date();

  return (
    <Layout>
      <div className="mx-auto w-full max-w-5xl px-4 pb-10 pt-6 sm:px-10 sm:pt-10">
        <header className="mb-6 sm:mb-8">
          <h1 className="text-2xl font-semibold text-stone-800 sm:text-3xl" style={SORA}>
            {greeting(now)}
          </h1>
          <p className="mt-1 text-sm text-stone-500">
            {now.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" })}
          </p>
        </header>

        <TodayStrip summary={today} loading={loadingToday} />

        {groups.map(({ g, items }) => (
          <section key={g} className="mb-6 sm:mb-8">
            <h2 className="mb-2 px-1 text-[11px] font-bold uppercase tracking-wide text-stone-500">{GROUP_LABELS[g]}</h2>
            <div className="grid grid-cols-4 gap-x-1 gap-y-3 min-[360px]:gap-x-2 sm:grid-cols-6 sm:gap-x-4 lg:grid-cols-8">
              {items.map((t) => (
                <Tile key={t.id} tile={t} badge={t.id === "comments" ? openComments : undefined} />
              ))}
            </div>
          </section>
        ))}
      </div>
    </Layout>
  );
}
