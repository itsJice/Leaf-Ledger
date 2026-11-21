/**
 * The error log and the "last minute" trail, browser side.
 *
 * Two jobs:
 *
 * 1. **The trail.** The last 100 steps or 10 minutes, whichever is shorter:
 *    pages opened, what was done on them (buttons, tabs, menus, dialogs,
 *    dropdown picks, ticks, fields changed by label, drag and drop, pop-up
 *    messages and their answers: utils/actionTrail.ts), calls to our server
 *    and how they went (saves say saved / not saved), errors, and what the
 *    Install Schedule frame reports. Kept in sessionStorage so it survives a
 *    reload in the same tab (the crash, then the reload, then the comment).
 *
 * 2. **Reporting errors.** `reportEvent` sends a crash, a failed request, a
 *    stuck or frozen page, etc. to POST /api/app-events with the steps that
 *    led up to it. It saves right away, whether or not anyone sends a comment.
 *
 * Rules, from how this app has broken before:
 *
 * - **Never break the app.** Every function here swallows its own failures.
 *   Sending uses plain fetch (not `apiFetch`, which would log its own
 *   failures and loop, and toasts view-only logins on a 403). A failed send
 *   is kept and retried with the next report or the next page load: no
 *   retry loop, no toast, nothing in the way of a save.
 * - **Don't flood.** The same error is reported at most once a minute, and a
 *   tab sends at most 30 events per 10 minutes. The server limits it too.
 * - **Nothing private.** Addresses lose everything after `?` or `#` (the
 *   calendar feed, share links and password resets carry tokens there;
 *   client pages carry names). Tokens are masked. No request or response
 *   bodies, no field values.
 * - **No Supabase at import time.** Node 20 on CI has no WebSocket, so the
 *   auth module is imported only when sending.
 */

import { startActionTrail, type TrailAction } from "utils/actionTrail";

export type StepType = "page" | "click" | "action" | "request" | "error" | "schedule" | "note";

export interface TrailStep {
  /** ISO time. */
  t: string;
  type: StepType;
  /** Plain words: "Opened /clients", "Pressed Save", "PUT /api/x 409". */
  label: string;
  page?: string;
  status?: number;
  ms?: number;
  source?: "app" | "schedule";
}

export type EventKind =
  | "crash"
  | "error"
  | "request_failed"
  | "stuck"
  | "freeze"
  | "blank"
  | "reload_after_deploy"
  | "previous_visit"
  | "save_blocked"
  | "save_conflict";

export interface AppEvent {
  kind: EventKind;
  source?: "app" | "schedule";
  message: string;
  detail?: Record<string, unknown>;
  page?: string;
}

export const TRAIL_MAX_STEPS = 100;
export const TRAIL_MAX_AGE_MS = 10 * 60 * 1000;
/** Steps sent with each error (a comment gets the whole trail). */
export const EVENT_TRAIL_STEPS = 30;
export const DEDUPE_MS = 60 * 1000;
export const TAB_LIMIT = 30;
export const TAB_WINDOW_MS = 10 * 60 * 1000;
const MAX_PENDING = 20;

const TRAIL_KEY = "ll-trail";
const PENDING_KEY = "ll-events-pending";
const ERROR_IDS_KEY = "ll-error-ids";
const ALIVE_KEY = "ll-page-alive";
const OPENED_KEY = "ll-tab-opened";

// ─── Pure helpers (tested in utils/__tests__/eventLog.test.ts) ─────────────

