import { useCallback, useEffect, useSyncExternalStore } from "react";
import { apiFetch } from "utils/apiFetch";

/**
 * Per-account UI preferences — sidebar layout and appearance.
 *
 * Backed by `GET`/`PUT /api/preferences`, but the server is never on the
 * critical path for rendering:
 *
 * - **Instant paint.** The last known preferences are cached in localStorage and
 *   read *synchronously* on first render, so the sidebar draws in its saved
 *   order on the first frame and never waits for a round-trip. The server is
 *   consulted right after, and the answer is reconciled in.
 * - **Partial, debounced, coalesced writes.** `save()` takes a patch, applies it
 *   optimistically, and batches ~400ms of patches into one `PUT`. A drag-reorder
 *   fires a dozen times; the server sees one request. Because both the patch and
 *   the endpoint are partial, the sidebar editor and the appearance picker can
 *   write at the same time without overwriting each other's subtree.
 * - **Never throws, never blanks the app.** Every `/api` route answers 401 when
 *   not signed in. On 401, a network failure, or an HTML error page, this falls
 *   back to the cached-or-default document and keeps working — local edits still
 *   apply visually, they just don't persist.
 *
 * State lives at module scope, not per-hook, so every consumer (the sidebar, the
 * appearance picker, `useTheme`) sees one document and one debounce queue.
 */

export interface SidebarPrefs {
  /**
   * Ordered nav item paths, e.g. ["/", "/designs", "/search"]. Missing items
   * fall back to their default position, so newly-shipped tabs still appear.
   * Empty (the default) means "no customisation — use the built-in order".
   */
  order: string[];
  /** Nav item paths the user has hidden. "/" and "/settings" can never be hidden. */
  hidden: string[];
}

export interface ThemePrefs {
  mode: "system" | "light" | "dark";
  /** Accent key from THEME_ACCENTS in utils/theme.ts. */
  accent: string;
}

export interface UserPreferences {
  sidebar: SidebarPrefs;
  theme: ThemePrefs;
}

/** A patch shape: any subtree may be omitted. Arrays are replaced, not merged. */
export type DeepPartial<T> = T extends (infer _U)[]
  ? T
  : T extends object
    ? { [K in keyof T]?: DeepPartial<T[K]> }
    : T;

export const DEFAULT_PREFERENCES: UserPreferences = {
  sidebar: { order: [], hidden: [] },
  theme: { mode: "system", accent: "emerald" },
};

/** Nav paths the user may never hide — losing Settings is unrecoverable. */
export const PINNED_PATHS = ["/", "/settings"];

/**
 * localStorage key holding the cached document.
 *
 * The value is the plain `UserPreferences` JSON with no wrapper, so a pre-paint
 * inline snippet in `index.html` can apply the saved theme before React boots:
 *
 *   JSON.parse(localStorage.getItem("ll.preferences.v1") || "{}").theme
 */
export const PREFERENCES_CACHE_KEY = "ll.preferences.v1";

const ENDPOINT = "/api/preferences";
const SAVE_DEBOUNCE_MS = 400;
const THEME_MODES = ["system", "light", "dark"];

// ─── Normalising ─────────────────────────────────────────────────────────────
// Applied to the cache and to every server response. The cache can be stale,
// hand-edited or written by an older build, and a proxy or dev server can answer
// with something that isn't the document at all — none of that may produce a
// half-shaped object that the sidebar then indexes into.

function canonPath(path: string): string {
  const text = String(path).trim().toLowerCase();
  if (!text) return "/";
  return text.replace(/\/+$/, "") || "/";
}

function stringList(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const out: string[] = [];
  for (const item of value) {
    if (typeof item !== "string") continue;
    const text = item.trim();
    if (text && !out.includes(text)) out.push(text);
  }
  return out;
}

/**
 * The valid subset of `raw`, keeping only the keys actually present, so the
 * result is safe to use as a patch. Unknown keys and bad values are dropped
 * rather than rejected — a mangled cache must degrade to the defaults.
 *
 * `/` and `/settings` are stripped from `hidden` here too. The server enforces
 * this authoritatively; doing it locally as well means the UI never even shows
 * a frame where Settings has vanished.
 */
