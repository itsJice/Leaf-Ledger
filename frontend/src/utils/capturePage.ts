/**
 * "Capture this page" (FeedbackWidget), frames included.
 *
 * html2canvas clones the page to draw it, and a cloned <iframe> starts out
 * empty: the Install Schedule (a same-origin srcDoc frame) came out as a
 * blank area next to the sidebar (comment #58's screenshot). Worse, the
 * clone re-loaded the whole schedule page in a hidden frame just to throw
 * it away.
 *
 * So the page is drawn without its frames, and each frame we may read
 * (same origin) is drawn on its own, from its own document at its own scroll
 * position, and painted onto the shot where the frame sits. A frame we may
 * not read (a YouTube video) gets a plain grey box with a label instead of
 * a misleading empty space. Frames inside frames are handled the same way,
 * two levels deep.
 */

/** html2canvas's call shape, so tests can pass a fake. */
export type Shoot = (el: HTMLElement, opts: Record<string, unknown>) => Promise<HTMLCanvasElement>;

export interface CaptureOptions {
  /** Device pixels per CSS pixel in the shot. */
  scale: number;
  /** Elements to leave out (the widget doing the capturing). */
  ignore?: (el: Element) => boolean;
}

/** How deep frames-in-frames are followed. */
const MAX_DEPTH = 2;

const isFrame = (el: Element) => el.tagName === "IFRAME";

/** A frame's document, or null when the browser won't let us read it. */
export function readableFrameDoc(frame: HTMLIFrameElement): Document | null {
  try {
    const doc = frame.contentDocument;
    return doc && doc.documentElement && doc.body ? doc : null;
  } catch {
    return null;
  }
}

/** The colour behind a frame's page (body first, then html), for the shot. */
function pageBackground(doc: Document): string | null {
  try {
    const view = doc.defaultView;
    if (!view) return null;
    for (const el of [doc.body, doc.documentElement]) {
      const c = el ? view.getComputedStyle(el).backgroundColor : "";
      if (c && c !== "transparent" && c !== "rgba(0, 0, 0, 0)") return c;
    }
  } catch {
    /* ignore */
  }
  return null;
}

/** The grey box for a frame we can't draw. */
function drawPlaceholder(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, scale: number) {
  ctx.save();
  ctx.fillStyle = "#e7e5e4";
  ctx.fillRect(x, y, w, h);
  ctx.fillStyle = "#57534e";
  ctx.font = `${Math.round(13 * scale)}px sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText("Embedded content (not captured)", x + w / 2, y + h / 2);
  ctx.restore();
}

/**
 * Paint every frame in `doc` onto `canvas`. `origin` is where the canvas's
 * top-left sits in `doc`'s viewport (CSS px).
 */
async function drawFrames(
  shoot: Shoot,
  canvas: HTMLCanvasElement,
  doc: Document,
  origin: { left: number; top: number },
  opts: CaptureOptions,
  depth: number,
): Promise<number> {
  const ctx = canvas.getContext("2d");
  if (!ctx) return 0;
  const { scale, ignore } = opts;
  let drawn = 0;
  const frames = Array.from(doc.querySelectorAll("iframe")) as HTMLIFrameElement[];
  for (const frame of frames) {
    if (ignore && (ignore(frame) || frame.closest("[data-feedback-widget]"))) continue;
    const rect = frame.getBoundingClientRect();
    const cw = frame.clientWidth || rect.width;
    const ch = frame.clientHeight || rect.height;
    if (cw < 1 || ch < 1) continue;
    const x = (rect.left - origin.left + (frame.clientLeft || 0)) * scale;
    const y = (rect.top - origin.top + (frame.clientTop || 0)) * scale;
    const w = cw * scale;
    const h = ch * scale;
    const fdoc = readableFrameDoc(frame);
    if (!fdoc) {
      drawPlaceholder(ctx, x, y, w, h, scale);
      continue;
    }
    try {
      const view = fdoc.defaultView;
      const sx = view ? view.scrollX : 0;
      const sy = view ? view.scrollY : 0;
      const inner = await shoot(fdoc.documentElement, {
        scale,
        useCORS: true,
        logging: false,
        backgroundColor: pageBackground(fdoc) ?? "#ffffff",
        x: sx,
        y: sy,
        width: cw,
        height: ch,
        windowWidth: cw,
        windowHeight: ch,
        ignoreElements: isFrame,
      });
      if (depth + 1 < MAX_DEPTH) await drawFrames(shoot, inner, fdoc, { left: 0, top: 0 }, opts, depth + 1);
      ctx.drawImage(inner, x, y, w, h);
      drawn++;
    } catch {
      drawPlaceholder(ctx, x, y, w, h, scale);
    }
  }
  return drawn;
}

/** A picture of the page, same-origin frames drawn in. */
export async function capturePage(shoot: Shoot, opts: CaptureOptions, doc: Document = document): Promise<HTMLCanvasElement> {
  const root = doc.body;
  const ignore = opts.ignore;
  const shot = await shoot(root, {
    // Frames are drawn separately below; a cloned one is always blank.
    ignoreElements: (el: Element) => isFrame(el) || (ignore ? ignore(el) : false),
    backgroundColor: null,
    scale: opts.scale,
    useCORS: true,
    logging: false,
  });
  const r = root.getBoundingClientRect();
  await drawFrames(shoot, shot, doc, { left: r.left, top: r.top }, opts, 0);
  return shot;
}
