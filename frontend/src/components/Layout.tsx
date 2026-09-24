import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import {
  Package,
  LogOut,
  Menu,
  X,
  ChevronRight,
  Monitor,
  Moon,
  Sun,
  Users,
} from "components/icons";
import { useAuth } from "app/auth/AuthProvider";
import { APP_BASE_PATH, apiClient } from "app";
import { apiFetch } from "utils/apiFetch";
import { usePreferences } from "utils/preferences";
import { useTheme } from "utils/theme";
import { currentMe } from "utils/me";
import {
  resolveSidebarRender,
  SIDEBAR_PREFS_EVENT,
} from "components/sidebarNav";
import type { ResolvedNavItem, SidebarPrefsEventDetail } from "components/sidebarNav";
import FeedbackWidget from "components/FeedbackWidget";
import { LeafLedgerLogo } from "components/LeafLedgerLogo";
import { readJsonCache, writeJsonCache } from "utils/jsonCache";
import { CLIENTS_PAGE_CACHE_KEY, PROJECTS_LIST_CACHE_KEY } from "../constants";
import { PROJECTS_CHANGED_EVENT } from "utils/projectsChanged";

// NAV_GROUPS, the pinned-path list and the ordering helpers live in
// components/sidebarNav.ts so that this sidebar and the Settings > Appearance
// editor render from the exact same list.
//
// COLOUR NOTE: the sidebar is deliberately dark in BOTH light and dark mode
// (PREFERENCES_THEME_CONTRACT section 3). Its neutrals are therefore expressed as
// white-with-opacity rather than borrowed from the `stone` ramp - that ramp is
// remapped to CSS variables and inverts in dark mode, which would turn this
// light-on-dark text unreadable. `emerald-*` accents ARE kept as Tailwind
// classes on purpose, so the active-tab colour follows the user's chosen accent.

interface Props {
  children: React.ReactNode;
}

const SIDEBAR_PROJECTS_CACHE_KEY = "leaf-ledger-sidebar-projects-cache-v1";
const CLIENTS_COMMENTS_SEEN_KEY = "leaf-ledger:clients-comments-seen-at";
const SUPPLIERS_CACHE_KEY = "leaf-ledger:suppliers-cache:v1";
// dead write kept pending decision; App reads :v2
const LEGACY_LAYOUT_DASHBOARD_CACHE_KEY = "leaf-ledger:dashboard-cache:v1";

const NAV_ITEM_IDLE = "text-white/60 hover:text-white hover:bg-white/5";
const NAV_ITEM_ACTIVE = "bg-emerald-700/40 text-emerald-300";
const GROUP_LABEL = "px-3 mb-1 text-[10px] font-semibold uppercase tracking-widest text-white/35";
const SUBTREE_ITEM_IDLE = "text-white/60 hover:bg-white/5 hover:text-white";
const SUBTREE_ITEM_ACTIVE = "bg-emerald-700/30 text-emerald-200";

const THEME_MODE_OPTIONS = [
  { mode: "system" as const, label: "Match system theme", icon: Monitor },
  { mode: "light" as const, label: "Light theme", icon: Sun },
  { mode: "dark" as const, label: "Dark theme", icon: Moon },
];

type SidebarProject = { id: number; name: string; client_name?: string; updated_at?: string };
type RecentComment = { id: number; client_id: number; client_name: string; text: string; author?: string | null; created_at: string };
type BootstrapSummary = {
  clients?: Array<{ name: string; project_count?: number }>;
  projects?: SidebarProject[];
  suppliers?: unknown[];
  stats?: Record<string, unknown> | null;
};

/**
 * One contiguous stretch of nav items that share a group. Runs are derived from
 * the user's flat order, so a group heading always sits above the first item of
 * that group wherever the user has moved it.
 */
type NavRun = {
  key: string;
  groupId: string;
  label: string | null;
  items: ResolvedNavItem[];
  hasAnchor: boolean;
};

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

/**
 * Field logins (leads, crew) get a bare header and their page -- none of the
 * office sidebar, whose data calls they aren't allowed to make. RoleGate has
 * already loaded the account before any page renders.
 */
