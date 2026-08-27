import { useRef, useState } from "react";
import { MessageSquarePlus, X, Camera, Eraser, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { apiFetch } from "utils/apiFetch";

// Floating "suggest a feature" button, present on every page through Layout.
// Deliberately NOT its own sidebar tab (considered and dropped): a sidebar
// entry competes for space with real work tabs for something used
// occasionally and never as a destination in itself. A floating button that
// travels with whatever page you're already on is the closer fit, and lets
// a screenshot of THAT page be attached in the same breath as the report.

const MAX_MESSAGE = 4000;

/** Freehand red-pen annotation directly onto the captured canvas -- no
 *  separate overlay layer, so `canvas.toDataURL()` on submit already IS
 *  the final annotated image. Coordinates are mapped from the canvas's
 *  on-screen (CSS) size to its internal pixel size, since the preview is
 *  shown scaled down from a full-page capture. */
function useCanvasAnnotate(canvasRef: React.RefObject<HTMLCanvasElement | null>) {
  const drawing = useRef(false);

  const posFromEvent = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return null;
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    return { x: (e.clientX - rect.left) * scaleX, y: (e.clientY - rect.top) * scaleY };
  };

  const onPointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    const pos = posFromEvent(e);
    if (!canvas || !pos) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    drawing.current = true;
    ctx.strokeStyle = "#dc2626";
    ctx.lineWidth = Math.max(2, canvas.width / 260);
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.beginPath();
    ctx.moveTo(pos.x, pos.y);
    canvas.setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!drawing.current) return;
    const canvas = canvasRef.current;
    const pos = posFromEvent(e);
    const ctx = canvas?.getContext("2d");
    if (!ctx || !pos) return;
    ctx.lineTo(pos.x, pos.y);
    ctx.stroke();
  };
  const onPointerUp = () => { drawing.current = false; };

  return { onPointerDown, onPointerMove, onPointerUp, onPointerLeave: onPointerUp };
}

export default function FeedbackWidget() {
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [capturing, setCapturing] = useState(false);
  const [hasShot, setHasShot] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const annotate = useCanvasAnnotate(canvasRef);

  const reset = () => {
    setMessage("");
    setHasShot(false);
    const canvas = canvasRef.current;
    if (canvas) canvas.getContext("2d")?.clearRect(0, 0, canvas.width, canvas.height);
  };

  const close = () => { if (!submitting) { setOpen(false); reset(); } };

  const captureScreenshot = async () => {
    setCapturing(true);
    try {
      const html2canvas = (await import("html2canvas")).default;
      const shot = await html2canvas(document.body, {
        // Never screenshot the widget capturing the screenshot.
        ignoreElements: (el) => el.hasAttribute("data-feedback-widget"),
        backgroundColor: null,
        scale: Math.min(1.5, window.devicePixelRatio || 1),
        useCORS: true,
        logging: false,
      });
      const canvas = canvasRef.current;
      if (!canvas) return;
      canvas.width = shot.width;
      canvas.height = shot.height;
      canvas.getContext("2d")?.drawImage(shot, 0, 0);
      setHasShot(true);
    } catch {
      toast.error("Couldn't capture a screenshot — you can still send your note without one.");
    } finally {
      setCapturing(false);
    }
  };

  const submit = async () => {
    const trimmed = message.trim();
    if (!trimmed) { toast.error("Say a bit about what you'd want."); return; }
    setSubmitting(true);
    try {
      const screenshot = hasShot && canvasRef.current ? canvasRef.current.toDataURL("image/png") : null;
      const res = await apiFetch("/api/feedback", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: trimmed,
          screenshot,
          page_path: window.location.pathname + window.location.search,
        }),
      });
      if (!res.ok) throw new Error(String(res.status));
      toast.success("Thanks — sent to the team.");
      setOpen(false);
      reset();
    } catch {
      toast.error("Couldn't send that — try again in a moment.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div data-feedback-widget className="fixed bottom-6 right-6 z-50 flex flex-col items-end gap-3">
      {open && (
        <div className="flex w-[380px] max-w-[calc(100vw-3rem)] flex-col overflow-hidden rounded-2xl border border-stone-200 bg-white shadow-2xl">
          <div className="flex items-center justify-between border-b border-stone-100 px-4 py-3">
            <p className="text-sm font-semibold text-stone-800" style={{ fontFamily: "Georgia, serif" }}>
              Suggest a feature
            </p>
            <button onClick={close} className="rounded-md p-1 text-stone-400 hover:bg-stone-100 hover:text-stone-700" aria-label="Close">
              <X size={16} />
            </button>
          </div>

          <div className="flex flex-col gap-3 px-4 py-3">
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value.slice(0, MAX_MESSAGE))}
              placeholder="What would help? What's missing or broken?"
              rows={4}
              className="w-full resize-none rounded-lg border border-stone-200 px-3 py-2 text-sm text-stone-800 outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
            />

            {!hasShot ? (
              <button
                type="button"
                onClick={captureScreenshot}
                disabled={capturing}
                className="flex items-center justify-center gap-2 rounded-lg border border-dashed border-stone-300 py-2.5 text-xs font-medium text-stone-500 hover:border-emerald-400 hover:text-emerald-700 disabled:opacity-60"
              >
                {capturing ? <Loader2 size={14} className="animate-spin" /> : <Camera size={14} />}
                {capturing ? "Capturing…" : "Attach a screenshot of this page"}
              </button>
            ) : (
              <div className="flex flex-col gap-1.5">
                <p className="text-[11px] text-stone-400">Draw on it to point something out.</p>
                <canvas
                  ref={canvasRef}
                  className="w-full touch-none rounded-lg border border-stone-200"
                  style={{ maxHeight: 220, objectFit: "contain", cursor: "crosshair" }}
                  onPointerDown={annotate.onPointerDown}
                  onPointerMove={annotate.onPointerMove}
                  onPointerUp={annotate.onPointerUp}
                  onPointerLeave={annotate.onPointerLeave}
                />
                <button
                  type="button"
                  onClick={() => { setHasShot(false); }}
                  className="flex w-fit items-center gap-1.5 text-[11px] font-medium text-stone-400 hover:text-red-600"
                >
                  <Eraser size={11} /> Remove screenshot
                </button>
              </div>
            )}
          </div>

          <div className="flex items-center justify-end gap-2 border-t border-stone-100 px-4 py-3">
            <button
              onClick={close}
              disabled={submitting}
              className="rounded-lg px-3 py-1.5 text-xs font-medium text-stone-500 hover:bg-stone-100"
            >
              Cancel
            </button>
            <button
              onClick={submit}
              disabled={submitting || !message.trim()}
              className="flex items-center gap-1.5 rounded-lg bg-emerald-700 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-emerald-800 disabled:opacity-50"
            >
              {submitting && <Loader2 size={12} className="animate-spin" />}
              Send
            </button>
          </div>
        </div>
      )}

      <button
        onClick={() => setOpen((v) => !v)}
        className="flex h-12 w-12 items-center justify-center rounded-full bg-emerald-700 text-white shadow-lg shadow-emerald-900/20 transition-transform hover:scale-105 hover:bg-emerald-800"
        aria-label="Suggest a feature"
        title="Suggest a feature"
      >
        {open ? <X size={20} /> : <MessageSquarePlus size={20} />}
      </button>
    </div>
  );
}
