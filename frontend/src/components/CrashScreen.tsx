import { useState } from "react";
import { AlertTriangle, Check, Loader2, MessageSquarePlus, RefreshCw } from "components/icons";
import { commentContext } from "utils/eventLog";

interface Props {
  /** An old tab that can't load the new version's pages: say so plainly. */
  newVersion?: boolean;
}

/**
 * What people see when a page crashes, in place of the blank screen they used
 * to get. The crash itself is already in the error log (utils/eventLog.ts);
 * this lets them reload, or tell us what they were doing, with the "last
 * minute" trail attached to the comment.
 *
 * It can show outside every provider (the outermost error boundary), so it
 * uses plain fetch through a dynamic import of the auth module and its own
 * classes, not toasts or theme context.
 */
export function CrashScreen({ newVersion = false }: Props) {
  const [writing, setWriting] = useState(false);
  const [note, setNote] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent" | "failed">("idle");

  const send = async () => {
    const message = note.trim() || "The page crashed (no note).";
    setState("sending");
    try {
      const { auth } = await import("app/auth/auth");
      const header = await auth.getAuthHeaderValue();
      const res = await fetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(header ? { Authorization: header } : {}) },
        body: JSON.stringify({
          message: `Crash: ${message}`,
          page_path: window.location.pathname + window.location.search,
          context: commentContext(),
        }),
      });
      setState(res.ok ? "sent" : "failed");
    } catch {
      setState("failed");
    }
  };

  return (
    <div className="flex min-h-[100dvh] w-full items-center justify-center bg-stone-50 px-4 py-10" role="alert">
      <div className="w-full max-w-md rounded-2xl border border-stone-200 bg-white p-6 shadow-sm">
        <div className="flex items-start gap-3">
          <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-amber-50 text-amber-600">
            {newVersion ? <RefreshCw className="h-5 w-5" /> : <AlertTriangle className="h-5 w-5" />}
          </span>
          <div className="min-w-0">
            <h1 className="font-[Sora] text-lg font-semibold text-stone-900">
              {newVersion ? "A new version of the app is ready" : "Something went wrong"}
            </h1>
            <p className="mt-1 text-sm text-stone-600">
              {newVersion
                ? "Reload to pick it up. Nothing you saved is lost."
                : "We've saved the details so we can fix it. Reloading usually gets you going again."}
            </p>
          </div>
        </div>

        <div className="mt-5 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="inline-flex min-h-[40px] items-center gap-2 rounded-lg bg-emerald-700 px-4 text-sm font-semibold text-white hover:bg-emerald-800"
          >
            <RefreshCw className="h-4 w-4" /> Reload
          </button>
          {!newVersion && !writing && state !== "sent" && (
            <button
              type="button"
              onClick={() => setWriting(true)}
              className="inline-flex min-h-[40px] items-center gap-2 rounded-lg border border-stone-300 px-4 text-sm font-medium text-stone-700 hover:bg-stone-50"
            >
              <MessageSquarePlus className="h-4 w-4" /> Tell us what happened
            </button>
          )}
        </div>

        {writing && state !== "sent" && (
          <div className="mt-4" data-no-trail>
            <label htmlFor="crash-note" className="text-sm font-medium text-stone-700">
              What were you doing?
            </label>
            <textarea
              id="crash-note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={3}
              maxLength={2000}
              placeholder="For example: I moved a client to the 16th and pressed Save"
              className="mt-1 w-full rounded-lg border border-stone-300 bg-white p-2 text-base text-stone-900 placeholder:text-stone-400 focus:border-emerald-600 focus:outline-none"
            />
            <div className="mt-2 flex items-center gap-3">
              <button
                type="button"
                onClick={send}
                disabled={state === "sending"}
                className="inline-flex min-h-[40px] items-center gap-2 rounded-lg bg-stone-800 px-4 text-sm font-semibold text-white hover:bg-stone-900 disabled:opacity-60"
              >
                {state === "sending" && <Loader2 className="h-4 w-4 animate-spin" />} Send
              </button>
              {state === "failed" && (
                <span className="text-sm text-red-600">Couldn't send. Try again after reloading.</span>
              )}
            </div>
            <p className="mt-2 text-xs text-stone-500">Your last few steps in the app are attached so we can see what happened.</p>
          </div>
        )}

        {state === "sent" && (
          <p className="mt-4 flex items-center gap-2 text-sm text-emerald-700">
            <Check className="h-4 w-4" /> Sent to the team. Thank you.
          </p>
        )}
      </div>
    </div>
  );
}
