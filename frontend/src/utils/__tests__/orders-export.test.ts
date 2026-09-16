import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const apiFetch = vi.hoisted(() => vi.fn());
vi.mock("../apiFetch", () => ({ apiFetch }));

import * as orders from "../orders";

beforeEach(() => {
  apiFetch.mockReset();
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function stubDom() {
  const anchor = { href: "", download: "", click: vi.fn(), remove: vi.fn() };
  const appendChild = vi.fn();
  vi.stubGlobal("document", { createElement: vi.fn(() => anchor), body: { appendChild } });
  const create = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:fake");
  const revoke = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
  return { anchor, appendChild, create, revoke };
}

describe("orderExportUrl", () => {
  it("carries the format, and the vendor only on a single-vendor PO", () => {
    expect(orders.orderExportUrl(10, "pdf")).toBe("/api/orders/10/export?format=pdf");
    expect(orders.orderExportUrl(10, "xlsx", 4)).toBe("/api/orders/10/export?format=xlsx&supplier_id=4");
  });
});

describe("exportFileName", () => {
  it("strips punctuation and appends the vendor", () => {
    expect(orders.exportFileName("Holiday  Order!")).toBe("Holiday_Order");
    expect(orders.exportFileName("Holiday Order", "Regency & Co.")).toBe("Holiday_Order_Regency_Co");
    expect(orders.exportFileName("")).toBe("order");
  });
});

describe("downloadOrderExport", () => {
  // The bug this pins: a plain <a href> to /api sends no Authorization header
  // and the download comes back 401 "Not signed in".
  it("goes through apiFetch and clicks a blob link", async () => {
    const dom = stubDom();
    apiFetch.mockResolvedValueOnce(new Response("pdf-bytes", { status: 200 }));
    await orders.downloadOrderExport(10, "pdf", "Holiday Order");
    expect(apiFetch).toHaveBeenCalledWith("/api/orders/10/export?format=pdf", { credentials: "include" });
    expect(dom.anchor.href).toBe("blob:fake");
    expect(dom.anchor.download).toBe("Holiday_Order.pdf");
    expect(dom.anchor.click).toHaveBeenCalledTimes(1);
    expect(dom.anchor.remove).toHaveBeenCalledTimes(1);
    expect(dom.revoke).toHaveBeenCalledWith("blob:fake");
  });

  it("names a single-vendor PO after the vendor", async () => {
    const dom = stubDom();
    apiFetch.mockResolvedValueOnce(new Response("pdf-bytes", { status: 200 }));
    await orders.downloadOrderExport(10, "pdf", "Holiday Order", 4, "Regency");
    expect(apiFetch).toHaveBeenCalledWith("/api/orders/10/export?format=pdf&supplier_id=4", { credentials: "include" });
    expect(dom.anchor.download).toBe("Holiday_Order_Regency.pdf");
  });

  it("throws when the export fails, so the page can say so", async () => {
    stubDom();
    apiFetch.mockResolvedValueOnce(new Response("nope", { status: 401 }));
    await expect(orders.downloadOrderExport(10, "pdf", "Holiday Order")).rejects.toThrow("Export failed");
  });
});
