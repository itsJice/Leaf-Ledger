import { describe, expect, it } from "vitest";
import { decideChunkErrorAction, isChunkLoadError } from "../utils/lazyWithReload";

function makeStorage(initial: Record<string, string> = {}) {
  const store = new Map(Object.entries(initial));
  return {
    getItem: (key: string) => (store.has(key) ? (store.get(key) as string) : null),
    setItem: (key: string, value: string) => {
      store.set(key, value);
    },
    removeItem: (key: string) => {
      store.delete(key);
    },
  };
}

const CHUNK_RELOAD_FLAG = "leaf-ledger:chunk-reload";

describe("isChunkLoadError", () => {
  it.each([
    "Failed to fetch dynamically imported module: https://x/assets/Jobs-abc.js",
    "Importing a module script failed",
    "error loading dynamically imported module",
  ])("matches known chunk-load message %s", (message) => {
    expect(isChunkLoadError(new Error(message))).toBe(true);
  });

  it("does not match an unrelated error", () => {
    expect(isChunkLoadError(new Error("TypeError: x is not a function"))).toBe(false);
  });
});

describe("decideChunkErrorAction", () => {
  it("reloads on a chunk error with no prior attempt, and sets the flag", () => {
    const storage = makeStorage();
    const decision = decideChunkErrorAction(
      new Error("Failed to fetch dynamically imported module"),
      storage,
    );
    expect(decision).toBe("reload");
    expect(storage.getItem(CHUNK_RELOAD_FLAG)).toBe("1");
  });

  it("rethrows on a second chunk error after the flag is already set", () => {
    const storage = makeStorage({ [CHUNK_RELOAD_FLAG]: "1" });
    const decision = decideChunkErrorAction(
      new Error("Importing a module script failed"),
      storage,
    );
    expect(decision).toBe("rethrow");
  });

  it("rethrows a non-chunk error without touching storage", () => {
    const storage = makeStorage();
    const decision = decideChunkErrorAction(new Error("network error"), storage);
    expect(decision).toBe("rethrow");
    expect(storage.getItem(CHUNK_RELOAD_FLAG)).toBeNull();
  });

  it("rethrows without reloading when storage access throws", () => {
    const throwingStorage = {
      getItem: () => {
        throw new Error("storage disabled");
      },
      setItem: () => {
        throw new Error("storage disabled");
      },
      removeItem: () => {
        throw new Error("storage disabled");
      },
    };
    const decision = decideChunkErrorAction(
      new Error("Failed to fetch dynamically imported module"),
      throwingStorage,
    );
    expect(decision).toBe("rethrow");
  });

  it("can loop only once: reload then rethrow on the next failure", () => {
    const storage = makeStorage();
    const error = new Error("error loading dynamically imported module");
    expect(decideChunkErrorAction(error, storage)).toBe("reload");
    expect(decideChunkErrorAction(error, storage)).toBe("rethrow");
  });
});
