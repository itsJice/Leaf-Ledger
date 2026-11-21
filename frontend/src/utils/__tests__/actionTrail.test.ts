import { describe, expect, it } from "vitest";
import vm from "node:vm";
import { startActionTrail, type TrailAction } from "utils/actionTrail";
import { actionStepType, requestLabel } from "utils/eventLog";
import { ACTION_KINDS, withFrameWatch } from "utils/scheduleFrameWatch";

// No DOM library in this repo's tests, so a small stand-in: just what the
// recorder touches (listeners, closest/getAttribute, labels, pop-ups).
type Attrs = Record<string, string>;
interface FakeEl {
  tagName: string;
  innerText?: string;
  textContent?: string;
  type?: string;
  checked?: boolean;
  value?: string;
  multiple?: boolean;
  selectedIndex?: number;
  options?: { text: string }[];
  labels?: unknown[];
  id?: string;
  getAttribute: (k: string) => string | null;
  closest: (sel: string) => FakeEl | null;
}

function el(tagName: string, attrs: Attrs = {}, extra: Partial<FakeEl> = {}, parent: FakeEl | null = null): FakeEl {
  const self: FakeEl = {
    tagName,
    getAttribute: (k) => (k in attrs ? attrs[k] : null),
    closest: (sel) => {
      if (sel === "[data-no-trail]") return "data-no-trail" in attrs ? self : parent ? parent.closest(sel) : null;
      const roles = /role="([^"]+)"/g;
      const wantRoles: string[] = [];
      let m: RegExpExecArray | null;
      while ((m = roles.exec(sel))) wantRoles.push(m[1]);
      const tags = sel.split(",").map((s) => s.trim().toLowerCase()).filter((s) => /^[a-z]+$/.test(s));
      if (tags.includes(tagName.toLowerCase()) || (attrs.role && wantRoles.includes(attrs.role))) return self;
      return parent ? parent.closest(sel) : null;
    },
    ...extra,
  };
  return self;
}

function fakeWindow() {
  const handlers: Record<string, ((e: unknown) => void)[]> = {};
  const answers: boolean[] = [];
  const doc = {
    documentElement: {},
    addEventListener: (t: string, fn: (e: unknown) => void) => (handlers[t] = handlers[t] || []).push(fn),
    querySelectorAll: () => [],
    getElementById: () => null,
  };
  const win = {
    document: doc,
    alert: (_m?: string): void => undefined,
    confirm: (_m?: string): boolean => answers.shift() ?? true,
    prompt: (_m?: string): string => "typed secret",
  };
  const fire = (type: string, target: unknown) => (handlers[type] || []).forEach((fn) => fn({ target }));
  return { win, fire, answers };
}

function record() {
  const { win, fire, answers } = fakeWindow();
  const got: TrailAction[] = [];
  startActionTrail(win as unknown as Window, (a) => got.push(a));
  return { win, fire, answers, got, labels: () => got.map((a) => a.label) };
}

