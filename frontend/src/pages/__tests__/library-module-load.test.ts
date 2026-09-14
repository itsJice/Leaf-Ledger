/**
 * Load check for the modules extracted from pages/Library.tsx: every module
 * must import without throwing (no TDZ ReferenceError from an import cycle).
 */
import { describe, expect, it, vi } from "vitest";

// Module mocks are hoisted only within the declaring file, so they live here.
vi.mock("app", () => ({ apiClient: {}, APP_BASE_PATH: "/" }));
vi.mock("utils/apiFetch", () => ({ apiFetch: vi.fn() }));
vi.mock("components/Layout", () => ({ default: () => null }));
vi.mock("components/WorkingJobBar", () => ({ default: () => null }));
vi.mock("components/PinToggle", () => ({ default: () => null }));

import "../../test/setup";

const modules: Record<string, () => Promise<Record<string, unknown>>> = {
  "library/types": () => import("../library/types"),
  "library/constants": () => import("../library/constants"),
  "library/cache": () => import("../library/cache"),
  "library/search": () => import("../library/search"),
  "library/display": () => import("../library/display"),
  "library/colors": () => import("../library/colors"),
  "library/facets": () => import("../library/facets"),
  "library/ProxiedImage": () => import("../library/ProxiedImage"),
  "library/ImageLightbox": () => import("../library/ImageLightbox"),
  "library/SupplierLinkBar": () => import("../library/SupplierLinkBar"),
  "library/InlinePriceEditor": () => import("../library/InlinePriceEditor"),
  "library/ProductModal": () => import("../library/ProductModal"),
  "library/AddToProjectModal": () => import("../library/AddToProjectModal"),
  "library/MultiSelectFilter": () => import("../library/MultiSelectFilter"),
  "library/ProductDetailModal": () => import("../library/ProductDetailModal"),
  "library/ProductCard": () => import("../library/ProductCard"),
  "library/VendorView": () => import("../library/VendorView"),
  "library/ProductView": () => import("../library/ProductView"),
  "library/index": () => import("../library/index"),
  Library: () => import("../Library"),
};

describe("Library module load", () => {
  for (const [name, load] of Object.entries(modules)) {
    it(`imports ${name} without throwing`, async () => {
      await expect(load()).resolves.toBeDefined();
    });
  }

  it("keeps the page default export and its re-exports", async () => {
    const Library = await import("../Library");
    expect(typeof Library.default).toBe("function");
    expect(typeof Library.ProductDetailModal).toBe("function");
    expect(typeof Library.ProductView).toBe("function");
    expect(typeof Library.ProxiedImage).toBe("function");
    expect(Array.isArray(Library.CATEGORIES)).toBe(true);
    expect(typeof Library.normalizeSearchText).toBe("function");
    expect(typeof Library.readLibraryCache).toBe("function");
  });
});
