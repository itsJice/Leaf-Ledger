import { lazy, type ComponentType } from "react";

/**
 * Session-scoped flag that records "we already tried reloading the page to
 * recover from a stale chunk once". Kept in sessionStorage (not a module
 * variable) because the recovery reload throws the whole JS context away, so
 * only persisted state survives it.
 */
const CHUNK_RELOAD_FLAG = "leaf-ledger:chunk-reload";

/**
 * Substrings seen in the errors browsers throw when a dynamic `import()`
 * resolves to a chunk that no longer exists on the server -- typically
 * because a deploy happened while the tab was still open with an old
 * `index.html` referencing now-stale chunk hashes.
 */
const CHUNK_LOAD_ERROR_PATTERNS = [
  "Failed to fetch dynamically imported module",
  "Importing a module script failed",
  "error loading dynamically imported module",
];

export function isChunkLoadError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error);
  return CHUNK_LOAD_ERROR_PATTERNS.some((pattern) => message.includes(pattern));
}

export type ChunkErrorDecision = "reload" | "rethrow";

type MinimalStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;

/**
 * Pure decision logic for how to react to a failed dynamic import. Kept
 * separate from `lazyWithReload` (and free of `window`/module-level state) so
 * it can be exercised directly in node tests.
 *
 * - Not a chunk-load error -> rethrow; let the existing error boundary
 *   (SomethingWentWrongPage) handle it as usual.
 * - A chunk-load error we have not tried to recover from yet -> mark the
 *   attempt and reload.
 * - A chunk-load error after we already reloaded once -> rethrow. This is
 *   the loop guard: a second failure means reloading did not help.
 * - Any failure reading/writing storage -> rethrow without reloading, since
 *   we cannot safely record that a reload was attempted (and so cannot
 *   guarantee we won't loop).
 */
export function decideChunkErrorAction(
  error: unknown,
  storage: MinimalStorage,
): ChunkErrorDecision {
  if (!isChunkLoadError(error)) {
    return "rethrow";
  }

  try {
    const alreadyAttempted = storage.getItem(CHUNK_RELOAD_FLAG) === "1";
    if (alreadyAttempted) {
      return "rethrow";
    }
    storage.setItem(CHUNK_RELOAD_FLAG, "1");
    return "reload";
  } catch {
    return "rethrow";
  }
}

function clearChunkReloadFlag(storage: MinimalStorage): void {
  try {
    storage.removeItem(CHUNK_RELOAD_FLAG);
  } catch {
    // Ignore: nothing useful to do if storage is unavailable.
  }
}

const noopStorage: MinimalStorage = {
  getItem() {
    throw new Error("sessionStorage unavailable");
  },
  setItem() {
    throw new Error("sessionStorage unavailable");
  },
  removeItem() {
    throw new Error("sessionStorage unavailable");
  },
};

/** Accessing `window.sessionStorage` itself can throw (e.g. some locked-down
 * or private-browsing contexts), so this is wrapped too. Falling back to a
 * storage stub that always throws keeps the caller's try/catch the single
 * source of truth for "storage is unusable" -> rethrow-without-reloading. */
function getSessionStorage(): MinimalStorage {
  try {
    return window.sessionStorage;
  } catch {
    return noopStorage;
  }
}

/**
 * Drop-in replacement for `React.lazy` that recovers from a stale chunk
 * reference after a deploy: an open tab's `index.html` can still point at
 * page chunk hashes that no longer exist once a new build has shipped. On
 * that specific failure it reloads the page once (via sessionStorage guard,
 * so it can never loop) so the user transparently picks up the new
 * `index.html` and its current chunk hashes. Any other failure -- including
 * a second chunk-load failure after the reload already happened -- is
 * rethrown for the existing error boundary to handle.
 */
export function lazyWithReload<T extends ComponentType<unknown>>(
  factory: () => Promise<{ default: T }>,
): ReturnType<typeof lazy<T>> {
  return lazy(() =>
    factory()
      .then((module) => {
        clearChunkReloadFlag(getSessionStorage());
        return module;
      })
      .catch((error: unknown) => {
        const decision = decideChunkErrorAction(error, getSessionStorage());
        if (decision === "reload") {
          window.location.reload();
          // Keep React.lazy pending forever: the reload is about to tear
          // down this JS context, so there is nothing useful to render.
          return new Promise<{ default: T }>(() => {});
        }
        throw error;
      }),
  );
}