function normalize(raw: unknown): DeepPartial<UserPreferences> {
  const out: DeepPartial<UserPreferences> = {};
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return out;
  const src = raw as Record<string, any>;

  if (src.sidebar && typeof src.sidebar === "object" && !Array.isArray(src.sidebar)) {
    const sidebar: Partial<SidebarPrefs> = {};
    const order = stringList(src.sidebar.order);
    if (order) sidebar.order = order;
    const hidden = stringList(src.sidebar.hidden);
    if (hidden) sidebar.hidden = hidden.filter((p) => !PINNED_PATHS.includes(canonPath(p)));
    if (Object.keys(sidebar).length) out.sidebar = sidebar;
  }

  if (src.theme && typeof src.theme === "object" && !Array.isArray(src.theme)) {
    const theme: Partial<ThemePrefs> = {};
    const mode = typeof src.theme.mode === "string" ? src.theme.mode.trim().toLowerCase() : "";
    if (THEME_MODES.includes(mode)) theme.mode = mode as ThemePrefs["mode"];
    const accent = typeof src.theme.accent === "string" ? src.theme.accent.trim() : "";
    if (accent) theme.accent = accent;
    if (Object.keys(theme).length) out.theme = theme;
  }

  return out;
}

/** `patch` over `base`, recursing into objects. Arrays and scalars replace. */
function mergeInto<T>(base: T, patch: any): T {
  if (!patch || typeof patch !== "object" || Array.isArray(patch)) return base;
  const out: any = { ...(base as any) };
  for (const key of Object.keys(patch)) {
    const value = patch[key];
    const current = out[key];
    if (
      value && typeof value === "object" && !Array.isArray(value) &&
      current && typeof current === "object" && !Array.isArray(current)
    ) {
      out[key] = mergeInto(current, value);
    } else if (value !== undefined) {
      out[key] = value;
    }
  }
  return out as T;
}

function withDefaults(raw: unknown): UserPreferences {
  return mergeInto(
    { sidebar: { ...DEFAULT_PREFERENCES.sidebar }, theme: { ...DEFAULT_PREFERENCES.theme } },
    normalize(raw),
  );
}

// ─── Cache ───────────────────────────────────────────────────────────────────

/**
 * The cached document, or the defaults. Synchronous and safe to call during
 * render — this is what makes the first paint correct.
 */
export function readCachedPreferences(): UserPreferences {
  try {
    const raw = window.localStorage.getItem(PREFERENCES_CACHE_KEY);
    return withDefaults(raw ? JSON.parse(raw) : null);
  } catch {
    // No localStorage (private mode / SSR) or corrupt JSON.
    return withDefaults(null);
  }
}

function writeCache(prefs: UserPreferences): void {
  try {
    window.localStorage.setItem(PREFERENCES_CACHE_KEY, JSON.stringify(prefs));
  } catch {
    // Quota or a blocked store — the app still works, it just won't paint
    // instantly next load.
  }
}

// ─── Module-scoped store ─────────────────────────────────────────────────────

export interface PreferencesState {
  prefs: UserPreferences;
  loading: boolean;
  saving: boolean;
}

let state: UserPreferences = readCachedPreferences();
let loading = true;
let saving = false;

// Rebuilt only when something actually changes: useSyncExternalStore compares
// snapshots by identity and would loop forever on a fresh object each call.
let snapshot: PreferencesState = { prefs: state, loading, saving };
const listeners = new Set<() => void>();

