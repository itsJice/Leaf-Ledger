/**
 * What people DO, for the "last minute" trail (utils/eventLog.ts): buttons
 * and links pressed, tabs and menus picked, dialogs opened and closed,
 * dropdowns picked, boxes ticked, fields changed, forms submitted, stops
 * dragged and dropped, and the messages and questions the page put in front
 * of them (alert / confirm pop-ups, toasts, "Cannot make this change").
 *
 * One recorder for every page and every frame. The app runs it on its own
 * window; it follows into every same-origin iframe it can reach (printables,
 * load sheets, the Install Schedule's season frame). The Install Schedule is
 * a srcDoc page with its own window, so scheduleFrameWatch.ts also puts this
 * same function, as source text, at the top of that page; there it posts each
 * step to the app instead of calling addStep. That is why it must stay
 * SELF-CONTAINED: no imports, nothing from this module's scope, plain syntax.
 * (Cross-origin frames, like the YouTube help videos, can't be watched.)
 *
 * Privacy: labels come from what the page shows (button text, a field's
 * label, a dialog's title). A field's VALUE is kept only for pickers whose
 * values aren't private: dropdown picks, dates and times, radio choices, and
 * tick boxes (on/off). Never anything typed, and never a password, email,
 * phone, card, address, note or search value, whatever the control.
 *
 * Bounded: labels are capped at 80 characters, the same step twice within
 * 1.5 seconds is dropped, and at most 25 steps are kept per 10 seconds, so a
 * burst of clicks can't flood the trail. Typing and scrolling are never
 * recorded (a field counts once, when it changes).
 */
export interface TrailAction {
  kind: "click" | "tab" | "menu" | "pick" | "toggle" | "field" | "dialog" | "message" | "ask" | "drop" | "submit" | "error";
  label: string;
}

