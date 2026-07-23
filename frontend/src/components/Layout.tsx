import React, { useCallback, useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import {
  Leaf,
  Heart,
  Package,
  LayoutGrid,
  FileText,
  Settings,
  Sparkles,
  LogOut,
  ChevronRight,
  ChevronDown,
  Building2,
  Activity,
  Users,
  Calculator,
  Search,
  ShoppingCart,
} from "lucide-react";
import { useAuth } from "app/auth/AuthProvider";
import { APP_BASE_PATH, apiClient } from "app";

const NAV_GROUPS = [
  {
    label: null,
    items: [{ path: "/", label: "Dashboard", icon: LayoutGrid }],
  },
  {
    label: "Catalog",
    items: [
      { path: "/suppliers", label: "Suppliers", icon: Building2 },
      { path: "/library", label: "Product Library", icon: Leaf },
      { path: "/search", label: "Catalog Search", icon: Search },
      { path: "/favorites", label: "Favorites", icon: Heart },
      { path: "/orders", label: "Purchase Orders", icon: ShoppingCart },
    ],
  },
  {
    label: "Design",
    items: [
      { path: "/mockups", label: "AI Mockups", icon: Sparkles },
      { path: "/ornament-calculator", label: "Ornament Calculator", icon: Calculator },
      { path: "/invoice", label: "Invoices", icon: FileText },
    ],
  },
  {
    label: "Admin",
    items: [
      { path: "/admin-dashboard", label: "Sync Operations", icon: Activity },
      { path: "/settings", label: "Settings", icon: Settings },
    ],
  },
];

interface Props {
  children: React.ReactNode;
}

const SIDEBAR_PROJECTS_CACHE_KEY = "leaf-ledger-sidebar-projects-cache-v1";
const CLIENTS_PAGE_CACHE_KEY = "leaf-ledger:clients-page-cache:v1";
const PROJECTS_LIST_CACHE_KEY = "leaf-ledger:projects-list-cache:v1";
const SUPPLIERS_CACHE_KEY = "leaf-ledger:suppliers-cache:v1";
const DASHBOARD_CACHE_KEY = "leaf-ledger:dashboard-cache:v1";

type SidebarProject = { id: number; name: string; client_name?: string; updated_at?: string };
type BootstrapSummary = {
  clients?: Array<{ name: string; project_count?: number }>;
  projects?: SidebarProject[];
  suppliers?: unknown[];
  stats?: Record<string, unknown> | null;
};

function writeJsonCache(key: string, value: unknown) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Cache writes should never block navigation.
  }
}

