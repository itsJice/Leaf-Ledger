import { useSyncExternalStore } from "react";

/**
 * Keep the menu open, or fold it to the icon rail (user, 2026-10-24: "give me
 * a way to keep the side tab open, and if its closed it can do the open when i
 * hover").
 *
 * The choice is `sidebar.pinned` in the account's preferences
 * (utils/preferences.ts) and has three states:
 *
 * - absent (the default): automatic, exactly what the app did before this
 *   setting existed. Open on every page, folded to the rail on the Install
 *   Schedule pages, which need the width for the map.
 * - `true`: open on every page, the Install Schedule included.
 * - `false`: folded to the rail on every page. Hovering it slides the full
 *   menu out OVER the page, so nothing underneath reflows.
 *
 * Desktop only. Phones and tablets use the off-canvas drawer, and a device
 * that can't hover (an iPad in landscape reaches the desktop width) has no way
 * to slide a folded rail open, so there an explicit `false` reads as automatic.
 * Pure helpers plus one media-query hook, so tests can import this.
 */

/** Open the hover overlay after this long, so a cursor crossing the rail on
 * its way somewhere else doesn't flash the menu. */
export const RAIL_OPEN_DELAY_MS = 150;
/** Close it this long after the cursor leaves, so a slight overshoot doesn't
 * snap it shut. Re-entering within the window cancels the close. */
export const RAIL_CLOSE_DELAY_MS = 300;

/** Whether a device has a real hover pointer (mouse or trackpad). */
export const CAN_HOVER_QUERY = "(hover: hover) and (pointer: fine)";

export interface RailInputs {
  /** `prefs.sidebar.pinned`: true, false, or absent/null for automatic. */
  pinned: boolean | null | undefined;
  /** On one of the Install Schedule routes (utils/installViews isInstallPath). */
  onInstallPage: boolean;
  /** The device can hover (CAN_HOVER_QUERY). */
  canHover: boolean;
}

/** The pin choice that actually applies on this device. */
export function effectivePinned({ pinned, canHover }: Pick<RailInputs, "pinned" | "canHover">): boolean | undefined {
  if (pinned === true) return true;
  if (pinned === false && canHover) return false;
  return undefined;
}

/**
 * True when the desktop menu is folded to the icon rail (and opens on hover),
 * false when it is open and pushes the page over.
 */
export function isRailMode(inputs: RailInputs): boolean {
  const pinned = effectivePinned(inputs);
  if (pinned === undefined) return inputs.onInstallPage;
  return !pinned;
}

/**
 * What a click on the pin control saves. The control reads as "Keep menu
 * open" and is pressed while the menu is open on this page, so a click always
 * flips what the user sees: a folded menu gets pinned open, an open one gets
 * unpinned to the rail.
 */
export function nextPinned(railMode: boolean): boolean {
  return railMode;
}

// ─── Hover capability ────────────────────────────────────────────────────────

function readCanHover(): boolean {
  try {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return true;
    return window.matchMedia(CAN_HOVER_QUERY).matches;
  } catch {
    return true;
  }
}

function subscribeCanHover(onChange: () => void): () => void {
  try {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return () => undefined;
    const mql = window.matchMedia(CAN_HOVER_QUERY);
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  } catch {
    return () => undefined;
  }
}

/** Live `(hover: hover) and (pointer: fine)`; true when it can't be asked. */
export function useCanHover(): boolean {
  return useSyncExternalStore(subscribeCanHover, readCanHover, () => true);
}
