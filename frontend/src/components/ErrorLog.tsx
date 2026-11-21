import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle, ChevronDown, ChevronRight, Clock, Loader2, Monitor, Navigation, Pencil, RefreshCw,
} from "components/icons";
import { apiFetch } from "utils/apiFetch";

/**
 * The owner's view of the error log (backend/app/apis/app_events) and of the
 * "last minute" trail attached to a comment. Owner only: the Comments page
 * shows these to a super_admin, and the server refuses everyone else.
 *
 * Kept deliberately small, a tab on the Comments page rather than a new page
 * (two dashboard rebuilds taught us to grow a view only once it earns it).
 */

export interface TrailStep {
  t: string;
  type: string;
  label: string;
  page?: string;
  status?: number;
  ms?: number;
  source?: string;
}

interface EventRow {
  id: number;
  created_at: string;
  occurred_at?: string | null;
  kind: string;
  source: string;
  user_name?: string | null;
  role?: string | null;
  page?: string | null;
  message?: string | null;
  detail?: Record<string, unknown> | null;
  trail?: TrailStep[] | null;
  user_agent?: string | null;
}

interface EventGroup {
  kind: string;
  message?: string | null;
  count: number;
  people: string[];
  pages: string[];
  first_at: string;
  last_at: string;
}

interface CommentContext {
  trail?: TrailStep[];
  device?: Record<string, unknown>;
  error_ids?: number[];
}

/** In words, for the kinds the log stores. */
export const KIND_LABEL: Record<string, string> = {
  crash: "Page crashed",
  error: "Script error",
  request_failed: "Request failed",
  stuck: "Stuck loading",
  freeze: "Page froze",
  blank: "Showed nothing",
  reload_after_deploy: "Reloaded for new version",
  previous_visit: "Tab ended suddenly",
  save_blocked: "Save blocked",
  save_conflict: "Change dropped in merge",
  server_error: "Server error",
  slow_request: "Slow request",
};

const KIND_TONE: Record<string, string> = {
  crash: "bg-rose-50 text-rose-700",
  server_error: "bg-rose-50 text-rose-700",
  previous_visit: "bg-rose-50 text-rose-700",
  save_conflict: "bg-rose-50 text-rose-700",
  save_blocked: "bg-amber-50 text-amber-700",
  error: "bg-amber-50 text-amber-700",
  request_failed: "bg-amber-50 text-amber-700",
  stuck: "bg-amber-50 text-amber-700",
  freeze: "bg-amber-50 text-amber-700",
  blank: "bg-amber-50 text-amber-700",
  slow_request: "bg-stone-100 text-stone-600",
  reload_after_deploy: "bg-stone-100 text-stone-600",
};

const TIME_FMT = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/Chicago",
  hour: "numeric",
  minute: "2-digit",
  second: "2-digit",
  hour12: true,
});
const DATE_TIME_FMT = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/Chicago",
  month: "numeric",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
  hour12: true,
});

/** 9:04:12 PM (Central). */
export function clockTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : TIME_FMT.format(d);
}

/** 11/16, 9:04 PM CT. */
export function whenCT(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : `${DATE_TIME_FMT.format(d)} CT`;
}

/** A short device name from a user agent: "iPhone Safari", "Mac Chrome". */
export function deviceName(ua?: string | null): string {
  if (!ua) return "";
  const os = /iPad/.test(ua) ? "iPad" : /iPhone/.test(ua) ? "iPhone" : /Android/.test(ua) ? "Android" : /Mac OS X/.test(ua) ? "Mac" : /Windows/.test(ua) ? "Windows" : "";
  const browser = /Edg\//.test(ua) ? "Edge" : /CriOS|Chrome\//.test(ua) ? "Chrome" : /FxiOS|Firefox\//.test(ua) ? "Firefox" : /Safari\//.test(ua) ? "Safari" : "";
  return [os, browser].filter(Boolean).join(" ");
}

function stepTone(step: TrailStep): string {
  if (step.type === "error") return "text-rose-700";
  if (typeof step.status === "number" && (step.status >= 400 || step.status === 0)) return "text-amber-700";
  return "text-stone-700";
}

function StepIcon({ type }: { type: string }) {
  const cls = "h-3.5 w-3.5 flex-none";
  if (type === "error") return <AlertTriangle className={`${cls} text-rose-500`} />;
  if (type === "page") return <Monitor className={`${cls} text-stone-400`} />;
  if (type === "click") return <Navigation className={`${cls} text-stone-400`} />;
  if (type === "action") return <Pencil className={`${cls} text-stone-400`} />;
  if (type === "request" || type === "schedule") return <RefreshCw className={`${cls} text-stone-400`} />;
  return <Clock className={`${cls} text-stone-400`} />;
}

