import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const apiFetch = vi.hoisted(() => vi.fn());
vi.mock("../apiFetch", () => ({ apiFetch }));

type Mod = typeof import("../theme");

function fakeDom(opts: { dark?: boolean; accent?: string | null; prefersDark?: boolean; matchMediaThrows?: boolean } = {}) {
  const classes = new Set<string>(opts.dark ? ["dark"] : []);
  let accent: string | null = opts.accent ?? null;
  const root = {
    classList: {
      contains: (c: string) => classes.has(c),
      toggle: vi.fn((c: string, force: boolean) => {
        if (force) classes.add(c);
        else classes.delete(c);
        return force;
      }),
    },
    getAttribute: vi.fn((name: string) => (name === "data-accent" ? accent : null)),
    setAttribute: vi.fn((name: string, value: string) => {
      if (name === "data-accent") accent = value;
    }),
  };
  const media = { matches: !!opts.prefersDark, addEventListener: vi.fn() };
  const matchMedia = vi.fn(() => {
    if (opts.matchMediaThrows) throw new Error("no matchMedia");
    return media;
  });
  vi.stubGlobal("document", { documentElement: root });
  vi.stubGlobal("window", { matchMedia });
  return { root, classes, media, matchMedia, accent: () => accent };
}

async function freshModule(): Promise<Mod> {
  vi.resetModules();
  return import("../theme");
}

beforeEach(() => {
  apiFetch.mockReset();
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("theme constants", () => {
  it("pins accents and the default", async () => {
    const mod = await freshModule();
    expect(mod.THEME_ACCENTS.map((a) => [a.key, a.label, a.swatch])).toEqual([
      ["emerald", "Emerald", "#059669"],
      ["teal", "Teal", "#0d9488"],
      ["sky", "Sky", "#0284c7"],
      ["indigo", "Indigo", "#4f46e5"],
      ["rose", "Rose", "#be123c"],
      ["amber", "Amber", "#b45309"],
    ]);
    expect(mod.DEFAULT_ACCENT).toBe("emerald");
    expect(mod.THEME_ACCENTS[0].key).toBe(mod.DEFAULT_ACCENT);
  });

  it("DEFAULT_ACCENT matches the preferences default", async () => {
    const mod = await freshModule();
    const prefs = await import("../preferences");
    expect(prefs.DEFAULT_PREFERENCES.theme.accent).toBe(mod.DEFAULT_ACCENT);
  });
});

describe("applyTheme", () => {
  it("is a no-op without a DOM (node)", async () => {
    const mod = await freshModule();
    expect(() => mod.applyTheme("dark", "rose")).not.toThrow();
  });

  it("explicit dark + known accent", async () => {
    const dom = fakeDom();
    const mod = await freshModule();
    mod.applyTheme("dark", "rose");
    expect(dom.root.classList.toggle).toHaveBeenCalledWith("dark", true);
    expect(dom.root.setAttribute).toHaveBeenCalledWith("data-accent", "rose");
  });

  it("normalises mode (trim/case) and unknown accents to the default", async () => {
    const dom = fakeDom({ dark: true, accent: "rose" });
    const mod = await freshModule();
    mod.applyTheme(" LIGHT " as never, "  neon ");
    expect(dom.classes.has("dark")).toBe(false);
    expect(dom.accent()).toBe("emerald");
    mod.applyTheme("weird" as never, " teal ");
    // unknown mode -> system -> resolved from prefers-color-scheme (light here)
    expect(dom.classes.has("dark")).toBe(false);
    expect(dom.accent()).toBe("teal");
  });

  it("system mode follows prefers-color-scheme and watches the OS once", async () => {
    const dom = fakeDom({ prefersDark: true });
    const mod = await freshModule();
    mod.applyTheme("system", "sky");
    mod.applyTheme("system", "sky");
    expect(dom.classes.has("dark")).toBe(true);
    expect(dom.media.addEventListener).toHaveBeenCalledTimes(1);
    expect(dom.media.addEventListener).toHaveBeenCalledWith("change", expect.any(Function));
  });

  it("does not rewrite an unchanged data-accent", async () => {
    const dom = fakeDom({ accent: "amber" });
    const mod = await freshModule();
    mod.applyTheme("light", "amber");
    expect(dom.root.setAttribute).not.toHaveBeenCalled();
  });

  it("assumes light when matchMedia throws", async () => {
    const dom = fakeDom({ dark: true, matchMediaThrows: true });
    const mod = await freshModule();
    mod.applyTheme("system", "emerald");
    expect(dom.classes.has("dark")).toBe(false);
  });
});
