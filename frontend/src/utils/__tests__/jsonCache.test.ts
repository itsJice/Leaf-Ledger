/* eslint-disable @typescript-eslint/no-explicit-any */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { clearStorage, memoryStorage, seedStorage } from "../../test/setup";
import { readJsonCache, writeJsonCache, writeTimestampedJsonCache } from "../jsonCache";
import * as C from "./inline-copies-3a";

const K = "test:cache";

beforeEach(() => {
  clearStorage();
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe("readJsonCache / writeJsonCache basics", () => {
  it("returns the fallback for a missing key, an empty string and corrupt JSON", () => {
    expect(readJsonCache(K, "fb")).toBe("fb");
    seedStorage({ [K]: "" });
    expect(readJsonCache(K, "fb")).toBe("fb");
    seedStorage({ [K]: "{not json" });
    expect(readJsonCache(K, "fb")).toBe("fb");
  });

  it("returns parsed JSON as-is, including a stored null (no shape check)", () => {
    seedStorage({ [K]: "null" });
    expect(readJsonCache(K, "fb")).toBeNull();
    seedStorage({ [K]: { a: [1] } });
    expect(readJsonCache(K, null)).toEqual({ a: [1] });
  });

  it("returns the fallback when getItem throws (storage unavailable)", () => {
    vi.spyOn(memoryStorage, "getItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });
    expect(readJsonCache(K, [])).toEqual([]);
  });

  it("round-trips a value", () => {
    writeJsonCache(K, { x: 1, y: [2] });
    expect(memoryStorage.getItem(K)).toBe('{"x":1,"y":[2]}');
  });

  it("swallows a throwing setItem (quota) and a circular value", () => {
    vi.spyOn(memoryStorage, "setItem").mockImplementation(() => {
      throw new Error("QuotaExceededError");
    });
    expect(() => writeJsonCache(K, [1])).not.toThrow();
    expect(() => writeTimestampedJsonCache(K, { a: 1 })).not.toThrow();
    vi.restoreAllMocks();
    const circular: any = {};
    circular.self = circular;
    expect(() => writeJsonCache(K, circular)).not.toThrow();
    expect(memoryStorage.getItem(K)).toBeNull();
  });

  it("writeTimestampedJsonCache appends cachedAt after the fields", () => {
    vi.spyOn(Date, "now").mockReturnValue(42);
    writeTimestampedJsonCache(K, { arrangements: [1], cachedAt: 1, extra: undefined });
    expect(memoryStorage.getItem(K)).toBe('{"arrangements":[1],"cachedAt":42}');
  });
});

// ─── equivalence with every page copy ────────────────────────────────────────

const STORED_STATES: Array<string | null> = [
  null, // missing
  "",
  "null",
  "{not json",
  "5",
  "[1,2]",
  "{}",
  '{"arrangements":[{"id":1}],"cachedAt":3}',
  '{"arrangements":"no"}',
  '{"products":[{"id":1}],"suppliers":[{"id":2}],"productTotal":9,"cachedAt":1}',
  '{"products":[{"id":1}]}',
  '{"clientRows":[{"name":"A"}],"projects":[],"cachedAt":7}',
  '{"clientRows":[]}',
];

function seed(state: string | null) {
  clearStorage();
  if (state !== null) memoryStorage.setItem(K, state);
}

/** Outputs of `read` for every stored state, plus a throwing getItem. */
function readerOutputs(read: () => unknown) {
  const out = STORED_STATES.map((state) => {
    seed(state);
    return read();
  });
  const spy = vi.spyOn(memoryStorage, "getItem").mockImplementation(() => {
    throw new Error("unavailable");
  });
  out.push(read());
  spy.mockRestore();
  return out;
}

// Proposed switch recipes: readJsonCache + the caller's existing shape check.
const recipes: Record<string, [() => unknown, () => unknown]> = {
  "App readDashboardCache": [() => C.readDashboardCacheApp(K), () => readJsonCache<any>(K, null)],
  "Mockups/Invoice read*ProjectsCache": [
    () => C.readProjectsCacheMockupsInvoice(K),
    () => {
      const parsed = readJsonCache<any>(K, null);
      return Array.isArray(parsed?.arrangements) ? parsed.arrangements : [];
    },
  ],
  "Arrangements readProjectsListCache": [
    () => C.readProjectsListCacheArrangements(K),
    () => {
      const parsed = readJsonCache<any>(K, null);
      return !parsed || !Array.isArray(parsed.arrangements) ? null : parsed;
    },
  ],
  "Library readLibraryCache": [
    () => C.readLibraryCacheLibrary(K),
    () => {
      const parsed = readJsonCache<any>(K, null);
      if (!Array.isArray(parsed?.products) || !Array.isArray(parsed?.suppliers)) return null;
      return { suppliers: parsed.suppliers, products: parsed.products, productTotal: parsed.productTotal };
    },
  ],
  "Library readLibraryMetadataCache": [
    () => C.readLibraryMetadataCacheLibrary(K),
    () => {
      const parsed = readJsonCache<any>(K, null);
      return !parsed || typeof parsed !== "object" ? null : parsed;
    },
  ],
  "Favorites readFavoritesCache": [
    () => C.readFavoritesCacheFavorites(K),
    () => {
      const parsed = readJsonCache<any>(K, null);
      return Array.isArray(parsed?.products) ? parsed.products : null;
    },
  ],
  "Favorites readLibraryProductsFromCache": [
    () => C.readLibraryProductsFromCacheFavorites(K),
    () => {
      const parsed = readJsonCache<any>(K, {});
      return Array.isArray(parsed?.products) ? parsed.products : [];
    },
  ],
  "Clients readClientsPageCache": [
    () => C.readClientsPageCacheClients(K),
    () => {
      const parsed = readJsonCache<any>(K, null);
      return !parsed || !Array.isArray(parsed.clientRows) || !Array.isArray(parsed.projects) ? null : parsed;
    },
  ],
  "Clients readLocalClients": [
    () => C.readLocalClientsClients(K),
    () => {
      const rows = readJsonCache<unknown>(K, []);
      return Array.isArray(rows) ? rows : [];
    },
  ],
  "Layout sidebar projects initializer": [
    () => C.readSidebarProjectsLayout(K),
    () => {
      const cached = readJsonCache<unknown>(K, []);
      return Array.isArray(cached) ? cached : [];
    },
  ],
};

describe("readers: readJsonCache + caller shape check reproduces each page copy", () => {
  for (const [name, [original, recipe]] of Object.entries(recipes)) {
    it(name, () => {
      expect(readerOutputs(recipe)).toEqual(readerOutputs(original));
    });
  }
});

/** Stored string after `write` (Date.now pinned), and whether it threw with a quota error. */
function writerOutputs(write: () => void, prior: string | null = null) {
  vi.spyOn(Date, "now").mockReturnValue(1000);
  seed(prior);
  write();
  const stored = memoryStorage.getItem(K);
  const spy = vi.spyOn(memoryStorage, "setItem").mockImplementation(() => {
    throw new Error("QuotaExceededError");
  });
  let threw = false;
  try {
    write();
  } catch {
    threw = true;
  }
  spy.mockRestore();
  vi.restoreAllMocks();
  return { stored, threw };
}

describe("writers: writeJsonCache / writeTimestampedJsonCache reproduce each page copy", () => {
  const rows = [{ id: 1, name: "A" }];

  it("App writeDashboardCache (merge with previous, then stamp)", () => {
    for (const prior of [null, "{bad", '{"summary":{"a":1},"cachedAt":5}', '{"recentDesigns":[1]}']) {
      const patch = { recentDesigns: [2] };
      expect(
        writerOutputs(() => writeTimestampedJsonCache(K, { ...(readJsonCache<any>(K, null) || {}), ...patch }), prior),
      ).toEqual(writerOutputs(() => C.writeDashboardCacheApp(K, patch), prior));
    }
  });

  it("Mockups/Invoice/Arrangements projects caches", () => {
    const shared = writerOutputs(() => writeTimestampedJsonCache(K, { arrangements: rows }));
    expect(shared).toEqual(writerOutputs(() => C.writeProjectsCacheMockupsInvoice(K, rows)));
    expect(shared).toEqual(writerOutputs(() => C.writeProjectsListCacheArrangements(K, rows)));
  });

  it("Library caches (productTotal undefined is dropped identically)", () => {
    for (const total of [undefined, 12]) {
      expect(writerOutputs(() => writeTimestampedJsonCache(K, { suppliers: rows, products: rows, productTotal: total }))).toEqual(
        writerOutputs(() => C.writeLibraryCacheLibrary(K, rows, rows, total)),
      );
    }
    const metadata = { colors: ["red"], cachedAt: 3 };
    expect(writerOutputs(() => writeTimestampedJsonCache(K, metadata))).toEqual(
      writerOutputs(() => C.writeLibraryMetadataCacheLibrary(K, metadata)),
    );
  });

  it("Favorites and Clients page caches", () => {
    expect(writerOutputs(() => writeTimestampedJsonCache(K, { products: rows }))).toEqual(
      writerOutputs(() => C.writeFavoritesCacheFavorites(K, rows)),
    );
    expect(writerOutputs(() => writeTimestampedJsonCache(K, { clientRows: rows, projects: [] }))).toEqual(
      writerOutputs(() => C.writeClientsPageCacheClients(K, rows, [])),
    );
  });

  it("Layout writeJsonCache", () => {
    for (const value of [rows, { clientRows: rows, cachedAt: 1 }, null]) {
      expect(writerOutputs(() => writeJsonCache(K, value))).toEqual(writerOutputs(() => C.writeJsonCacheLayout(K, value)));
    }
  });

  it("Clients writeLocalClients is NOT equivalent: the original throws on quota", () => {
    expect(writerOutputs(() => C.writeLocalClientsClients(K, rows))).toEqual({ stored: '[{"id":1,"name":"A"}]', threw: true });
    expect(writerOutputs(() => writeJsonCache(K, rows))).toEqual({ stored: '[{"id":1,"name":"A"}]', threw: false });
  });
});
