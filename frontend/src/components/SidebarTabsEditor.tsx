import React, { useCallback, useMemo, useRef, useState } from "react";
import { ChevronDown, ChevronUp, Eye, EyeOff, GripVertical, Lock, RotateCcw } from "lucide-react";
import { PINNED_PATHS as STORE_PINNED_PATHS, usePreferences } from "utils/preferences";
import {
  DEFAULT_NAV_ORDER,
  isPinnedPath,
  navItemForPath,
  PINNED_PATHS,
  resolveHiddenPaths,
  resolveSidebarOrder,
  SIDEBAR_PREFS_EVENT,
} from "components/sidebarNav";
import type { SidebarPrefsEventDetail } from "components/sidebarNav";

// sidebarNav keeps its own copy of the un-hideable paths so it stays a pure
// config module. If the two ever drift, this UI would offer to hide something the
// store and server silently put back - so say so loudly in development.
if (import.meta.env.DEV && [...PINNED_PATHS].sort().join("|") !== [...STORE_PINNED_PATHS].sort().join("|")) {
  console.error(
    "PINNED_PATHS drift: components/sidebarNav.ts has",
    PINNED_PATHS,
    "but utils/preferences.ts has",
    STORE_PINNED_PATHS
  );
}

function broadcast(detail: SidebarPrefsEventDetail) {
  try {
    window.dispatchEvent(new CustomEvent<SidebarPrefsEventDetail>(SIDEBAR_PREFS_EVENT, { detail }));
  } catch {
    // Broadcasting is a nicety; the preference write is the source of truth.
  }
}

function move(list: string[], from: number, to: number) {
  if (from === to || from < 0 || to < 0 || from >= list.length || to >= list.length) return list;
  const next = [...list];
  const [moved] = next.splice(from, 1);
  next.splice(to, 0, moved);
  return next;
}

/**
 * Reorder / show-hide editor for the sidebar tabs.
 *
 * Everything is optimistic: a local draft drives the list so dragging never
 * waits on the network, and each change is handed to the debounced
 * `usePreferences().save`.
 */
