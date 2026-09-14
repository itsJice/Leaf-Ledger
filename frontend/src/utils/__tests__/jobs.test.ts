import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const apiFetch = vi.hoisted(() => vi.fn());
vi.mock("../apiFetch", () => ({ apiFetch }));

import * as jobs from "../jobs";

const H = { "content-type": "application/json" };
const ok = (body: unknown = {}) => new Response(JSON.stringify(body), { status: 200, headers: H });

beforeEach(() => {
  apiFetch.mockReset();
  apiFetch.mockImplementation(async () => ok({ ok: true }));
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("constants", () => {
  it("pins stages and labels", () => {
    expect(jobs.STAGES).toEqual(["new", "sourcing", "ordered", "receiving", "complete"]);
    expect(jobs.STAGE_LABEL).toEqual({ new: "New", sourcing: "Sourcing", ordered: "Ordered", receiving: "Receiving", complete: "Complete" });
    expect(jobs.SOURCING_LABEL).toEqual({
      proposed: "Proposed",
      ready: "Ready to order",
      ordered: "On order",
      follow_up: "Follow-up",
      allocated: "Allocated",
      sold_out: "Sold out",
      on_hold: "On hold",
    });
    expect(jobs.exportUrl(7)).toBe("/api/jobs/7/export?format=xlsx");
  });
});

describe("API routes", () => {
  const GET = (url: string) => [url, { credentials: "include" }];
  const DEL = (url: string) => [url, { credentials: "include", method: "DELETE" }];
  const POST = (url: string, body: unknown) => [url, { credentials: "include", method: "POST", headers: H, body: JSON.stringify(body) }];
  const PATCH = (url: string, body: unknown) => [url, { credentials: "include", method: "PATCH", headers: H, body: JSON.stringify(body) }];

  const cases: [string, () => Promise<unknown>, unknown[]][] = [
    ["listJobs", () => jobs.listJobs(), GET("/api/jobs/list")],
    ["getJob", () => jobs.getJob(3), GET("/api/jobs/3")],
    ["createJob", () => jobs.createJob({ name: "A" }), POST("/api/jobs/create", { name: "A" })],
    ["updateJob", () => jobs.updateJob(3, { notes: "n" }), PATCH("/api/jobs/3", { notes: "n" })],
    ["deleteJob", () => jobs.deleteJob(3), DEL("/api/jobs/3")],
    ["touchJob", () => jobs.touchJob(3), POST("/api/jobs/3/touch", {})],
    ["addNeeds", () => jobs.addNeeds(3, [{ label: "x" }]), POST("/api/jobs/3/needs", { needs: [{ label: "x" }] })],
    ["updateNeed", () => jobs.updateNeed(5, { need_qty: 9 }), PATCH("/api/jobs/needs/5", { need_qty: 9 })],
    ["deleteNeed", () => jobs.deleteNeed(5), DEL("/api/jobs/needs/5")],
    ["addSourcing", () => jobs.addSourcing(5, { sku: "S", unit_cost: 1.5 }), POST("/api/jobs/needs/5/sourcing", { sku: "S", unit_cost: 1.5 })],
    ["updateSourcing", () => jobs.updateSourcing(6, { status: "ready" }), PATCH("/api/jobs/sourcing/6", { status: "ready" })],
    ["deleteSourcing", () => jobs.deleteSourcing(6), DEL("/api/jobs/sourcing/6")],
    ["searchOpenOrders (both)", () => jobs.searchOpenOrders({ product_id: 12, q: "red ball" }), GET("/api/jobs/open-orders/search?product_id=12&q=red+ball")],
    ["searchOpenOrders (product_id 0 dropped)", () => jobs.searchOpenOrders({ product_id: 0, q: "" }), GET("/api/jobs/open-orders/search?")],
    ["allocateFromOrder", () => jobs.allocateFromOrder(5, { order_item_id: 8, qty: 2 }), POST("/api/jobs/needs/5/allocate", { order_item_id: 8, qty: 2 })],
    ["sendToPO", () => jobs.sendToPO(3, { sourcing_line_ids: [1, 2] }), POST("/api/jobs/3/send-to-po", { sourcing_line_ids: [1, 2] })],
    ["openPOsForVendor", () => jobs.openPOsForVendor(9), GET("/api/jobs/vendors/9/open-pos")],
    ["updatePO", () => jobs.updatePO(10, { status: "placed" }), PATCH("/api/jobs/po/10", { status: "placed" })],
    ["poLines", () => jobs.poLines(10), GET("/api/jobs/po/10/lines")],
    ["receiveLine", () => jobs.receiveLine(11, 5, "dented"), POST("/api/jobs/order-items/11/receive", { qty: 5, note: "dented" })],
    ["receiveLine (no note)", () => jobs.receiveLine(11, 5), POST("/api/jobs/order-items/11/receive", { qty: 5 })],
    ["addTask", () => jobs.addTask(3, { title: "Call" }), POST("/api/jobs/3/tasks", { title: "Call" })],
    ["updateTask", () => jobs.updateTask(12, { done: true }), PATCH("/api/jobs/tasks/12", { done: true })],
    ["deleteTask", () => jobs.deleteTask(12), DEL("/api/jobs/tasks/12")],
    ["listBoards", () => jobs.listBoards(), GET("/api/jobs/board-list")],
    ["getBoard", () => jobs.getBoard(3), GET("/api/jobs/3/board")],
    ["getPins", () => jobs.getPins(3), GET("/api/jobs/3/pins")],
    ["addGroup", () => jobs.addGroup(3, "Tall"), POST("/api/jobs/3/groups", { name: "Tall" })],
    ["updateGroup", () => jobs.updateGroup(13, { sort_order: 2 }), PATCH("/api/jobs/groups/13", { sort_order: 2 })],
    ["deleteGroup", () => jobs.deleteGroup(13), DEL("/api/jobs/groups/13")],
    ["pinProduct", () => jobs.pinProduct(3, { product_id: 99, group_id: null }), POST("/api/jobs/3/items", { product_id: 99, group_id: null })],
    ["unpinProduct", () => jobs.unpinProduct(3, 99), DEL("/api/jobs/3/items/by-product/99")],
    ["updatePin", () => jobs.updatePin(14, { clear_group: true }), PATCH("/api/jobs/items/14", { clear_group: true })],
    ["removePin", () => jobs.removePin(14), DEL("/api/jobs/items/14")],
  ];

  for (const [name, run, expected] of cases) {
    it(`${name}`, async () => {
      await expect(run()).resolves.toEqual({ ok: true });
      expect(apiFetch).toHaveBeenCalledTimes(1);
      expect(apiFetch.mock.calls[0]).toEqual(expected);
    });
  }
});

describe("error handling", () => {
  it("throws the server's detail when present", async () => {
    apiFetch.mockResolvedValueOnce(new Response(JSON.stringify({ detail: "Job not found" }), { status: 404, statusText: "Not Found" }));
    await expect(jobs.getJob(1)).rejects.toThrow("Job not found");
  });

  it("falls back to statusText when the body is not JSON or has no detail", async () => {
    apiFetch.mockResolvedValueOnce(new Response("<html>", { status: 502, statusText: "Bad Gateway" }));
    await expect(jobs.getJob(1)).rejects.toThrow("Bad Gateway");
    apiFetch.mockResolvedValueOnce(new Response("{}", { status: 400, statusText: "Bad Request" }));
    await expect(jobs.getJob(1)).rejects.toThrow("Bad Request");
  });

  it("uses 'Request failed' when there is neither detail nor statusText", async () => {
    apiFetch.mockResolvedValueOnce(new Response("{}", { status: 500, statusText: "" }));
    await expect(jobs.getJob(1)).rejects.toThrow("Request failed");
  });
});

describe("downloadExport", () => {
  function stubDom() {
    const anchor = { href: "", download: "", click: vi.fn(), remove: vi.fn() };
    const appendChild = vi.fn();
    vi.stubGlobal("document", { createElement: vi.fn(() => anchor), body: { appendChild } });
    const create = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:fake");
    const revoke = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    return { anchor, appendChild, create, revoke };
  }

  it("fetches the export and clicks a sanitised download link", async () => {
    const dom = stubDom();
    apiFetch.mockResolvedValueOnce(new Response("xlsx-bytes", { status: 200 }));
    await jobs.downloadExport(7, "Smith & Co. — Lobby  Tree!");
    expect(apiFetch).toHaveBeenCalledWith("/api/jobs/7/export?format=xlsx", { credentials: "include" });
    expect(dom.anchor.href).toBe("blob:fake");
    expect(dom.anchor.download).toBe("Smith_Co_Lobby_Tree_tracking.xlsx");
    expect(dom.appendChild).toHaveBeenCalledWith(dom.anchor);
    expect(dom.anchor.click).toHaveBeenCalledTimes(1);
    expect(dom.anchor.remove).toHaveBeenCalledTimes(1);
    expect(dom.revoke).toHaveBeenCalledWith("blob:fake");
  });

  it("names an unprintable job 'job' and throws when the export fails", async () => {
    const dom = stubDom();
    apiFetch.mockResolvedValueOnce(new Response("x", { status: 200 }));
    await jobs.downloadExport(7, "!!!");
    expect(dom.anchor.download).toBe("job_tracking.xlsx");
    apiFetch.mockResolvedValueOnce(new Response("x", { status: 500 }));
    await expect(jobs.downloadExport(7, "A")).rejects.toThrow("Export failed");
  });
});

describe("working job (localStorage)", () => {
  const KEY = "leaf-ledger:working-job:v1";
  let store: Map<string, string>;
  beforeEach(() => {
    store = new Map();
    vi.stubGlobal("localStorage", {
      getItem: (k: string) => (store.has(k) ? store.get(k)! : null),
      setItem: (k: string, v: string) => void store.set(k, v),
    });
  });

  it("reads nulls when missing or corrupt", () => {
    expect(jobs.readWorkingJob()).toEqual({ jobId: null, groupId: null });
    store.set(KEY, "{nope");
    expect(jobs.readWorkingJob()).toEqual({ jobId: null, groupId: null });
  });

  it("coerces ids with Number; falsy ids (0, '') become null", () => {
    store.set(KEY, JSON.stringify({ jobId: "4", groupId: 0 }));
    expect(jobs.readWorkingJob()).toEqual({ jobId: 4, groupId: null });
  });

  // FIX: a non-numeric stored id (e.g. groupId: "x") used to come back as
  // NaN; it must become null like every other invalid/missing id.
  it("a non-numeric id becomes null, not NaN", () => {
    store.set(KEY, JSON.stringify({ jobId: 2, groupId: "x" }));
    expect(jobs.readWorkingJob()).toEqual({ jobId: 2, groupId: null });
  });

  it("writes JSON and swallows storage errors", () => {
    jobs.writeWorkingJob({ jobId: 3, groupId: null });
    expect(store.get(KEY)).toBe('{"jobId":3,"groupId":null}');
    vi.stubGlobal("localStorage", {
      setItem: () => {
        throw new Error("quota");
      },
    });
    expect(() => jobs.writeWorkingJob({ jobId: 1, groupId: 1 })).not.toThrow();
  });
});