function clientCountsFromProjects(rows: SidebarProject[]) {
  const counts = new Map<string, number>();
  rows.forEach((row) => {
    const rawName = (row.client_name || "").trim();
    const name = rawName || "Unassigned";
    counts.set(name, (counts.get(name) || 0) + 1);
  });
  return Array.from(counts.entries())
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

function sortProjectsByUpdated(rows: SidebarProject[]) {
  return [...rows].sort((a, b) => {
    const aTime = a.updated_at ? new Date(a.updated_at).getTime() : 0;
    const bTime = b.updated_at ? new Date(b.updated_at).getTime() : 0;
    return bTime - aTime;
  });
}

export default function Layout({ children }: Props) {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, signOut } = useAuth();
  const [projectClients, setProjectClients] = useState<Array<{ name: string; count: number }>>([]);
  const [sidebarProjects, setSidebarProjects] = useState<SidebarProject[]>(() => {
    try {
      const cached = JSON.parse(window.localStorage.getItem(SIDEBAR_PROJECTS_CACHE_KEY) || "[]");
      return Array.isArray(cached) ? cached : [];
    } catch {
      return [];
    }
  });
  const [projectsLoading, setProjectsLoading] = useState(() => sidebarProjects.length === 0);
  const [projectsOpen, setProjectsOpen] = useState(() => {
    try {
      return window.localStorage.getItem("leaf-ledger-sidebar-projects-open") !== "false";
    } catch {
      return true;
    }
  });
  const [clientsOpen, setClientsOpen] = useState(() => {
    try {
      return window.localStorage.getItem("leaf-ledger-sidebar-clients-open") === "true";
    } catch {
      return false;
    }
  });

  const loadSidebarProjects = useCallback((mountedRef?: { current: boolean }) => {
    if (sidebarProjects.length === 0) setProjectsLoading(true);
    apiClient.request<BootstrapSummary>({
      path: "/routes/bootstrap/summary",
      method: "GET",
      format: "json",
    })
      .then((r) => {
        const summary = r.data || {};
        const safeProjects = Array.isArray(summary.projects) ? summary.projects : [];
        const safeClients = Array.isArray(summary.clients) ? summary.clients : [];
        const sortedProjects = sortProjectsByUpdated(safeProjects);

        writeJsonCache(SIDEBAR_PROJECTS_CACHE_KEY, sortedProjects.slice(0, 100));
        writeJsonCache(CLIENTS_PAGE_CACHE_KEY, {
          clientRows: safeClients,
          projects: safeProjects,
          cachedAt: Date.now(),
        });
        writeJsonCache(PROJECTS_LIST_CACHE_KEY, {
          arrangements: safeProjects,
          cachedAt: Date.now(),
        });
        if (Array.isArray(summary.suppliers)) {
          writeJsonCache(SUPPLIERS_CACHE_KEY, summary.suppliers);
        }
        if (summary.stats) {
          writeJsonCache(DASHBOARD_CACHE_KEY, {
            stats: summary.stats,
            recentProjects: sortedProjects.slice(0, 5),
            cachedAt: Date.now(),
          });
        }

        if (mountedRef && !mountedRef.current) return;
        const clientCounts = safeClients.length > 0
          ? safeClients
              .map((client) => ({
                name: client.name,
                count: client.project_count || 0,
              }))
              .filter((client) => client.name)
              .sort((a, b) => a.name.localeCompare(b.name))
          : clientCountsFromProjects(safeProjects);
        setProjectClients(clientCounts);
        setSidebarProjects(sortedProjects);
      })
      .catch(() => apiClient.list_arrangements()
        .then((r) => {
          if (!r.ok) throw new Error("Failed to load projects");
          return r.json();
        })
        .then((rows: SidebarProject[]) => {
        if (mountedRef && !mountedRef.current) return;
        const safeRows = Array.isArray(rows) ? rows : [];
        const sortedRows = sortProjectsByUpdated(safeRows);
        writeJsonCache(SIDEBAR_PROJECTS_CACHE_KEY, sortedRows.slice(0, 100));
        setProjectClients(clientCountsFromProjects(safeRows));
        setSidebarProjects(sortedRows);
      }))
      .catch(() => {})
      .finally(() => {
        if (!mountedRef || mountedRef.current) setProjectsLoading(false);
      });
  }, [sidebarProjects.length]);

  useEffect(() => {
    const mountedRef = { current: true };
    loadSidebarProjects(mountedRef);
    const refresh = () => loadSidebarProjects(mountedRef);
    window.addEventListener("leaf-ledger-projects-changed", refresh);
    return () => {
      mountedRef.current = false;
      window.removeEventListener("leaf-ledger-projects-changed", refresh);
    };
  }, [loadSidebarProjects]);

  useEffect(() => {
    try {
      window.localStorage.setItem("leaf-ledger-sidebar-projects-open", String(projectsOpen));
    } catch {}
  }, [projectsOpen]);

  useEffect(() => {
    try {
      window.localStorage.setItem("leaf-ledger-sidebar-clients-open", String(clientsOpen));
    } catch {}
  }, [clientsOpen]);

  const handleSignOut = async () => {
    await signOut();
    navigate("/login", { replace: true });
  };

  const isActive = (path: string) => {
    if (path === "/") return location.pathname === APP_BASE_PATH || location.pathname === APP_BASE_PATH + "/" || location.pathname === "/";
    return location.pathname.includes(path);
  };
  const activeProjectId = new URLSearchParams(location.search).get("id");
  const activeClientName = new URLSearchParams(location.search).get("client");

  return (
    <div className="min-h-screen flex" style={{ fontFamily: "'Montserrat', sans-serif", backgroundColor: "#f7f4ef" }}>
      {/* Sidebar */}
      <aside
        className="w-60 flex-shrink-0 flex flex-col border-r border-stone-800 py-8 px-4 fixed top-0 left-0 h-full z-20"
        style={{ backgroundColor: "#1c2e1e" }}
      >
        {/* Logo */}
        <div className="mb-10 px-2">
          <div className="flex items-center gap-2 mb-1">
            <Leaf className="text-emerald-400" size={20} strokeWidth={1.5} />
            <span
              className="text-lg font-bold tracking-wide text-white"
              style={{ fontFamily: "Georgia, serif", letterSpacing: "0.04em" }}
            >
              Leaf &amp; Ledger
            </span>
          </div>
          <p className="text-xs text-stone-400 pl-7 leading-tight">Catalog &amp; project operations</p>
        </div>

        {/* Nav */}
        <nav className="flex flex-col gap-4 flex-1 overflow-y-auto pr-1">
          {NAV_GROUPS.map((group) => (
            <React.Fragment key={group.label ?? "top"}>
            <div>
              {group.label && (
                <p className="px-3 mb-1 text-[10px] font-semibold uppercase tracking-widest text-stone-600">
                  {group.label}
                </p>
              )}
              <div className="flex flex-col gap-0.5">
                {group.items.map(({ path, label, icon: Icon }) => {
                  const active = isActive(path);
                  return (
                    <button
                      key={path}
                      onClick={() => navigate(path)}
                      className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all text-left w-full ${
                        active
                          ? "bg-emerald-700/40 text-emerald-300"
                          : "text-stone-400 hover:text-stone-200 hover:bg-white/5"
                      }`}
                    >
                      <Icon size={16} strokeWidth={1.8} />
                      {label}
                      {active && <ChevronRight size={12} className="ml-auto opacity-60" />}
                    </button>
                  );
                })}
              </div>
            </div>

            {group.label === "Catalog" && (
              <div>
                <p className="px-3 mb-1 text-[10px] font-semibold uppercase tracking-widest text-stone-600">
                  Projects
                </p>
                <div className="flex flex-col gap-0.5">
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => navigate("/clients")}
                      className={`flex min-w-0 flex-1 items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all text-left ${
                        isActive("/clients")
                          ? "bg-emerald-700/40 text-emerald-300"
                          : "text-stone-400 hover:text-stone-200 hover:bg-white/5"
                      }`}
                    >
                      <Users size={16} strokeWidth={1.8} />
                      Clients
                    </button>
                    <button
                      onClick={() => setClientsOpen((open) => !open)}
                      className="flex h-9 w-9 items-center justify-center rounded-lg text-stone-500 transition-all hover:bg-white/5 hover:text-stone-200"
                      title={clientsOpen ? "Hide client list" : "Show client list"}
                      aria-label={clientsOpen ? "Hide client list" : "Show client list"}
                    >
                      {clientsOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    </button>
                  </div>
                  {clientsOpen && (
                    <div className="ml-5 mt-1 flex flex-col gap-0.5 border-l border-white/10 pl-2">
                      {projectClients.slice(0, 12).map((client) => {
                        const active = isActive("/clients") && activeClientName === client.name;
                        return (
                          <button
                            key={client.name}
                            onClick={() => navigate(`/clients?client=${encodeURIComponent(client.name)}`)}
                            className={`flex items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs font-medium transition-all ${
                              active
                                ? "bg-emerald-700/30 text-emerald-200"
                                : "text-stone-400 hover:bg-white/5 hover:text-stone-200"
                            }`}
                            title={`${client.count} project${client.count === 1 ? "" : "s"}`}
                          >
                            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500/70" />
                            <span className="truncate">{client.name}</span>
                          </button>
                        );
                      })}
                      {projectsLoading ? (
                        <div className="rounded-lg px-2 py-1.5 text-left text-xs text-stone-500">
                          Loading clients...
                        </div>
                      ) : projectClients.length === 0 && (
                        <button
                          onClick={() => navigate("/clients")}
                          className="rounded-lg px-2 py-1.5 text-left text-xs text-stone-500 hover:bg-white/5 hover:text-stone-300"
                        >
                          No clients yet
                        </button>
                      )}
                    </div>
                  )}
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => navigate("/projects")}
                      className={`flex min-w-0 flex-1 items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all text-left ${
                        isActive("/projects")
                          ? "bg-emerald-700/40 text-emerald-300"
                          : "text-stone-400 hover:text-stone-200 hover:bg-white/5"
                      }`}
                    >
                      <Package size={16} strokeWidth={1.8} />
                      All Projects
                    </button>
                    <button
                      onClick={() => setProjectsOpen((open) => !open)}
                      className="flex h-9 w-9 items-center justify-center rounded-lg text-stone-500 transition-all hover:bg-white/5 hover:text-stone-200"
                      title={projectsOpen ? "Hide project list" : "Show project list"}
                      aria-label={projectsOpen ? "Hide project list" : "Show project list"}
                    >
                      {projectsOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    </button>
                  </div>
                  {projectsOpen && (
                    <div className="ml-5 mt-1 flex flex-col gap-0.5 border-l border-white/10 pl-2">
                      {sidebarProjects.map((project) => {
                        const active = isActive("/projects") && activeProjectId === String(project.id);
                        return (
                          <button
                            key={project.id}
                            onClick={() => navigate(`/projects?id=${project.id}`)}
                            className={`rounded-lg px-2 py-1.5 text-left text-xs transition-all ${
                              active
                                ? "bg-emerald-700/30 text-emerald-200"
                                : "text-stone-400 hover:bg-white/5 hover:text-stone-200"
                            }`}
                            title={`${project.client_name || "No client"} · ${project.name}`}
                          >
                            <span className="block truncate font-medium">{project.name}</span>
                            <span className="block truncate text-[10px] opacity-60">{project.client_name || "No client"}</span>
                          </button>
                        );
                      })}
                      {projectsLoading ? (
                        <div className="rounded-lg px-2 py-1.5 text-left text-xs text-stone-500">
                          Loading projects...
                        </div>
                      ) : sidebarProjects.length === 0 && (
                        <button
                          onClick={() => navigate("/projects")}
                          className="rounded-lg px-2 py-1.5 text-left text-xs text-stone-500 hover:bg-white/5 hover:text-stone-300"
                        >
                          No projects yet
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )}
            </React.Fragment>
          ))}
        </nav>

        {/* User info + sign out */}
        <div className="px-2 pt-6 border-t border-stone-700">
          {user && (
            <div className="mb-3">
              <p className="text-xs font-medium text-stone-300 truncate">{user.user_metadata?.full_name || user.email?.split("@")[0]}</p>
              <p className="text-xs text-stone-500 truncate">{user.email}</p>
            </div>
          )}
          <button
            onClick={handleSignOut}
            className="flex items-center gap-2 text-xs text-stone-500 hover:text-stone-300 transition-colors w-full"
          >
            <LogOut size={13} />
            Sign out
          </button>
        </div>
      </aside>

      {/* Main content offset for sidebar */}
      <div className="flex-1 ml-60 min-h-screen overflow-auto">
        {children}
      </div>
    </div>
  );
}
