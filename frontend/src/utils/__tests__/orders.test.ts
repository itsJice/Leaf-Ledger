import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const apiFetch = vi.hoisted(() => vi.fn());
vi.mock("../apiFetch", () => ({ apiFetch }));

import {
  ORDER_STATUSES,
  addToOrder,
  createOrder,
  defaultOrderName,
  deleteOrder,
  ensureActiveOrder,
  getActiveOrderId,
  getOrder,
  listOrders,
  removeItem,
  renameOrder,
  setActiveOrderId,
  setOrderStatus,
  updateItemQty,
} from "../orders";

const ACTIVE_KEY = "leaf-ledger:active-order:v1";
const JSON_HEADERS = { "content-type": "application/json" };
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

let store: Map<string, string>;
beforeEach(() => {
  apiFetch.mockReset();
  store = new Map();
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => (store.has(k) ? store.get(k)! : null),
    setItem: (k: string, v: string) => void store.set(k, String(v)),
  });
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("constants and active order pointer", () => {
  it("pins ORDER_STATUSES", () => {
    expect(ORDER_STATUSES).toEqual(["draft", "approved", "placed", "follow_up", "shipped", "arrived", "closed"]);
  });

  it("get/setActiveOrderId round-trip through localStorage", () => {
    expect(getActiveOrderId()).toBeNull();
    setActiveOrderId(42);
    expect(store.get(ACTIVE_KEY)).toBe("42");
    expect(getActiveOrderId()).toBe(42);
    store.set(ACTIVE_KEY, "0");
    expect(getActiveOrderId()).toBe(0);
    store.set(ACTIVE_KEY, "abc");
    expect(getActiveOrderId()).toBeNaN();
  });

  it("defaultOrderName uses today's short month/day (pinned as UTC, en-US)", () => {
    // toLocaleDateString(undefined, ...) is machine locale + timezone dependent;
    // pinned here with UTC and an en-US default injected.
    const orig = Date.prototype.toLocaleDateString;
    vi.spyOn(Date.prototype, "toLocaleDateString").mockImplementation(function (this: Date, l?: string | string[], o?: Intl.DateTimeFormatOptions) {
      return orig.call(this, l ?? "en-US", { ...o, timeZone: "UTC" });
    });
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-13T12:00:00Z"));
    expect(defaultOrderName()).toBe("Order — Sep 13");
  });
});

describe("order API calls", () => {
  it("setOrderStatus PATCHes the status", async () => {
    apiFetch.mockResolvedValue(json({}));
    await setOrderStatus(5, "placed");
    expect(apiFetch).toHaveBeenCalledWith("/api/orders/5", {
      method: "PATCH",
      credentials: "include",
      headers: JSON_HEADERS,
      body: '{"status":"placed"}',
    });
  });

  it("listOrders GETs the list; non-ok resolves to []", async () => {
    apiFetch.mockResolvedValueOnce(json([{ id: 1 }]));
    await expect(listOrders()).resolves.toEqual([{ id: 1 }]);
    expect(apiFetch).toHaveBeenCalledWith("/api/orders/list", { credentials: "include" });
    apiFetch.mockResolvedValueOnce(json({ detail: "x" }, 401));
    await expect(listOrders()).resolves.toEqual([]);
  });

  it("createOrder POSTs name + created_by (undefined dropped by JSON)", async () => {
    apiFetch.mockImplementation(async () => json({ id: 3 }));
    await expect(createOrder("Lobby", "sam")).resolves.toEqual({ id: 3 });
    expect(apiFetch).toHaveBeenCalledWith("/api/orders/create", {
      method: "POST",
      credentials: "include",
      headers: JSON_HEADERS,
      body: '{"name":"Lobby","created_by":"sam"}',
    });
    await createOrder("Lobby");
    expect(apiFetch.mock.calls[1][1].body).toBe('{"name":"Lobby"}');
  });

  it("getOrder returns the body or throws 'Order not found'", async () => {
    apiFetch.mockResolvedValueOnce(json({ id: 7, vendors: [] }));
    await expect(getOrder(7)).resolves.toEqual({ id: 7, vendors: [] });
    expect(apiFetch).toHaveBeenCalledWith("/api/orders/7", { credentials: "include" });
    apiFetch.mockResolvedValueOnce(json({}, 404));
    await expect(getOrder(7)).rejects.toThrow("Order not found");
  });

  it("item and order mutations hit the expected routes", async () => {
    apiFetch.mockResolvedValue(json({}));
    await addToOrder(1, 2, 3, "sam");
    await addToOrder(1, 2, 3);
    await updateItemQty(9, 12);
    await removeItem(9);
    await renameOrder(4, "New");
    await deleteOrder(4);
    expect(apiFetch.mock.calls).toEqual([
      ["/api/orders/1/items", { method: "POST", credentials: "include", headers: JSON_HEADERS, body: '{"product_id":2,"quantity":3,"added_by":"sam"}' }],
      ["/api/orders/1/items", { method: "POST", credentials: "include", headers: JSON_HEADERS, body: '{"product_id":2,"quantity":3}' }],
      ["/api/orders/items/9", { method: "PATCH", credentials: "include", headers: JSON_HEADERS, body: '{"quantity":12}' }],
      ["/api/orders/items/9", { method: "DELETE", credentials: "include" }],
      ["/api/orders/4", { method: "PATCH", credentials: "include", headers: JSON_HEADERS, body: '{"name":"New"}' }],
      ["/api/orders/4", { method: "DELETE", credentials: "include" }],
    ]);
  });
});

describe("ensureActiveOrder", () => {
  it("returns the remembered active order when it still exists", async () => {
    store.set(ACTIVE_KEY, "2");
    apiFetch.mockResolvedValueOnce(json([{ id: 1 }, { id: 2 }]));
    await expect(ensureActiveOrder()).resolves.toEqual({ id: 2 });
    expect(apiFetch).toHaveBeenCalledTimes(1);
    expect(store.get(ACTIVE_KEY)).toBe("2");
  });

  it("falls back to the first listed order and remembers it", async () => {
    store.set(ACTIVE_KEY, "99");
    apiFetch.mockResolvedValueOnce(json([{ id: 5 }, { id: 2 }]));
    await expect(ensureActiveOrder()).resolves.toEqual({ id: 5 });
    expect(store.get(ACTIVE_KEY)).toBe("5");
  });

  it("creates a dated order when there are none", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-13T12:00:00Z"));
    const expectedName = defaultOrderName();
    apiFetch.mockResolvedValueOnce(json([])).mockResolvedValueOnce(json({ id: 11, name: expectedName }));
    await expect(ensureActiveOrder("sam")).resolves.toEqual({ id: 11, name: expectedName });
    expect(apiFetch.mock.calls[1]).toEqual([
      "/api/orders/create",
      { method: "POST", credentials: "include", headers: JSON_HEADERS, body: JSON.stringify({ name: expectedName, created_by: "sam" }) },
    ]);
    expect(store.get(ACTIVE_KEY)).toBe("11");
  });
});
