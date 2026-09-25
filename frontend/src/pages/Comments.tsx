import { useEffect, useState } from "react";
import {
  MessageSquare, Check, Image as ImageIcon, X, ChevronDown, ChevronRight, Sparkles,
  CheckCircle2, AlertTriangle, HelpCircle, ShieldCheck, Clock, ExternalLink,
} from "components/icons";
import Layout from "components/Layout";
import { apiFetch } from "utils/apiFetch";
import { toast } from "sonner";

// Shared team list of what came in through the floating "Suggest a feature"
// button (FeedbackWidget.tsx) -- everyone signed in sees the same list and
// can check an item off; that flips it for everyone, not just the person
// who checked it. See backend/app/apis/feedback for the storage side.
//
// A daily Claude Code run reviews every open item and leaves a note on it:
// what it fixed (with a link to test), or why it needs a person. Answering
// that note here puts the item back in Claude's queue for the next run.

interface FeedbackRow {
  id: number;
  message: string;
  has_screenshot: boolean;
  page_path?: string | null;
  submitted_name?: string | null;
  status: string;
  created_at: string;
  claude_status?: string | null;
  claude_note?: string | null;
  claude_link?: string | null;
  claude_reviewed_at?: string | null;
  reply?: string | null;
  reply_name?: string | null;
  replied_at?: string | null;
}

type Filter = "all" | "needs_you" | "to_test" | "waiting";

const REVIEW_STYLES: Record<string, { label: string; icon: typeof Sparkles; tone: string }> = {
  fixed: { label: "Fixed — ready for you to test", icon: CheckCircle2, tone: "border-emerald-200 bg-emerald-50 text-emerald-800" },
  needs_approval: { label: "Needs your approval", icon: ShieldCheck, tone: "border-amber-200 bg-amber-50 text-amber-800" },
  needs_human: { label: "Too complex — needs a person", icon: AlertTriangle, tone: "border-rose-200 bg-rose-50 text-rose-800" },
  unclear: { label: "Unclear — needs more detail", icon: HelpCircle, tone: "border-amber-200 bg-amber-50 text-amber-800" },
  approved: { label: "Approved — Claude builds it next run", icon: Clock, tone: "border-stone-200 bg-stone-50 text-stone-700" },
  replied: { label: "Answered — Claude looks again next run", icon: Clock, tone: "border-stone-200 bg-stone-50 text-stone-700" },
};

const NEEDS_YOU = new Set(["needs_approval", "needs_human", "unclear"]);

function matchesFilter(row: FeedbackRow, filter: Filter): boolean {
  const cs = row.claude_status ?? "";
  if (filter === "needs_you") return NEEDS_YOU.has(cs);
  if (filter === "to_test") return cs === "fixed";
  if (filter === "waiting") return !cs || cs === "approved" || cs === "replied";
  return true;
}

function relativeTime(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const min = Math.floor(ms / 60000);
  if (min < 1) return "just now";
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  if (day < 30) return `${day}d ago`;
  return new Date(iso).toLocaleDateString();
}

function ScreenshotViewer({ id, onClose }: { id: number; onClose: () => void }) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    apiFetch(`/api/feedback/${id}/screenshot`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((data) => { if (alive) setSrc(data.screenshot); })
      .catch(() => { if (alive) setFailed(true); });
    return () => { alive = false; };
  }, [id]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-6 ll-overlay" onClick={onClose}>
      <div className="relative max-h-full max-w-4xl overflow-auto rounded-xl bg-white p-2 shadow-2xl ll-modal" onClick={(e) => e.stopPropagation()}>
        <button onClick={onClose} className="absolute right-3 top-3 rounded-full bg-white/90 p-1.5 text-stone-500 shadow hover:text-stone-800" aria-label="Close">
          <X size={16} />
        </button>
        {failed ? (
          <p className="p-8 text-sm text-stone-400">Couldn't load this screenshot.</p>
        ) : src ? (
          <img src={src} alt="Attached screenshot" className="max-h-[80vh] rounded-lg" />
        ) : (
          <div className="flex h-64 w-96 items-center justify-center text-sm text-stone-400">Loading…</div>
        )}
      </div>
    </div>
  );
}