function emit(): void {
  snapshot = { prefs: state, loading, saving };
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

// ─── Server sync ─────────────────────────────────────────────────────────────

/** Accumulated unsent patch. Successive `save()` calls coalesce into this. */
let pending: DeepPartial<UserPreferences> | null = null;
let timer: ReturnType<typeof setTimeout> | null = null;
let inflight = false;
let started = false;

function scheduleFlush(): void {
  if (timer) clearTimeout(timer);
  timer = setTimeout(() => {
    timer = null;
    void flush();
  }, SAVE_DEBOUNCE_MS);
}

async function flush(keepalive = false): Promise<void> {
  if (timer) {
    clearTimeout(timer);
    timer = null;
  }
  if (!pending || inflight) return;
  const patch = pending;
  pending = null;
  inflight = true;
  try {
    const res = await apiFetch(ENDPOINT, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
      keepalive,
    });
    if (res.ok && (res.headers.get("content-type") || "").includes("json")) {
      // The server is authoritative (it strips the un-hideable paths and fills
      // defaults), but anything the user changed while this was in flight must
      // survive — so re-apply the newer pending patch on top of its answer.
      state = mergeInto(withDefaults(await res.json()), pending ?? {});
      writeCache(state);
    }
    // 401 / 4xx / 5xx: keep the optimistic local state. The change is visible
    // and cached; it simply isn't persisted for this session.
  } catch {
    // Offline or aborted — same story.
  } finally {
    inflight = false;
    if (pending) scheduleFlush();
    else saving = false;
    emit();
  }
}

async function revalidate(): Promise<void> {
  try {
    const res = await apiFetch(ENDPOINT);
    if (res.ok && (res.headers.get("content-type") || "").includes("json")) {
      const server = withDefaults(await res.json());
      // A PUT that is already in flight is newer than this read; its response
      // will supersede this one, so don't let a stale GET undo the user's edit.
      if (!inflight) {
        state = mergeInto(server, pending ?? {});
        writeCache(state);
      }
    }
    // Not signed in (401) or unreachable: the cached/default document stands.
  } catch {
    // Offline — same.
  } finally {
    loading = false;
    emit();
  }
}

function start(): void {
  if (started) return;
  started = true;
  void revalidate();

  if (typeof window !== "undefined") {
    // Don't lose a debounced reorder to a navigation or a closing tab.
    window.addEventListener("pagehide", () => {
      if (pending) void flush(true);
    });
    // Another tab saved: adopt it, unless we hold unsent edits of our own.
    window.addEventListener("storage", (event) => {
      if (event.key !== PREFERENCES_CACHE_KEY || pending || inflight) return;
      state = readCachedPreferences();
      emit();
    });
  }
}

// ─── Public API ──────────────────────────────────────────────────────────────

/** Apply a partial change: optimistic locally, debounced and merged remotely. */
export function savePreferences(patch: DeepPartial<UserPreferences>): void {
  const clean = normalize(patch);
  if (!Object.keys(clean).length) return;
  state = mergeInto(state, clean);
  writeCache(state);
  pending = mergeInto(pending ?? {}, clean);
  saving = true;
  emit();
  scheduleFlush();
}

/** Restore the defaults, locally and on the server. */
export function resetPreferences(): void {
  state = withDefaults(null);
  writeCache(state);
  // A full document (every leaf present) overwrites everything server-side,
  // since a deep merge of a complete object leaves nothing behind.
  pending = {
    sidebar: { ...DEFAULT_PREFERENCES.sidebar },
    theme: { ...DEFAULT_PREFERENCES.theme },
  };
  saving = true;
  emit();
  scheduleFlush();
}

/**
 * The current preferences plus writers.
 *
 * `prefs` is always a complete document — cached on the first render, then the
 * server's. `loading` is true only until the first read settles; don't gate the
 * UI on it, the values are already usable.
 */
export function usePreferences(): {
  prefs: UserPreferences;
  save: (patch: DeepPartial<UserPreferences>) => void;
  reset: () => void;
  loading: boolean;
  saving: boolean;
} {
  const store = useSyncExternalStore(subscribe, () => snapshot, () => snapshot);

  useEffect(() => {
    start();
  }, []);

  const save = useCallback((patch: DeepPartial<UserPreferences>) => savePreferences(patch), []);
  const reset = useCallback(() => resetPreferences(), []);

  return { prefs: store.prefs, save, reset, loading: store.loading, saving: store.saving };
}
