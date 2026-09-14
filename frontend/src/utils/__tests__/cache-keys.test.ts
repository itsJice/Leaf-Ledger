import { describe, expect, it } from "vitest";
import {
  ACTIVE_ORDER_KEY,
  BUILD_TEMPLATE_STORAGE_KEY,
  CLIENTS_PAGE_CACHE_KEY,
  DASHBOARD_CACHE_KEY,
  LIBRARY_CACHE_KEY,
  PROJECTS_LIST_CACHE_KEY,
} from "../../constants";
import { countOccurrences, readSrc } from "./source-text";
import { listSrcFiles } from "./list-src-files";

describe("shared cache key constants", () => {
  it("pins the exact strings", () => {
    expect({
      DASHBOARD_CACHE_KEY,
      PROJECTS_LIST_CACHE_KEY,
      LIBRARY_CACHE_KEY,
      CLIENTS_PAGE_CACHE_KEY,
      BUILD_TEMPLATE_STORAGE_KEY,
      ACTIVE_ORDER_KEY,
    }).toEqual({
      DASHBOARD_CACHE_KEY: "leaf-ledger:dashboard-cache:v2",
      PROJECTS_LIST_CACHE_KEY: "leaf-ledger:projects-list-cache:v1",
      LIBRARY_CACHE_KEY: "leaf-ledger:library-cache:v1",
      CLIENTS_PAGE_CACHE_KEY: "leaf-ledger:clients-page-cache:v1",
      BUILD_TEMPLATE_STORAGE_KEY: "leaf-ledger:build-templates:v1",
      ACTIVE_ORDER_KEY: "leaf-ledger:active-order:v1",
    });
  });
});

// The literal values a cache key may still appear as, keyed by a readable name.
// "DASHBOARD_CACHE_KEY_DEAD_V1" isn't exported anywhere: Layout.tsx keeps writing
// this orphaned key (nothing reads it) while App.tsx reads DASHBOARD_CACHE_KEY (:v2).
const CACHE_KEY_LITERALS: Record<string, string> = {
  DASHBOARD_CACHE_KEY,
  DASHBOARD_CACHE_KEY_DEAD_V1: "leaf-ledger:dashboard-cache:v1",
  PROJECTS_LIST_CACHE_KEY,
  LIBRARY_CACHE_KEY,
  CLIENTS_PAGE_CACHE_KEY,
  BUILD_TEMPLATE_STORAGE_KEY,
  ACTIVE_ORDER_KEY,
};

// Files excluded from the scan below: constants.ts defines the literals, and
// utils/projectsChanged.ts is out of scope for cache keys (it only defines the
// projects-changed event, guarded separately in projectsChanged.test.ts).
// __tests__ files (including this one) are already excluded by listSrcFiles.
const EXCLUDED_FILES = new Set(["constants.ts", "utils/projectsChanged.ts"]);

// How many raw occurrences of each cache-key literal legitimately remain outside
// constants.ts, keyed by file (relative to src/), then by the literal's name in
// CACHE_KEY_LITERALS above. Shrink this as call sites move to shared modules; a
// literal may never be added (to this map, or to a file not already listed here).
const REMAINING_LITERALS_ALLOWLIST: Record<string, Record<string, number>> = {
  "components/Layout.tsx": {
    DASHBOARD_CACHE_KEY_DEAD_V1: 1,
  },
};

describe("cache key literals do not creep back into src/", () => {
  for (const file of listSrcFiles()) {
    if (EXCLUDED_FILES.has(file)) continue;
    it(`${file} does not exceed its allowlisted literal occurrences`, () => {
      const src = readSrc(file);
      const allowed = REMAINING_LITERALS_ALLOWLIST[file] ?? {};
      for (const [name, value] of Object.entries(CACHE_KEY_LITERALS)) {
        const count = countOccurrences(src, `"${value}"`);
        expect(count, `${file}: raw occurrences of ${name} ("${value}")`).toBeLessThanOrEqual(allowed[name] ?? 0);
      }
    });
  }
});
