import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Leaf,
  Search,
  Shapes,
  ShoppingCart,
  Calculator,
  Sparkles,
  Plus,
  BookOpen,
  Building2,
  ArrowRight,
  Package,
  TreePine,
  CircleDashed,
  Sprout,
} from "lucide-react";
import Layout from "components/Layout";
import { apiFetch } from "utils/apiFetch";
import { formatCurrency } from "utils/format";

const DASHBOARD_CACHE_KEY = "leaf-ledger:dashboard-cache:v2";

interface DashboardSummary {
  catalog: { products: number; suppliers: number };
  designs: { total: number; with_parts: number; projects: number };
  orders: { count: number; open_value: number; vendors: number; items: number };
  recipes: { total: number; components: number };
  favorites: number;
}

interface RecentDesign {
  id: number;
  name: string;
  build_type?: string | null;
  project_name?: string | null;
  client_name?: string | null;
  group_name?: string | null;
  item_count: number;
  total_cost: number;
}

type DashboardCache = {
  summary?: DashboardSummary;
  recentDesigns?: RecentDesign[];
  cachedAt?: number;
};

function readDashboardCache(): DashboardCache | null {
  try {
    const raw = localStorage.getItem(DASHBOARD_CACHE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function writeDashboardCache(patch: DashboardCache) {
  try {
    const prev = readDashboardCache() || {};
    localStorage.setItem(DASHBOARD_CACHE_KEY, JSON.stringify({ ...prev, ...patch, cachedAt: Date.now() }));
  } catch {
    // Ignore storage issues.
  }
}

async function getJson<T>(path: string): Promise<T | null> {
  try {
    // Must be apiFetch: every /api route authenticates off the Supabase token,
    // which lives in the session rather than a cookie, so a plain fetch() 401s
    // and the dashboard silently renders em-dashes.
    const res = await apiFetch(path);
    if (!res.ok) return null;
    const ct = res.headers.get("content-type") || "";
    if (!ct.includes("application/json")) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

/** Icon per build type, matching the Designs grid so a build reads the same everywhere. */
function buildTypeIcon(buildType?: string | null) {
  const t = (buildType || "").toLowerCase();
  if (t.includes("wreath")) return CircleDashed;
  if (t.includes("tree")) return TreePine;
  if (t.includes("plant") || t.includes("bush") || t.includes("planter")) return Sprout;
  return Package;
}

const nf = (n: number | undefined | null) => (n == null ? "—" : n.toLocaleString());

export default function App() {
  const navigate = useNavigate();
  const cached = useMemo(() => readDashboardCache(), []);
  const [summary, setSummary] = useState<DashboardSummary | null>(cached?.summary ?? null);
  const [recent, setRecent] = useState<RecentDesign[]>(cached?.recentDesigns ?? []);
  const [refreshing, setRefreshing] = useState(true);

  useEffect(() => {
    let alive = true;
    Promise.all([
      getJson<DashboardSummary>("/api/dashboard/summary"),
      getJson<RecentDesign[]>("/api/dashboard/recent-designs?limit=6"),
    ])
      .then(([s, r]) => {
        if (!alive) return;
        if (s) setSummary(s);
        if (Array.isArray(r)) setRecent(r);
        if (s || r) writeDashboardCache({ summary: s ?? undefined, recentDesigns: r ?? undefined });
      })
      .finally(() => alive && setRefreshing(false));
    return () => {
      alive = false;
    };
  }, []);

  // What the app actually does now: a catalog you search, designs you build
  // from it, and orders you send to vendors.
  const STATS = [
    {
      label: "Products in catalog",
      value: nf(summary?.catalog.products),
      sub: summary ? `${nf(summary.catalog.suppliers)} suppliers` : "",
      icon: Leaf,
      path: "/search",
    },
    {
      label: "Designs",
      value: nf(summary?.designs.total),
      sub: summary ? `${nf(summary.designs.projects)} projects` : "",
      icon: Shapes,
      path: "/designs",
    },
    {
      label: "On order",
      value: summary ? formatCurrency(summary.orders.open_value) : "—",
      sub: summary ? `${nf(summary.orders.items)} items · ${nf(summary.orders.vendors)} vendors` : "",
      icon: ShoppingCart,
      path: "/orders",
    },
    {
      label: "Recipes on file",
      value: nf(summary?.recipes.total),
      sub: summary ? `${nf(summary.recipes.components)} components` : "",
      icon: BookOpen,
      path: "/designs",
    },
  ];

  const ACTIONS = [
    {
      title: "Start a design",
      description: "Pick a type and species, then build it from the catalog.",
      icon: Shapes,
      cta: "New design",
      path: "/designs/new",
      primary: true,
    },
    {
      title: "Search the catalog",
      description: "Every supplier at once — filter by colour, size and price.",
      icon: Search,
      cta: "Search",
      path: "/search",
    },
    {
      title: "Purchase orders",
      description: "Grouped by vendor, ready to export as PDF, Word or Excel.",
      icon: ShoppingCart,
      cta: "View orders",
      path: "/orders",
    },
    {
      title: "Ornament calculator",
      description: "Size a tree's ornament package and match it to real products.",
      icon: Calculator,
      cta: "Open calculator",
      path: "/ornament-calculator",
    },
  ];

  return (
    <Layout>
      <header
        className="sticky top-0 z-10 flex items-center justify-between border-b border-stone-200 px-10 py-4"
        style={{ backgroundColor: "rgb(var(--ll-page))" }}
      >
        <div>
          <h1 className="text-xl font-semibold text-stone-800" style={{ fontFamily: "Georgia, serif" }}>
            Welcome back
          </h1>
          <p className="mt-0.5 text-xs text-stone-500">
            {new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric" })}
            {refreshing && <span className="ml-2 text-emerald-700">Refreshing…</span>}
          </p>
        </div>
        <button
          onClick={() => navigate("/designs/new")}
          className="flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold text-white transition-colors hover:opacity-90"
          style={{ backgroundColor: "rgb(var(--ll-brand))" }}
        >
          <Plus size={15} strokeWidth={2.2} />
          New Design
        </button>
      </header>

      <div className="max-w-6xl px-10 py-8">
        {/* Stats — each one is a doorway to the page behind it. */}
        <div className="mb-10 grid grid-cols-2 gap-4 lg:grid-cols-4">
          {STATS.map(({ label, value, sub, icon: Icon, path }) => (
            <button
              key={label}
              onClick={() => navigate(path)}
              className="flex items-center gap-4 rounded-xl border border-stone-200 bg-white px-5 py-4 text-left transition-colors hover:border-stone-300"
            >
              <div
                className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg"
                style={{ backgroundColor: "rgb(var(--ll-brand-soft))" }}
              >
                <Icon size={16} className="text-emerald-700" strokeWidth={1.8} />
              </div>
              <div className="min-w-0">
                <p className="truncate text-2xl font-bold text-stone-800">{value}</p>
                <p className="mt-0.5 truncate text-xs leading-tight text-stone-500">{label}</p>
                {sub && <p className="mt-0.5 truncate text-[11px] text-stone-400">{sub}</p>}
              </div>
            </button>
          ))}
        </div>

        <div className="mb-10">
          <h2 className="mb-4 text-base font-semibold text-stone-700" style={{ fontFamily: "Georgia, serif" }}>
            Quick actions
          </h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {ACTIONS.map(({ title, description, icon: Icon, cta, path, primary }) => (
              <div
                key={title}
                onClick={() => navigate(path)}
                className={`group flex cursor-pointer flex-col gap-3 rounded-xl border bg-white p-5 transition-all hover:shadow-sm ${
                  primary ? "border-emerald-300" : "border-stone-200 hover:border-stone-300"
                }`}
              >
                <div className="flex items-start justify-between">
                  <div
                    className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg"
                    style={{ backgroundColor: "rgb(var(--ll-brand-soft))" }}
                  >
                    <Icon size={16} strokeWidth={1.8} className="text-emerald-700" />
                  </div>
                  <ArrowRight size={15} className="mt-1 text-stone-300 transition-colors group-hover:text-stone-500" />
                </div>
                <div>
                  <p className="mb-1 text-sm font-semibold text-stone-800">{title}</p>
                  <p className="text-xs leading-relaxed text-stone-500">{description}</p>
                </div>
                <span
                  className="mt-1 self-start rounded-md border px-3 py-1.5 text-xs font-semibold"
                  style={{
                    color: "rgb(var(--ll-ok-ink))",
                    borderColor: "rgb(var(--ll-ok-line))",
                    backgroundColor: "rgb(var(--ll-brand-soft))",
                  }}
                >
                  {cta}
                </span>
              </div>
            ))}
          </div>
        </div>

        <RecentDesigns designs={recent} loading={refreshing && recent.length === 0} />
      </div>
    </Layout>
  );
}

function RecentDesigns({ designs, loading }: { designs: RecentDesign[]; loading: boolean }) {
  const navigate = useNavigate();

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-base font-semibold text-stone-700" style={{ fontFamily: "Georgia, serif" }}>
          Recent designs
        </h2>
        <button
          onClick={() => navigate("/designs")}
          className="text-xs font-semibold text-emerald-700 hover:text-emerald-900"
        >
          View all
        </button>
      </div>

      {loading ? (
        <p className="rounded-xl border border-stone-200 bg-white px-5 py-8 text-center text-sm text-stone-400">
          Loading designs…
        </p>
      ) : designs.length === 0 ? (
        <div className="rounded-xl border border-dashed border-stone-300 bg-white/60 px-5 py-10 text-center">
          <Sparkles className="mx-auto mb-2 text-emerald-700/50" size={26} strokeWidth={1.5} />
          <p className="text-sm font-medium text-stone-600">No designs yet</p>
          <p className="mx-auto mt-1 max-w-sm text-xs text-stone-400">
            Start one and it will show up here with its parts and running cost.
          </p>
          <button
            onClick={() => navigate("/designs/new")}
            className="mt-4 rounded-lg px-4 py-2 text-xs font-semibold text-white"
            style={{ backgroundColor: "rgb(var(--ll-brand))" }}
          >
            New design
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {designs.map((d) => {
            const Icon = buildTypeIcon(d.build_type);
            const where = [d.client_name, d.project_name, d.group_name].filter(Boolean).join(" · ");
            return (
              <button
                key={d.id}
                onClick={() => navigate("/designs")}
                className="flex items-start gap-3 rounded-xl border border-stone-200 bg-white p-4 text-left transition-colors hover:border-stone-300"
              >
                <div
                  className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg"
                  style={{ backgroundColor: "rgb(var(--ll-brand-soft))" }}
                >
                  <Icon size={16} className="text-emerald-700" strokeWidth={1.8} />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold text-stone-800">{d.name}</p>
                  {where && <p className="mt-0.5 truncate text-[11px] text-stone-400">{where}</p>}
                  <p className="mt-1 text-[11px] text-stone-500">
                    {d.item_count} part{d.item_count === 1 ? "" : "s"}
                    {d.total_cost > 0 ? ` · ${formatCurrency(d.total_cost)}` : ""}
                  </p>
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
