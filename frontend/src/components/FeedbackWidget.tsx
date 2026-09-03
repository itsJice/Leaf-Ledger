import { useRef, useState } from "react";
import { MessageSquarePlus, X, Camera, Eraser, Loader2, ImagePlus } from "lucide-react";
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

/** Canvas -> data URL that the server will actually accept.
 *
 *  MAX_SCREENSHOT_BYTES is 3,000,000 base64 characters and the endpoint
 *  answers 413 rather than trimming, so a submission that is too large loses
 *  the note along with the image. PNG is tried first because a UI screenshot
 *  stays sharp and small in it; a photograph does not, so it steps down
 *  through JPEG quality instead of failing. */
const MAX_SHOT_CHARS = 3_000_000;
function exportCanvas(canvas: HTMLCanvasElement): string | null {
  const png = canvas.toDataURL("image/png");
  if (png.length <= MAX_SHOT_CHARS) return png;
  for (const q of [0.9, 0.75, 0.6, 0.45]) {
    const jpg = canvas.toDataURL("image/jpeg", q);
    if (jpg.length <= MAX_SHOT_CHARS) return jpg;
  }
  return null;   // give up on the image rather than lose the note with it
}

export default function FeedbackWidget() {
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [capturing, setCapturing] = useState(false);
  const [hasShot, setHasShot] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const annotate = useCanvasAnnotate(canvasRef);

  const reset = () => {
    setMessage("");
    setHasShot(false);
    const canvas = canvasRef.current;
    if (canvas) canvas.getContext("2d")?.clearRect(0, 0, canvas.width, canvas.height);
  };

  const close = () => { if (!submitting) { setOpen(false); reset(); } };

  /** Draw any image source into the annotation canvas, scaled to fit.
   *
   *  The backend caps a submission at MAX_SCREENSHOT_BYTES of base64, which a
   *  page capture never approaches but a phone photo clears easily -- so a
   *  file the user picks is scaled down here rather than being rejected with
   *  a 413 after they have already typed their note. */
  const MAX_EDGE = 1800;
  const drawSource = (src: string) =>
    new Promise<void>((resolve, reject) => {
      const img = new Image();
      img.onload = () => {
        const canvas = canvasRef.current;
        if (!canvas) { reject(new Error("no canvas")); return; }
        const scale = Math.min(1, MAX_EDGE / Math.max(img.width, img.height));
        canvas.width = Math.round(img.width * scale);
        canvas.height = Math.round(img.height * scale);
        const ctx = canvas.getContext("2d");
        if (!ctx) { reject(new Error("no context")); return; }
        // A pasted PNG can carry transparency; flatten it so annotation ink
        // stays legible and the stored image looks like what was pasted.
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        setHasShot(true);
        resolve();
      };
      img.onerror = () => reject(new Error("decode failed"));
      img.src = src;
    });

  const readFile = async (file: File | null | undefined) => {
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      toast.error("That file isn't an image.");
      return;
    }
    try {
      const src: string = await new Promise((resolve, reject) => {
        const fr = new FileReader();
        fr.onload = () => resolve(String(fr.result));
        fr.onerror = () => reject(fr.error);
        fr.readAsDataURL(file);
      });
      await drawSource(src);
    } catch {
      toast.error("Couldn't read that image — try a PNG or JPG.");
    }
  };

  /** Cmd/Ctrl-V straight into the note. How people actually move a screenshot. */
  const onPaste = async (e: React.ClipboardEvent) => {
    const item = [...(e.clipboardData?.items || [])].find(i => i.type.startsWith("image/"));
    if (!item) return;                 // plain text paste: leave it to the textarea
    e.preventDefault();
    await readFile(item.getAsFile());
  };

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
      const screenshot = hasShot && canvasRef.current ? exportCanvas(canvasRef.current) : null;
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
    // onPaste sits on the whole widget, not just the textarea: the natural
    // move after copying a screenshot is to hit paste wherever the cursor
    // happens to be, and the panel is small enough that "anywhere in here"
    // is the honest target. A non-image paste falls through untouched.
    <div data-feedback-widget onPaste={onPaste}
         className="fixed bottom-6 right-6 z-50 flex flex-col items-end gap-3">
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

            {!hasShot && (
              <div className="flex flex-col gap-1.5">
                <div className="grid grid-cols-2 gap-1.5">
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    className="flex items-center justify-center gap-2 rounded-lg border border-dashed border-stone-300 py-2.5 text-xs font-medium text-stone-500 hover:border-emerald-400 hover:text-emerald-700"
                  >
                    <ImagePlus size={14} />
                    Upload an image
                  </button>
                  <button
                    type="button"
                    onClick={captureScreenshot}
                    disabled={capturing}
                    className="flex items-center justify-center gap-2 rounded-lg border border-dashed border-stone-300 py-2.5 text-xs font-medium text-stone-500 hover:border-emerald-400 hover:text-emerald-700 disabled:opacity-60"
                  >
                    {capturing ? <Loader2 size={14} className="animate-spin" /> : <Camera size={14} />}
                    {capturing ? "Capturing…" : "Capture this page"}
                  </button>
                </div>
                {/* Says what the two buttons do not: the thing you want to show
                    is often not in this app at all -- a supplier's site, an
                    email -- and pasting is how a screenshot usually travels. */}
                <p className="text-center text-[11px] text-stone-400">
                  …or paste an image with {navigator.platform.includes("Mac") ? "⌘V" : "Ctrl+V"}
                </p>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={(e) => { readFile(e.target.files?.[0]); e.target.value = ""; }}
                />
              </div>
            )}
            {/* Always mounted, not just once hasShot flips -- captureScreenshot
                draws into this element BEFORE setting hasShot, so a canvas that
                only rendered in the `hasShot` branch was never there yet to draw
                into (canvasRef.current was null, and the capture silently
                no-opped). Hidden rather than unmounted while empty. */}
            <div className={hasShot ? "flex flex-col gap-1.5" : "hidden"}>
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
