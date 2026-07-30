import type { LucideIcon } from "lucide-react";
import {
  Activity,
  Building2,
  Calculator,
  FileText,
  Heart,
  LayoutGrid,
  Leaf,
  Search,
  Settings,
  Shapes,
  ShoppingCart,
  Sparkles,
} from "lucide-react";

/**
 * Single source of truth for the sidebar's navigation items.
 *
 * Lives outside Layout.tsx so the sidebar itself and the Settings > Appearance
 * editor render from exactly the same list. Adding a tab here is all that is
 * needed for it to show up in both places - `resolveSidebarOrder` guarantees a
 * newly added item appears at its default position even for users whose saved
 * order predates it.
 */

export interface NavItem {
  path: string;
  label: string;
  icon: LucideIcon;
}

export interface NavGroup {
  id: string;
  label: string | null;
  items: NavItem[];
}

/**
 * The expandable Clients / Projects tree is rendered directly after the last
 * *visible* item belonging to this group. Kept here (rather than in Layout) so
 * the ordering helpers can report where the tree belongs.
 */
export const CLIENTS_PROJECTS_ANCHOR_GROUP_ID = "workspace";

/**
 * DEFAULT ORDER - deliberately chosen by the owner. A user with no saved
 * preference must see exactly this.
 */
export const NAV_GROUPS: NavGroup[] = [
  {
    id: "home",
    label: null,
    items: [{ path: "/", label: "Dashboard", icon: LayoutGrid }],
  },
  {
    id: "workspace",
    label: "Workspace",
    items: [
      { path: "/designs", label: "Designs", icon: Shapes },
      { path: "/mockups", label: "AI Mockups", icon: Sparkles },
      { path: "/ornament-calculator", label: "Ornament Calculator", icon: Calculator },
      { path: "/search", label: "Catalog Search", icon: Search },
      { path: "/library", label: "Product Library", icon: Leaf },
      { path: "/suppliers", label: "Suppliers", icon: Building2 },
      { path: "/orders", label: "Purchase Orders", icon: ShoppingCart },
      { path: "/favorites", label: "Favorites", icon: Heart },
      { path: "/invoice", label: "Invoices", icon: FileText },
    ],
  },
  {
    id: "admin",
    label: "Admin",
    items: [
      { path: "/admin-dashboard", label: "Sync Operations", icon: Activity },
      { path: "/settings", label: "Settings", icon: Settings },
    ],
  },
];

/**
 * Nav items that can never be hidden - a user who hides these locks themselves
 * out of the screens that would let them undo it.
 *
 * This must stay identical to `PINNED_PATHS` in utils/preferences.ts, which the
 * store and the server use to strip these paths out of `hidden` on every read
 * and write. It is duplicated rather than imported so that this module stays a
 * pure, side-effect-free config unit (importing the store would pull the
 * Supabase client and fetch layer into it). SidebarTabsEditor asserts the two
 * lists agree in development.
 */
export const PINNED_PATHS: string[] = ["/", "/settings"];

export function isPinnedPath(path: string): boolean {
  return PINNED_PATHS.indexOf(path) !== -1;
}

export interface ResolvedNavItem extends NavItem {
  groupId: string;
  groupLabel: string | null;
  pinned: boolean;
}

const NAV_ITEMS: ResolvedNavItem[] = NAV_GROUPS.flatMap((group) =>
  group.items.map((item) => ({
    ...item,
    groupId: group.id,
    groupLabel: group.label,
    pinned: isPinnedPath(item.path),
  }))
);

const NAV_ITEM_BY_PATH: Record<string, ResolvedNavItem> = NAV_ITEMS.reduce(
  (acc, item) => {
    acc[item.path] = item;
    return acc;
  },
  {} as Record<string, ResolvedNavItem>
);

/** Flattened default order, used as the fallback and by "Reset to default". */
export const DEFAULT_NAV_ORDER: string[] = NAV_ITEMS.map((item) => item.path);

export function navItemForPath(path: string): ResolvedNavItem | undefined {
  return NAV_ITEM_BY_PATH[path];
}

/**
 * Merge a saved order with the default order.
 *
 * The saved order is an *override hint*, never the list itself. An empty (or
 * absent) order means "no customisation" - which is what a brand-new account
 * stores - and yields the full default order, not an empty sidebar.
 *
 * Rules:
 *  - Unknown paths in the saved order are dropped (a tab that no longer exists
 *    must not leave a hole or a dead button).
 *  - Duplicates in the saved order are collapsed to their first occurrence.
 *  - **Any default item missing from the saved order is re-inserted at its
 *    default position** - immediately after the nearest preceding default
 *    neighbour that survived, or, if it has none, immediately before the
 *    nearest following one. This is what stops a stale saved order from
 *    silently swallowing tabs shipped after it was written.
 *  - Missing items are processed in default order, so a run of several new
 *    neighbouring tabs keeps its relative default order too.
 *
 * The result always contains every known path exactly once, which also
 * guarantees the pinned items can never be ordered out of existence.
 */