export default function Layout(props: Props) {
  const me = currentMe();
  if (me?.fieldOnly) return <FieldLayout>{props.children}</FieldLayout>;
  return <StaffLayout {...props} />;
}

function FieldLayout({ children }: Props) {
  const navigate = useNavigate();
  const { signOut } = useAuth();
  const me = currentMe();
  return (
    <div className="min-h-screen bg-[#f7f6f2]">
      <header className="sticky top-0 z-20 flex items-center justify-between gap-3 bg-[#1f3d2b] px-4 py-3 text-white">
        <div className="min-w-0">
          <p className="text-sm font-semibold">Leaf &amp; Ledger</p>
          <p className="truncate text-xs text-white/70">{me?.person?.name || me?.email}</p>
        </div>
        <button
          type="button"
          onClick={async () => {
            await signOut();
            navigate("/login", { replace: true });
          }}
          className="flex items-center gap-1.5 rounded-lg border border-white/30 px-3 py-1.5 text-xs font-semibold"
        >
          <LogOut size={14} /> Sign out
        </button>
      </header>
      <main>{children}</main>
    </div>
  );
}

function StaffLayout({ children }: Props) {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, signOut } = useAuth();
  const { prefs } = usePreferences();
  const { mode, setMode } = useTheme();
  const [projectClients, setProjectClients] = useState<Array<{ name: string; count: number }>>([]);
  const [sidebarProjects, setSidebarProjects] = useState<SidebarProject[]>(() => {
    const cached = readJsonCache<unknown>(SIDEBAR_PROJECTS_CACHE_KEY, []);
    return Array.isArray(cached) ? cached : [];
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
  // Optimistic echo of an edit made in Settings > Appearance. Preferences stay
  // the source of truth; this only removes any wait on the debounced save, and
  // is always at least as fresh as `prefs` for the life of the page.
  const [sidebarOverride, setSidebarOverride] = useState<SidebarPrefsEventDetail | null>(null);
  // Dot on the "Clients" tab for a comment someone else added since this
  // account last opened it. "Seen" is a per-browser timestamp (not a server
  // read-receipt) -- good enough for a small team, and avoids a table just
  // for this.
  const [hasNewClientComments, setHasNewClientComments] = useState(false);
  // Below the `lg` breakpoint the sidebar is an off-canvas drawer opened from
  // the top bar. It closes on every navigation and on Escape.
  const [navOpen, setNavOpen] = useState(false);
  useEffect(() => { setNavOpen(false); }, [location.pathname, location.search]);
  useEffect(() => {
    if (!navOpen) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setNavOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navOpen]);

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
          writeJsonCache(LEGACY_LAYOUT_DASHBOARD_CACHE_KEY, {
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
    window.addEventListener(PROJECTS_CHANGED_EVENT, refresh);
    return () => {
      mountedRef.current = false;
      window.removeEventListener(PROJECTS_CHANGED_EVENT, refresh);
    };
  }, [loadSidebarProjects]);

  useEffect(() => {
    const onSidebarPrefs = (event: Event) => {
      const detail = (event as CustomEvent<SidebarPrefsEventDetail>).detail;
      if (detail && Array.isArray(detail.order) && Array.isArray(detail.hidden)) {
        setSidebarOverride({ order: detail.order, hidden: detail.hidden });
      }
    };
    window.addEventListener(SIDEBAR_PREFS_EVENT, onSidebarPrefs);
    return () => window.removeEventListener(SIDEBAR_PREFS_EVENT, onSidebarPrefs);
  }, []);

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

  const checkNewClientComments = useCallback(() => {
    apiFetch("/api/clients/comments/recent?limit=20", { credentials: "include" })
      .then((r) => (r.ok ? r.json() : []))
      .then((rows: RecentComment[]) => {
        if (!Array.isArray(rows) || rows.length === 0) return;
        let seenAt = 0;
        try {
          seenAt = Number(window.localStorage.getItem(CLIENTS_COMMENTS_SEEN_KEY)) || 0;
        } catch {}
        const unseen = rows.some(
          (row) => row.author !== user?.email && new Date(row.created_at).getTime() > seenAt
        );
        setHasNewClientComments(unseen);
      })
      .catch(() => {});
  }, [user?.email]);

  useEffect(() => {
    checkNewClientComments();
    // Same "cheap version of polling" as the Comments page -- refetch on
    // focus rather than run an interval in every tab all day.
    window.addEventListener("focus", checkNewClientComments);
    return () => window.removeEventListener("focus", checkNewClientComments);
  }, [checkNewClientComments]);

  // Opening the Clients tab clears the dot -- everything up to now is "seen".
  useEffect(() => {
    if (!location.pathname.includes("/clients")) return;
    try {
      window.localStorage.setItem(CLIENTS_COMMENTS_SEEN_KEY, String(Date.now()));
    } catch {}
    setHasNewClientComments(false);
  }, [location.pathname]);

  // Nav order / visibility come from the account's preferences. Anything the
  // saved order does not mention still lands at its default position, so tabs
  // shipped after a preference was saved are never swallowed.
  const navRuns = useMemo<NavRun[]>(() => {
    const plan = resolveSidebarRender(sidebarOverride || prefs?.sidebar);
    const runs: NavRun[] = [];
    const isAdmin = Boolean(currentMe()?.isAdmin);
    plan.items.forEach(({ item, showGroupLabel }, index) => {
      if (item.adminOnly && !isAdmin) return;
      const current = runs[runs.length - 1];
      if (!current || current.groupId !== item.groupId) {
        runs.push({
          key: `${item.groupId}-${index}`,
          groupId: item.groupId,
          label: showGroupLabel ? item.groupLabel : null,
          items: [item],
          hasAnchor: index === plan.anchorIndex,
        });
        return;
      }
      current.items.push(item);
      if (index === plan.anchorIndex) current.hasAnchor = true;
    });
    // anchorIndex === -1 means every Workspace tab is hidden. The Clients &
    // Projects tree must never vanish with them, so it falls to the end.
    if (plan.anchorIndex === -1 && runs.length > 0) {
      runs[runs.length - 1].hasAnchor = true;
    }
    return runs;
  }, [prefs, sidebarOverride]);

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

  // Rendered once, placed after the run that holds the anchor group. Extracted
  // into a variable (rather than duplicated) so the expandable Clients and
  // Projects trees keep a single implementation no matter where they land.
  const clientsProjectsSection = (
    <div>
      <p className={GROUP_LABEL}>Clients &amp; Projects</p>
      <div className="flex flex-col gap-0.5">
        <div className="flex items-center gap-1">
          <Link
            to="/clients"
            className={`flex min-w-0 flex-1 items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors text-left ${
              isActive("/clients") ? NAV_ITEM_ACTIVE : NAV_ITEM_IDLE
            }`}
          >
            <span className="relative flex-none">
              <Users size={16} strokeWidth={1.8} />
              {hasNewClientComments && (
                <span
                  className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-emerald-400 ring-2 ring-[#1c2e1e]"
                  title="New comment"
                  aria-label="New comment"
                />
              )}
            </span>
            Clients
          </Link>
          <button
            onClick={() => setClientsOpen((open) => !open)}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-white/45 transition-colors hover:bg-white/5 hover:text-white"
            title={clientsOpen ? "Hide client list" : "Show client list"}
            aria-label={clientsOpen ? "Hide client list" : "Show client list"}
          >
            <ChevronRight size={14} className={`transition-transform ${clientsOpen ? "rotate-90" : ""}`} />
          </button>
        </div>
        {clientsOpen && (
          <div className="ml-5 mt-1 flex flex-col gap-0.5 border-l border-white/10 pl-2">
            {projectClients.slice(0, 12).map((client) => {
              const active = isActive("/clients") && activeClientName === client.name;
              return (
                <Link
                  key={client.name}
                  to={`/clients?client=${encodeURIComponent(client.name)}`}
                  className={`flex items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs font-medium transition-colors ${
                    active ? SUBTREE_ITEM_ACTIVE : SUBTREE_ITEM_IDLE
                  }`}
                  title={`${client.count} project${client.count === 1 ? "" : "s"}`}
                >
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500/70" />
                  <span className="truncate">{client.name}</span>
                </Link>
              );
            })}
            {projectsLoading ? (
              <div className="rounded-lg px-2 py-1.5 text-left text-xs text-white/45">
                Loading clients...
              </div>
            ) : projectClients.length === 0 && (
              <Link
                to="/clients"
                className="rounded-lg px-2 py-1.5 text-left text-xs text-white/45 hover:bg-white/5 hover:text-white"
              >
                No clients yet
              </Link>
            )}
          </div>
        )}
        <div className="flex items-center gap-1">
          <Link
            to="/projects"
            className={`flex min-w-0 flex-1 items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors text-left ${
              isActive("/projects") ? NAV_ITEM_ACTIVE : NAV_ITEM_IDLE
            }`}
          >
            <Package size={16} strokeWidth={1.8} />
            All Projects
          </Link>
          <button
            onClick={() => setProjectsOpen((open) => !open)}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-white/45 transition-colors hover:bg-white/5 hover:text-white"
            title={projectsOpen ? "Hide project list" : "Show project list"}
            aria-label={projectsOpen ? "Hide project list" : "Show project list"}
          >
            <ChevronRight size={14} className={`transition-transform ${projectsOpen ? "rotate-90" : ""}`} />
          </button>
        </div>
        {projectsOpen && (
          <div className="ml-5 mt-1 flex flex-col gap-0.5 border-l border-white/10 pl-2">
            {sidebarProjects.map((project) => {
              const active = isActive("/projects") && activeProjectId === String(project.id);
              return (
                <Link
                  key={project.id}
                  to={`/projects?id=${project.id}`}
                  className={`rounded-lg px-2 py-1.5 text-left text-xs transition-colors ${
                    active ? SUBTREE_ITEM_ACTIVE : SUBTREE_ITEM_IDLE
                  }`}
                  title={`${project.client_name || "No client"} · ${project.name}`}
                >
                  <span className="block truncate font-medium">{project.name}</span>
                  <span className="block truncate text-[10px] opacity-60">{project.client_name || "No client"}</span>
                </Link>
              );
            })}
            {projectsLoading ? (
              <div className="rounded-lg px-2 py-1.5 text-left text-xs text-white/45">
                Loading projects...
              </div>
            ) : sidebarProjects.length === 0 && (
              <Link
                to="/projects"
                className="rounded-lg px-2 py-1.5 text-left text-xs text-white/45 hover:bg-white/5 hover:text-white"
              >
                No projects yet
              </Link>
            )}
          </div>
        )}
      </div>
    </div>
  );

  // The wrapper uses `bg-background` (previously a hardcoded #f7f4ef) so the
  // content area follows the theme while the sidebar keeps its dark identity.
  return (
    <div className="min-h-screen flex bg-background" style={{ fontFamily: "'Montserrat', sans-serif" }}>
      {/* Phone / tablet top bar. Same dark chrome as the sidebar; hidden at lg
          where the sidebar is always on screen. */}
      <header
        data-ll-chrome="dark"
        className="fixed inset-x-0 top-0 z-30 flex h-14 items-center gap-2 border-b border-white/10 px-2 lg:hidden"
        style={{ backgroundColor: "#1c2e1e" }}
      >
        <button
          type="button"
          onClick={() => setNavOpen(true)}
          aria-label="Open navigation"
          aria-expanded={navOpen}
          className="flex h-10 w-10 items-center justify-center rounded-lg text-white/80 hover:bg-white/10 hover:text-white"
        >
          <Menu size={20} />
        </button>
        <Link to="/" className="flex items-center rounded-lg px-1 py-1" aria-label="Leaf & Ledger home">
          <LeafLedgerLogo className="h-9 w-auto" />
        </Link>
      </header>
      {navOpen && (
        <div
          className="ll-overlay fixed inset-0 z-30 bg-black/50 lg:hidden"
          onClick={() => setNavOpen(false)}
          aria-hidden="true"
        />
      )}
      {/* Sidebar - intentionally dark in BOTH light and dark mode. */}
      <aside
        // `data-ll-chrome="dark"` is the hook index.css uses to pin the stone /
        // emerald ramps to their light-on-dark values inside this element, so the
        // sidebar renders identically in both modes. Without it the stylesheet
        // falls back to matching `aside.w-60`, which is brittle.
        data-ll-chrome="dark"
        className={`w-60 flex-shrink-0 flex flex-col border-r border-white/10 py-8 px-4 fixed top-0 left-0 h-full z-40 transition-transform duration-200 ease-drawer motion-reduce:transition-none lg:z-20 lg:translate-x-0 lg:shadow-none ${
          navOpen ? "translate-x-0 shadow-2xl" : "-translate-x-full"
        }`}
        style={{ backgroundColor: "#1c2e1e" }}
        aria-label="Main navigation"
      >
        {/* Logo */}
        <div className="relative mb-10 px-2">
          <button
            type="button"
            onClick={() => setNavOpen(false)}
            aria-label="Close navigation"
            className="absolute -right-1 -top-2 flex h-9 w-9 items-center justify-center rounded-lg text-white/60 hover:bg-white/10 hover:text-white lg:hidden"
          >
            <X size={18} />
          </button>
          <Link to="/" className="block w-[176px] pr-8" aria-label="Leaf & Ledger home">
            <LeafLedgerLogo className="h-auto w-full" />
          </Link>
          <p className="mt-2 text-xs text-white/45 leading-tight">Catalog &amp; project operations</p>
        </div>

        {/* Nav */}
        <nav className="flex flex-col gap-4 flex-1 overflow-y-auto pr-1">
          {navRuns.map((run) => (
            <React.Fragment key={run.key}>
              <div>
                {run.label && <p className={GROUP_LABEL}>{run.label}</p>}
                <div className="flex flex-col gap-0.5">
                  {run.items.map(({ path, label, icon: Icon }) => {
                    const active = isActive(path);
                    return (
                      <Link
                        key={path}
                        to={path}
                        className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors text-left w-full ${
                          active ? NAV_ITEM_ACTIVE : NAV_ITEM_IDLE
                        }`}
                      >
                        <Icon size={16} strokeWidth={1.8} />
                        {label}
                        {active && <ChevronRight size={12} className="ml-auto opacity-60" />}
                      </Link>
                    );
                  })}
                </div>
              </div>

              {run.hasAnchor && clientsProjectsSection}
            </React.Fragment>
          ))}
          {navRuns.length === 0 && clientsProjectsSection}
        </nav>

        {/* Appearance quick toggle + user info + sign out */}
        <div className="px-2 pt-6 border-t border-white/10">
          <div className="mb-3 flex items-center gap-1 rounded-lg bg-white/5 p-1">
            {THEME_MODE_OPTIONS.map((option) => {
              const OptionIcon = option.icon;
              const selected = mode === option.mode;
              return (
                <button
                  key={option.mode}
                  onClick={() => setMode(option.mode)}
                  className={`flex h-6 flex-1 items-center justify-center rounded-md transition-colors ${
                    selected ? "bg-emerald-700/50 text-emerald-200" : "text-white/40 hover:bg-white/5 hover:text-white/80"
                  }`}
                  title={option.label}
                  aria-label={option.label}
                  aria-pressed={selected}
                >
                  <OptionIcon size={12} />
                </button>
              );
            })}
          </div>
          {user && (
            <div className="mb-3">
              <p className="text-xs font-medium text-white/80 truncate">{user.user_metadata?.full_name || user.email?.split("@")[0]}</p>
              <p className="text-xs text-white/40 truncate">{user.email}</p>
            </div>
          )}
          <button
            onClick={handleSignOut}
            className="flex items-center gap-2 text-xs text-white/45 hover:text-white transition-colors w-full"
          >
            <LogOut size={13} />
            Sign out
          </button>
        </div>
      </aside>

      {/* Main content offset for sidebar. data-scroll-root: this div, not
          window, is what actually scrolls -- pages that restore a saved
          scroll position (Catalog Search) select it by that attribute.
          It must be h-screen, not min-h-screen: min-h let it grow to fit its
          content, so it never overflowed, the window scrolled instead, and
          every `sticky top-0` page header rode away inside a container that
          never moved -- while this comment claimed the opposite. */}
      <div data-scroll-root className="mt-14 h-[calc(100dvh-3.5rem)] flex-1 overflow-auto lg:ml-60 lg:mt-0 lg:h-screen">
        {children}
      </div>
      <FeedbackWidget />
    </div>
  );
}
