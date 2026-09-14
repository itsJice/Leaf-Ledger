import { beforeEach, describe, expect, it, vi } from "vitest";

const apiFetch = vi.hoisted(() => vi.fn());
vi.mock("../apiFetch", () => ({ apiFetch }));

import { EMPTY_FACETS, designListParams, fetchDesignList } from "../designs";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
const html = (status = 200) => new Response("<html></html>", { status, headers: { "content-type": "text/html" } });

beforeEach(() => {
  apiFetch.mockReset();
});

describe("designListParams", () => {
  it("is empty for an empty query", () => {
    expect(designListParams({})).toBe("");
  });

  it("serialises every field in a fixed order; arrays as CSV; empties skipped", () => {
    expect(
      designListParams({
        offset: 20,
        limit: 0,
        sort: "cost",
        materials: [],
        build_types: ["tree"],
        groups: ["G 1"],
        projects: ["P"],
        clients: ["A", "B&C"],
        search: "red tree",
      }),
    ).toBe("search=red+tree&clients=A%2CB%26C&projects=P&groups=G+1&build_types=tree&sort=cost&limit=0&offset=20");
    expect(designListParams({ search: "", clients: [] })).toBe("");
  });
});

describe("fetchDesignList", () => {
  it("calls the list endpoint (trailing ? with no params)", async () => {
    apiFetch.mockResolvedValue(json({ items: [], total: 0 }));
    await fetchDesignList();
    expect(apiFetch).toHaveBeenCalledWith("/api/designs/list?");
    await fetchDesignList({ search: "x", limit: 5 });
    expect(apiFetch).toHaveBeenLastCalledWith("/api/designs/list?search=x&limit=5");
  });

  it("normalises facets and total", async () => {
    apiFetch.mockResolvedValue(
      json({
        items: [{ id: 1, name: "A" }, { id: 2, name: "B" }],
        total: 40,
        facets: {
          clients: ["Acme", { value: "Beta", count: "3" }, { value: null, count: 2 }, { value: "Gamma", count: "x" }],
          projects: "nope",
          groups: [{ value: 7 }],
        },
      }),
    );
    await expect(fetchDesignList()).resolves.toEqual({
      items: [{ id: 1, name: "A" }, { id: 2, name: "B" }],
      total: 40,
      facets: {
        clients: [
          { value: "Acme", count: 0 },
          { value: "Beta", count: 3 },
          { value: "Gamma", count: 0 },
        ],
        projects: [],
        groups: [{ value: "7", count: 0 }],
        build_types: [],
        materials: [],
      },
    });
  });

  it("falls back to items.length when total is missing, zero or non-numeric", async () => {
    const items = [{ id: 1, name: "A" }];
    for (const total of [undefined, 0, "abc"]) {
      apiFetch.mockResolvedValueOnce(json({ items, total }));
      expect((await fetchDesignList()).total).toBe(1);
    }
    apiFetch.mockResolvedValueOnce(json({ items: "bad" }));
    expect(await fetchDesignList()).toEqual({ items: [], total: 0, facets: EMPTY_FACETS });
  });

  it("resolves to the shared empty list on non-ok, HTML, null body or network error", async () => {
    apiFetch.mockResolvedValueOnce(json({}, 404));
    const a = await fetchDesignList();
    expect(a).toEqual({ items: [], total: 0, facets: EMPTY_FACETS });
    apiFetch.mockResolvedValueOnce(html());
    expect(await fetchDesignList()).toBe(a);
    apiFetch.mockRejectedValueOnce(new Error("offline"));
    expect(await fetchDesignList()).toBe(a);
    apiFetch.mockResolvedValueOnce(json(null));
    expect(await fetchDesignList()).toEqual({ items: [], total: 0, facets: EMPTY_FACETS });
  });
});
