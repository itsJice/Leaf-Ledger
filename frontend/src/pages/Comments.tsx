import { useEffect, useState } from "react";
import { MessageSquare, Check, Image as ImageIcon, X, ChevronDown, ChevronRight } from "lucide-react";
import Layout from "components/Layout";
import { apiFetch } from "utils/apiFetch";
import { toast } from "sonner";

// Shared team list of what came in through the floating "Suggest a feature"
// button (FeedbackWidget.tsx) -- everyone signed in sees the same list and
// can check an item off; that flips it for everyone, not just the person
// who checked it. See backend/app/apis/feedback for the storage side.

interface FeedbackRow {
  id: number;
  message: string;
  has_screenshot: boolean;
  page_path?: string | null;
  submitted_name?: string | null;
  status: string;
  created_at: string;
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-6" onClick={onClose}>
      <div className="relative max-h-full max-w-4xl overflow-auto rounded-xl bg-white p-2 shadow-2xl" onClick={(e) => e.stopPropagation()}>
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

function CommentRow({ row, onToggle, onViewScreenshot }: {
  row: FeedbackRow;
  onToggle: (row: FeedbackRow) => void;
  onViewScreenshot: (id: number) => void;
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
      </div>
    </div>
  );
}

export default function Comments() {
  const [rows, setRows] = useState<FeedbackRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [showDone, setShowDone] = useState(false);
  const [viewingScreenshot, setViewingScreenshot] = useState<number | null>(null);

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

  const open = rows.filter((r) => r.status !== "done");
  const done = rows.filter((r) => r.status === "done");

  return (
    <Layout>
      <header className="border-b border-stone-200 px-10 py-5">
        <h1 className="flex items-center gap-2 text-xl font-semibold text-stone-800" style={{ fontFamily: "Georgia, serif" }}>
          <MessageSquare size={18} className="text-emerald-700" />
          Comments
        </h1>
        <p className="mt-0.5 text-xs text-stone-500">
          Feature requests and notes sent in from around the app — check one off once it's handled.
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
            <div className="overflow-hidden rounded-xl border border-stone-200 bg-white">
              {open.length === 0 ? (
                <p className="px-5 py-8 text-center text-sm text-stone-400">Nothing open — nice.</p>
              ) : (
                open.map((row) => (
                  <CommentRow key={row.id} row={row} onToggle={toggle} onViewScreenshot={setViewingScreenshot} />
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
                      <CommentRow key={row.id} row={row} onToggle={toggle} onViewScreenshot={setViewingScreenshot} />
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
