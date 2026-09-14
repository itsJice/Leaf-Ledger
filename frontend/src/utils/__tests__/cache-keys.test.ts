import { describe, expect, it } from "vitest";
import {
  ACTIVE_ORDER_KEY,
  BUILD_TEMPLATE_STORAGE_KEY,
  CLIENTS_PAGE_CACHE_KEY,
  DASHBOARD_CACHE_KEY,
  LIBRARY_CACHE_KEY,
  PROJECTS_LIST_CACHE_KEY,
} from "../../constants";
import { readSrc } from "./source-text";

// Each constant must equal the literal that the listed files use today.
const KEYS: Array<[string, string, string[]]> = [
  ["DASHBOARD_CACHE_KEY", DASHBOARD_CACHE_KEY, ["pages/App.tsx"]],
  ["PROJECTS_LIST_CACHE_KEY", PROJECTS_LIST_CACHE_KEY, ["pages/Arrangements.tsx", "components/Layout.tsx"]],
  ["LIBRARY_CACHE_KEY", LIBRARY_CACHE_KEY, ["pages/Library.tsx", "pages/Favorites.tsx"]],
  ["CLIENTS_PAGE_CACHE_KEY", CLIENTS_PAGE_CACHE_KEY, ["pages/Clients.tsx", "components/Layout.tsx"]],
  ["BUILD_TEMPLATE_STORAGE_KEY", BUILD_TEMPLATE_STORAGE_KEY, ["pages/Settings.tsx", "pages/Arrangements.tsx"]],
  ["ACTIVE_ORDER_KEY", ACTIVE_ORDER_KEY, ["utils/orders.ts", "pages/Sourcing.tsx"]],
];

describe("shared cache key constants", () => {
  it("pins the exact strings", () => {
    expect(Object.fromEntries(KEYS.map(([name, value]) => [name, value]))).toEqual({
      DASHBOARD_CACHE_KEY: "leaf-ledger:dashboard-cache:v2",
      PROJECTS_LIST_CACHE_KEY: "leaf-ledger:projects-list-cache:v1",
      LIBRARY_CACHE_KEY: "leaf-ledger:library-cache:v1",
      CLIENTS_PAGE_CACHE_KEY: "leaf-ledger:clients-page-cache:v1",
      BUILD_TEMPLATE_STORAGE_KEY: "leaf-ledger:build-templates:v1",
      ACTIVE_ORDER_KEY: "leaf-ledger:active-order:v1",
    });
  });

  for (const [name, value, files] of KEYS) {
    it(`${name} matches the literal in ${files.join(", ")}`, () => {
      for (const file of files) expect(readSrc(file)).toContain(`"${value}"`);
    });
  }

  it("Layout still writes the dead dashboard :v1 key (App reads :v2)", () => {
    expect(readSrc("components/Layout.tsx")).toContain('"leaf-ledger:dashboard-cache:v1"');
    expect(readSrc("pages/App.tsx")).not.toContain('"leaf-ledger:dashboard-cache:v1"');
  });
});