/** The steps, oldest first, newest at the bottom (what happened just before). */
export function TrailTimeline({ steps }: { steps: TrailStep[] }) {
  if (!steps.length) return <p className="text-xs text-stone-400">No steps were recorded.</p>;
  return (
    <ol className="space-y-1">
      {steps.map((s, i) => (
        <li key={`${s.t}-${i}`} className="flex items-start gap-2 text-xs">
          <span className="w-[74px] flex-none font-mono text-[11px] tabular-nums text-stone-400">{clockTime(s.t)}</span>
          <StepIcon type={s.type} />
          <span className={`min-w-0 break-words ${stepTone(s)}`}>
            {s.label}
            {typeof s.ms === "number" && s.ms >= 1000 && <span className="text-stone-400"> · {(s.ms / 1000).toFixed(1)}s</span>}
          </span>
        </li>
      ))}
    </ol>
  );
}

function Facts({ facts }: { facts: Record<string, unknown> }) {
  const bits: string[] = [];
  if (facts.screen) bits.push(`Screen ${facts.screen}`);
  if (facts.online === false) bits.push("Offline");
  if (typeof facts.tab_open_s === "number") bits.push(`Tab open ${Math.round(Number(facts.tab_open_s) / 60)} min`);
  if (typeof facts.token_expires_in_s === "number") {
    const s = Number(facts.token_expires_in_s);
    bits.push(s <= 0 ? "Sign-in had expired" : `Sign-in good for ${Math.round(s / 60)} more min`);
  }
  if (facts.build) bits.push(`Version ${String(facts.build).replace(/^index-|\.js$/g, "")}`);
  if (!bits.length) return null;
  return <p className="text-[11px] text-stone-500">{bits.join(" · ")}</p>;
}

