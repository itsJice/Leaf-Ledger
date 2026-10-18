/**
 * Cmd+P / Ctrl+P prints the whole page you're on (user, 2026-10-17: "I need
 * every page on L&L, when I push Command P, to print the page I'm on, not
 * including the sidebar, but everything on the page that I can scroll up and
 * down and see").
 *
 * The app is a fixed-height shell: the sidebar, a content pane that scrolls
 * ([data-scroll-root]) and, inside pages, more panes that scroll on their own
 * (split list/detail views, tables, modals). Printed as-is the browser shows
 * one screenful of each. Static print CSS in index.css covers the common
 * cases; this module covers the rest by looking at what is actually on
 * screen the moment printing starts (`beforeprint`, which every current
 * browser fires for Cmd+P, File > Print and window.print()):
 *
 *   - every element that scrolls or clips TEXT is marked to grow to its
 *     content, and so is every container above it (a fixed-height parent
 *     would clip it again);
 *   - sticky / fixed bits inside the page are laid out in place;
 *   - an open modal prints on its own, in full, instead of the page under it;
 *   - a page can register a fallback (`setPrintFallback`): the Install
 *     Schedule uses it so File > Print, which can't be redirected into its
 *     iframe, still prints the whole schedule (see InstallSchedule.tsx).
 *
 * `afterprint` undoes all of it. The marks are plain data attributes; the
 * styling for them lives in index.css under @media print.
 */

export const PRINT_ATTR = {
  /** An element that scrolls/clips text on screen: printed at full size. */
  unclip: "data-ll-print-unclip",
  /** A container of one of those: loses its height limits. */
  grow: "data-ll-print-grow",
  /** Sticky / fixed (or absolutely placed scroll pane): laid out in place. */
  inplace: "data-ll-print-inplace",
  /** The open modal, printed alone. */
  modal: "data-ll-print-modal",
  /** On <html> while a modal prints alone. */
  modalOpen: "data-ll-print-modal-open",
  /** The ancestors of that modal (everything else is hidden). */
  path: "data-ll-print-path",
  /** A print-only copy a fallback added (e.g. the schedule). */
  clone: "data-ll-print-clone",
  /** On <html> while a fallback copy is the thing being printed. */
  cloneOn: "data-ll-print-clone-on",
  /** A sideways scroller, scaled (--ll-print-zoom) so all of it fits the page width. */
  fit: "data-ll-print-fit",
  /** Small enough to keep on one page (a card or row): not split across pages. */
  keep: "data-ll-print-keep",
} as const;

/** About how wide the printed content is, in CSS px, on Letter/A4 with the
 *  browser's default margins, inside the page area (which prints at 80%). */
export const PRINT_ZOOM = 0.8; // index.css: [data-scroll-root] { zoom: 0.8 } in print
export const PRINT_WIDTH = { portrait: 720 / PRINT_ZOOM, landscape: 960 / PRINT_ZOOM } as const;

/**
 * How much a sideways scroller must shrink to fit the paper. `share` is the
 * part of the page's width it takes on screen (0..1), `contentWidth` how wide
 * its content is. Portrait unless that would shrink it below 60%, then the
 * whole printout goes landscape. Never below 40% (still complete, if small).
 */
export function fitScale(share: number, contentWidth: number, landscape: boolean): number {
  const w = (landscape ? PRINT_WIDTH.landscape : PRINT_WIDTH.portrait) * Math.min(1, Math.max(0.1, share));
  return Math.max(0.4, Math.min(1, w / Math.max(1, contentWidth)));
}
export function needsLandscape(share: number, contentWidth: number): boolean {
  return fitScale(share, contentWidth, false) < 0.6;
}

/** Cards/rows shorter than this (screen px) are kept whole on one page;
 *  taller ones may split (keeping them whole would leave blank pages). */
const KEEP_MAX_HEIGHT = 420;

