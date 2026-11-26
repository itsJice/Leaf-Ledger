import { describe, expect, it, vi } from "vitest";
import { capturePage, type Shoot } from "utils/capturePage";

/** A canvas stand-in that records what is drawn on it. */
function fakeCanvas(name: string) {
  const calls: Array<[string, ...unknown[]]> = [];
  const ctx = {
    drawImage: (...a: unknown[]) => calls.push(["drawImage", ...a]),
    fillRect: (...a: unknown[]) => calls.push(["fillRect", ...a]),
    fillText: (...a: unknown[]) => calls.push(["fillText", ...a]),
    save() {},
    restore() {},
    fillStyle: "",
    font: "",
    textAlign: "",
    textBaseline: "",
  };
  return { name, calls, getContext: () => ctx } as unknown as HTMLCanvasElement & { name: string; calls: typeof calls };
}

const rect = (left: number, top: number, width: number, height: number) => ({ left, top, width, height, right: left + width, bottom: top + height, x: left, y: top });

function fakeDoc(frames: unknown[], bodyRect = rect(0, 0, 1200, 800)) {
  const doc: Record<string, unknown> = {
    body: { tagName: "BODY", getBoundingClientRect: () => bodyRect },
    documentElement: { tagName: "HTML" },
    defaultView: { scrollX: 0, scrollY: 0, getComputedStyle: () => ({ backgroundColor: "rgb(247, 246, 242)" }) },
    querySelectorAll: (q: string) => (q === "iframe" ? frames : []),
  };
  return doc as unknown as Document;
}

function fakeFrame(r: ReturnType<typeof rect>, contentDocument: Document | null | "throws") {
  const f: Record<string, unknown> = {
    tagName: "IFRAME",
    clientLeft: 0,
    clientTop: 0,
    clientWidth: r.width,
    clientHeight: r.height,
    getBoundingClientRect: () => r,
    closest: () => null,
  };
  Object.defineProperty(f, "contentDocument", {
    get() {
      if (contentDocument === "throws") throw new Error("SecurityError");
      return contentDocument;
    },
  });
  return f;
}

describe("capturePage", () => {
  it("draws a same-origin frame's own document where the frame sits", async () => {
    const inner = fakeDoc([]);
    (inner.defaultView as unknown as { scrollX: number; scrollY: number }).scrollY = 40;
    const frame = fakeFrame(rect(90, 0, 1110, 800), inner);
    const doc = fakeDoc([frame]);
    const page = fakeCanvas("page");
    const schedule = fakeCanvas("schedule");
    const shots: Array<{ el: unknown; opts: Record<string, unknown> }> = [];
    const shoot: Shoot = vi.fn(async (el, opts) => {
      shots.push({ el, opts });
      return shots.length === 1 ? page : schedule;
    });

    const out = await capturePage(shoot, { scale: 1.5 }, doc);

    expect(out).toBe(page);
    expect(shots).toHaveLength(2);
    // The page pass leaves every iframe out (a cloned frame is blank).
    const ignorePage = shots[0].opts.ignoreElements as (el: Element) => boolean;
    expect(ignorePage({ tagName: "IFRAME" } as Element)).toBe(true);
    expect(ignorePage({ tagName: "DIV" } as Element)).toBe(false);
    // The frame pass: its document, its viewport and scroll.
    expect(shots[1].el).toBe(inner.documentElement);
    expect(shots[1].opts).toMatchObject({ x: 0, y: 40, width: 1110, height: 800, windowWidth: 1110, windowHeight: 800, scale: 1.5, backgroundColor: "rgb(247, 246, 242)" });
    // Painted at the frame's spot, scaled.
    expect(page.calls).toEqual([["drawImage", schedule, 135, 0, 1665, 1200]]);
  });

  it("keeps the caller's ignore rule on the page pass", async () => {
    const doc = fakeDoc([]);
    const shoot: Shoot = vi.fn(async () => fakeCanvas("page"));
    await capturePage(shoot, { scale: 1, ignore: (el) => (el as unknown as { widget?: boolean }).widget === true }, doc);
    const ignore = (shoot as unknown as { mock: { calls: Array<[unknown, Record<string, unknown>]> } }).mock.calls[0][1].ignoreElements as (el: Element) => boolean;
    expect(ignore({ tagName: "DIV", widget: true } as unknown as Element)).toBe(true);
  });

  it("puts a labelled box where a cross-origin frame is", async () => {
    const frame = fakeFrame(rect(100, 50, 640, 360), "throws");
    const doc = fakeDoc([frame]);
    const page = fakeCanvas("page");
    const shoot: Shoot = vi.fn(async () => page);
    await capturePage(shoot, { scale: 1 }, doc);
    expect(shoot).toHaveBeenCalledTimes(1);
    expect(page.calls[0]).toEqual(["fillRect", 100, 50, 640, 360]);
    expect(page.calls[1][0]).toBe("fillText");
    expect(page.calls[1][1]).toBe("Embedded content (not captured)");
  });

  it("skips hidden frames and measures from the body when the page is scrolled", async () => {
    const hidden = fakeFrame(rect(0, 0, 0, 0), fakeDoc([]));
    const inner = fakeDoc([]);
    const shown = fakeFrame(rect(90, -100, 500, 400), inner);
    const doc = fakeDoc([hidden, shown], rect(0, -300, 1200, 2000));
    const page = fakeCanvas("page");
    const frameShot = fakeCanvas("frame");
    let n = 0;
    const shoot: Shoot = vi.fn(async () => (n++ === 0 ? page : frameShot));
    await capturePage(shoot, { scale: 1 }, doc);
    expect(shoot).toHaveBeenCalledTimes(2);
    expect(page.calls).toEqual([["drawImage", frameShot, 90, 200, 500, 400]]);
  });

  it("a frame that fails to draw gets the box, not a crash", async () => {
    const frame = fakeFrame(rect(0, 0, 300, 200), fakeDoc([]));
    const doc = fakeDoc([frame]);
    const page = fakeCanvas("page");
    let n = 0;
    const shoot: Shoot = vi.fn(async () => {
      if (n++ === 0) return page;
      throw new Error("tainted");
    });
    await capturePage(shoot, { scale: 1 }, doc);
    expect(page.calls[0]).toEqual(["fillRect", 0, 0, 300, 200]);
  });
});