/** One error, collapsed to a line; open for the details and its trail. */
function EventItem({ ev, defaultOpen = false }: { ev: EventRow; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const detail = ev.detail || {};
  const stack = typeof detail.stack === "string" ? detail.stack : "";
  return (
    <div className="border-b border-stone-100 last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-start gap-2 px-4 py-3 text-left hover:bg-stone-50 sm:px-5"
        aria-expanded={open}
      >
        {open ? <ChevronDown className="mt-0.5 h-4 w-4 flex-none text-stone-400" /> : <ChevronRight className="mt-0.5 h-4 w-4 flex-none text-stone-400" />}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${KIND_TONE[ev.kind] ?? "bg-stone-100 text-stone-600"}`}>
              {KIND_LABEL[ev.kind] ?? ev.kind}
            </span>
            {ev.source === "schedule" && <span className="text-[11px] text-stone-400">in the schedule</span>}
            <span className="text-[11px] text-stone-400">{whenCT(ev.occurred_at || ev.created_at)}</span>
          </div>
          <p className="mt-1 break-words text-sm text-stone-800">{ev.message}</p>
          <p className="mt-0.5 text-xs text-stone-500">
            {[ev.user_name, ev.role, ev.page, deviceName(ev.user_agent)].filter(Boolean).join(" · ")}
          </p>
        </div>
      </button>
      {open && (
        <div className="space-y-3 px-4 pb-4 pl-10 sm:px-5 sm:pl-11">
          <Facts facts={detail} />
          {typeof detail.server_detail === "string" && (
            <p className="text-xs text-stone-600"><span className="font-medium">Server said:</span> {detail.server_detail}</p>
          )}
          {ev.trail && ev.trail.length > 0 && (
            <div>
              <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-stone-400">What happened before</p>
              <TrailTimeline steps={ev.trail} />
            </div>
          )}
          {stack && (
            <details className="text-xs">
              <summary className="cursor-pointer text-stone-500">Technical details</summary>
              <pre className="mt-1 max-h-60 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-stone-50 p-2 font-mono text-[11px] text-stone-600">{stack}</pre>
            </details>
          )}
        </div>
      )}
    </div>
  );
}

/** "What happened before this" under a comment (owner only). */
export function CommentTrail({ id }: { id: number }) {
  const [open, setOpen] = useState(false);
  const [ctx, setCtx] = useState<CommentContext | null>(null);
  const [errors, setErrors] = useState<EventRow[]>([]);
  const [failed, setFailed] = useState(false);

  // Loaded once, the first time it's opened. The linked errors are fetched
  // before any state is set, so a re-render can't cancel that second call.
  const loaded = useRef(false);
  useEffect(() => {
    if (!open || loaded.current) return;
    let unmounted = false;
    (async () => {
      try {
        const res = await apiFetch(`/api/feedback/${id}/context`);
        if (!res.ok) throw new Error(String(res.status));
        const data = (await res.json()) as CommentContext;
        let linked: EventRow[] = [];
        if (data.error_ids?.length) {
          const r = await apiFetch(`/api/app-events?ids=${data.error_ids.join(",")}`);
          if (r.ok) linked = (await r.json()) as EventRow[];
        }
        if (unmounted) return;
        loaded.current = true;
        setErrors(linked);
        setCtx(data);
      } catch {
        if (!unmounted) setFailed(true);
      }
    })();
    return () => {
      unmounted = true;
    };
  }, [open, id]);

  return (
    <div className="mt-2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1 rounded-full border border-stone-200 px-2 py-1.5 text-[11px] font-medium text-stone-500 hover:border-emerald-300 hover:text-emerald-700 sm:py-0.5"
        aria-expanded={open}
      >
        {open ? <ChevronDown size={11} /> : <ChevronRight size={11} />} What happened before this
      </button>
      {open && (
        <div className="mt-2 space-y-3 rounded-lg border border-stone-200 bg-stone-50/60 p-3">
          {failed ? (
            <p className="text-xs text-stone-500">Couldn't load the steps for this comment.</p>
          ) : !ctx ? (
            <p className="flex items-center gap-2 text-xs text-stone-400"><Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading</p>
          ) : (
            <>
              {ctx.device && <Facts facts={ctx.device} />}
              {errors.length > 0 && (
                <div className="overflow-hidden rounded-lg border border-rose-100 bg-white">
                  {errors.map((ev) => <EventItem key={ev.id} ev={ev} />)}
                </div>
              )}
              <TrailTimeline steps={ctx.trail || []} />
            </>
          )}
        </div>
      )}
    </div>
  );
}

/** The Errors tab: repeats grouped (last 7 days), then every error, newest first. */
export function ErrorsPanel() {
  const [groups, setGroups] = useState<EventGroup[] | null>(null);
  const [events, setEvents] = useState<EventRow[]>([]);
  const [more, setMore] = useState(true);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const loadPage = async (reset: boolean, msg: string | null) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: "50" });
      const last = reset ? undefined : events[events.length - 1];
      if (last) params.set("before_id", String(last.id));
      if (msg) params.set("message", msg);
      const res = await apiFetch(`/api/app-events?${params.toString()}`);
      if (!res.ok) throw new Error(String(res.status));
      const page = (await res.json()) as EventRow[];
      setEvents((prev) => (reset ? page : [...prev, ...page]));
      setMore(page.length === 50);
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void (async () => {
      try {
        const res = await apiFetch("/api/app-events/summary?days=7");
        if (!res.ok) throw new Error(String(res.status));
        setGroups((await res.json()) as EventGroup[]);
      } catch {
        setFailed(true);
      }
    })();
    void loadPage(true, null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const pick = (msg: string | null) => {
    setMessage(msg);
    void loadPage(true, msg);
  };

  if (failed && !groups && !events.length) {
    return <p className="px-5 py-8 text-center text-sm text-stone-400">Couldn't load the error log.</p>;
  }

  return (
    <div className="space-y-4">
      <section className="overflow-hidden rounded-xl border border-stone-200 bg-white">
        <h2 className="border-b border-stone-100 px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-stone-500 sm:px-5">
          Last 7 days
        </h2>
        {groups === null ? (
          <p className="px-5 py-6 text-center text-sm text-stone-400">Loading…</p>
        ) : groups.length === 0 ? (
          <p className="px-5 py-6 text-center text-sm text-stone-400">No errors in the last 7 days.</p>
        ) : (
          groups.map((g, i) => {
            const active = message !== null && message === (g.message ?? "");
            return (
              <button
                key={`${g.kind}-${i}`}
                type="button"
                onClick={() => pick(active ? null : g.message ?? "")}
                className={`flex w-full items-start gap-3 border-b border-stone-100 px-4 py-2.5 text-left last:border-b-0 sm:px-5 ${active ? "bg-emerald-50" : "hover:bg-stone-50"}`}
              >
                <span className="mt-0.5 min-w-[2.5rem] rounded-full bg-stone-100 px-2 py-0.5 text-center text-[11px] font-semibold tabular-nums text-stone-600">
                  {g.count}×
                </span>
                <div className="min-w-0 flex-1">
                  <p className="break-words text-sm text-stone-800">
                    <span className="font-medium">{KIND_LABEL[g.kind] ?? g.kind}:</span> {g.message}
                  </p>
                  <p className="mt-0.5 text-xs text-stone-500">
                    {[g.people.join(", "), `last ${whenCT(g.last_at)}`].filter(Boolean).join(" · ")}
                  </p>
                </div>
              </button>
            );
          })
        )}
      </section>

      <section className="overflow-hidden rounded-xl border border-stone-200 bg-white">
        <div className="flex items-center justify-between border-b border-stone-100 px-4 py-2.5 sm:px-5">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-stone-500">
            {message !== null ? "Just this error" : "Every error, newest first"}
          </h2>
          {message !== null && (
            <button type="button" onClick={() => pick(null)} className="text-xs font-medium text-emerald-700 hover:underline">
              Show all
            </button>
          )}
        </div>
        {events.length === 0 && !loading ? (
          <p className="px-5 py-6 text-center text-sm text-stone-400">Nothing logged yet.</p>
        ) : (
          events.map((ev) => <EventItem key={ev.id} ev={ev} />)
        )}
        {more && events.length > 0 && (
          <div className="border-t border-stone-100 p-3 text-center">
            <button
              type="button"
              onClick={() => void loadPage(false, message)}
              disabled={loading}
              className="inline-flex min-h-[40px] items-center gap-2 rounded-lg border border-stone-200 px-4 text-sm font-medium text-stone-600 hover:bg-stone-50 disabled:opacity-60"
            >
              {loading && <Loader2 className="h-4 w-4 animate-spin" />} Show more
            </button>
          </div>
        )}
      </section>
    </div>
  );
}
