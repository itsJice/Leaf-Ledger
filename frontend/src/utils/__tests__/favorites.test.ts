import { beforeEach, describe, expect, it, vi } from "vitest";
import { readFavoriteIds, setLocalFavorite, writeFavoriteIds } from "../favorites";

const KEY = "leaf-ledger:favorite-product-ids:v1";

function memoryStorage() {
  const data = new Map<string, string>();
  return {
    data,
    getItem: vi.fn((k: string) => (data.has(k) ? data.get(k)! : null)),
    setItem: vi.fn((k: string, val: string) => void data.set(k, String(val))),
    removeItem: vi.fn((k: string) => void data.delete(k)),
    clear: vi.fn(() => data.clear()),
  };
}

let storage: ReturnType<typeof memoryStorage>;
beforeEach(() => {
  vi.unstubAllGlobals();
  storage = memoryStorage();
  vi.stubGlobal("localStorage", storage);
});

describe("favorites", () => {
  it("reads an empty set when nothing is stored", () => {
    expect(readFavoriteIds()).toEqual(new Set());
    expect(storage.getItem).toHaveBeenCalledWith(KEY);
  });

  // FIX: `null` used to coerce via `Number(null)` to a fake id 0; it's now
  // dropped before coercion, same as it would be if it weren't in the array
  // at all. "x" was already dropped (Number("x") is NaN, non-finite); `true`
  // coerces to 1, which is already in the set, so it adds nothing new.
  it("coerces stored values with Number and drops null and non-finite ones", () => {
    storage.data.set(KEY, JSON.stringify([1, "2", "x", null, 3.5, true]));
    expect([...readFavoriteIds()]).toEqual([1, 2, 3.5]);
  });

  it("returns an empty set for non-array JSON, corrupt JSON, or a throwing store", () => {
    storage.data.set(KEY, "{}");
    expect(readFavoriteIds()).toEqual(new Set());
    storage.data.set(KEY, "not json");
    expect(readFavoriteIds()).toEqual(new Set());
    storage.getItem.mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(readFavoriteIds()).toEqual(new Set());
  });

  it("writes the set as a JSON array in insertion order and swallows storage errors", () => {
    writeFavoriteIds(new Set([3, 1]));
    expect(storage.setItem).toHaveBeenCalledWith(KEY, "[3,1]");
    storage.setItem.mockImplementation(() => {
      throw new Error("quota");
    });
    expect(() => writeFavoriteIds(new Set([9]))).not.toThrow();
  });

  it("setLocalFavorite adds/removes, persists and returns the new set", () => {
    expect([...setLocalFavorite(5, true)]).toEqual([5]);
    expect([...setLocalFavorite(7, true)]).toEqual([5, 7]);
    expect([...setLocalFavorite(5, true)]).toEqual([5, 7]);
    expect([...setLocalFavorite(5, false)]).toEqual([7]);
    expect([...setLocalFavorite(99, false)]).toEqual([7]);
    expect(storage.data.get(KEY)).toBe("[7]");
  });
});
