/**
 * Errors and server calls from inside the Install Schedule, for the error
 * log and the "last minute" trail (utils/eventLog.ts).
 *
 * The schedule is its own page (scheduler/review_template.html) in a srcDoc
 * frame, with its own window: the app's error handlers never see its
 * errors, and its saves don't go through apiFetch. So the app adds a small
 * script to the very top of the page's <head> as it hands the HTML over
 * (`withFrameWatch`). Being first means it is listening before the
 * schedule's own scripts start, so a crash while the board is starting up
 * (a blank schedule, like Comment #39) is caught too. Because the app adds
 * it, the schedule template is unchanged and needs no publish.
 *
 * The script only reports: script errors, each /api call's method, path
 * (no query string), status and time, and what was done on the page
 * (utils/actionTrail.ts, injected as its own source: buttons, dialogs,
 * picks, drag and drop, the pop-ups the schedule shows and their answers,
 * like "Cannot make this change"). Never a body, header, token or anything
 * typed. Because the app injects it, it covers the live page as soon as the
 * app deploys, with no schedule publish. It
 * posts to the parent, which checks the message came from one of its own
 * frames (`handleFrameMessage`), scrubs it again and logs it.
 */
import { startActionTrail } from "utils/actionTrail";
import { actionStepType, addStep, isIgnorableError, isLoggableStatus, pathOnly, reportEvent, requestLabel, scrubText, type EventKind } from "utils/eventLog";

export const FRAME_STEP = "ll-frame-step";
export const FRAME_EVENT = "ll-frame-event";

const SCRIPT = `(function(){try{
var P=window.parent;if(!P||P===window)return;
function post(m){try{P.postMessage(m,'*');}catch(e){}}
function path(u){try{u=String(u&&u.url||u);var i=u.indexOf('://');if(i>=0){var s=u.indexOf('/',i+3);u=s>=0?u.slice(s):'/';}return u.split('#')[0].split('?')[0].slice(0,300);}catch(e){return '';}}
window.addEventListener('error',function(e){try{post({type:'${FRAME_EVENT}',kind:'error',message:String(e.message||''),stack:String(e.error&&e.error.stack||'').slice(0,4000),line:e.lineno,col:e.colno});}catch(x){}});
window.addEventListener('unhandledrejection',function(e){try{var r=e.reason;post({type:'${FRAME_EVENT}',kind:'error',message:'Unhandled: '+String(r&&r.message||r),stack:String(r&&r.stack||'').slice(0,4000)});}catch(x){}});
try{(${startActionTrail.toString()})(window,function(a){post({type:'${FRAME_STEP}',action:String(a.kind),label:String(a.label).slice(0,80)});});}catch(e){}
var F=window.fetch;if(!F)return;
window.fetch=function(input,init){var t=Date.now(),p=path(input),m=String(init&&init.method||input&&input.method||'GET').toUpperCase();
var watch=p.indexOf('/api/')===0;var q=F.apply(this,arguments);if(!watch)return q;
return q.then(function(r){try{var s={type:'${FRAME_STEP}',method:m,path:p,status:r.status,ms:Date.now()-t};
if(r.status>=400){r.clone().json().then(function(b){s.detail=b&&typeof b.detail==='string'?b.detail.slice(0,300):undefined;post(s);},function(){post(s);});}else{post(s);}}catch(x){}return r;},
function(err){try{post({type:'${FRAME_STEP}',method:m,path:p,status:0,ms:Date.now()-t,error:String(err&&err.name||err)});}catch(x){}throw err;});};
}catch(e){}})();`;

/** The schedule's HTML with the watcher first in <head>. */
export function withFrameWatch(html: string): string {
  try {
    const tag = `<script>${SCRIPT}</script>`;
    const m = /<head[^>]*>/i.exec(html);
    if (!m) return tag + html;
    const at = m.index + m[0].length;
    return html.slice(0, at) + tag + html.slice(at);
  } catch {
    return html;
  }
}

interface FrameStep {
  type: typeof FRAME_STEP;
  /** Something done on the page (actionTrail.ts kind) and its label. */
  action?: string;
  label?: string;
  method?: string;
  path?: string;
  status?: number;
  ms?: number;
  detail?: string;
  error?: string;
}