const JWT_RE = /eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}/g;
const BEARER_RE = /\bbearer\s+[A-Za-z0-9._~+/=-]+/gi;
const PAIR_RE = /\b(access_token|refresh_token|token_hash|token|password|secret|api[_-]?key)(\s*[=:]\s*)[^\s"&,;]+/gi;
const URL_QS_RE = /((?:https?:\/\/[^\s?#"']+)|(?:\/[\w\-./{}%]*))[?#][^\s"']*/g;

/** Text with tokens, secrets and query strings masked. Never throws. */
export function scrubText(value: unknown, limit = 1000): string {
  try {
    const text = String(value ?? "")
      .replace(URL_QS_RE, "$1")
      .replace(JWT_RE, "[hidden]")
      .replace(BEARER_RE, "Bearer [hidden]")
      .replace(PAIR_RE, "$1$2[hidden]");
    return text.slice(0, limit);
  } catch {
    return "";
  }
}

/** The path of an address, with no origin, query string or hash. */
export function pathOnly(value: unknown): string {
  try {
    let text = String(value ?? "");
    const proto = text.indexOf("://");
    if (proto >= 0) {
      const slash = text.indexOf("/", proto + 3);
      text = slash >= 0 ? text.slice(slash) : "/";
    }
    text = text.split("#")[0].split("?")[0];
    return text.replace(/(\/(?:api\/)?share\/)[^/]+/, "$1[hidden]").slice(0, 300);
  } catch {
    return "";
  }
}

/** Steps newer than TRAIL_MAX_AGE_MS, at most TRAIL_MAX_STEPS, oldest first. */
export function pruneTrail(steps: TrailStep[], now: number): TrailStep[] {
  const cutoff = now - TRAIL_MAX_AGE_MS;
  return steps
    .filter((s) => {
      const t = Date.parse(s.t);
      return Number.isFinite(t) && t >= cutoff;
    })
    .slice(-TRAIL_MAX_STEPS);
}

/**
 * Which failed responses are errors worth logging. 404/422-style answers are
 * often a page asking "is there one?" and getting "no" (a comment with no
 * screenshot), so they go in the trail only.
 */
export function isLoggableStatus(status: number): boolean {
  return status >= 500 || status === 401 || status === 403 || status === 409 || status === 408 || status === 413 || status === 429;
}

/** Calls whose failures are not worth an event (or would log about the log). */
export function isQuietUrl(path: string): boolean {
  return path.startsWith("/api/app-events");
}

export function dedupeKey(ev: Pick<AppEvent, "kind" | "message">): string {
  return `${ev.kind}|${ev.message.slice(0, 200)}`;
}

/** The trail step type for something done on a page (actionTrail.ts). */
export function actionStepType(kind: TrailAction["kind"] | string): StepType {
  if (kind === "click" || kind === "tab" || kind === "menu") return "click";
  if (kind === "error") return "error";
  return "action";
}

/** A call's trail label. A save (anything but GET) says how it went. */
export function requestLabel(verb: string, path: string, status: number): string {
  const base = `${verb} ${path} ${status}`;
  if (verb === "GET" || verb === "HEAD" || verb === "OPTIONS") return base;
  return `${base} ${status >= 200 && status < 400 ? "(saved)" : "(not saved)"}`;
}

/** Seconds since the token was issued and until it expires, from its own claims. */
export function tokenTiming(authHeader: string, nowMs: number): { token_age_s?: number; token_expires_in_s?: number } {
  try {
    const token = authHeader.replace(/^Bearer\s+/i, "");
    const part = token.split(".")[1];
    if (!part) return {};
    const json = JSON.parse(atob(part.replace(/-/g, "+").replace(/_/g, "/")));
    const now = Math.floor(nowMs / 1000);
    return {
      token_age_s: typeof json.iat === "number" ? now - json.iat : undefined,
      token_expires_in_s: typeof json.exp === "number" ? json.exp - now : undefined,
    };
  } catch {
    return {};
  }
}

// ─── Storage (sessionStorage; every access can throw) ──────────────────────

function readJson<T>(key: string, fallback: T): T {
  try {
    const raw = window.sessionStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function writeJson(key: string, value: unknown): void {
  try {
    window.sessionStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* full or blocked: the trail is a nicety */
  }
}

// ─── The trail ─────────────────────────────────────────────────────────────

let memoryTrail: TrailStep[] | null = null;

export function getTrail(): TrailStep[] {
  try {
    if (memoryTrail === null) memoryTrail = readJson<TrailStep[]>(TRAIL_KEY, []);
    memoryTrail = pruneTrail(memoryTrail, Date.now());
    return memoryTrail.slice();
  } catch {
    return [];
  }
}

export function addStep(step: Omit<TrailStep, "t"> & { t?: string }): void {
  try {
    const full: TrailStep = {
      ...step,
      t: step.t || new Date().toISOString(),
      label: scrubText(step.label, 160),
      page: step.page !== undefined ? pathOnly(step.page) : currentPage(),
    };
    const next = pruneTrail([...getTrail(), full], Date.now());
    memoryTrail = next;
    writeJson(TRAIL_KEY, next);
  } catch {
    /* never break the app */
  }
}

function currentPage(): string {
  try {
    return pathOnly(window.location.pathname);
  } catch {
    return "";
  }
}

// ─── Facts sent with every event and comment ───────────────────────────────

const loadedAt = Date.now();

function buildId(): string {
  try {
    const s = document.querySelector<HTMLScriptElement>('script[type="module"][src*="/assets/"]');
    return s ? pathOnly(s.src).split("/").pop() || "" : "dev";
  } catch {
    return "";
  }
}

function tabOpenedAt(): number {
  const stored = readJson<number | null>(OPENED_KEY, null);
  if (typeof stored === "number") return stored;
  writeJson(OPENED_KEY, loadedAt);
  return loadedAt;
}

export function deviceFacts(): Record<string, unknown> {
  try {
    return {
      build: buildId(),
      screen: `${window.innerWidth}x${window.innerHeight}`,
      online: navigator.onLine,
      visible: document.visibilityState,
      since_load_s: Math.round((Date.now() - loadedAt) / 1000),
      tab_open_s: Math.round((Date.now() - tabOpenedAt()) / 1000),
      lang: navigator.language,
    };
  } catch {
    return {};
  }
}

// ─── Reporting ─────────────────────────────────────────────────────────────

interface PendingEvent extends AppEvent {
  occurred_at: string;
  trail: TrailStep[];
}

const lastSent = new Map<string, number>();
let tabSends: number[] = [];
let flushTimer: number | null = null;
let flushing = false;

/** Record an error. Saves right away (batched over 1.5s), with recent steps. */
export function reportEvent(ev: AppEvent): void {
  try {
    const now = Date.now();
    const message = scrubText(ev.message, 1000) || ev.kind;
    const key = dedupeKey({ kind: ev.kind, message });
    const last = lastSent.get(key);
    if (last !== undefined && now - last < DEDUPE_MS) return;
    tabSends = tabSends.filter((t) => now - t < TAB_WINDOW_MS);
    if (tabSends.length >= TAB_LIMIT) return;
    lastSent.set(key, now);
    tabSends.push(now);

    addStep({ type: "error", label: `${ev.kind}: ${message}`.slice(0, 160), source: ev.source });
    const pending: PendingEvent = {
      ...ev,
      message,
      page: pathOnly(ev.page ?? window.location.pathname),
      detail: { ...deviceFacts(), ...(ev.detail || {}) },
      occurred_at: new Date(now).toISOString(),
      trail: getTrail().slice(-EVENT_TRAIL_STEPS),
    };
    const queue = readJson<PendingEvent[]>(PENDING_KEY, []);
    queue.push(pending);
    writeJson(PENDING_KEY, queue.slice(-MAX_PENDING));
    scheduleFlush(1500);
  } catch {
    /* never break the app */
  }
}

function scheduleFlush(delay: number): void {
  try {
    if (flushTimer !== null) return;
    flushTimer = window.setTimeout(() => {
      flushTimer = null;
      void flushEvents();
    }, delay);
  } catch {
    /* ignore */
  }
}

/** Send whatever is waiting. Called after a report and once on page load. */
export async function flushEvents(opts: { keepalive?: boolean } = {}): Promise<void> {
  if (flushing) return;
  flushing = true;
  try {
    const queue = readJson<PendingEvent[]>(PENDING_KEY, []);
    if (!queue.length) return;
    const { auth } = await import("app/auth/auth");
    const header = await auth.getAuthHeaderValue();
    if (!header) return; // signed out: keep them for after sign-in
    const timing = tokenTiming(header, Date.now());
    const events = queue.slice(0, 20).map((e) => ({ ...e, detail: { ...timing, ...e.detail } }));
    const res = await fetch("/api/app-events", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: header },
      body: JSON.stringify({ events }),
      keepalive: Boolean(opts.keepalive),
    });
    if (!res.ok) return; // keep them; the next report or load tries again
    const body = (await res.json().catch(() => null)) as { ids?: number[] } | null;
    writeJson(PENDING_KEY, readJson<PendingEvent[]>(PENDING_KEY, []).slice(events.length));
    if (body?.ids?.length) {
      const ids = readJson<{ id: number; t: number }[]>(ERROR_IDS_KEY, []);
      const now = Date.now();
      const next = [...ids, ...body.ids.map((id) => ({ id, t: now }))].filter((x) => now - x.t < TRAIL_MAX_AGE_MS);
      writeJson(ERROR_IDS_KEY, next.slice(-20));
    }
  } catch {
    /* offline, server down: keep them */
  } finally {
    flushing = false;
  }
}

/** Error-log ids saved from this tab in the last 10 minutes (for a comment). */
export function recentErrorIds(): number[] {
  const now = Date.now();
  const ids = readJson<{ id: number; t: number }[]>(ERROR_IDS_KEY, [])
    .filter((x) => now - x.t < TRAIL_MAX_AGE_MS)
    .map((x) => x.id);
  return Array.from(new Set(ids));
}

/** What a comment carries: the whole trail, device facts and recent error ids. */
export function commentContext(): Record<string, unknown> {
  try {
    return { trail: getTrail(), device: deviceFacts(), error_ids: recentErrorIds() };
  } catch {
    return {};
  }
}

// ─── Request hook (apiFetch and apiclient) ─────────────────────────────────

/**
 * Wraps one call to our server: a trail step for every call, and an event
 * for the failures that matter (5xx, 401, 403, 409, timeouts, no answer),
 * with the server's own explanation when it gave one.
 */
export async function trackRequest(
  url: string,
  method: string,
  run: () => Promise<Response>,
  source: "app" | "schedule" = "app",
): Promise<Response> {
  const started = Date.now();
  const path = pathOnly(url);
  const verb = (method || "GET").toUpperCase();
  let res: Response;
  try {
    res = await run();
  } catch (err) {
    try {
      const ms = Date.now() - started;
      const aborted = err instanceof DOMException && err.name === "AbortError";
      addStep({ type: "request", label: `${verb} ${path} ${aborted ? "cancelled" : "no answer"}${verb === "GET" ? "" : " (not saved)"}`, ms, source });
      // A cancelled GET is usually a page moving on; a cancelled save is not.
      if (!isQuietUrl(path) && (!aborted || verb !== "GET")) {
        reportEvent({
          kind: "request_failed",
          source,
          message: `${verb} ${path} ${aborted ? "timed out or was cancelled" : "got no answer"}`,
          detail: { method: verb, route: path, ms, error: scrubText(String(err), 300), online: navigator.onLine },
        });
      }
    } catch {
      /* ignore */
    }
    throw err;
  }
  try {
    const ms = Date.now() - started;
    if (!isQuietUrl(path)) {
      addStep({ type: "request", label: requestLabel(verb, path, res.status), status: res.status, ms, source });
      if (isLoggableStatus(res.status)) {
        void res
          .clone()
          .json()
          .catch(() => null)
          .then((body: { detail?: unknown } | null) => {
            const detail = body && typeof body.detail === "string" ? body.detail : undefined;
            reportEvent({
              kind: "request_failed",
              source,
              message: `${verb} ${path} ${res.status}${detail ? `: ${detail}` : ""}`,
              detail: { method: verb, route: path, status: res.status, ms, server_detail: detail ? scrubText(detail, 300) : undefined },
            });
          });
      }
    }
  } catch {
    /* ignore */
  }
  return res;
}

// ─── Page watchers: errors, clicks, navigation, freezes, the last visit ────

/** Errors that are noise, or are handled elsewhere. */
export function isIgnorableError(message: string): boolean {
  return (
    !message ||
    message === "Script error." || // another origin's script; no details
    /ResizeObserver loop/i.test(message) ||
    /Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module/i.test(message) // lazyWithReload reloads these
  );
}

export function isChunkLoadErrorMessage(message: string): boolean {
  return /Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module/i.test(message || "");
}

export function errorDetail(err: unknown): Record<string, unknown> {
  try {
    if (err instanceof Error) {
      return { error_type: err.name, stack: scrubText(err.stack || "", 4000) };
    }
    return { error_type: typeof err };
  } catch {
    return {};
  }
}

let started = false;

/** Freeze check: a 1s tick that arrives 5s+ late while the page is on screen. */
export function freezeGap(lastTick: number, now: number, wasVisible: boolean, isVisible: boolean): number | null {
  const gap = now - lastTick - 1000;
  // Over a minute is a laptop asleep, not a freeze.
  if (!wasVisible || !isVisible || gap < 5000 || gap > 60000) return null;
  return gap;
}

/**
 * Start watching. Called once from AppWrapper with the router, so page
 * changes go in the trail without this module importing the router.
 */
export function startEventLog(router?: { subscribe: (fn: (state: { location: { pathname: string } }) => void) => unknown; state: { location: { pathname: string } } }): void {
  if (started || typeof window === "undefined") return;
  started = true;
  try {
    // The last visit in this tab ended while on screen, without the page
    // being hidden or closed: the browser tab crashed or was killed.
    const alive = readJson<{ page: string; t: number } | null>(ALIVE_KEY, null);
    if (alive && Date.now() - alive.t < 6 * 3600 * 1000) {
      reportEvent({
        kind: "previous_visit",
        message: "The last visit in this tab ended suddenly while on screen (the tab crashed or was closed by the browser)",
        page: alive.page,
        detail: { ended_near: new Date(alive.t).toISOString() },
      });
    }
    const markAlive = () => writeJson(ALIVE_KEY, { page: currentPage(), t: Date.now() });
    const clearAlive = () => {
      try {
        window.sessionStorage.removeItem(ALIVE_KEY);
      } catch {
        /* ignore */
      }
    };
    if (document.visibilityState === "visible") markAlive();
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") markAlive();
      else {
        clearAlive();
        void flushEvents({ keepalive: true });
      }
    });
    window.addEventListener("pagehide", () => {
      clearAlive();
      void flushEvents({ keepalive: true });
    });
    window.setInterval(() => {
      if (document.visibilityState === "visible") markAlive();
    }, 30000);

    window.addEventListener("error", (e: ErrorEvent) => {
      const message = e.message || String(e.error || "");
      if (isIgnorableError(message)) return;
      reportEvent({ kind: "error", message, detail: { ...errorDetail(e.error), file: pathOnly(e.filename), line: e.lineno, col: e.colno } });
    });
    window.addEventListener("unhandledrejection", (e: PromiseRejectionEvent) => {
      const reason = e.reason;
      const message = reason instanceof Error ? reason.message : String(reason ?? "");
      if (isIgnorableError(message)) return;
      reportEvent({ kind: "error", message: `Unhandled: ${message}`, detail: errorDetail(reason) });
    });

    // Clicks, tabs, menus, dialogs, picks, ticks, fields, drag and drop and
    // pop-ups, on every page and in every same-origin frame (actionTrail.ts).
    startActionTrail(window, (a) => addStep({ type: actionStepType(a.kind), label: a.label }));

    if (router) {
      let lastPath = router.state.location.pathname;
      addStep({ type: "page", label: `Opened ${pathOnly(lastPath)}`, page: lastPath });
      router.subscribe((state) => {
        const p = state.location.pathname;
        if (p !== lastPath) {
          lastPath = p;
          addStep({ type: "page", label: `Opened ${pathOnly(p)}`, page: p });
        }
      });
    }

    let lastTick = Date.now();
    let lastVisible = document.visibilityState === "visible";
    window.setInterval(() => {
      const now = Date.now();
      const visible = document.visibilityState === "visible";
      const gap = freezeGap(lastTick, now, lastVisible, visible);
      if (gap !== null) {
        reportEvent({ kind: "freeze", message: `The page stopped responding for ${Math.round(gap / 1000)}s`, detail: { gap_ms: gap } });
      }
      lastTick = now;
      lastVisible = visible;
    }, 1000);

    // Anything a previous load couldn't send (a crash, then a reload).
    window.setTimeout(() => void flushEvents(), 3000);
  } catch {
    /* never break the app */
  }
}

/** lazyWithReload is about to reload an old tab onto the new version. */
export function noteReloadAfterDeploy(): void {
  reportEvent({
    kind: "reload_after_deploy",
    message: "An old tab reloaded itself to pick up the new version",
  });
}
