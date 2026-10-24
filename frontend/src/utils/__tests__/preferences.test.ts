import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const apiFetch = vi.hoisted(() => vi.fn());
vi.mock("../apiFetch", () => ({ apiFetch }));

type Mod = typeof import("../preferences");

const KEY = "ll.preferences.v1";
let store: Map<string, string>;

async function freshModule(): Promise<Mod> {
  vi.resetModules();
  return import("../preferences");
}

beforeEach(() => {
  apiFetch.mockReset();
  store = new Map();
  vi.stubGlobal("window", {
    localStorage: {
      getItem: (k: string) => (store.has(k) ? store.get(k)! : null),
      setItem: (k: string, v: string) => void store.set(k, v),
    },
  });
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("constants", () => {
  it("pins defaults, pinned paths and the cache key", async () => {
    const mod = await freshModule();
    expect(mod.DEFAULT_PREFERENCES).toEqual({ sidebar: { order: [], hidden: [] }, theme: { mode: "system", accent: "emerald" } });
    expect(mod.PINNED_PATHS).toEqual(["/", "/settings"]);
    expect(mod.PREFERENCES_CACHE_KEY).toBe(KEY);
  });
});

describe("readCachedPreferences (normalisation)", () => {
  it("returns fresh default copies when nothing is cached", async () => {
    const mod = await freshModule();
    const prefs = mod.readCachedPreferences();
    expect(prefs).toEqual(mod.DEFAULT_PREFERENCES);
    expect(prefs.sidebar).not.toBe(mod.DEFAULT_PREFERENCES.sidebar);
    expect(prefs.theme).not.toBe(mod.DEFAULT_PREFERENCES.theme);
  });

  it("falls back to defaults on corrupt JSON, non-object roots, or no window", async () => {
    const mod = await freshModule();
    for (const raw of ["{bad", "[1,2]", "42", "null", '"str"']) {
      store.set(KEY, raw);
      expect(mod.readCachedPreferences()).toEqual(mod.DEFAULT_PREFERENCES);
    }
    vi.unstubAllGlobals();
    expect(mod.readCachedPreferences()).toEqual(mod.DEFAULT_PREFERENCES);
  });

  it("trims, de-duplicates and strips un-hideable paths; normalises theme", async () => {
    const mod = await freshModule();
    store.set(
      KEY,
      JSON.stringify({
        sidebar: { order: [" /a ", "/a", 3, "", "/b"], hidden: ["/", "/Settings/", "/x", "  ", "//", "/settings"] },
        theme: { mode: " DARK ", accent: " rose " },
        extra: true,
      }),
    );
    expect(mod.readCachedPreferences()).toEqual({
      sidebar: { order: ["/a", "/b"], hidden: ["/x"] },
      theme: { mode: "dark", accent: "rose" },
    });
  });

  it("drops invalid subtrees/values but keeps valid siblings (accent is not validated here)", async () => {
    const mod = await freshModule();
    store.set(KEY, JSON.stringify({ sidebar: [], theme: { mode: "blue", accent: "not-a-palette" } }));
    expect(mod.readCachedPreferences()).toEqual({ sidebar: { order: [], hidden: [] }, theme: { mode: "system", accent: "not-a-palette" } });
    store.set(KEY, JSON.stringify({ sidebar: { order: "x", hidden: ["/y"] }, theme: { mode: "light", accent: "" } }));
    expect(mod.readCachedPreferences()).toEqual({ sidebar: { order: [], hidden: ["/y"] }, theme: { mode: "light", accent: "emerald" } });
  });
});

describe("savePreferences / resetPreferences", () => {
  it("applies optimistically, then coalesces patches into one debounced PUT", async () => {
    vi.useFakeTimers();
    apiFetch.mockImplementation(async () => new Response("{}", { status: 401 }));
    const mod = await freshModule();
    mod.savePreferences({ theme: { mode: "dark" } });
    mod.savePreferences({ sidebar: { hidden: ["/settings", "/designs"] } });
    expect(JSON.parse(store.get(KEY)!)).toEqual({ sidebar: { order: [], hidden: ["/designs"] }, theme: { mode: "dark", accent: "emerald" } });
    expect(apiFetch).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(399);
    expect(apiFetch).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(apiFetch).toHaveBeenCalledTimes(1);
    expect(apiFetch).toHaveBeenCalledWith("/api/preferences", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: '{"theme":{"mode":"dark"},"sidebar":{"hidden":["/designs"]}}',
      keepalive: false,
    });
  });

  it("ignores patches that normalise to nothing", async () => {
    vi.useFakeTimers();
    const mod = await freshModule();
    mod.savePreferences({});
    mod.savePreferences({ theme: { mode: "sepia" as never } });
    await vi.advanceTimersByTimeAsync(1000);
    expect(store.has(KEY)).toBe(false);
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it("resetPreferences writes defaults and PUTs the full default document", async () => {
    vi.useFakeTimers();
    apiFetch.mockImplementation(async () => new Response("{}", { status: 500 }));
    store.set(KEY, JSON.stringify({ theme: { mode: "dark", accent: "rose" } }));
    const mod = await freshModule();
    mod.resetPreferences();
    expect(JSON.parse(store.get(KEY)!)).toEqual(mod.DEFAULT_PREFERENCES);
    await vi.advanceTimersByTimeAsync(400);
    expect(apiFetch.mock.calls[0][1].body).toBe('{"sidebar":{"order":[],"hidden":[],"pinned":null},"theme":{"mode":"system","accent":"emerald"}}');
  });
});

describe("sidebar.pinned (keep the menu open)", () => {
  it("is absent by default, which means automatic", async () => {
    const mod = await freshModule();
    expect(mod.readCachedPreferences().sidebar).toEqual({ order: [], hidden: [] });
    expect("pinned" in mod.readCachedPreferences().sidebar).toBe(false);
  });

  it("keeps true/false from the cache and drops junk", async () => {
    const mod = await freshModule();
    store.set(KEY, JSON.stringify({ sidebar: { pinned: false } }));
    expect(mod.readCachedPreferences().sidebar.pinned).toBe(false);
    store.set(KEY, JSON.stringify({ sidebar: { pinned: true } }));
    expect(mod.readCachedPreferences().sidebar.pinned).toBe(true);
    for (const junk of ["yes", 1, 0, [], {}]) {
      store.set(KEY, JSON.stringify({ sidebar: { pinned: junk, hidden: ["/x"] } }));
      expect(mod.readCachedPreferences().sidebar).toEqual({ order: [], hidden: ["/x"] });
    }
    store.set(KEY, JSON.stringify({ sidebar: { pinned: null } }));
    expect("pinned" in mod.readCachedPreferences().sidebar).toBe(false);
  });

  it("saves optimistically and PUTs only the pin, leaving order alone", async () => {
    vi.useFakeTimers();
    apiFetch.mockImplementation(async () => new Response("{}", { status: 401 }));
    store.set(KEY, JSON.stringify({ sidebar: { order: ["/designs", "/"], hidden: ["/x"] } }));
    const mod = await freshModule();
    mod.savePreferences({ sidebar: { pinned: false } });
    expect(JSON.parse(store.get(KEY)!).sidebar).toEqual({ order: ["/designs", "/"], hidden: ["/x"], pinned: false });
    await vi.advanceTimersByTimeAsync(400);
    expect(apiFetch.mock.calls[0][1].body).toBe('{"sidebar":{"pinned":false}}');
  });

  it("null clears it locally but still reaches the server as null", async () => {
    vi.useFakeTimers();
    apiFetch.mockImplementation(async () => new Response("{}", { status: 401 }));
    store.set(KEY, JSON.stringify({ sidebar: { pinned: true } }));
    const mod = await freshModule();
    mod.savePreferences({ sidebar: { pinned: false } });
    mod.savePreferences({ sidebar: { pinned: null } });
    expect("pinned" in JSON.parse(store.get(KEY)!).sidebar).toBe(false);
    await vi.advanceTimersByTimeAsync(400);
    expect(apiFetch).toHaveBeenCalledTimes(1);
    expect(apiFetch.mock.calls[0][1].body).toBe('{"sidebar":{"pinned":null}}');
  });

  it("adopts the server's answer after a save", async () => {
    vi.useFakeTimers();
    apiFetch.mockImplementation(async () => new Response(
      JSON.stringify({ sidebar: { order: [], hidden: [], pinned: true }, theme: { mode: "system", accent: "emerald" } }),
      { status: 200, headers: { "content-type": "application/json" } },
    ));
    const mod = await freshModule();
    mod.savePreferences({ sidebar: { pinned: true } });
    await vi.advanceTimersByTimeAsync(400);
    expect(JSON.parse(store.get(KEY)!).sidebar.pinned).toBe(true);
  });
});