/** True for Cmd+P / Ctrl+P (not Shift/Alt variants, which browsers use for other things). */
export function isPrintShortcut(e: Pick<KeyboardEvent, "metaKey" | "ctrlKey" | "altKey" | "shiftKey" | "key">): boolean {
  return (e.metaKey || e.ctrlKey) && !e.altKey && !e.shiftKey && String(e.key).toLowerCase() === "p";
}

/**
 * Rewrites a stylesheet written for a whole document so it works inside a
 * shadow root whose stand-ins for <html> and <body> are
 * `.ll-frame-html` / `.ll-frame-body`: `html`, `body` and `:root` in
 * SELECTORS are replaced; declarations, at-rule preludes and keyframe steps
 * are left alone.
 */
export function scopeDocumentCss(css: string): string {
  const src = css.replace(/\/\*[\s\S]*?\*\//g, "");
  // What each open `{` is: a style rule (its body is declarations) or a
  // grouping at-rule / keyframes (its body holds more rules).
  const stack: Array<"rule" | "group" | "keyframes"> = [];
  let out = "";
  let buf = "";
  const inDeclarations = () => stack[stack.length - 1] === "rule";
  for (const ch of src) {
    if (ch === "{") {
      const prelude = buf;
      const head = prelude.trim();
      if (inDeclarations()) {
        // Nested rule inside a declaration block (CSS nesting): treat as a rule.
        out += rewriteSelector(prelude) + "{";
        stack.push("rule");
      } else if (head.startsWith("@")) {
        out += prelude + "{";
        stack.push(/^@(-\w+-)?keyframes/i.test(head) ? "keyframes" : /^@(font-face|page|property|counter-style)/i.test(head) ? "rule" : "group");
      } else if (stack[stack.length - 1] === "keyframes") {
        out += prelude + "{";
        stack.push("rule");
      } else {
        out += rewriteSelector(prelude) + "{";
        stack.push("rule");
      }
      buf = "";
    } else if (ch === "}") {
      out += buf + "}";
      buf = "";
      stack.pop();
    } else if (ch === ";" && !inDeclarations()) {
      // A statement at-rule (@import, @charset) between rules.
      out += buf + ";";
      buf = "";
    } else {
      buf += ch;
    }
  }
  return out + buf;
}

function rewriteSelector(sel: string): string {
  return sel
    .replace(/:root\b/g, ":host")
    .replace(/(^|[\s,>+~(])html(?![\w-])/g, "$1.ll-frame-html")
    .replace(/(^|[\s,>+~(])body(?![\w-])/g, "$1.ll-frame-body");
}

// ---------------------------------------------------------------------------
// DOM side (browser only)

type Fallback = () => HTMLElement | null;
let fallback: Fallback | null = null;
let suppressed = 0;
let installed = false;

/**
 * Registers what to print instead of the page when the page itself can't
 * print properly (one at a time; pass null to clear). The function returns a
 * print-only element, which is added under <body> for the print and removed
 * after it.
 */
export function setPrintFallback(fn: Fallback | null): void {
  fallback = fn;
}

/**
 * Runs `print` (e.g. an iframe's own window.print()) without this window's
 * fallback kicking in, in case the browser also tells this window.
 */
export function printWithoutFallback(print: () => void): void {
  suppressed += 1;
  try {
    print();
  } finally {
    // print() blocks until the dialog closes in Chrome/Safari; Firefox returns
    // at once, so keep the guard briefly for its late beforeprint.
    setTimeout(() => {
      suppressed = Math.max(0, suppressed - 1);
    }, 1000);
  }
}

const marked = new Set<Element>();
let addedClone: HTMLElement | null = null;

function mark(el: Element, attr: string): void {
  el.setAttribute(attr, "");
  marked.add(el);
}

function isShown(el: Element): boolean {
  const r = el.getBoundingClientRect();
  if (r.width === 0 && r.height === 0) return false;
  const v = (el as HTMLElement).checkVisibility;
  return typeof v === "function" ? v.call(el, { checkVisibilityCSS: true } as never) : true;
}

function cutOnPurpose(cs: CSSStyleDeclaration): boolean {
  // Ellipsis / line-clamp text is shortened on screen too; letting it spill
  // over its neighbours on paper helps nobody.
  return cs.textOverflow === "ellipsis" || (Boolean(cs.webkitLineClamp) && cs.webkitLineClamp !== "none");
}

/** Does `el` hide any text (or a whole image) past its edges? */
function hidesContent(el: Element, box: DOMRect): boolean {
  const doc = el.ownerDocument;
  const walker = doc.createTreeWalker(el, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
  const range = doc.createRange();
  let n: Node | null;
  let seen = 0;
  while ((n = walker.nextNode())) {
    if (++seen > 20000) return true; // huge: assume it scrolls something real
    if (n.nodeType === Node.ELEMENT_NODE) {
      const e = n as Element;
      if (e.tagName === "IMG" || e.tagName === "svg") {
        const r = e.getBoundingClientRect();
        if (r.width && r.height && (r.top >= box.bottom || r.bottom <= box.top || r.left >= box.right || r.right <= box.left)) return true;
      }
      continue;
    }
    if (!n.textContent || !n.textContent.trim()) continue;
    range.selectNodeContents(n);
    const r = range.getBoundingClientRect();
    if (!r.width && !r.height) continue;
    if (r.bottom > box.bottom + 2 || r.top < box.top - 2 || r.right > box.right + 2 || r.left < box.left - 2) {
      const parent = n.parentElement;
      if (parent && cutOnPurpose(getComputedStyle(parent))) continue;
      return true;
    }
  }
  return false;
}

function findOpenModal(doc: Document): Element | null {
  const found = [...doc.querySelectorAll('.ll-overlay, [role="dialog"], [aria-modal="true"]')].filter(
    (el) => !el.closest("[data-feedback-widget]") && el.children.length > 0 && isShown(el) && (el as HTMLElement).innerText?.trim(),
  );
  const top = found[found.length - 1];
  if (!top) return null;
  return top.closest(".ll-overlay") ?? top;
}

type Sideways = { el: HTMLElement; share: number; width: number };

function markScrollers(scope: Element, stopAt: Element, sideways: Sideways[]): void {
  const doc = scope.ownerDocument;
  const scrollRoot = doc.querySelector("[data-scroll-root]") as HTMLElement | null;
  const pageW = scrollRoot?.clientWidth || doc.documentElement.clientWidth || 1;
  const all = [scope, ...scope.querySelectorAll("*")];
  for (const el of all) {
    if (!(el instanceof HTMLElement)) continue;
    const overY = el.scrollHeight > el.clientHeight + 1;
    const overX = el.scrollWidth > el.clientWidth + 1;
    let cs: CSSStyleDeclaration | null = null;
    // Anything that can scroll sideways is a candidate for fitting to the
    // paper, even if it fits on this screen: the page is narrower (a board
    // of fixed-width columns that fits 1440px may not fit Letter).
    // (A vertical scroller's overflow-x computes to auto too, so it only
    // counts if it is meant to scroll sideways or actually does.)
    if (el !== scrollRoot && !el.contains(scrollRoot) && el.scrollWidth > 160) {
      cs = getComputedStyle(el);
      const sidewaysByDesign = /(^|\s|:)(overflow-x-(auto|scroll)|snap-x)(\s|$)/.test(el.className.toString());
      if (
        cs.overflowX !== "visible" &&
        (sidewaysByDesign || overX) &&
        !cutOnPurpose(cs) &&
        !el.closest("[data-ll-chrome], [data-feedback-widget]") &&
        isShown(el)
      ) {
        sideways.push({ el, share: el.clientWidth / pageW, width: el.scrollWidth });
      }
    }
    if (!overY && !overX) continue;
    cs = cs ?? getComputedStyle(el);
    const clipsY = overY && cs.overflowY !== "visible";
    const clipsX = overX && cs.overflowX !== "visible";
    if (!clipsY && !clipsX) continue;
    if (cutOnPurpose(cs) || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName)) continue;
    if (!isShown(el) || !hidesContent(el, el.getBoundingClientRect())) continue;
    mark(el, PRINT_ATTR.unclip);
    if (cs.position === "absolute" || cs.position === "fixed" || cs.position === "sticky") mark(el, PRINT_ATTR.inplace);
    for (let p = el.parentElement; p && p !== stopAt.parentElement; p = p.parentElement) {
      if (p.hasAttribute(PRINT_ATTR.grow)) break;
      mark(p, PRINT_ATTR.grow);
      const pp = getComputedStyle(p).position;
      if (pp === "absolute" || pp === "fixed" || pp === "sticky") mark(p, PRINT_ATTR.inplace);
    }
  }
}

let pageStyle: HTMLStyleElement | null = null;
const zoomed = new Set<HTMLElement>();

/**
 * How wide a sideways scroller's content needs to be on paper: its
 * narrowest layout (fixed-width columns stay fixed; tables forced wide on
 * screen with min-w-[1800px] may wrap, since index.css drops that
 * min-width in print) -- but not below 55% of its screen width, which would
 * stack every word.
 */
function printedWidth(el: HTMLElement, screenWidth: number): number {
  el.setAttribute("data-ll-print-measure", "");
  const narrowest = el.scrollWidth;
  el.removeAttribute("data-ll-print-measure");
  return Math.min(screenWidth, Math.max(narrowest, screenWidth * 0.55));
}

/** Scales sideways scrollers to the paper; wide ones turn the printout landscape. */
function fitSideways(doc: Document, sideways: Sideways[]): void {
  for (const s of sideways) s.width = printedWidth(s.el, s.width);
  const tooWide = sideways.filter((s) => fitScale(s.share, s.width, true) < 0.98 || fitScale(s.share, s.width, false) < 0.98);
  // Nested: only the outermost one that needs it is scaled.
  const outer = tooWide.filter((s) => !tooWide.some((o) => o !== s && o.el.contains(s.el)));
  const landscape = outer.some((s) => needsLandscape(s.share, s.width));
  if (landscape) {
    pageStyle = doc.createElement("style");
    pageStyle.setAttribute("data-ll-print-page", "");
    pageStyle.textContent = "@page { size: landscape; }";
    doc.head.appendChild(pageStyle);
  }
  for (const s of outer) {
    const z = fitScale(s.share, s.width, landscape);
    if (z > 0.98) continue;
    s.el.style.setProperty("--ll-print-zoom", z.toFixed(3));
    zoomed.add(s.el);
    mark(s.el, PRINT_ATTR.fit);
  }
}

/** Small cards and rows stay whole; big sections may split (no blank pages). */
function markKeepTogether(scope: Element): void {
  for (const el of scope.querySelectorAll('tr, li, article, [class*="rounded"], [class*="card"]')) {
    const h = (el as HTMLElement).offsetHeight;
    if (h > 0 && h < KEEP_MAX_HEIGHT) mark(el, PRINT_ATTR.keep);
  }
}

function markPinned(scope: Element): void {
  for (const el of scope.querySelectorAll("*")) {
    const pos = getComputedStyle(el).position;
    if (pos === "sticky" || pos === "fixed") mark(el, PRINT_ATTR.inplace);
  }
}

/** Marks the page for printing. Safe to call twice; `cleanupPrint` undoes it. */
export function preparePrint(doc: Document = document): void {
  cleanupPrint(doc);
  if (suppressed > 0) return;
  // A page that can't print itself (the schedule's iframe) hands over a copy.
  if (fallback) {
    let copy: HTMLElement | null = null;
    try {
      copy = fallback();
    } catch {
      copy = null;
    }
    if (copy) {
      copy.setAttribute(PRINT_ATTR.clone, "");
      doc.body.appendChild(copy);
      addedClone = copy;
      doc.documentElement.setAttribute(PRINT_ATTR.cloneOn, "");
      return;
    }
  }
  const shell = doc.querySelector("[data-ll-shell]") ?? doc.body;
  const modal = findOpenModal(doc);
  if (modal) {
    mark(modal, PRINT_ATTR.modal);
    mark(doc.documentElement, PRINT_ATTR.modalOpen);
    for (let p = modal.parentElement; p && p !== doc.documentElement; p = p.parentElement) {
      mark(p, PRINT_ATTR.path);
      mark(p, PRINT_ATTR.grow);
    }
    const sideways: Sideways[] = [];
    markScrollers(modal, modal, sideways);
    fitSideways(doc, sideways);
    markKeepTogether(modal);
    return;
  }
  const sideways: Sideways[] = [];
  markScrollers(shell, shell, sideways);
  fitSideways(doc, sideways);
  markPinned(shell);
  markKeepTogether(shell);
}

export function cleanupPrint(doc: Document = document): void {
  const attrs = Object.values(PRINT_ATTR);
  for (const el of marked) for (const a of attrs) el.removeAttribute(a);
  marked.clear();
  for (const el of zoomed) el.style.removeProperty("--ll-print-zoom");
  zoomed.clear();
  pageStyle?.remove();
  pageStyle = null;
  doc.documentElement.removeAttribute(PRINT_ATTR.modalOpen);
  doc.documentElement.removeAttribute(PRINT_ATTR.cloneOn);
  addedClone?.remove();
  addedClone = null;
}

/** Wires beforeprint/afterprint once for the app (main.tsx). */
export function installPrintSupport(win: Window = window): void {
  if (installed) return;
  installed = true;
  win.addEventListener("beforeprint", () => preparePrint(win.document));
  win.addEventListener("afterprint", () => cleanupPrint(win.document));
}

/**
 * A print-only copy of a same-origin iframe's document, as it looks right
 * now (open view, scroll-independent), inside a shadow root so its styles and
 * the app's never meet. Its own @media print rules apply when this window
 * prints. Returns null if the frame isn't reachable or loaded.
 */
export function copyFrameForPrint(frame: HTMLIFrameElement | null): HTMLElement | null {
  let fdoc: Document | null = null;
  try {
    fdoc = frame?.contentDocument ?? null;
  } catch {
    return null;
  }
  if (!fdoc?.body || !fdoc.body.children.length) return null;
  const doc = frame!.ownerDocument;
  const host = doc.createElement("div");
  const root = host.attachShadow({ mode: "open" });
  for (const link of fdoc.querySelectorAll('link[rel="stylesheet"]')) root.appendChild(doc.importNode(link, true));
  const style = doc.createElement("style");
  style.textContent = [...fdoc.querySelectorAll("style")].map((s) => scopeDocumentCss(s.textContent || "")).join("\n");
  root.appendChild(style);
  const html = doc.createElement("div");
  html.className = `ll-frame-html ${fdoc.documentElement.className}`.trim();
  const body = doc.createElement("div");
  body.className = `ll-frame-body ${fdoc.body.className}`.trim();
  const bodyStyle = fdoc.body.getAttribute("style");
  if (bodyStyle) body.setAttribute("style", bodyStyle);
  for (const child of fdoc.body.childNodes) {
    if (child.nodeName === "SCRIPT") continue;
    body.appendChild(doc.importNode(child, true));
  }
  body.querySelectorAll("script").forEach((s) => s.remove());
  // Form values live in properties, not attributes: carry them over.
  const srcFields = fdoc.body.querySelectorAll("input, select, textarea");
  const dstFields = body.querySelectorAll("input, select, textarea");
  if (srcFields.length === dstFields.length) {
    srcFields.forEach((f, i) => {
      const d = dstFields[i] as HTMLInputElement;
      const s = f as HTMLInputElement;
      if (s.type === "checkbox" || s.type === "radio") d.checked = s.checked;
      else d.value = s.value;
    });
  }
  html.appendChild(body);
  root.appendChild(html);
  return host;
}
