import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Leaf,
  Heart,
  Package,
  FileText,
  Sparkles,
  Plus,
  TrendingUp,
  Users,
  ShoppingBag,
  ArrowRight,
} from "lucide-react";
import Layout from "components/Layout";
import { apiClient } from "app";
import { formatCurrency } from "utils/format";

const DASHBOARD_CACHE_KEY = "leaf-ledger:dashboard-cache:v1";

type DashboardCache = {
  stats?: {
    total_products: number;
    total_suppliers: number;
    total_favorites: number;
    total_arrangements: number;
  };
  recentProjects?: any[];
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
    localStorage.setItem(
      DASHBOARD_CACHE_KEY,
      JSON.stringify({ ...prev, ...patch, cachedAt: Date.now() })
    );
  } catch {
    // Ignore storage issues.
  }
}

export default function App() {
  const navigate = useNavigate();
  const cached = readDashboardCache();
  const [stats, setStats] = useState(
    cached?.stats || {
      total_products: 0,
      total_suppliers: 0,
      total_favorites: 0,
      total_arrangements: 0,
    }
  );
  const [loading, setLoading] = useState(!cached?.stats);
  const [refreshing, setRefreshing] = useState(!!cached?.stats);

  useEffect(() => {
    setRefreshing(true);
    apiClient.get_product_stats()
      .then(r => r.json())
      .then((nextStats) => {
        setStats(nextStats);
        writeDashboardCache({ stats: nextStats });
      })
      .catch(() => {})
      .finally(() => {
        setLoading(false);
        setRefreshing(false);
      });
  }, []);

  const QUICK_STATS = [
    { label: "Products", value: stats.total_products, icon: ShoppingBag },
    { label: "Projects", value: stats.total_arrangements, icon: Package },
    { label: "Favorites", value: stats.total_favorites, icon: Heart },
    { label: "Suppliers", value: stats.total_suppliers, icon: Users },
  ];

  const QUICK_ACTIONS = [
    {
      title: "Product Library",
      description: "Browse and manage your plant and accent catalog with pricing.",
      icon: Leaf,
      cta: "Browse Library",
      accent: "green",
      path: "/library",
    },
    {
      title: "Build a Project",
      description: "Create client jobs, buckets, saved ideas, and selected products.",
      icon: Package,
      cta: "New Project",
      accent: "amber",
      path: "/projects",
    },
    {
      title: "AI Mockups",
      description: "Turn project selections into a beautiful rendered image.",
      icon: Sparkles,
      cta: "Generate Mockup",
      accent: "green",
      path: "/mockups",
    },
    {
      title: "Export Invoices",
      description: "Print a priced line-item sheet with markup, ready to send.",
      icon: FileText,
      cta: "View Invoices",
      accent: "amber",
      path: "/invoice",
    },
  ];

  return (
    <Layout>
      {/* Top bar */}
      <header
        className="sticky top-0 z-10 flex items-center justify-between px-10 py-4 border-b border-stone-200"
        style={{ backgroundColor: "#f7f4ef" }}
      >
        <div>
          <h1 className="text-xl font-semibold text-stone-800" style={{ fontFamily: "Georgia, serif" }}>
            Welcome back
          </h1>
          <p className="text-xs text-stone-500 mt-0.5">
            {new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric" })}
            {refreshing && <span className="ml-2 text-emerald-700">Refreshing…</span>}
          </p>
        </div>
        <button
          onClick={() => navigate("/projects")}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-white transition-colors hover:opacity-90"
          style={{ backgroundColor: "#2d5a33" }}
        >
          <Plus size={15} strokeWidth={2.2} />
          New Project
        </button>
      </header>

      <div className="px-10 py-8 max-w-5xl">
        {/* Stats row */}
        <div className="grid grid-cols-4 gap-4 mb-10">
          {QUICK_STATS.map(({ label, value, icon: Icon }) => (
            <div key={label} className="bg-white rounded-xl border border-stone-200 px-5 py-4 flex items-center gap-4">
              <div className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0" style={{ backgroundColor: "#e8f0e8" }}>
                <Icon size={16} className="text-emerald-700" strokeWidth={1.8} />
              </div>
              <div>
                <p className="text-2xl font-bold text-stone-800">{loading ? "—" : value}</p>
                <p className="text-xs text-stone-500 leading-tight mt-0.5">{label}</p>
              </div>
            </div>
          ))}
        </div>

        {/* Quick actions */}
        <div className="mb-10">
          <h2 className="text-base font-semibold text-stone-700 mb-4" style={{ fontFamily: "Georgia, serif" }}>
            Quick actions
          </h2>
          <div className="grid grid-cols-2 gap-4">
            {QUICK_ACTIONS.map(({ title, description, icon: Icon, cta, accent, path }) => (
              <div
                key={title}
                onClick={() => navigate(path)}
                className="bg-white rounded-xl border border-stone-200 p-5 flex flex-col gap-3 hover:border-stone-300 hover:shadow-sm transition-all group cursor-pointer"
              >
                <div className="flex items-start justify-between">
                  <div
                    className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0"
                    style={{ backgroundColor: accent === "amber" ? "#fef3e2" : "#e8f0e8" }}
                  >
                    <Icon size={16} strokeWidth={1.8} className={accent === "amber" ? "text-amber-600" : "text-emerald-700"} />
                  </div>
                  <ArrowRight size={15} className="text-stone-300 group-hover:text-stone-500 transition-colors mt-1" />
                </div>
                <div>
                  <p className="font-semibold text-stone-800 text-sm mb-1">{title}</p>
                  <p className="text-xs text-stone-500 leading-relaxed">{description}</p>
                </div>
                <button
                  className="self-start mt-1 text-xs font-semibold px-3 py-1.5 rounded-md border transition-colors"
                  style={
                    accent === "amber"
                      ? { color: "#92400e", borderColor: "#fcd34d", backgroundColor: "#fef3e2" }
                      : { color: "#14532d", borderColor: "#6ee7b7", backgroundColor: "#e8f0e8" }
                  }
                >
                  {cta}
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* Recent projects */}
        <RecentArrangements />
      </div>
    </Layout>
  );
}

function RecentArrangements() {
  const navigate = useNavigate();
  const cached = readDashboardCache();
  const [arrangements, setArrangements] = useState<any[]>(cached?.recentProjects || []);
  const [loading, setLoading] = useState(!cached?.recentProjects);
  const [refreshing, setRefreshing] = useState(!!cached?.recentProjects);

  useEffect(() => {
    setRefreshing(true);
    apiClient.list_arrangements()
      .then(r => r.json())
      .then((data) => {
        const recentProjects = data.slice(0, 5);
        setArrangements(recentProjects);
        writeDashboardCache({ recentProjects });
      })
      .catch(() => {})
      .finally(() => {
        setLoading(false);
        setRefreshing(false);
      });
  }, []);

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-base font-semibold text-stone-700" style={{ fontFamily: "Georgia, serif" }}>Recent projects</h2>
          {refreshing && <p className="text-xs text-emerald-700">Refreshing…</p>}
        </div>
        <button onClick={() => navigate("/projects")} className="text-xs text-emerald-700 hover:underline font-medium">View all</button>
      </div>
      <div className="bg-white rounded-xl border border-stone-200 overflow-hidden">
        <div className="grid grid-cols-4 px-5 py-3 bg-stone-50 border-b border-stone-100 text-xs font-semibold text-stone-500 uppercase tracking-wider">
          <span>Name</span>
          <span>Client</span>
          <span>Updated</span>
          <span className="text-right">Cost</span>
        </div>
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="w-5 h-5 border-2 border-emerald-600 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : arrangements.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-14 text-center">
            <div className="w-12 h-12 rounded-full flex items-center justify-center mb-3" style={{ backgroundColor: "#e8f0e8" }}>
              <TrendingUp size={20} className="text-emerald-600" strokeWidth={1.5} />
            </div>
            <p className="text-sm font-medium text-stone-600 mb-1">No projects yet</p>
            <p className="text-xs text-stone-400 max-w-xs leading-relaxed">Build your first project to see it here.</p>
            <button
              onClick={() => navigate("/projects")}
              className="mt-4 text-xs font-semibold px-4 py-2 rounded-md text-white"
              style={{ backgroundColor: "#2d5a33" }}
            >
              Create Project
            </button>
          </div>
        ) : (
          arrangements.map((arr) => (
            <div
              key={arr.id}
              onClick={() => navigate(`/projects?id=${arr.id}`)}
              className="grid grid-cols-4 px-5 py-3 border-b border-stone-50 hover:bg-stone-50 cursor-pointer text-sm items-center last:border-b-0"
            >
              <span className="font-medium text-stone-800 truncate">{arr.name}</span>
              <span className="text-stone-500 truncate">{arr.client_name || "—"}</span>
              <span className="text-stone-400 text-xs">{new Date(arr.updated_at).toLocaleDateString()}</span>
              <span className="text-right font-medium text-stone-700">{formatCurrency(arr.total_cost)}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