describe("startActionTrail", () => {
  it("records buttons, links, tabs and menu items by what they say", () => {
    const { fire, labels } = record();
    const btn = el("BUTTON", {}, { innerText: "Move\n(3 stops)" });
    fire("click", el("SPAN", {}, {}, btn));
    fire("click", el("BUTTON", { "aria-label": "Close" }));
    fire("click", el("A", {}, { innerText: "Clients" }));
    fire("click", el("DIV", { role: "tab" }, { innerText: "Staffing" }));
    fire("click", el("DIV", { role: "menuitem" }, { innerText: "Print all" }));
    fire("click", el("DIV")); // not a control
    fire("click", el("BUTTON", { "data-no-trail": "" }, { innerText: "Hidden" }));
    expect(labels()).toEqual(["Pressed Move", "Pressed Close", "Opened link Clients", "Switched to Staffing", "Picked menu item Print all"]);
  });

  it("keeps values only for safe pickers, never typed or private ones", () => {
    const { fire, got, labels } = record();
    const dateSel = el("SELECT", { "aria-label": "Date" }, { selectedIndex: 1, options: [{ text: "Tue 11/17/26" }, { text: "Wed 11/18/26 (already passed)" }] });
    fire("change", dateSel);
    fire("change", el("SELECT", { "aria-label": "Billing address" }, { selectedIndex: 0, options: [{ text: "12 Elm St" }] }));
    fire("change", el("INPUT", { "aria-label": "Install date" }, { type: "date", value: "2026-11-18" }));
    fire("change", el("INPUT", { "aria-label": "Phone" }, { type: "tel", value: "214-555-0100" }));
    fire("change", el("INPUT", { "aria-label": "Password" }, { type: "password", value: "hunter2" }));
    fire("change", el("TEXTAREA", { "aria-label": "Notes" }, { value: "gate code 1234" }));
    fire("change", el("INPUT", { "aria-label": "Hold" }, { type: "checkbox", checked: true }));
    fire("change", el("INPUT", { placeholder: "Client name" }, { type: "text", value: "Michol" }));
    expect(labels()).toEqual([
      "Picked Date: Wed 11/18/26 (already passed)",
      "Changed Billing address",
      "Set Install date: 2026-11-18",
      "Changed Phone",
      "Changed Password",
      "Changed Notes",
      "Ticked Hold",
      "Changed Client name",
    ]);
    const all = JSON.stringify(got);
    for (const secret of ["12 Elm", "214-555", "hunter2", "1234", "Michol"]) expect(all).not.toContain(secret);
  });

  it("records the pop-ups shown and their answers (never a prompt's text)", () => {
    const { win, answers, labels } = record();
    win.alert("Cannot make this change:\n\n  • Michol Ecklund is a joint job");
    answers.push(false);
    expect(win.confirm("This date already passed. Move anyway?")).toBe(false);
    expect(win.prompt("New crew name?")).toBe("typed secret");
    expect(labels()).toEqual([
      "Message: Cannot make this change: • Michol Ecklund is a joint job",
      "Asked: This date already passed. Move anyway? -> Cancel",
      "Asked: New crew name?",
    ]);
  });

  it("records drag and drop", () => {
    const { fire, labels } = record();
    fire("dragstart", el("DIV", { draggable: "true" }, { innerText: "Michol Ecklund\n2.0h" }));
    fire("drop", el("BUTTON", { "data-date": "2026-11-18" }));
    expect(labels()).toEqual(["Dropped Michol Ecklund on 2026-11-18"]);
  });

  it("caps labels and does not flood", () => {
    const { fire, labels } = record();
    const long = el("BUTTON", {}, { innerText: "x".repeat(300) });
    fire("click", long);
    fire("click", long); // same step right away: dropped
    expect(labels()).toHaveLength(1);
    expect(labels()[0].length).toBeLessThanOrEqual(80);
    for (let i = 0; i < 60; i++) fire("click", el("BUTTON", {}, { innerText: `Button ${i}` }));
    expect(labels().length).toBeLessThanOrEqual(25);
  });

  it("starts once per window and never throws", () => {
    const { win } = fakeWindow();
    const got: TrailAction[] = [];
    startActionTrail(win as unknown as Window, (a) => got.push(a));
    startActionTrail(win as unknown as Window, (a) => got.push(a));
    win.alert("once");
    expect(got).toHaveLength(1);
    expect(() => startActionTrail(null as unknown as Window, () => undefined)).not.toThrow();
  });
});

describe("trail labels", () => {
  it("saves say how they went", () => {
    expect(requestLabel("GET", "/api/x", 200)).toBe("GET /api/x 200");
    expect(requestLabel("PUT", "/api/install-schedule/state", 200)).toBe("PUT /api/install-schedule/state 200 (saved)");
    expect(requestLabel("PUT", "/api/install-schedule/state", 409)).toBe("PUT /api/install-schedule/state 409 (not saved)");
  });
  it("maps actions onto step types", () => {
    expect(["click", "tab", "menu", "pick", "dialog", "error"].map(actionStepType)).toEqual(["click", "click", "click", "action", "action", "error"]);
  });
});

describe("the Install Schedule frame", () => {
  it("runs the same recorder inside the frame and posts each step to the app", () => {
    const html = withFrameWatch("<head></head>");
    const script = html.slice(html.indexOf("<script>") + 8, html.indexOf("</script>"));
    const posted: { type: string; action?: string; label?: string }[] = [];
    const { win, fire } = fakeWindow();
    const frameWin = { ...win, parent: { postMessage: (m: never) => posted.push(m) }, addEventListener: () => undefined, fetch: undefined };
    vm.runInNewContext(script, { window: frameWin, Date, String });
    fire("click", el("BUTTON", {}, { innerText: "Move" }));
    frameWin.confirm("This date already passed. Move anyway?");
    expect(posted).toEqual([
      { type: "ll-frame-step", action: "click", label: "Pressed Move" },
      { type: "ll-frame-step", action: "ask", label: "Asked: This date already passed. Move anyway? -> OK" },
    ]);
    expect(posted.every((p) => ACTION_KINDS.has(p.action || ""))).toBe(true);
  });
});