export function startActionTrail(win: Window, emit: (a: TrailAction) => void): void {
  try {
    // Once per document. (Not per window: a frame's first blank page and the
    // page it then loads can share one window object.)
    if (!win || !win.document) return;
    const doc = win.document;
    const d0 = doc as unknown as Record<string, unknown>;
    if (d0.__llActionTrail) return;
    d0.__llActionTrail = true;
    const w = win as unknown as Record<string, unknown>;
    const MAX = 80;
    const PRIVATE = /pass|e-?mail|phone|\btel\b|mobile|cell|card|cvv|cvc|expir|ssn|social|address|street|zip|postal|token|secret|api.?key|account|routing|note|comment|message|search/i;
    const VALUE_TYPES = /^(date|time|datetime-local|month|week)$/;

    const clip = (s: unknown, n: number): string => String(s == null ? "" : s).replace(/\s+/g, " ").trim().slice(0, n);
    const firstLine = (s: unknown, n: number): string => {
      const lines = String(s == null ? "" : s).split("\n").map((l) => l.trim()).filter(Boolean);
      return clip(lines[0] || "", n);
    };

    let last = "";
    let lastAt = 0;
    let burstAt = 0;
    let burst = 0;
    const send = (kind: TrailAction["kind"], label: string) => {
      try {
        const text = clip(label, MAX);
        if (!text) return;
        const now = Date.now();
        if (text === last && now - lastAt < 1500) return;
        if (now - burstAt > 10000) {
          burstAt = now;
          burst = 0;
        }
        if (++burst > 25) return;
        last = text;
        lastAt = now;
        emit({ kind, label: text });
      } catch (e) {
        /* never break the page */
      }
    };

    const shown = (el: Element | null): string => {
      if (!el) return "";
      const h = el as HTMLElement;
      return firstLine(el.getAttribute("aria-label") || el.getAttribute("title") || h.innerText || el.textContent || "", 60);
    };

    // A field's name as the page shows it: its label, never its value.
    const fieldName = (el: Element): string => {
      try {
        const f = el as HTMLInputElement;
        const aria = el.getAttribute("aria-label");
        if (aria) return clip(aria, 40);
        const by = el.getAttribute("aria-labelledby");
        if (by) {
          const t = by.split(/\s+/).map((id) => { const x = doc.getElementById(id); return x ? x.textContent || "" : ""; }).join(" ");
          if (clip(t, 40)) return clip(t, 40);
        }
        const lab = f.labels && f.labels[0];
        if (lab) {
          // The label's own words, not the options or text inside the field.
          let t = "";
          lab.childNodes.forEach((n) => {
            if (n.nodeType === 3) t += n.textContent || "";
            else if (n.nodeType === 1 && !(n as Element).contains(el) && !/^(SELECT|INPUT|TEXTAREA)$/.test((n as Element).tagName)) t += " " + ((n as HTMLElement).innerText || n.textContent || "");
          });
          if (clip(t, 40)) return clip(t, 40);
        }
        return clip(el.getAttribute("placeholder") || el.getAttribute("name") || el.getAttribute("title") || el.id || "a field", 40);
      } catch (e) {
        return "a field";
      }
    };

    // ── Clicks: buttons, links, tabs, menu items, custom options ──
    doc.addEventListener(
      "click",
      (e) => {
        try {
          const t = e.target as Element | null;
          if (!t || !t.closest) return;
          const el = t.closest(
            'button, a, [role="button"], [role="tab"], [role="menuitem"], [role="menuitemradio"], [role="menuitemcheckbox"], [role="option"], [role="switch"], [role="checkbox"], summary',
          );
          if (!el || el.closest("[data-no-trail]")) return;
          // A real <input>/<select> inside reports through "change" instead.
          if (/^(INPUT|SELECT|TEXTAREA|OPTION)$/.test(el.tagName)) return;
          const role = el.getAttribute("role") || "";
          const name = shown(el) || "(unlabelled " + el.tagName.toLowerCase() + ")";
          if (role === "tab") send("tab", "Switched to " + name);
          else if (role.indexOf("menuitem") === 0) send("menu", "Picked menu item " + name);
          else if (role === "option") send("pick", "Picked " + name);
          else if (role === "switch" || role === "checkbox") send("toggle", (el.getAttribute("aria-checked") === "true" ? "Turned off " : "Turned on ") + name);
          else if (el.tagName === "A" && !el.getAttribute("role")) send("click", "Opened link " + name);
          else send("click", "Pressed " + name);
        } catch (x) {
          /* ignore */
        }
      },
      true,
    );

    // ── Fields: picks, ticks, dates; anything typed is only "Changed X" ──
    doc.addEventListener(
      "change",
      (e) => {
        try {
          const el = e.target as HTMLInputElement | HTMLSelectElement | null;
          if (!el || !el.tagName || (el.closest && el.closest("[data-no-trail]"))) return;
          const name = fieldName(el);
          const secret = PRIVATE.test(name);
          if (el.tagName === "SELECT") {
            const s = el as HTMLSelectElement;
            if (s.multiple) return send("pick", "Picked " + s.selectedOptions.length + " in " + name);
            const opt = s.options[s.selectedIndex];
            return send("pick", secret || !opt ? "Changed " + name : "Picked " + name + ": " + clip(opt.text, 50));
          }
          if (el.tagName !== "INPUT") return send("field", "Changed " + name);
          const i = el as HTMLInputElement;
          const type = (i.type || "text").toLowerCase();
          if (type === "checkbox") return send("toggle", (i.checked ? "Ticked " : "Unticked ") + name);
          if (type === "radio") return send("pick", "Picked " + name);
          if (type === "file") return send("field", "Chose a file for " + name);
          if (VALUE_TYPES.test(type) && !secret) return send("field", "Set " + name + ": " + clip(i.value, 20));
          send("field", "Changed " + name);
        } catch (x) {
          /* ignore */
        }
      },
      true,
    );

    doc.addEventListener(
      "submit",
      (e) => {
        try {
          const f = e.target as HTMLFormElement;
          const h = f && f.querySelector ? f.querySelector("h1,h2,h3,h4,legend") : null;
          send("submit", "Submitted " + clip((f && f.getAttribute("aria-label")) || (h && h.textContent) || "a form", 50));
        } catch (x) {
          /* ignore */
        }
      },
      true,
    );

    // ── Drag and drop (schedule stops, crew headers, bubbles) ──
    let dragging = "";
    doc.addEventListener(
      "dragstart",
      (e) => {
        try {
          const t = e.target as Element;
          const el = t && t.closest ? t.closest('[draggable="true"]') || t : t;
          // What the thing says (a stop's name, a crew's title), before any tooltip.
          dragging = el ? firstLine((el as HTMLElement).innerText || el.textContent || "", 40) || shown(el).slice(0, 40) : "";
        } catch (x) {
          dragging = "";
        }
      },
      true,
    );
    doc.addEventListener(
      "drop",
      (e) => {
        try {
          const t = e.target as Element;
          const el = t && t.closest ? t.closest("[data-date],[data-val],[data-drop-date],[aria-label],[title]") || t : t;
          const where = el ? clip(el.getAttribute("data-date") || el.getAttribute("data-drop-date") || shown(el), 40) : "";
          send("drop", "Dropped " + (dragging || "something") + (where ? " on " + where : ""));
          dragging = "";
        } catch (x) {
          /* ignore */
        }
      },
      true,
    );

    // ── Pop-ups the page shows: alert, confirm (and the answer), prompt ──
    try {
      if (!w.__llPopups) {
        w.__llPopups = true;
        const A = win.alert, C = win.confirm, P = win.prompt;
        if (A) win.alert = function (m?: unknown) { send("message", "Message: " + clip(m, 70)); return A.call(win, m as string); };
        if (C) win.confirm = function (m?: unknown) { const r = C.call(win, m as string); send("ask", "Asked: " + clip(m, 55) + " -> " + (r ? "OK" : "Cancel")); return r; };
        // The answer to a prompt is typed text: only that it was asked.
        if (P) win.prompt = function (m?: unknown, d?: unknown) { send("ask", "Asked: " + clip(m, 70)); return P.call(win, m as string, d as string); };
      }
    } catch (x) {
      /* ignore */
    }

    // ── Dialogs opening and closing, toasts, and frames to follow into ──
    const DIALOG = '[role="dialog"],[role="alertdialog"]';
    const TOAST = '[data-sonner-toast],[role="alert"]';
    const dialogTitle = (d: Element): string => {
      try {
        const by = d.getAttribute("aria-labelledby");
        const lab = by ? doc.getElementById(by.split(/\s+/)[0]) : null;
        const h = lab || d.querySelector("h1,h2,h3,h4,[id$=title]");
        return clip(d.getAttribute("aria-label") || (h && h.textContent) || firstLine((d as HTMLElement).innerText, 50) || "a dialog", 60);
      } catch (x) {
        return "a dialog";
      }
    };
    const frames: Element[] = [];
    const follow = (f: HTMLIFrameElement) => {
      if (frames.indexOf(f) >= 0) return;
      frames.push(f);
      const attach = () => {
        try {
          const cw = f.contentWindow;
          // Same-origin only; a cross-origin frame throws here and is skipped.
          // A frame already watched (the Install Schedule watches itself and
          // reports its own errors) is left alone.
          if (!cw || !cw.document || !cw.document.documentElement) return;
          const cd = cw.document as unknown as Record<string, unknown>;
          // The blank page a frame shows before its own loads: wait for "load".
          if (cw.document.URL === "about:blank" && (f.hasAttribute("srcdoc") || f.getAttribute("src"))) return;
          if (cd.__llActionTrail) return;
          startActionTrail(cw, emit);
          const cwr = cw as unknown as Record<string, unknown>;
          if (!cwr.__llFrameErrors) {
            cwr.__llFrameErrors = true;
            cw.addEventListener("error", (ev) => send("error", "Error in a frame: " + clip(ev.message, 60)));
          }
        } catch (x) {
          /* cross-origin */
        }
      };
      f.addEventListener("load", attach);
      attach();
    };
    // A dialog counts as opened only once it is on screen (pages keep hidden
    // ones in the markup), and as closed only if it was seen open.
    const shownDialogs: Element[] = [];
    const onScreen = (d: Element): boolean => {
      try {
        return !d.hasAttribute("hidden") && d.getClientRects().length > 0;
      } catch (x) {
        return false;
      }
    };
    const dialogShown = (d: Element, now: boolean) => {
      const at = shownDialogs.indexOf(d);
      if (now && at < 0 && onScreen(d)) {
        shownDialogs.push(d);
        if (shownDialogs.length > 20) shownDialogs.shift();
        send("dialog", "Opened " + dialogTitle(d));
      } else if (!now && at >= 0) {
        shownDialogs.splice(at, 1);
        send("dialog", "Closed " + dialogTitle(d));
      }
    };
    const look = (n: Node, added: boolean) => {
      if (n.nodeType !== 1) return;
      const el = n as Element;
      if (added) {
        if (el.tagName === "IFRAME") follow(el as HTMLIFrameElement);
        else if (el.querySelector && el.querySelector("iframe")) el.querySelectorAll("iframe").forEach((f) => follow(f as HTMLIFrameElement));
      }
      // While the page is still being parsed, everything is "added": only
      // frames matter then.
      if (doc.readyState === "loading") return;
      const d = el.matches && el.matches(DIALOG) ? el : el.querySelector ? el.querySelector(DIALOG) : null;
      if (d) dialogShown(d, added);
      if (added) {
        const t = el.matches && el.matches(TOAST) ? el : el.querySelector ? el.querySelector(TOAST) : null;
        if (t) send("message", "Message: " + clip((t as HTMLElement).innerText || t.textContent, 70));
      }
    };
    const start = () => {
      try {
        doc.querySelectorAll("iframe").forEach((f) => follow(f as HTMLIFrameElement));
        const MO = (win as unknown as { MutationObserver?: typeof MutationObserver }).MutationObserver;
        if (!MO) return;
        new MO((list) => {
          try {
            list.forEach((m) => {
              if (m.type === "attributes") {
                const el = m.target as Element;
                // <dialog> (the schedule's own pop-ups) opens and closes in
                // place; other pop-ups show and hide with `hidden`.
                if (el.tagName === "DIALOG" && m.attributeName === "open") {
                  if (el.hasAttribute("open") !== (m.oldValue !== null)) dialogShown(el, el.hasAttribute("open"));
                } else if (m.attributeName === "hidden" && el.matches && el.matches(DIALOG)) {
                  dialogShown(el, !el.hasAttribute("hidden"));
                }
                return;
              }
              m.addedNodes.forEach((n) => look(n, true));
              m.removedNodes.forEach((n) => look(n, false));
            });
          } catch (x) {
            /* ignore */
          }
        }).observe(doc.documentElement, { subtree: true, childList: true, attributes: true, attributeFilter: ["open", "hidden"], attributeOldValue: true });
      } catch (x) {
        /* ignore */
      }
    };
    if (doc.documentElement) start();
    else doc.addEventListener("DOMContentLoaded", start);
  } catch (e) {
    /* never break the page */
  }
}
