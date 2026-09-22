/**
 * Load check for the modules extracted from pages/Arrangements.tsx: every module
 * must import without throwing (no TDZ ReferenceError from an import cycle).
 */
import { describe, expect, it, vi } from "vitest";

// Module mocks are hoisted only within the declaring file, so they live here.
vi.mock("app", () => ({ apiClient: {}, APP_BASE_PATH: "/" }));
vi.mock("utils/apiFetch", () => ({ apiFetch: vi.fn() }));
vi.mock("components/Layout", () => ({ default: () => null }));

import "../../test/setup";

const modules: Record<string, () => Promise<Record<string, unknown>>> = {
  "arrangements/types": () => import("../arrangements/types"),
  "arrangements/constants": () => import("../arrangements/constants"),
  "arrangements/textHelpers": () => import("../arrangements/textHelpers"),
  "arrangements/builderTypes": () => import("../arrangements/builderTypes"),
  "arrangements/projects": () => import("../arrangements/projects"),
  "arrangements/scopeNotes": () => import("../arrangements/scopeNotes"),
  "arrangements/templates": () => import("../arrangements/templates"),
  "arrangements/buildConfigs": () => import("../arrangements/buildConfigs"),
  "arrangements/parts": () => import("../arrangements/parts"),
  "arrangements/BuilderProductPicker": () => import("../arrangements/BuilderProductPicker"),
  "arrangements/MeasuredScopeFields": () => import("../arrangements/MeasuredScopeFields"),
  "arrangements/NewProjectModal": () => import("../arrangements/NewProjectModal"),
  "arrangements/index": () => import("../arrangements/index"),
  Arrangements: () => import("../Arrangements"),
};

describe("Arrangements module load", () => {
  for (const [name, load] of Object.entries(modules)) {
    it(`imports ${name} without throwing`, async () => {
      await expect(load()).resolves.toBeDefined();
    });
  }

  it("keeps the page default export and its re-exports", async () => {
    const Arrangements = await import("../Arrangements");
    expect(typeof Arrangements.default).toBe("function");
    expect(typeof Arrangements.NewProjectModal).toBe("function");
    expect(Array.isArray(Arrangements.DEFAULT_EDITABLE_BUILD_TEMPLATES)).toBe(true);
    expect(typeof Arrangements.cleanEditableBuildTemplates).toBe("function");
    expect(Arrangements.LEGACY_TOP_DOWN_SLOT_ORDERS).toBeDefined();
  });
});