export default function SidebarTabsEditor() {
  const { prefs, save, saving } = usePreferences();
  const [draft, setDraft] = useState<SidebarPrefsEventDetail | null>(null);
  const [dragPath, setDragPath] = useState<string | null>(null);
  const dragPathRef = useRef<string | null>(null);

  // Until the user touches anything, follow the stored preference (so a slow
  // server revalidation still lands). After that the draft wins, so an
  // in-flight save echo can never yank a row out from under the pointer.
  const order = useMemo(
    () => (draft ? resolveSidebarOrder(draft.order) : resolveSidebarOrder(prefs?.sidebar?.order)),
    [draft, prefs]
  );
  const hidden = useMemo(
    () => (draft ? resolveHiddenPaths(draft.hidden) : resolveHiddenPaths(prefs?.sidebar?.hidden)),
    [draft, prefs]
  );

  const commit = useCallback(
    (nextOrder: string[], nextHidden: string[]) => {
      const detail: SidebarPrefsEventDetail = {
        order: resolveSidebarOrder(nextOrder),
        hidden: resolveHiddenPaths(nextHidden),
      };
      setDraft(detail);
      broadcast(detail);
      save({ sidebar: detail });
    },
    [save]
  );

  // Pinned rows are fixed slots: they cannot be dragged, and nothing can be
  // dropped onto their position, so Dashboard stays first and Settings stays
  // last no matter how the rest is shuffled.
  const moveTo = useCallback(
    (path: string, targetIndex: number) => {
      if (isPinnedPath(path)) return;
      const from = order.indexOf(path);
      if (from === -1) return;
      const to = Math.max(0, Math.min(order.length - 1, targetIndex));
      if (from === to) return;
      if (isPinnedPath(order[to])) return;
      // Reordering is within-group: a tab moves inside its own section only.
      // `resolveSidebarOrder` clamps items back to their home group anyway, so
      // without this the row would visibly snap back after a cross-group drop.
      if (navItemForPath(path)?.groupId !== navItemForPath(order[to])?.groupId) return;
      commit(move(order, from, to), hidden);
    },
    [commit, hidden, order]
  );

  const moveBy = useCallback(
    (path: string, delta: number) => moveTo(path, order.indexOf(path) + delta),
    [moveTo, order]
  );

  const toggleHidden = useCallback(
    (path: string) => {
      if (isPinnedPath(path)) return;
      const next = hidden.indexOf(path) === -1 ? [...hidden, path] : hidden.filter((value) => value !== path);
      commit(order, next);
    },
    [commit, hidden, order]
  );

  // Persists `order: []` rather than today's explicit default order. An empty
  // order means "no customisation", so a tab shipped next month appears for this
  // user instead of being frozen out by a snapshot of today's nav.
  const resetToDefault = useCallback(() => {
    const detail: SidebarPrefsEventDetail = { order: [...DEFAULT_NAV_ORDER], hidden: [] };
    setDraft(detail);
    broadcast(detail);
    save({ sidebar: { order: [], hidden: [] } });
  }, [save]);

  const isDefault = useMemo(
    () => hidden.length === 0 && order.join("|") === DEFAULT_NAV_ORDER.join("|"),
    [hidden, order]
  );
  const hiddenCount = hidden.length;

  const handleDragStart = (path: string) => (event: React.DragEvent) => {
    dragPathRef.current = path;
    setDragPath(path);
    try {
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", path);
    } catch {
      // Safari can throw on setData outside a user gesture; drag still works.
    }
  };

  // Live reorder on drag-over: the list shifts under the pointer, so no drop
  // indicator or placeholder bookkeeping is needed. The midpoint test stops the
  // dragged row oscillating with its neighbour while the pointer sits still.
  const handleDragOver = (path: string) => (event: React.DragEvent) => {
    event.preventDefault();
    try {
      event.dataTransfer.dropEffect = "move";
    } catch {
      // Ignored - purely a cursor hint.
    }
    const source = dragPathRef.current;
    if (!source || source === path) return;
    const from = order.indexOf(source);
    const to = order.indexOf(path);
    if (from === -1 || to === -1) return;
    const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
    const pastMidpoint = event.clientY > rect.top + rect.height / 2;
    if (from < to && !pastMidpoint) return;
    if (from > to && pastMidpoint) return;
    moveTo(source, to);
  };

  const handleDragEnd = () => {
    dragPathRef.current = null;
    setDragPath(null);
  };

  return (
    <div className="rounded-xl border border-stone-200 bg-white p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold text-stone-800">Sidebar Tabs</h2>
          <p className="mt-1 max-w-2xl text-xs leading-relaxed text-stone-500">
            Drag a row, or use the arrows, to change the order the tabs appear in the sidebar. Hide the
            ones you never use. Dashboard and Settings stay pinned so you can always get back here.
            Changes save automatically for your account only.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[11px] font-semibold text-stone-400">
            {saving ? "Saving..." : hiddenCount > 0 ? `${hiddenCount} hidden` : "All tabs shown"}
          </span>
          <button
            type="button"
            onClick={resetToDefault}
            disabled={isDefault}
            className="flex items-center gap-2 rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs font-semibold text-stone-500 hover:bg-stone-50 disabled:opacity-50"
          >
            <RotateCcw size={13} />
            Reset to default
          </button>
        </div>
      </div>

      <ul className="mt-4 space-y-1.5">
        {order.map((path, index) => {
          const item = navItemForPath(path);
          if (!item) return null;
          const Icon = item.icon;
          const isHidden = hidden.indexOf(path) !== -1;
          const pinned = item.pinned;
          const dragging = dragPath === path;
          // Movement is bounded by the item's own group, so the arrows go dead
          // at a section boundary instead of appearing to work and snapping back.
          const prev = index > 0 ? navItemForPath(order[index - 1]) : undefined;
          const next = index < order.length - 1 ? navItemForPath(order[index + 1]) : undefined;
          const canMoveUp = !pinned && !!prev && !isPinnedPath(prev.path) && prev.groupId === item.groupId;
          const canMoveDown = !pinned && !!next && !isPinnedPath(next.path) && next.groupId === item.groupId;
          // The order is group-contiguous, so a change of groupId starts a section.
          const startsGroup = index === 0 || prev?.groupId !== item.groupId;

          return (
            <React.Fragment key={`${path}-group`}>
            {startsGroup && item.groupLabel && (
              <li className="pt-2 pb-0.5 text-[11px] font-semibold uppercase tracking-wider text-stone-400">
                {item.groupLabel}
              </li>
            )}
            <li
              key={path}
              draggable={!pinned}
              onDragStart={pinned ? undefined : handleDragStart(path)}
              onDragOver={handleDragOver(path)}
              onDrop={(event) => event.preventDefault()}
              onDragEnd={handleDragEnd}
              className={`flex items-center gap-3 rounded-lg border px-3 py-2 transition-colors ${
                dragging ? "border-emerald-300 bg-emerald-50/60" : "border-stone-100 bg-white hover:bg-stone-50"
              } ${isHidden ? "opacity-60" : ""}`}
            >
              {pinned ? (
                <span
                  className="flex h-7 w-7 shrink-0 items-center justify-center text-stone-300"
                  title="Pinned - this tab cannot be moved or hidden"
                >
                  <Lock size={13} />
                </span>
              ) : (
                <span
                  className="flex h-7 w-7 shrink-0 cursor-grab items-center justify-center rounded-lg text-stone-300 hover:bg-stone-100 hover:text-stone-500 active:cursor-grabbing"
                  title={`Drag to reorder ${item.label}`}
                  aria-hidden="true"
                >
                  <GripVertical size={14} />
                </span>
              )}

              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-stone-50 text-emerald-700">
                <Icon size={14} strokeWidth={1.8} />
              </span>

              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-semibold text-stone-800">{item.label}</span>
                <span className="block truncate text-[11px] text-stone-400">
                  {item.groupLabel || "Top level"}
                  {pinned ? " · pinned" : ""}
                  {isHidden ? " · hidden" : ""}
                </span>
              </span>

              <span className="flex shrink-0 items-center gap-1">
                <button
                  type="button"
                  onClick={() => moveBy(path, -1)}
                  disabled={!canMoveUp}
                  className="flex h-7 w-7 items-center justify-center rounded-lg text-stone-400 hover:bg-stone-100 hover:text-stone-700 disabled:opacity-30 disabled:hover:bg-transparent"
                  aria-label={`Move ${item.label} up`}
                >
                  <ChevronUp size={14} />
                </button>
                <button
                  type="button"
                  onClick={() => moveBy(path, 1)}
                  disabled={!canMoveDown}
                  className="flex h-7 w-7 items-center justify-center rounded-lg text-stone-400 hover:bg-stone-100 hover:text-stone-700 disabled:opacity-30 disabled:hover:bg-transparent"
                  aria-label={`Move ${item.label} down`}
                >
                  <ChevronDown size={14} />
                </button>
                <button
                  type="button"
                  onClick={() => toggleHidden(path)}
                  disabled={pinned}
                  className={`flex h-7 w-7 items-center justify-center rounded-lg disabled:opacity-30 disabled:hover:bg-transparent ${
                    isHidden
                      ? "text-stone-400 hover:bg-stone-100 hover:text-stone-700"
                      : "text-emerald-700 hover:bg-emerald-50"
                  }`}
                  aria-label={pinned ? `${item.label} is always shown` : isHidden ? `Show ${item.label}` : `Hide ${item.label}`}
                  aria-pressed={!isHidden}
                  title={pinned ? "Always shown" : isHidden ? "Hidden from the sidebar" : "Shown in the sidebar"}
                >
                  {isHidden ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </span>
            </li>
            </React.Fragment>
          );
        })}
      </ul>

      <p className="mt-3 text-[11px] leading-relaxed text-stone-400">
        Tabs reorder within their own group, so each heading stays in one place. The Clients &amp;
        Projects tree always stays with the Workspace group. New tabs added to Leaf &amp; Ledger later
        appear automatically in their default spot.
      </p>
    </div>
  );
}
