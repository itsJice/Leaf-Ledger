/* eslint-disable @typescript-eslint/no-explicit-any */
import { describe, expect, it, vi } from "vitest";

vi.mock("app", () => ({ apiClient: {}, APP_BASE_PATH: "/" }));
vi.mock("utils/apiFetch", () => ({ apiFetch: vi.fn() }));
vi.mock("components/Layout", () => ({ default: () => null }));

import "../../test/setup";
import * as A from "../../pages/Arrangements";
import {
  ARRANGEMENTS_DEFAULT_BUILD_TEMPLATES,
  cleanArrangementsBuildTemplates,
  cleanBuildTemplateList,
  cleanSettingsBuildTemplates,
  LEGACY_TOP_DOWN_SLOT_ORDERS,
  SETTINGS_DEFAULT_BUILD_TEMPLATES,
} from "../buildTemplates";
import {
  SETTINGS_COPY_DEFAULT_BUILD_TEMPLATES,
  SETTINGS_COPY_LEGACY_TOP_DOWN_SLOT_ORDERS,
  settingsCopyCleanTemplateList,
} from "./inline-copies-3a";
import { readSrc, snippet } from "./source-text";

type Outcome = { value: unknown; isFallback?: boolean } | { throws: string };
function outcome(fn: () => unknown, fallback: unknown): Outcome {
  try {
    const value = fn();
    return { value, isFallback: value === fallback };
  } catch (e) {
    return { throws: (e as Error).constructor.name };
  }
}

const reversed = (id: string) => [...LEGACY_TOP_DOWN_SLOT_ORDERS[id]].reverse();

const INPUTS: Array<[string, unknown]> = [
  ["null", null],
  ["undefined", undefined],
  ["non-array string", "christmas-tree"],
  ["plain object", { id: "x", name: "X" }],
  ["empty array", []],
  ["only invalid entries", [{ id: "", name: "x" }, { id: "x", name: "  " }, {}]],
  ["legacy top-down orders for every green template", Object.entries(LEGACY_TOP_DOWN_SLOT_ORDERS).map(([id, slots]) => ({ id, name: id, slots }))],
  ["legacy order with case/whitespace noise", [{ id: "green-tree", name: "Tree", slots: [" container ", "TOP DRESSING", "Trunks & Branches", "leaves"] }]],
  ["customised (non-legacy) order is kept", [{ id: "planter", name: "Planter", slots: reversed("planter").slice(1) }]],
  ["legacy wreath slots", [{ id: "wreath", name: "Wreath", slots: ["Wreath Base", " greenery", "RIBBON", "Decor"] }]],
  ["missing fields", [{ id: " rug ", name: " Rug " }]],
  ["duplicate ids and names", [{ id: "a", name: "Same" }, { id: "a", name: "Same", section: "Christmas" }, { id: "b", name: "Same" }]],
  [
    "odd field types",
    [{ id: 7, name: 8, section: "christmas", summary: 0, usedFor: "x", slots: [1, " two ", "", null], regularMaterials: [" a ", ""], premiumMaterials: {} }],
  ],
  ["summary is carried through", [{ id: "s", name: "S", summary: "hello", section: "Christmas" }]],
  ["null entry throws", [null]],
  ["Settings defaults as input", SETTINGS_COPY_DEFAULT_BUILD_TEMPLATES],
  ["Arrangements defaults as input", A.DEFAULT_EDITABLE_BUILD_TEMPLATES],
];

describe("build templates: oracle", () => {
  it("the Settings copies are verbatim page source", () => {
    const oracle = readSrc("utils/__tests__/inline-copies-3a.ts");
    const settings = readSrc("pages/Settings.tsx");
    expect(oracle).toContain(snippet(settings, "type BuildTemplate = {", "\n};\n"));
    expect(oracle).toContain(snippet(settings, "const DEFAULT_BUILD_TEMPLATES", "\n];\n"));
    expect(oracle).toContain(snippet(settings, "const LEGACY_TOP_DOWN_SLOT_ORDERS", "\n};\n"));
    expect(oracle).toContain(snippet(settings, "function cleanTemplateList", "\n}\n"));
  });
});

describe("build templates: data", () => {
  it("each default list equals its page original", () => {
    expect(SETTINGS_DEFAULT_BUILD_TEMPLATES).toEqual(SETTINGS_COPY_DEFAULT_BUILD_TEMPLATES);
    expect(ARRANGEMENTS_DEFAULT_BUILD_TEMPLATES).toEqual(A.DEFAULT_EDITABLE_BUILD_TEMPLATES);
  });

  it("LEGACY_TOP_DOWN_SLOT_ORDERS is identical in both pages", () => {
    expect(LEGACY_TOP_DOWN_SLOT_ORDERS).toEqual(SETTINGS_COPY_LEGACY_TOP_DOWN_SLOT_ORDERS);
    expect(LEGACY_TOP_DOWN_SLOT_ORDERS).toEqual(A.LEGACY_TOP_DOWN_SLOT_ORDERS);
  });

  it("DRIFT: the lists differ only by summary (all 10) and wreath materials", () => {
    const settingsWithoutDrift = SETTINGS_DEFAULT_BUILD_TEMPLATES.map((template) => {
      const { summary, ...rest } = template;
      expect(summary.length).toBeGreaterThan(0);
      if (rest.id !== "wreath") return rest;
      const { regularMaterials, premiumMaterials, ...wreath } = rest;
      expect(regularMaterials).toHaveLength(2);
      expect(premiumMaterials).toHaveLength(2);
      return wreath;
    });
    expect(settingsWithoutDrift).toEqual(ARRANGEMENTS_DEFAULT_BUILD_TEMPLATES);
    const arrWreath = ARRANGEMENTS_DEFAULT_BUILD_TEMPLATES.find((t) => t.id === "wreath") as any;
    expect(arrWreath.regularMaterials).toBeUndefined();
    expect(arrWreath.premiumMaterials).toBeUndefined();
  });
});

describe("build templates: cleaner", () => {
  for (const [name, input] of INPUTS) {
    it(`Settings: ${name}`, () => {
      const shared = outcome(() => cleanSettingsBuildTemplates(input), SETTINGS_DEFAULT_BUILD_TEMPLATES);
      const original = outcome(() => settingsCopyCleanTemplateList(input), SETTINGS_COPY_DEFAULT_BUILD_TEMPLATES);
      expect(shared).toEqual(original);
    });

    it(`Arrangements: ${name}`, () => {
      const shared = outcome(() => cleanArrangementsBuildTemplates(input), ARRANGEMENTS_DEFAULT_BUILD_TEMPLATES);
      const original = outcome(() => A.cleanEditableBuildTemplates(input), A.DEFAULT_EDITABLE_BUILD_TEMPLATES);
      expect(shared).toEqual(original);
    });
  }

  it("both originals produce identical non-fallback output (summary included)", () => {
    for (const [, input] of INPUTS) {
      const s = outcome(() => settingsCopyCleanTemplateList(input, [] as any), []);
      const a = outcome(() => A.cleanEditableBuildTemplates(input, [] as any), []);
      expect(a).toEqual(s);
    }
  });

  it("an explicit fallback is returned by reference", () => {
    const fallback: any[] = [];
    expect(cleanSettingsBuildTemplates(null, fallback)).toBe(fallback);
    expect(cleanArrangementsBuildTemplates([], fallback)).toBe(fallback);
    expect(cleanBuildTemplateList("x")).toBeNull();
  });
});