export function resolveSidebarOrder(savedOrder?: string[] | null): string[] {
  const saved = Array.isArray(savedOrder) ? savedOrder : [];
  const kept: string[] = [];
  const keptSet = new Set<string>();

  saved.forEach((value) => {
    const path = typeof value === "string" ? value : "";
    if (!path || keptSet.has(path) || !NAV_ITEM_BY_PATH[path]) return;
    keptSet.add(path);
    kept.push(path);
  });

  const missing = DEFAULT_NAV_ORDER.filter((path) => !keptSet.has(path));
  if (missing.length === 0) return kept;
  if (kept.length === 0) return [...DEFAULT_NAV_ORDER];

  const result = [...kept];
  missing.forEach((path) => {
    const defaultIndex = DEFAULT_NAV_ORDER.indexOf(path);

    for (let i = defaultIndex - 1; i >= 0; i -= 1) {
      const anchor = result.indexOf(DEFAULT_NAV_ORDER[i]);
      if (anchor !== -1) {
        result.splice(anchor + 1, 0, path);
        return;
      }
    }

    for (let i = defaultIndex + 1; i < DEFAULT_NAV_ORDER.length; i += 1) {
      const follower = result.indexOf(DEFAULT_NAV_ORDER[i]);
      if (follower !== -1) {
        result.splice(follower, 0, path);
        return;
      }
    }

    result.push(path);
  });

  return clampToGroups(result);
}

/**
 * Reordering is *within-group*: a tab can be moved around inside its own
 * section but never into another one.
 *
 * The saved order is a single flat path list, so a stale or hand-edited row can
 * still interleave groups. Rather than honour that (which renders a group
 * heading once per contiguous run, so an interleaved order shows the same
 * heading twice), each item is placed back under its home group. Groups keep
 * their canonical order; within a group, items follow the saved order.
 */
function clampToGroups(order: string[]): string[] {
  const position = new Map(order.map((path, index) => [path, index]));
  const out: string[] = [];

  NAV_GROUPS.forEach((group) => {
    group.items
      .filter((item) => position.has(item.path))
      .sort((a, b) => position.get(a.path)! - position.get(b.path)!)
      .forEach((item) => out.push(item.path));
  });

  return out;
}

/** Drops unknown paths and refuses to hide a pinned item. */
export function resolveHiddenPaths(savedHidden?: string[] | null): string[] {
  const saved = Array.isArray(savedHidden) ? savedHidden : [];
  const out: string[] = [];
  saved.forEach((value) => {
    const path = typeof value === "string" ? value : "";
    if (!path || out.indexOf(path) !== -1) return;
    if (!NAV_ITEM_BY_PATH[path] || isPinnedPath(path)) return;
    out.push(path);
  });
  return out;
}

export interface SidebarPrefsLike {
  order?: string[] | null;
  hidden?: string[] | null;
}

/**
 * Fired by the tabs editor so an already-mounted Layout repaints its sidebar the
 * instant an edit is made, instead of waiting for the debounced write to land.
 * Mirrors the existing "leaf-ledger-projects-changed" pattern.
 */
export const SIDEBAR_PREFS_EVENT = "leaf-ledger-sidebar-prefs-changed";

export interface SidebarPrefsEventDetail {
  order: string[];
  hidden: string[];
}

export interface SidebarEditorRow {
  item: ResolvedNavItem;
  hidden: boolean;
}

/** Every known item in resolved order, flagged - what the editor lists. */
export function resolveSidebarRows(sidebar?: SidebarPrefsLike | null): SidebarEditorRow[] {
  const order = resolveSidebarOrder(sidebar?.order);
  const hidden = new Set(resolveHiddenPaths(sidebar?.hidden));
  return order.map((path) => ({
    item: NAV_ITEM_BY_PATH[path],
    hidden: hidden.has(path),
  }));
}

export interface SidebarRenderItem {
  item: ResolvedNavItem;
  /**
   * True at the start of each contiguous run of items sharing a group, so the
   * group heading follows the user's ordering instead of fighting it.
   */
  showGroupLabel: boolean;
}

export interface SidebarRenderPlan {
  items: SidebarRenderItem[];
  /**
   * Index in `items` after which the Clients & Projects tree renders. -1 means
   * "nothing from the anchor group is visible" - render the tree last so it can
   * never disappear.
   */
  anchorIndex: number;
}

/** Visible items only, with heading placement and the sub-tree anchor. */
export function resolveSidebarRender(sidebar?: SidebarPrefsLike | null): SidebarRenderPlan {
  const hidden = new Set(resolveHiddenPaths(sidebar?.hidden));
  const visible = resolveSidebarOrder(sidebar?.order)
    .map((path) => NAV_ITEM_BY_PATH[path])
    .filter((item) => item && !hidden.has(item.path));

  let anchorIndex = -1;
  const items = visible.map((item, index) => {
    if (item.groupId === CLIENTS_PROJECTS_ANCHOR_GROUP_ID) anchorIndex = index;
    const previous = visible[index - 1];
    return {
      item,
      showGroupLabel: Boolean(item.groupLabel) && (!previous || previous.groupId !== item.groupId),
    };
  });

  return { items, anchorIndex };
}