interface FrameEvent {
  type: typeof FRAME_EVENT;
  kind?: string;
  message?: string;
  stack?: string;
  line?: number;
  col?: number;
  /** Counts and reasons from the schedule's own reports (llReport). */
  detail?: Record<string, unknown>;
}

/** Kinds the schedule may report itself (review_template.html llReport);
 *  anything else from the frame is a plain script error. */
export const FRAME_KINDS: ReadonlySet<EventKind> = new Set<EventKind>(["error", "blank", "save_blocked", "save_conflict"]);

/** What the frame may say it did (actionTrail.ts TrailAction kinds). */
export const ACTION_KINDS: ReadonlySet<string> = new Set(["click", "tab", "menu", "pick", "toggle", "field", "dialog", "message", "ask", "drop", "submit", "save", "error"]);

/** The schedule's own detail, kept small and flat. */
export function frameDetail(detail: unknown): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  try {
    if (!detail || typeof detail !== "object") return out;
    for (const [k, v] of Object.entries(detail as Record<string, unknown>).slice(0, 30)) {
      if (v === null || typeof v === "number" || typeof v === "boolean") out[k.slice(0, 40)] = v;
      else if (typeof v === "string") out[k.slice(0, 40)] = scrubText(v, 200);
    }
  } catch {
    /* ignore */
  }
  return out;
}

/**
 * The schedule retries a 401 once with a fresh token (authFetch, since
 * #100), so a lone 401 followed by a success is normal. A 401 is only logged
 * if no call to the same address worked within 5 seconds.
 */
const pending401 = new Map<string, number>();
const RETRY_GRACE_MS = 5000;

function isOwnFrame(source: MessageEventSource | null): boolean {
  try {
    if (!source) return false;
    return Array.from(document.querySelectorAll("iframe")).some((f) => f.contentWindow === source);
  } catch {
    return false;
  }
}

/** Handle one message from a frame. Returns true when it was ours. */
export function handleFrameMessage(e: MessageEvent): boolean {
  try {
    const data = e.data as FrameStep | FrameEvent | null;
    if (!data || (data.type !== FRAME_STEP && data.type !== FRAME_EVENT)) return false;
    if (!isOwnFrame(e.source)) return true;

    if (data.type === FRAME_EVENT) {
      const message = scrubText(data.message || "", 1000);
      const kind = FRAME_KINDS.has(data.kind as EventKind) ? (data.kind as EventKind) : "error";
      if (kind === "error" && isIgnorableError(message)) return true;
      reportEvent({
        kind,
        source: "schedule",
        message,
        detail: { ...frameDetail(data.detail), stack: data.stack ? scrubText(data.stack, 4000) : undefined, line: data.line, col: data.col },
      });
      return true;
    }

    if (data.action) {
      const label = scrubText(String(data.label || ""), 80);
      if (label && ACTION_KINDS.has(data.action))
        addStep({ type: actionStepType(data.action), source: "schedule", label: `Schedule: ${label}` });
      return true;
    }

    const method = String(data.method || "GET").toUpperCase().slice(0, 10);
    const path = pathOnly(data.path);
    const status = Number(data.status) || 0;
    const ms = Number(data.ms) || 0;
    const key = `${method} ${path}`;
    addStep({
      type: "schedule",
      source: "schedule",
      label: `Schedule: ${status ? requestLabel(method, path, status) : `${key} ${data.error ? "no answer" : "?"}`}`,
      status,
      ms,
    });
    if (status > 0 && status < 400) {
      const t = pending401.get(key);
      if (t !== undefined) {
        window.clearTimeout(t);
        pending401.delete(key);
      }
      return true;
    }
    const detail = data.detail ? scrubText(data.detail, 300) : undefined;
    const report = () =>
      reportEvent({
        kind: "request_failed",
        source: "schedule",
        message: `${key} ${status || "got no answer"}${detail ? `: ${detail}` : ""}`,
        detail: { method, route: path, status, ms, server_detail: detail, error: data.error ? scrubText(data.error, 100) : undefined },
      });
    if (status === 401) {
      if (!pending401.has(key)) {
        pending401.set(
          key,
          window.setTimeout(() => {
            pending401.delete(key);
            report();
          }, RETRY_GRACE_MS),
        );
      }
    } else if (status === 0 || isLoggableStatus(status)) {
      report();
    }
    return true;
  } catch {
    return true;
  }
}