function ClaudeReview({ row, onReply }: {
  row: FeedbackRow;
  onReply: (row: FeedbackRow, reply: string, approve: boolean) => Promise<boolean>;
}) {
  const [replying, setReplying] = useState(false);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);

  if (!row.claude_status) {
    if (row.status === "done") return null;
    return (
      <p className="mt-2 inline-flex items-center gap-1.5 text-[11px] text-stone-400">
        <Sparkles size={11} /> Waiting for Claude's daily review
      </p>
    );
  }

  const style = REVIEW_STYLES[row.claude_status] ?? REVIEW_STYLES.needs_human;
  const Icon = style.icon;
  const canAnswer = NEEDS_YOU.has(row.claude_status) && row.status !== "done";

  const send = async (approve: boolean) => {
    setSending(true);
    const ok = await onReply(row, text, approve);
    setSending(false);
    if (ok) { setReplying(false); setText(""); }
  };

  return (
    <div className={`mt-2.5 rounded-lg border px-3 py-2.5 ${style.tone}`}>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs font-semibold">
        <Sparkles size={12} className="opacity-70" />
        <span>Claude</span>
        <span className="inline-flex items-center gap-1 font-medium">
          <Icon size={12} /> {style.label}
        </span>
        {row.claude_reviewed_at && (
          <span className="font-normal opacity-60">· {relativeTime(row.claude_reviewed_at)}</span>
        )}
      </div>
      {row.claude_note && (
        <p className="mt-1.5 whitespace-pre-wrap text-[13px] leading-relaxed text-stone-700">{row.claude_note}</p>
      )}
      {row.claude_link && (
        <a
          href={row.claude_link}
          target="_blank"
          rel="noreferrer"
          className="mt-1.5 inline-flex items-center gap-1 text-xs font-medium underline underline-offset-2 hover:no-underline"
        >
          Open the change <ExternalLink size={11} />
        </a>
      )}
      {row.reply && (
        <p className="mt-2 border-t border-stone-300/60 pt-2 text-[13px] text-stone-600">
          <span className="font-medium text-stone-700">{row.reply_name || "Someone"} replied:</span> {row.reply}
        </p>
      )}

      {canAnswer && !replying && (
        <div className="mt-2 flex flex-wrap gap-2">
          {row.claude_status === "needs_approval" && (
            <button
              onClick={() => send(true)}
              disabled={sending}
              className="rounded-md bg-emerald-700 px-2.5 py-1 text-xs font-medium text-white hover:bg-emerald-800 disabled:opacity-50"
            >
              Approve plan
            </button>
          )}
          <button
            onClick={() => setReplying(true)}
            className="rounded-md border border-stone-300 bg-white px-2.5 py-1 text-xs font-medium text-stone-700 hover:border-stone-400"
          >
            Reply to Claude
          </button>
        </div>
      )}

      {replying && (
        <div className="mt-2">
          <textarea
            autoFocus
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={3}
            placeholder={row.claude_status === "unclear" ? "Add the detail Claude asked for…" : "Answer Claude, or tell it how to proceed…"}
            className="w-full resize-y rounded-md border border-stone-300 bg-white px-2.5 py-2 text-[13px] text-stone-800 focus:border-emerald-500 focus:outline-none"
          />
          <div className="mt-1.5 flex flex-wrap items-center gap-2">
            <button
              onClick={() => send(false)}
              disabled={sending || !text.trim()}
              className="rounded-md bg-emerald-700 px-2.5 py-1 text-xs font-medium text-white hover:bg-emerald-800 disabled:opacity-50"
            >
              Send
            </button>
            {row.claude_status === "needs_approval" && (
              <button
                onClick={() => send(true)}
                disabled={sending}
                className="rounded-md border border-emerald-600 bg-white px-2.5 py-1 text-xs font-medium text-emerald-700 hover:bg-emerald-50 disabled:opacity-50"
              >
                Send and approve
              </button>
            )}
            <button
              onClick={() => { setReplying(false); setText(""); }}
              className="px-1.5 py-1 text-xs text-stone-500 hover:text-stone-700"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function CommentRow({ row, onToggle, onViewScreenshot, onReply }: {
  row: FeedbackRow;
  onToggle: (row: FeedbackRow) => void;
  onViewScreenshot: (id: number) => void;
  onReply: (row: FeedbackRow, reply: string, approve: boolean) => Promise<boolean>;
}) {
  const done = row.status === "done";
  return (
    <div className="flex items-start gap-3 border-b border-stone-100 px-5 py-3.5 last:border-b-0">
      <button
        onClick={() => onToggle(row)}
        className={`mt-0.5 flex h-5 w-5 flex-none items-center justify-center rounded-md border transition-colors ${
          done ? "border-emerald-600 bg-emerald-600 text-white" : "border-stone-300 hover:border-emerald-500"
        }`}
        aria-label={done ? "Mark as not done" : "Mark as done"}
        title={done ? "Mark as not done" : "Mark as done"}
      >
        {done && <Check size={13} strokeWidth={3} />}
      </button>
      <div className="min-w-0 flex-1">
        <p className={`text-sm leading-relaxed ${done ? "text-stone-400 line-through" : "text-stone-800"}`}>
          {row.message}
        </p>
        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-stone-400">
          {row.submitted_name && <span className="font-medium text-stone-500">{row.submitted_name}</span>}
          <span>· {relativeTime(row.created_at)}</span>
          {row.page_path && (
            <span className="truncate rounded-full bg-stone-100 px-2 py-0.5 text-[11px] text-stone-500" title={row.page_path}>
              {row.page_path}
            </span>
          )}
          {row.has_screenshot && (
            <button
              onClick={() => onViewScreenshot(row.id)}
              className="inline-flex items-center gap-1 rounded-full border border-stone-200 px-2 py-0.5 text-[11px] font-medium text-stone-500 hover:border-emerald-300 hover:text-emerald-700"
            >
              <ImageIcon size={11} /> Screenshot
            </button>
          )}
        </div>
        <ClaudeReview row={row} onReply={onReply} />
      </div>
    </div>
  );
}

export default function Comments() {
  const [rows, setRows] = useState<FeedbackRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [showDone, setShowDone] = useState(false);
  const [viewingScreenshot, setViewingScreenshot] = useState<number | null>(null);
  const [filter, setFilter] = useState<Filter>("all");

  const load = () => {
    apiFetch("/api/feedback", { credentials: "include" })
      .then((r) => (r.ok ? r.json() : []))
      .then((data) => setRows(Array.isArray(data) ? data : []))
      .catch(() => toast.error("Couldn't load comments"))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // Someone else's checkmark should show up without a manual refresh --
    // refetching on focus is the cheap version of that, no polling loop.
    const onFocus = () => load();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, []);

  const toggle = async (row: FeedbackRow) => {
    const nextStatus = row.status === "done" ? "new" : "done";
    setRows((prev) => prev.map((r) => (r.id === row.id ? { ...r, status: nextStatus } : r)));
    try {
      const res = await apiFetch(`/api/feedback/${row.id}`, {
        method: "PUT",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: nextStatus }),
      });
      if (!res.ok) throw new Error(String(res.status));
    } catch {
      setRows((prev) => prev.map((r) => (r.id === row.id ? { ...r, status: row.status } : r)));
      toast.error("Couldn't update that — try again.");
    }
  };

  const reply = async (row: FeedbackRow, text: string, approve: boolean): Promise<boolean> => {
    try {
      const res = await apiFetch(`/api/feedback/${row.id}/reply`, {
        method: "PUT",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reply: text, approve }),
      });
      if (!res.ok) throw new Error(String(res.status));
      const updated: FeedbackRow = await res.json();
      setRows((prev) => prev.map((r) => (r.id === row.id ? updated : r)));
      toast.success(approve ? "Approved — Claude will build it on its next run." : "Sent — Claude will look again on its next run.");
      return true;
    } catch {
      toast.error("Couldn't send that — try again.");
      return false;
    }
  };

  const allOpen = rows.filter((r) => r.status !== "done");
  const open = allOpen.filter((r) => matchesFilter(r, filter));
  const done = rows.filter((r) => r.status === "done");
  const filters: { key: Filter; label: string }[] = [
    { key: "all", label: "All open" },
    { key: "needs_you", label: "Needs you" },
    { key: "to_test", label: "Ready to test" },
    { key: "waiting", label: "With Claude" },
  ];

  return (
    <Layout>
      <header className="border-b border-stone-200 px-4 sm:px-10 py-5">
        <h1 className="flex items-center gap-2 text-xl font-semibold text-stone-800" style={{ fontFamily: "'Sora', system-ui, sans-serif" }}>
          <MessageSquare size={18} className="text-emerald-700" />
          Comments
        </h1>
        <p className="mt-0.5 text-xs text-stone-500">
          Feature requests and notes sent in from around the app. Claude reviews open ones every morning — check one off once it's handled.
        </p>
      </header>

      <div className="mx-auto max-w-3xl px-6 py-6">
        {loading ? (
          <p className="py-12 text-center text-sm text-stone-400">Loading…</p>
        ) : rows.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-stone-200 py-16 text-center">
            <MessageSquare size={28} className="mb-3 text-stone-300" strokeWidth={1.5} />
            <p className="text-sm text-stone-500">Nothing sent in yet.</p>
            <p className="mt-1 max-w-xs text-xs text-stone-400">
              The floating button in the corner of any page sends a note straight here.
            </p>
          </div>
        ) : (
          <>
            <div className="mb-3 flex flex-wrap gap-1.5">
              {filters.map((f) => {
                const count = allOpen.filter((r) => matchesFilter(r, f.key)).length;
                const active = filter === f.key;
                return (
                  <button
                    key={f.key}
                    onClick={() => setFilter(f.key)}
                    className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                      active
                        ? "border-emerald-600 bg-emerald-50 text-emerald-800"
                        : "border-stone-200 bg-white text-stone-500 hover:border-stone-300 hover:text-stone-700"
                    }`}
                  >
                    {f.label}
                    <span className={`ml-1.5 ${active ? "text-emerald-600" : "text-stone-400"}`}>{count}</span>
                  </button>
                );
              })}
            </div>

            <div className="overflow-hidden rounded-xl border border-stone-200 bg-white">
              {open.length === 0 ? (
                <p className="px-5 py-8 text-center text-sm text-stone-400">
                  {filter === "all" ? "Nothing open — nice." : "Nothing here right now."}
                </p>
              ) : (
                open.map((row) => (
                  <CommentRow key={row.id} row={row} onToggle={toggle} onViewScreenshot={setViewingScreenshot} onReply={reply} />
                ))
              )}
            </div>

            {done.length > 0 && (
              <div className="mt-5">
                <button
                  onClick={() => setShowDone((v) => !v)}
                  className="flex items-center gap-1.5 text-xs font-medium text-stone-400 hover:text-stone-600"
                >
                  {showDone ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                  Completed ({done.length})
                </button>
                {showDone && (
                  <div className="mt-2 overflow-hidden rounded-xl border border-stone-200 bg-white">
                    {done.map((row) => (
                      <CommentRow key={row.id} row={row} onToggle={toggle} onViewScreenshot={setViewingScreenshot} onReply={reply} />
                    ))}
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>

      {viewingScreenshot != null && (
        <ScreenshotViewer id={viewingScreenshot} onClose={() => setViewingScreenshot(null)} />
      )}
    </Layout>
  );
}
