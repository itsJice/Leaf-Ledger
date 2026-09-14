import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const apiFetch = vi.hoisted(() => vi.fn());
vi.mock("../apiFetch", () => ({ apiFetch }));

type Mod = typeof import("../supplierDirectory");
let mod: Mod;

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

beforeEach(async () => {
  vi.resetModules();
  apiFetch.mockReset();
  mod = await import("../supplierDirectory");
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("supplier directory cache", () => {
  it("fetches the list once and keys it by id", async () => {
    apiFetch.mockResolvedValue(json([{ id: 2, name: "Vickerman", has_credentials: true }, { id: 9, name: "Other" }]));
    const dir = await mod.loadSupplierDirectory();
    expect(apiFetch).toHaveBeenCalledWith("/api/suppliers/list", { credentials: "include" });
    expect(dir).toEqual({ 2: { id: 2, name: "Vickerman", has_credentials: true }, 9: { id: 9, name: "Other" } });
  });

  it("returns the same promise until invalidated", async () => {
    apiFetch.mockImplementation(async () => json([{ id: 1 }]));
    const a = mod.loadSupplierDirectory();
    expect(mod.loadSupplierDirectory()).toBe(a);
    await a;
    expect(apiFetch).toHaveBeenCalledTimes(1);
    mod.invalidateSupplierDirectory();
    const b = mod.loadSupplierDirectory();
    expect(b).not.toBe(a);
    await b;
    expect(apiFetch).toHaveBeenCalledTimes(2);
  });

  it("degrades to {} on non-ok, null body, or a rejected fetch — and caches that result", async () => {
    apiFetch.mockResolvedValueOnce(json({ detail: "nope" }, 500));
    await expect(mod.loadSupplierDirectory()).resolves.toEqual({});
    mod.invalidateSupplierDirectory();
    apiFetch.mockResolvedValueOnce(json(null));
    await expect(mod.loadSupplierDirectory()).resolves.toEqual({});
    mod.invalidateSupplierDirectory();
    apiFetch.mockRejectedValueOnce(new Error("offline"));
    await expect(mod.loadSupplierDirectory()).resolves.toEqual({});
    // The failure is cached: no retry until invalidated.
    await expect(mod.loadSupplierDirectory()).resolves.toEqual({});
    expect(apiFetch).toHaveBeenCalledTimes(3);
  });

  it("exports the credentials-changed event name", () => {
    expect(mod.SUPPLIER_CREDENTIALS_CHANGED_EVENT).toBe("leaf-ledger-supplier-credentials-changed");
  });

  it("registers invalidation on the window event when a window exists", async () => {
    const addEventListener = vi.fn();
    vi.stubGlobal("window", { addEventListener });
    vi.resetModules();
    const fresh = await import("../supplierDirectory");
    expect(addEventListener).toHaveBeenCalledWith("leaf-ledger-supplier-credentials-changed", fresh.invalidateSupplierDirectory);
  });
});
