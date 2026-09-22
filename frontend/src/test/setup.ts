/**
 * Shared test setup for the page-helper characterisation tests.
 *
 * Importing a page module executes its top-level code. The pages (and the
 * modules they pull in) read `window` / `localStorage` lazily, so a minimal
 * in-memory stub is enough. Module mocks (`vi.mock`) are hoisted only within
 * the file that declares them, so each test file declares its own mocks and
 * imports this file before importing the page.
 */
import { vi } from "vitest";

const store = new Map<string, string>();

export const memoryStorage: Storage = {
  get length() {
    return store.size;
  },
  clear: () => store.clear(),
  getItem: (key: string) => (store.has(key) ? (store.get(key) as string) : null),
  key: (index: number) => Array.from(store.keys())[index] ?? null,
  removeItem: (key: string) => {
    store.delete(key);
  },
  setItem: (key: string, value: string) => {
    store.set(key, String(value));
  },
};

vi.stubGlobal("localStorage", memoryStorage);
vi.stubGlobal("window", {
  localStorage: memoryStorage,
  location: { origin: "http://localhost:5173", href: "http://localhost:5173/", pathname: "/" },
  addEventListener: () => undefined,
  removeEventListener: () => undefined,
  dispatchEvent: () => true,
  setTimeout: globalThis.setTimeout.bind(globalThis),
  clearTimeout: globalThis.clearTimeout.bind(globalThis),
});

/** Replace the stub storage contents with the given key/value pairs (values are JSON-encoded unless already strings). */
export function seedStorage(entries: Record<string, unknown>) {
  store.clear();
  for (const [key, value] of Object.entries(entries)) {
    store.set(key, typeof value === "string" ? value : JSON.stringify(value));
  }
}

export function clearStorage() {
  store.clear();
}
