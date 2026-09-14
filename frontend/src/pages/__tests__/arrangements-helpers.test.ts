/**
 * Characterisation tests for the pure helpers inside pages/Arrangements.tsx.
 *
 * These pin the CURRENT behaviour (quirks included) so the helpers can later be
 * moved into their own modules and proven unchanged. Do not "fix" an expectation
 * here without a deliberate behaviour change.
 */
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

// Module mocks are hoisted only within the declaring file, so they live here.
vi.mock("app", () => ({ apiClient: {}, APP_BASE_PATH: "/" }));
vi.mock("utils/apiFetch", () => ({ apiFetch: vi.fn() }));
vi.mock("components/Layout", () => ({ default: () => null }));

import { clearStorage, seedStorage } from "../../test/setup";
import * as A from "../arrangements/index";

// The page's Container/Arrangement types are not exported; build loose fixtures.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Loose = any;
const bucket = (overrides: Loose = {}): Loose => ({
  id: 1,
  arrangement_id: 1,
  sort_order: 0,
  items: [],
  subtotal: 0,
  ...overrides,
});
const item = (overrides: Loose = {}): Loose => ({
  id: 1,
  product_id: 1,
  product_name: "",
  product_category: "",
  unit: "each",
  quantity: 1,
  ...overrides,
});

const TEMPLATE_KEY = "leaf-ledger:build-templates:v1";
const BUILDER_TYPES_KEY = "leaf-ledger:builder-build-types:v1";

const API_TYPES = [
  {
    key: "topiary",
    label: "Topiary",
    aliases: ["Topiary Tree"],
    slots: [
      { order: 1, label: "Topiary Form", scope: "plant_material" },
      { order: 0, label: "Container", scope: "container" },
    ],
    fields: { height: true, canopy: true },
  },
  { key: "plant_bush", label: "Plant & Bush", aliases: ["Plant", "Bush"] },
];

beforeEach(() => {
  clearStorage();
});

describe("builder build-type cache", () => {
  // Must run first: readBuilderBuildTypes memoises the first value it reads.
  it("readBuilderBuildTypes parses the stored cache on first read and memoises it", () => {
    seedStorage({ [BUILDER_TYPES_KEY]: API_TYPES });
    const first = A.readBuilderBuildTypes();
    expect(first.map((type) => type.key)).toEqual(["topiary", "plant_bush"]);
    expect(first[0].slots).toEqual([
      { order: 0, label: "Container", scope: "container", scope_label: "" },
      { order: 1, label: "Topiary Form", scope: "plant_material", scope_label: "" },
    ]);
    clearStorage();
    expect(A.readBuilderBuildTypes()).toBe(first);
  });

  it("writeBuilderBuildTypes replaces the memo and persists JSON", () => {
    const cleaned = A.cleanBuilderBuildTypes(API_TYPES);
    A.writeBuilderBuildTypes(cleaned);
    expect(A.readBuilderBuildTypes()).toBe(cleaned);
    expect(JSON.parse(localStorage.getItem(BUILDER_TYPES_KEY) as string)).toEqual(JSON.parse(JSON.stringify(cleaned)));
  });

  it("cleanBuilderBuildTypes normalises rows and drops unlabeled ones", () => {
    expect(A.cleanBuilderBuildTypes(null)).toEqual([]);
    expect(A.cleanBuilderBuildTypes({ label: "x" })).toEqual([]);
    expect(
      A.cleanBuilderBuildTypes([
        {
          label: " Topiary ",
          key: "topiary",
          aliases: ["Topiaries", 5],
          recipe_count: "3",
          slots: [
            { order: 2, label: "Container", scope: "container" },
            { label: "Plant", scope: "plant_material" },
            { order: 1, label: "  " },
          ],
          fields: { height: true },
        },
        { label: "" },
        { label: "Plant & Bush" },
      ])
    ).toEqual([
      {
        key: "topiary",
        label: "Topiary",
        aliases: ["Topiaries", "5"],
        recipe_count: 3,
        usable_recipe_count: 0,
        has_history: false,
        slots: [
          { order: 1, label: "Plant", scope: "plant_material", scope_label: "" },
          { order: 2, label: "Container", scope: "container", scope_label: "" },
        ],
        fields: { height: true },
        applies: [],
        notes: null,
      },
      {
        key: "Plant & Bush",
        label: "Plant & Bush",
        aliases: [],
        recipe_count: 0,
        usable_recipe_count: 0,
        has_history: false,
        slots: [],
        fields: undefined,
        applies: [],
        notes: null,
      },
    ]);
  });

  it("builderApiTypeFor matches label/alias exactly, then by containment (>3 chars)", () => {
    const known = A.cleanBuilderBuildTypes(API_TYPES);
    expect(A.builderApiTypeFor("topiary tree", known)?.key).toBe("topiary");
    expect(A.builderApiTypeFor("Plant", known)?.key).toBe("plant_bush");
    expect(A.builderApiTypeFor("Big Topiary Ball", known)?.key).toBe("topiary");
    expect(A.builderApiTypeFor("Bus", known)?.key).toBe("plant_bush");
    expect(A.builderApiTypeFor("Rug", known)).toBeNull();
    expect(A.builderApiTypeFor("", known)).toBeNull();
  });

  it("builderApiSlotsForBuildType reads slot labels from the memoised cache", () => {
    expect(A.builderApiSlotsForBuildType("Topiary")).toEqual(["Container", "Topiary Form"]);
    expect(A.builderApiSlotsForBuildType("Plant & Bush")).toBeNull();
    expect(A.builderApiSlotsForBuildType("Rug")).toBeNull();
  });

  it("builderFieldsForBuildType uses declared fields or the fallback copy", () => {
    const known = A.cleanBuilderBuildTypes(API_TYPES);
    expect(A.builderFieldsForBuildType("Topiary", known)).toEqual({
      height: true, width: false, canopy: true, silhouette: false, depth: false, species: false, density: false,
    });
    const fallback = A.builderFieldsForBuildType("Rug", known);
    expect(fallback).toEqual({
      height: true, width: true, canopy: false, silhouette: false, depth: true, species: false, density: false,
    });
    expect(fallback).not.toBe(A.BUILDER_FIELDS_FALLBACK);
  });
});

describe("small formatting helpers", () => {
  it("scopeSlotForPartLabel maps part labels to scope slots", () => {
    expect(A.scopeSlotForPartLabel("Container/Base")).toBe("container");
    expect(A.scopeSlotForPartLabel("Drop-in Base")).toBe("container");
    expect(A.scopeSlotForPartLabel("Finish/Top Dressing")).toBe("top_dressing");
    expect(A.scopeSlotForPartLabel("Finish")).toBe("top_dressing");
    expect(A.scopeSlotForPartLabel("Trunks & Branches")).toBe("trunks");
    expect(A.scopeSlotForPartLabel("Accent Plant")).toBe("accent");
    expect(A.scopeSlotForPartLabel("Leaves")).toBe("plant_material");
    expect(A.scopeSlotForPartLabel("Main Plant")).toBe("plant_material");
    expect(A.scopeSlotForPartLabel("Ribbon")).toBeNull();
    expect(A.scopeSlotForPartLabel("")).toBeNull();
  });

  it("builderApiUrl skips empty params", () => {
    expect(A.builderApiUrl("types")).toBe("/api/builder/types");
    expect(A.builderApiUrl("density", { species: "Olive", height_in: 72, band: "", x: null, y: undefined })).toBe(
      "/api/builder/density?species=Olive&height_in=72"
    );
  });

  it("silhouetteOption falls back to the default then the first option", () => {
    expect(A.silhouetteOption("corner", A.SILHOUETTE_FALLBACK)?.key).toBe("corner");
    expect(A.silhouetteOption("nope", A.SILHOUETTE_FALLBACK)?.key).toBe("full_round");
    expect(A.silhouetteOption("nope", [{ key: "a", label: "A", depth_ratio: 1 }])?.key).toBe("a");
    expect(A.silhouetteOption("x", [])).toBeNull();
  });

  it("formatInches rounds to one decimal", () => {
    expect(A.formatInches(undefined)).toBe("");
    expect(A.formatInches(NaN)).toBe("");
    expect(A.formatInches(42)).toBe('42"');
    expect(A.formatInches(42.04)).toBe('42"');
    expect(A.formatInches(42.25)).toBe('42.3"');
  });

  it("widthForCanopyTier picks the middle of the range or a 3in offset", () => {
    const tier = (min_in: number | null, max_in: number | null) => ({ key: "M", label: "M", range_label: "", min_in, max_in });
    expect(A.widthForCanopyTier(tier(40, 46))).toBe(43);
    expect(A.widthForCanopyTier(tier(null, 30))).toBe(27);
    expect(A.widthForCanopyTier(tier(null, 2))).toBe(1);
    expect(A.widthForCanopyTier(tier(60, null))).toBe(63);
    expect(A.widthForCanopyTier(tier(null, null))).toBeNull();
    expect(A.widthForCanopyTier(null)).toBeNull();
  });

  it("confidenceLabel capitalises and de-underscores", () => {
    expect(A.confidenceLabel("very_high")).toBe("Very high");
    expect(A.confidenceLabel("  low ")).toBe("Low");
    expect(A.confidenceLabel(null)).toBe("");
  });

  it("sortedScopeTerms demotes unverified terms, then sorts by weight desc", () => {
    const sorted = A.sortedScopeTerms([
      { term: "a", weight: 1 },
      { term: "b", weight: 5, catalog_verified: false },
      { term: "c", weight: 3 },
      { term: "d", weight: 2, catalog_verified: null },
    ]);
    expect(sorted.map((t) => t.term)).toEqual(["c", "d", "a", "b"]);
  });

  it("formatProjectsCacheStamp formats a local time", () => {
    expect(A.formatProjectsCacheStamp(null)).toBe("");
    expect(A.formatProjectsCacheStamp(0)).toBe("");
    expect(A.formatProjectsCacheStamp(new Date(2026, 0, 5, 14, 7).getTime())).toMatch(/^2:07\sPM$/);
  });

  it("firstNumber extracts the first decimal number", () => {
    expect(A.firstNumber("7.5 ft")).toBe(7.5);
    expect(A.firstNumber("12' x 86\"")).toBe(12);
    expect(A.firstNumber("abc")).toBeNull();
    expect(A.firstNumber(null)).toBeNull();
  });

  it("treeWidthNumber prefers an 'x 57\"' width, then a diameter, then the first number", () => {
    expect(A.treeWidthNumber('9 ft x 57"')).toBe(57);
    expect(A.treeWidthNumber('65" diam')).toBe(65);
    expect(A.treeWidthNumber("7.5' 65 in d")).toBe(65);
    expect(A.treeWidthNumber("48")).toBe(48);
    expect(A.treeWidthNumber("Oregon Fir WA 900LED Warm White")).toBe(900);
    expect(A.treeWidthNumber(null)).toBeNull();
  });

  it("compactSkuPart strips non-alphanumerics and upper-cases", () => {
    expect(A.compactSkuPart("Oak & Ivy Hotel")).toBe("OAKIV");
    expect(A.compactSkuPart(null)).toBe("NEW");
    expect(A.compactSkuPart("!!", "BUILD")).toBe("BUILD");
    expect(A.compactSkuPart("abc123xyz", "X", 3)).toBe("ABC");
  });

  it("normalizeLabel trims and lower-cases", () => {
    expect(A.normalizeLabel("  Christmas Tree ")).toBe("christmas tree");
    expect(A.normalizeLabel(null)).toBe("");
  });
});

describe("project shells and scope basics", () => {
  afterAll(() => {
    vi.useRealTimers();
  });

  it("readProjectsListCache returns parsed cache or null", () => {
    expect(A.readProjectsListCache()).toBeNull();
    seedStorage({ "leaf-ledger:projects-list-cache:v1": { arrangements: [{ id: 1, name: "A" }], cachedAt: 5 } });
    expect(A.readProjectsListCache()).toEqual({ arrangements: [{ id: 1, name: "A" }], cachedAt: 5 });
    seedStorage({ "leaf-ledger:projects-list-cache:v1": { arrangements: "no" } });
    expect(A.readProjectsListCache()).toBeNull();
    seedStorage({ "leaf-ledger:projects-list-cache:v1": "{not json" });
    expect(A.readProjectsListCache()).toBeNull();
  });

  it("arrangementShellFromSummary builds an empty arrangement", () => {
    expect(
      A.arrangementShellFromSummary({
        id: 3, name: "Lobby", client_name: "Acme", created_at: "a", updated_at: "b", total_cost: 0, container_count: 2,
      })
    ).toEqual({
      id: 3, name: "Lobby", client_name: "Acme", notes: "", created_by: "", created_at: "a", updated_at: "b",
      rooms: [], containers: [], total_cost: 0, total_with_markup: 0,
    });
  });

  it("arrangementRouteShell stamps now", () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-03-01T12:00:00.000Z"));
    expect(A.arrangementRouteShell(9, "Acme")).toEqual({
      id: 9, name: "Opening project...", client_name: "Acme", notes: "", created_by: "",
      created_at: "2026-03-01T12:00:00.000Z", updated_at: "2026-03-01T12:00:00.000Z",
      rooms: [], containers: [], total_cost: 0, total_with_markup: 0,
    });
    vi.useRealTimers();
  });

  it("scopeTitle and scopeQuantity", () => {
    expect(A.scopeTitle(null)).toBe("Scope");
    expect(A.scopeTitle(bucket({ label: "Lobby", bucket_type: "Planter" }))).toBe("Lobby");
    expect(A.scopeTitle(bucket({ bucket_type: "Planter" }))).toBe("Planter");
    expect(A.scopeTitle(bucket({ sort_order: 2 }))).toBe("Scope 3");
    expect(A.scopeQuantity(null)).toBe(1);
    expect(A.scopeQuantity(bucket({ requested_quantity: 4 }))).toBe(4);
    expect(A.scopeQuantity(bucket({ requested_quantity: 0 }))).toBe(1);
    expect(A.scopeQuantity(bucket({ requested_quantity: -3 }))).toBe(1);
  });
});

describe("scope-notes parsers", () => {
  const intelligence = {
    build_type: "Christmas Tree",
    evidence_count: 4,
    confidence: "high",
    components: [{ label: "Ribbon", suggested_quantity: 3, evidence_count: 2 }],
  };
  const intelligenceLine = `LL_BUILD_INTELLIGENCE:${JSON.stringify(intelligence)}`;
  const notes = [
    "Height: 7.5 ft",
    'Width: 48"',
    "Species: Fraser Fir",
    'Canopy: M (42-45")',
    "Silhouette: Corner",
    "Density: Full (12 pieces)",
    "Enhancer package: Premium",
    intelligenceLine,
    'LL_CUSTOM_SECTIONS:["Lights"," ","Bows"]',
    "Deliver to lobby",
  ].join("\n");

  it("parseScopeIntelligence reads the JSON line", () => {
    expect(A.parseScopeIntelligence(notes)).toEqual(intelligence);
    expect(A.parseScopeIntelligence("LL_BUILD_INTELLIGENCE:{bad")).toBeNull();
    expect(A.parseScopeIntelligence(null)).toBeNull();
  });

  it("parseCustomSections reads trimmed non-empty strings", () => {
    expect(A.parseCustomSections(notes)).toEqual(["Lights", "Bows"]);
    expect(A.parseCustomSections('LL_CUSTOM_SECTIONS:{"a":1}')).toEqual([]);
    expect(A.parseCustomSections("LL_CUSTOM_SECTIONS:[oops")).toEqual([]);
    expect(A.parseCustomSections(undefined)).toEqual([]);
  });

  it("displayScopeNotes strips machine lines; editableScopeNotes also strips managed keys", () => {
    expect(A.displayScopeNotes(notes)).toBe(
      'Height: 7.5 ft\nWidth: 48"\nSpecies: Fraser Fir\nCanopy: M (42-45")\nSilhouette: Corner\nDensity: Full (12 pieces)\nEnhancer package: Premium\nDeliver to lobby'
    );
    expect(A.editableScopeNotes(notes)).toBe("Deliver to lobby");
    expect(A.editableScopeNotes(null)).toBe("");
  });

  it("MANAGED_SCOPE_LINE_RE matches managed keys case-insensitively", () => {
    expect(A.MANAGED_SCOPE_LINE_RE.test("Garland Length: 9 ft")).toBe(true);
    expect(A.MANAGED_SCOPE_LINE_RE.test("width / canopy: 40")).toBe(true);
    expect(A.MANAGED_SCOPE_LINE_RE.test("Notes: x")).toBe(false);
  });

  it("scopeNoteValue finds a key case-insensitively", () => {
    expect(A.scopeNoteValue(notes, "height")).toBe("7.5 ft");
    expect(A.scopeNoteValue(notes, "Missing")).toBe("");
    expect(A.scopeNoteValue(null, "Height")).toBe("");
  });

  it("dimension readers with legacy fallbacks", () => {
    expect(A.buildHeightFromNotes(notes)).toBe("7.5 ft");
    expect(A.buildWidthFromNotes(notes)).toBe('48"');
    expect(A.buildWidthFromNotes("Width / canopy: 40 in")).toBe("40 in");
    expect(A.buildDepthFromNotes("Depth: 30")).toBe("30");
    expect(A.buildDepthFromNotes("Depth / density: 24 in")).toBe("24 in");
    expect(A.buildDepthFromNotes("Depth / density: dense")).toBe("");
    expect(A.buildSpeciesFromNotes(notes)).toBe("Fraser Fir");
  });

  it("buildCanopyTierFromNotes takes the leading tier key", () => {
    expect(A.buildCanopyTierFromNotes(notes)).toBe("M");
    expect(A.buildCanopyTierFromNotes("Canopy: xl")).toBe("XL");
    expect(A.buildCanopyTierFromNotes("Canopy: Medium")).toBe("");
    expect(A.buildCanopyTierFromNotes("")).toBe("");
  });

  it("buildSilhouetteFromNotes maps labels to keys", () => {
    expect(A.buildSilhouetteFromNotes(notes)).toBe("corner");
    expect(A.buildSilhouetteFromNotes("Silhouette: 3-sided / flat-back")).toBe("flat_back");
    expect(A.buildSilhouetteFromNotes("Silhouette: Full-round")).toBe("full_round");
    expect(A.buildSilhouetteFromNotes("Silhouette: Oval")).toBe("");
  });

  it("buildDensityBandFromNotes maps words, including legacy placeholders", () => {
    expect(A.buildDensityBandFromNotes(notes)).toBe("full");
    expect(A.buildDensityBandFromNotes("Density: Super full")).toBe("super_full");
    expect(A.buildDensityBandFromNotes("Depth / density: light")).toBe("sparse");
    expect(A.buildDensityBandFromNotes("Depth / density: medium")).toBe("standard");
    expect(A.buildDensityBandFromNotes("Depth / density: 24")).toBe("");
    expect(A.buildDensityBandFromNotes("")).toBe("");
  });

  it("buildScopeSetupLines writes only supported, non-empty fields", () => {
    const values = {
      height: " 7.5 ft ", width: '48"', depth: "", species: "Fraser Fir", canopy: "M", canopyRange: '42-45"',
      silhouette: "corner", silhouetteLabel: "Corner", density: "full", densityLabel: "Full", densityPieces: 12,
    };
    const all = { height: true, width: true, canopy: true, silhouette: true, depth: true, species: true, density: true };
    expect(A.buildScopeSetupLines(all, values)).toEqual([
      "Height: 7.5 ft", "Species: Fraser Fir", 'Canopy: M (42-45")', 'Width: 48"', "Silhouette: Corner", "Density: Full (12 pieces)",
    ]);
    expect(A.buildScopeSetupLines(A.BUILDER_FIELDS_FALLBACK, values)).toEqual(["Height: 7.5 ft", 'Width: 48"']);
    expect(A.buildScopeSetupLines(all, { ...values, densityLabel: "", densityPieces: null, canopyRange: "" })).toEqual([
      "Height: 7.5 ft", "Species: Fraser Fir", "Canopy: M", 'Width: 48"', "Silhouette: Corner", "Density: full",
    ]);
  });

  it("scopeIntelligenceLine and scopeNotesWithCustomSections", () => {
    expect(A.scopeIntelligenceLine(notes)).toBe(intelligenceLine);
    expect(A.scopeIntelligenceLine("Height: 1")).toBe("");
    const b = bucket({ scope_notes: 'Height: 6 ft\nLL_CUSTOM_SECTIONS:["Old"]' });
    expect(A.scopeNotesWithCustomSections(b, [])).toBe("Height: 6 ft");
    expect(A.scopeNotesWithCustomSections(b, ["New"])).toBe('Height: 6 ft\nLL_CUSTOM_SECTIONS:["New"]');
    expect(A.scopeNotesWithCustomSections(bucket({ scope_notes: `A\n${intelligenceLine}` }), ["X"])).toBe(
      `A\n${intelligenceLine}\nLL_CUSTOM_SECTIONS:["X"]`
    );
  });

  it("enhancer package read/write", () => {
    expect(A.christmasEnhancerPackageFromNotes(notes)).toBe("premium");
    expect(A.christmasEnhancerPackageFromNotes("")).toBe("regular");
    expect(A.scopeNotesWithEnhancerPackage(bucket({ scope_notes: "Height: 9 ft\nEnhancer package: Regular" }), "premium")).toBe(
      "Height: 9 ft\nEnhancer package: Premium"
    );
    expect(A.scopeNotesWithEnhancerPackage(bucket(), "regular")).toBe("Enhancer package: Regular");
  });

  it("garland readers", () => {
    expect(A.garlandPackageFromNotes("Garland package: Premium")).toBe("premium");
    expect(A.garlandPackageFromNotes(null)).toBe("regular");
    expect(A.garlandLengthFromNotes("Garland length: 12 ft")).toBe("12");
    expect(A.garlandLengthFromNotes("Garland length: 4.5 ft")).toBe("4.5");
    expect(A.garlandLengthFromNotes('Garland size: 18 ft x 14"')).toBe("18");
    expect(A.garlandLengthFromNotes("")).toBe("9");
    expect(A.garlandDiameterFromNotes('Garland diameter: 18"')).toBe("18");
    expect(A.garlandDiameterFromNotes('Garland size: 9 ft x 18"')).toBe("18");
    expect(A.garlandDiameterFromNotes("Garland length: 18 ft")).toBe("14");
    expect(A.garlandDiameterFromNotes("")).toBe("14");
  });

  it("garland labels, multipliers and setup lines", () => {
    expect(A.garlandLengthLabel("12")).toBe("12 ft");
    expect(A.garlandLengthLabel("4.5 ft")).toBe("4.5 ft");
    expect(A.garlandLengthLabel(null)).toBe("9 ft");
    expect(A.garlandLengthMultiplier("9")).toBe(1);
    expect(A.garlandLengthMultiplier("10")).toBe(2);
    expect(A.garlandLengthMultiplier("27")).toBe(3);
    expect(A.garlandLengthMultiplier("0")).toBe(1);
    expect(A.garlandSetupLabel("12", "18")).toBe('12 ft x 18"');
    expect(A.garlandSetupLabel(null)).toBe('9 ft x 14"');
    expect(A.garlandSetupLines("premium", "12", "18")).toEqual([
      "Garland package: Premium", "Garland length: 12 ft", 'Garland diameter: 18"',
    ]);
    expect(
      A.scopeNotesWithGarlandSetup(bucket({ scope_notes: "Garland size: 9 ft\nGarland light: Lit\nNotes here" }), {
        packageType: "regular", lengthValue: "18", diameter: "14",
      })
    ).toBe('Notes here\nGarland package: Regular\nGarland length: 18 ft\nGarland diameter: 14"');
  });

  it("wreath size read/write", () => {
    expect(A.wreathSizeFromNotes('Wreath size: 36" Wreath')).toBe("36");
    expect(A.wreathSizeFromNotes("Width: 50")).toBe("48");
    expect(A.wreathSizeFromNotes("Wreath size: 32")).toBe("30");
    expect(A.wreathSizeFromNotes("Width / canopy: 30 in")).toBe("30");
    expect(A.wreathSizeFromNotes("")).toBe("24");
    expect(A.wreathSetupLines("30")).toEqual(['Wreath size: 30" Wreath']);
    expect(
      A.scopeNotesWithWreathSetup(bucket({ scope_notes: 'Height: 3 ft\nWidth: 30\nDoor 2\nWreath size: 24" Wreath' }), "48")
    ).toBe('Door 2\nWreath size: 48" Wreath');
  });
});

describe("editable build templates", () => {
  const stored = [
    { id: "wreath", section: "Christmas", name: "Wreath", usedFor: ["Wreath", " "], slots: ["Wreath Base", "Greenery", "Ribbon", "Decor"] },
    {
      id: "green-tree", section: "Other", name: " Tree ", summary: "Tall",
      slots: ["Container", "Top Dressing", "Trunks & Branches", "Leaves"], regularMaterials: [" 2 x Moss ", ""],
    },
    { id: "custom", name: "Custom", slots: ["B", "A"] },
    { id: "", name: "Nameless id" },
  ];
  const expectedStored = [
    {
      id: "wreath", section: "Christmas", name: "Wreath", summary: "", usedFor: ["Wreath"], slots: ["Wreath Base", "Decor Package"],
      regularMaterials: undefined, premiumMaterials: undefined,
    },
    {
      id: "green-tree", section: "Green", name: "Tree", summary: "Tall", usedFor: [],
      slots: ["Leaves", "Trunks & Branches", "Top Dressing", "Container"], regularMaterials: ["2 x Moss"], premiumMaterials: undefined,
    },
    { id: "custom", section: "Green", name: "Custom", summary: "", usedFor: [], slots: ["B", "A"] },
  ];

  it("DEFAULT_EDITABLE_BUILD_TEMPLATES structure", () => {
    expect(A.DEFAULT_EDITABLE_BUILD_TEMPLATES.map((t) => [t.id, t.section, t.name])).toEqual([
      ["christmas-tree", "Christmas", "Christmas Tree"],
      ["garland", "Christmas", "Garland"],
      ["wreath", "Christmas", "Wreath"],
      ["teardrop", "Christmas", "Vertical Spray"],
      ["swag", "Christmas", "Horizontal Swag"],
      ["green-tree", "Green", "Tree"],
      ["arrangement", "Green", "Arrangement"],
      ["planter", "Green", "Planter"],
      ["drop-in", "Green", "Drop-in Arrangement"],
      ["succulent", "Green", "Succulent / Cactus"],
    ]);
    expect(A.DEFAULT_EDITABLE_BUILD_TEMPLATES[0]).toEqual({
      id: "christmas-tree",
      section: "Christmas",
      name: "Christmas Tree",
      usedFor: ["Christmas Tree", "Decor Packages"],
      slots: ["Tree", "Enhancers", "Tree Skirt", "Tree Topper"],
      regularMaterials: ["2 x Assorted Branch", '1 x 4" Ornament', "2 1/2 Yards of Ribbon"],
      premiumMaterials: ["1 Flower", "2 x Assorted Branch", '1 x 4" Ornament', "1 1/2 Yards of Ribbon", "1 Yard of Premium Ribbon"],
    });
  });

  it("LEGACY_TOP_DOWN_SLOT_ORDERS and FLIPPED_SLOT_LABELS", () => {
    expect(Object.keys(A.LEGACY_TOP_DOWN_SLOT_ORDERS)).toEqual(["green-tree", "arrangement", "planter", "drop-in", "succulent"]);
    expect(A.LEGACY_TOP_DOWN_SLOT_ORDERS["drop-in"]).toEqual(["Drop-in Base", "Main Material", "Accent Material", "Finish"]);
    expect(A.FLIPPED_SLOT_COUNT).toBe(4);
    expect(A.FLIPPED_SLOT_LABELS.size).toBe(16);
    expect(A.FLIPPED_SLOT_LABELS.has("finish/top dressing")).toBe(true);
    expect(A.FLIPPED_SLOT_LABELS.has("tree")).toBe(false);
  });

  it("cleanEditableBuildTemplates migrates legacy slot orders and falls back when empty", () => {
    expect(A.cleanEditableBuildTemplates(stored)).toEqual(expectedStored);
    expect(A.cleanEditableBuildTemplates(null)).toBe(A.DEFAULT_EDITABLE_BUILD_TEMPLATES);
    expect(A.cleanEditableBuildTemplates([])).toBe(A.DEFAULT_EDITABLE_BUILD_TEMPLATES);
    expect(A.cleanEditableBuildTemplates([{ id: "", name: "x" }])).toBe(A.DEFAULT_EDITABLE_BUILD_TEMPLATES);
  });

  it("readEditableBuildTemplates returns defaults when storage is empty or corrupt", () => {
    expect(A.readEditableBuildTemplates()).toBe(A.DEFAULT_EDITABLE_BUILD_TEMPLATES);
    seedStorage({ [TEMPLATE_KEY]: "{" });
    expect(A.readEditableBuildTemplates()).toBe(A.DEFAULT_EDITABLE_BUILD_TEMPLATES);
  });

  it("readEditableBuildTemplates parses a stored template list", () => {
    seedStorage({ [TEMPLATE_KEY]: stored });
    expect(A.readEditableBuildTemplates()).toEqual(expectedStored);
  });

  it("buildTemplateMatches compares name and usedFor", () => {
    const template = A.DEFAULT_EDITABLE_BUILD_TEMPLATES[3];
    expect(A.buildTemplateMatches(template, " teardrop ")).toBe(true);
    expect(A.buildTemplateMatches(template, "Vertical Spray")).toBe(true);
    expect(A.buildTemplateMatches(template, "Tear")).toBe(false);
  });

  it("editableTemplateForBuildType resolves exact, alias, then containment (defaults)", () => {
    expect(A.editableTemplateForBuildType("Christmas Tree")?.id).toBe("christmas-tree");
    expect(A.editableTemplateForBuildType("decor packages")?.id).toBe("christmas-tree");
    expect(A.editableTemplateForBuildType("Teardrop")?.id).toBe("teardrop");
    expect(A.editableTemplateForBuildType("Greenery Tree")?.id).toBe("green-tree");
    expect(A.editableTemplateForBuildType("Big Planter Box")?.id).toBe("planter");
    expect(A.editableTemplateForBuildType("Rug")).toBeNull();
  });

  it("editableTemplateForBuildType uses stored templates instead of defaults", () => {
    seedStorage({ [TEMPLATE_KEY]: [{ id: "rug", name: "Rug Runner", usedFor: ["Rug"], slots: ["Pad", "Rug"] }] });
    expect(A.editableTemplateForBuildType("rug")?.id).toBe("rug");
    expect(A.editableTemplateForBuildType("Christmas Tree")).toBeNull();
    expect(A.templateSlotsForBuildType("Rug")).toEqual(["Pad", "Rug"]);
  });

  it("templateSlotsForBuildType returns slots or null", () => {
    expect(A.templateSlotsForBuildType("Wreath")).toEqual(["Wreath Base", "Decor Package"]);
    expect(A.templateSlotsForBuildType("Rug")).toBeNull();
    seedStorage({ [TEMPLATE_KEY]: [{ id: "rug", name: "Rug", slots: [] }] });
    expect(A.templateSlotsForBuildType("Rug")).toBeNull();
  });

  it("parseMaterialQuantity reads whole, mixed and decimal quantities", () => {
    expect(A.parseMaterialQuantity("2 x Assorted Branch")).toBe(2);
    expect(A.parseMaterialQuantity("2 1/2 Yards of Ribbon")).toBe(2.5);
    expect(A.parseMaterialQuantity("1.5 yd")).toBe(1.5);
    expect(A.parseMaterialQuantity("Flower")).toBe(1);
    expect(A.parseMaterialQuantity("0 x Foo")).toBe(1);
  });

  it("templateMaterialLabel strips quantity, units and 'per enhancer'", () => {
    expect(A.templateMaterialLabel("2 x Assorted Branch")).toBe("Assorted Branch");
    expect(A.templateMaterialLabel('1 x 4" Ornament')).toBe('4" Ornament');
    expect(A.templateMaterialLabel("2 1/2 Yards of Ribbon")).toBe("Ribbon");
    expect(A.templateMaterialLabel("1 Yard of Premium Ribbon per premium enhancer")).toBe("Premium Ribbon");
    expect(A.templateMaterialLabel("2 x Assorted Branches per enhancer")).toBe("Assorted Branches");
    expect(A.templateMaterialLabel("1 Flower")).toBe("Flower");
    expect(A.templateMaterialLabel("Moss")).toBe("Moss");
  });

  it("enhancerPartFromTemplateLine builds a part config", () => {
    expect(A.enhancerPartFromTemplateLine("2 1/2 Yards of Ribbon", "regular", new Set())).toEqual({
      label: "Ribbon", note: "Used in this enhancer package", regularFormula: "2.5 yd", premiumFormula: undefined,
      fallbackQuantity: 8, searchTerms: "christmas ribbon enhancer", optional: false, premiumOnly: false,
    });
    expect(A.enhancerPartFromTemplateLine("1 Flower", "premium", new Set(["assorted branch"]))).toEqual({
      label: "Flower", note: "Only needed for premium enhancers", regularFormula: undefined, premiumFormula: "1 each",
      fallbackQuantity: 8, searchTerms: "christmas flower enhancer", optional: true, premiumOnly: true,
    });
    expect(A.enhancerPartFromTemplateLine("1 1/2 Yards of Ribbon", "premium", new Set(["ribbon"]))?.premiumFormula).toBe("1.5 yd");
    expect(A.enhancerPartFromTemplateLine("5 Regular Enhancers", "regular", new Set())).toBeNull();
  });

  it("enhancerPartsFromTemplate reads the template materials", () => {
    const summarise = (parts: ReturnType<typeof A.enhancerPartsFromTemplate>) =>
      parts?.map((p) => [p.label, p.regularFormula ?? p.premiumFormula, p.premiumOnly]);
    expect(summarise(A.enhancerPartsFromTemplate("Christmas Tree", "regular"))).toEqual([
      ["Assorted Branch", "2 each", false], ['4" Ornament', "1 each", false], ["Ribbon", "2.5 yd", false],
    ]);
    expect(summarise(A.enhancerPartsFromTemplate("Christmas Tree", "premium"))).toEqual([
      ["Flower", "1 each", true], ["Assorted Branch", "2 each", false], ['4" Ornament', "1 each", false],
      ["Ribbon", "1.5 yd", false], ["Premium Ribbon", "1 yd", true],
    ]);
    expect(summarise(A.enhancerPartsFromTemplate("Garland", "regular"))).toEqual([
      ["Assorted Branches", "2 each", false], ['4" Ornament', "1 each", false], ["Ribbon", "2.5 yd", false],
    ]);
    expect(A.enhancerPartsFromTemplate("Wreath", "regular")).toBeNull();
  });
});

describe("config tables", () => {
  it("BUILD_TYPE_CONFIGS structure", () => {
    expect(A.BUILD_TYPE_CONFIGS.map((c) => [c.section, c.label, c.skuCode])).toEqual([
      ["green", "Tree", "GR-TREE"],
      ["green", "Arrangement", "GR-ARR"],
      ["green", "Planter", "GR-PLN"],
      ["green", "Drop-in Arrangement", "GR-DRP"],
      ["christmas", "Christmas Tree", "CH-TREE"],
      ["christmas", "Garland", "CH-GAR"],
      ["christmas", "Wreath", "CH-WRE"],
      ["christmas", "Vertical Spray", "CH-VSP"],
      ["christmas", "Horizontal Swag", "CH-HSW"],
    ]);
    const planter = A.BUILD_TYPE_CONFIGS[2];
    expect(Object.keys(planter)).toEqual(["section", "label", "skuCode", "icon", "aliases", "prefixes", "visibleParts"]);
    expect(planter.icon).toBeTruthy();
    expect(planter.aliases).toEqual(["Planter", "Container Garden", "Plant / Vase", "Container Arrangement"]);
    expect(planter.prefixes).toEqual(["CG", "PV", "CT"]);
    expect(planter.visibleParts).toEqual(["Accent Plant", "Main Plant", "Finish/Top Dressing", "Container/Planter"]);
  });

  it("enhancer/wreath/garland tables", () => {
    expect(A.CHRISTMAS_ENHANCER_PARTS.map((p) => [p.label, p.regularFormula, p.premiumFormula, p.fallbackQuantity])).toEqual([
      ["Assorted Branch", "2 each", "2 each", 8],
      ['4" Ornament', "1 each", "1 each", 8],
      ["Ribbon", "2.5 yd", "1.5 yd", 20],
      ["Flower", undefined, "1 each", 8],
      ["Premium Ribbon", undefined, "1 yd", 8],
    ]);
    expect(A.GARLAND_DIAMETER_OPTIONS).toEqual(["14", "18"]);
    expect(A.WREATH_SIZE_OPTIONS).toEqual(["24", "30", "36", "48"]);
    expect(A.WREATH_DECOR_PARTS.map((p) => p.label)).toEqual([
      "Assorted Branches", "Ribbon", '4" Ornaments', "Flowers", '8" Ornaments', '6" Ornaments',
    ]);
    expect(Object.keys(A.WREATH_DECOR_RECIPES)).toEqual(["24", "30", "36", "48"]);
    expect(A.WREATH_DECOR_RECIPES["48"]).toEqual([
      { label: "Flowers", quantity: 3, unit: "total" },
      { label: "Assorted Branches", quantity: 14, unit: "total" },
      { label: '8" Ornaments', quantity: 2, unit: "total" },
      { label: '6" Ornaments', quantity: 3, unit: "total" },
    ]);
    expect(A.GARLAND_ENHANCER_PARTS.map((p) => [p.label, "premiumOnly" in p])).toEqual([
      ["Assorted Branches", false], ['4" Ornament', false], ["Ribbon", false],
      ["Flower", true], ["Premium Ribbon", true], ["Extra Ornaments", true],
    ]);
  });

  it("christmas tree option tables", () => {
    expect(A.CHRISTMAS_TREE_OPTIONS).toHaveLength(31);
    expect(A.CHRISTMAS_TREE_OPTIONS[0]).toEqual({
      code: "C164176LED", name: "Oregon Fir WA 900LED Warm White", source: "Vickerman", heightFeet: 7.5,
      heightLabel: "7.5 ft", diameterIn: 65, profile: "Standard", lightStatus: "Lit",
    });
    expect(A.CHRISTMAS_TREE_SIZE_OPTIONS.map((o) => o.code)).toEqual([
      "6-PENCIL", "7-5-PENCIL", "7-SLIM", "7-5-8-STANDARD", "9-PENCIL", "9-SLIM", "9-STANDARD", "10-STANDARD",
      "12-SLIM", "12-STANDARD", "14-STANDARD", "15-STANDARD",
    ]);
  });

  it("misc constants", () => {
    expect(A.BUILDER_FIELD_KEYS).toEqual(["height", "width", "canopy", "silhouette", "depth", "species", "density"]);
    expect(A.SILHOUETTE_FALLBACK.map((s) => [s.key, s.depth_ratio])).toEqual([["full_round", 1], ["corner", 0.66], ["flat_back", 0.5]]);
    expect(A.INTELLIGENCE_NOTE_PREFIX).toBe("LL_BUILD_INTELLIGENCE:");
    expect(A.CUSTOM_SECTIONS_PREFIX).toBe("LL_CUSTOM_SECTIONS:");
    expect(A.BUILD_TEMPLATE_STORAGE_KEY).toBe(TEMPLATE_KEY);
    expect(A.BUILDER_TYPES_CACHE_KEY).toBe(BUILDER_TYPES_KEY);
    expect(A.PROJECTS_LIST_CACHE_KEY).toBe("leaf-ledger:projects-list-cache:v1");
    expect(A.BUILDER_CATALOG_PAGE_SIZE).toBe(48);
    expect(A.EMPTY_CATALOG_SELECTION).toEqual({ categories: [], colors: [], product_types: [] });
  });
});

describe("build type resolution", () => {
  it("buildTypeConfigFor resolves exact aliases then keyword fallbacks in order", () => {
    const label = (value: string) => A.buildTypeConfigFor(value)?.label ?? null;
    expect(label("Tree / Plant")).toBe("Tree");
    expect(label("christmas tree - lobby")).toBe("Christmas Tree");
    expect(label("Front door WREATH")).toBe("Wreath");
    expect(label("Lantern drop")).toBe("Vertical Spray");
    expect(label("door drop box")).toBe("Vertical Spray");
    expect(label("Mantel swag")).toBe("Horizontal Swag");
    expect(label("drop")).toBe("Drop-in Arrangement");
    expect(label("Container Garden")).toBe("Planter");
    expect(label("Fiddle fig")).toBe("Tree");
    expect(label("Garland tree")).toBe("Garland");
    expect(label("Foliage wall")).toBe("Arrangement");
    expect(label("Rug")).toBeNull();
    expect(label("")).toBeNull();
  });

  it("designPartsForBuildType uses template, then config, then API slots", () => {
    expect(A.designPartsForBuildType("Tree")).toEqual(["Leaves", "Trunks & Branches", "Top Dressing", "Container"]);
    expect(A.designPartsForBuildType("Swag")).toEqual(["Horizontal Swag Base", "Greenery", "Ribbon", "Decor"]);
    expect(A.designPartsForBuildType("Topiary")).toEqual(["Container", "Topiary Form"]);
    expect(A.designPartsForBuildType("Rug")).toBeNull();
    // With stored templates lacking a match, the static config still answers.
    seedStorage({ [TEMPLATE_KEY]: [{ id: "rug", name: "Rug", slots: ["Pad"] }] });
    expect(A.designPartsForBuildType("Wreath")).toEqual(["Wreath Base", "Decor Package"]);
  });

  it("baseScopePlaceholders, fallbackSectionsForBuildType, scopePlaceholders", () => {
    expect(A.baseScopePlaceholders(bucket({ bucket_type: "Garland", label: "Lobby" }))).toEqual(["Garland", "Enhancers"]);
    const intel = `LL_BUILD_INTELLIGENCE:${JSON.stringify({ components: [{ label: "Pad" }, { label: "Rug" }, { label: "Tape" }] })}`;
    expect(A.baseScopePlaceholders(bucket({ bucket_type: "Rug", scope_notes: intel }))).toEqual(["Pad", "Rug", "Tape", "Product"]);
    expect(A.baseScopePlaceholders(bucket({ label: "Rug" }))).toEqual(["Products", "Notes", "Pricing", "Product"]);
    expect(A.fallbackSectionsForBuildType("Rug")).toEqual(["Products", "Notes", "Pricing"]);
    expect(A.fallbackSectionsForBuildType("container thing")).toEqual(["Accent Plant", "Main Plant", "Finish/Top Dressing", "Container/Planter"]);
    expect(A.fallbackSectionsForBuildType("Tree")).toEqual(["Leaves", "Trunks & Branches", "Top Dressing", "Container"]);
    expect(A.scopePlaceholders(bucket({ bucket_type: "Wreath", scope_notes: 'LL_CUSTOM_SECTIONS:["Bow"]' }))).toEqual([
      "Wreath Base", "Decor Package", "Bow",
    ]);
  });

  it("is*Build / is*Bucket predicates", () => {
    expect(A.isChristmasTreeBuild("Christmas Tree")).toBe(true);
    expect(A.isChristmasTreeBuild("Tree")).toBe(false);
    expect(A.isChristmasTreeBuild(null)).toBe(false);
    expect(A.isChristmasTreeBucket(bucket({ bucket_type: "Christmas Tree" }))).toBe(true);
    expect(A.isChristmasTreeBucket(null)).toBe(false);
    expect(A.isGarlandBuild("Mantel garland")).toBe(true);
    expect(A.isGarlandBucket(bucket({ label: "Garland" }))).toBe(true);
    expect(A.isWreathBuild("Swag")).toBe(false);
    expect(A.isWreathBucket(bucket({ label: "Door Wreath" }))).toBe(true);
    expect(A.isStructuredChristmasBucket(bucket({ bucket_type: "Wreath" }))).toBe(true);
    expect(A.isStructuredChristmasBucket(bucket({ bucket_type: "Vertical Spray" }))).toBe(false);
    expect(A.isStructuredChristmasBucket(bucket({ bucket_type: "Tree" }))).toBe(false);
  });

  it("isEnhancersPart / isWreathDecorPart", () => {
    expect(A.isEnhancersPart("Enhancers")).toBe(true);
    expect(A.isEnhancersPart("Tree Topper")).toBe(false);
    expect(A.isWreathDecorPart("Decor Package")).toBe(true);
    expect(A.isWreathDecorPart(" decor ")).toBe(true);
    expect(A.isWreathDecorPart("Decor Items")).toBe(false);
  });
});

describe("christmas tree decor", () => {
  it("christmasTreeDecorRule by height and width", () => {
    expect(A.christmasTreeDecorRule(null, null)).toBeNull();
    expect(A.christmasTreeDecorRule("15 ft")).toEqual({ label: "15 ft", enhancers: 60, ornaments: 200 });
    expect(A.christmasTreeDecorRule("14 ft")).toEqual({ label: "14 ft", enhancers: 48, ornaments: 160 });
    expect(A.christmasTreeDecorRule("12 ft", '86"')).toEqual({ label: "12 ft standard", enhancers: 36, ornaments: 126 });
    expect(A.christmasTreeDecorRule("12", "72")).toEqual({ label: "12 ft slim", enhancers: 30, ornaments: 108 });
    expect(A.christmasTreeDecorRule("9.5")).toEqual({ label: "9.5-10 ft", enhancers: 24, ornaments: 84 });
    expect(A.christmasTreeDecorRule("9", "57")).toEqual({ label: "8.5-9 ft standard", enhancers: 18, ornaments: 72 });
    expect(A.christmasTreeDecorRule("9", "50")).toEqual({ label: "8.5-9 ft slim", enhancers: 16, ornaments: 60 });
    expect(A.christmasTreeDecorRule("7.5", "30")).toEqual({ label: "7.5 ft pencil", enhancers: 8, ornaments: 30 });
    expect(A.christmasTreeDecorRule("7.5", "42")).toEqual({ label: "7-7.5 ft slim", enhancers: 8, ornaments: 36 });
    expect(A.christmasTreeDecorRule("7.5", null)).toEqual({ label: "7.5 ft standard", enhancers: 14, ornaments: 60 });
    expect(A.christmasTreeDecorRule("6")).toEqual({ label: "small tree", enhancers: 8, ornaments: 30 });
    expect(A.christmasTreeDecorRule(null, "50")).toEqual({ label: "small tree", enhancers: 8, ornaments: 30 });
  });

  it("christmasTreeDecorRuleForBucket reads notes then the selected tree name", () => {
    expect(A.christmasTreeDecorRuleForBucket(null)).toBeNull();
    expect(A.christmasTreeDecorRuleForBucket(bucket({ scope_notes: "Height: 9.5 ft" }))?.label).toBe("9.5-10 ft");
    expect(
      A.christmasTreeDecorRuleForBucket(bucket({ items: [item({ part_key: "0-tree", product_name: 'Brighton Pine 12\' x 73"' })] }))?.label
    ).toBe("12 ft standard");
  });

  it("christmasEnhancerCountSummary", () => {
    expect(A.christmasEnhancerCountSummary(null)).toBe("Select a tree size to calculate how many enhancers are needed.");
    expect(A.christmasEnhancerCountSummary(A.christmasTreeDecorRule("7.5"), "Slim")).toBe(
      "14 enhancers needed for the 7.5 ft standard slim tree selected."
    );
    expect(A.christmasEnhancerCountSummary(A.christmasTreeDecorRule("12", "72"), "Slim")).toBe(
      "30 enhancers needed for the 12 ft slim tree selected."
    );
  });

  it("christmasEnhancerPartIndex / christmasEnhancerBaseCount", () => {
    expect(A.christmasEnhancerPartIndex(2, 3)).toBe(204);
    expect(A.christmasEnhancerPartIndex(0, 0)).toBe(1);
    expect(A.christmasEnhancerBaseCount(null)).toBe(8);
    expect(A.christmasEnhancerBaseCount(bucket({ scope_notes: "Height: 14 ft" }))).toBe(48);
  });

  it("mergeEnhancerParts keeps the first formula per label", () => {
    expect(
      A.mergeEnhancerParts([
        { label: "Ribbon", note: "a", regularFormula: "2.5 yd", fallbackQuantity: 20 },
        { label: "ribbon ", note: "b", premiumFormula: "1.5 yd", fallbackQuantity: 8 },
        { label: "Flower", note: "c", fallbackQuantity: 8 },
      ])
    ).toEqual([
      { label: "ribbon ", note: "b", regularFormula: "2.5 yd", premiumFormula: "1.5 yd", fallbackQuantity: 8 },
      { label: "Flower", note: "c", fallbackQuantity: 8 },
    ]);
  });

  it("allChristmasEnhancerPartConfigs merges template packages, else the static table", () => {
    expect(A.allChristmasEnhancerPartConfigs().map((p) => [p.label, p.regularFormula, p.premiumFormula, p.optional])).toEqual([
      ["Assorted Branch", "2 each", "2 each", false],
      ['4" Ornament', "1 each", "1 each", false],
      ["Ribbon", "2.5 yd", "1.5 yd", false],
      ["Flower", undefined, "1 each", true],
      ["Premium Ribbon", undefined, "1 yd", true],
    ]);
    seedStorage({ [TEMPLATE_KEY]: [{ id: "rug", name: "Rug", slots: ["Pad"] }] });
    expect(A.allChristmasEnhancerPartConfigs()).toBe(A.CHRISTMAS_ENHANCER_PARTS);
  });

  it("christmasEnhancerPartConfig and formula accessors", () => {
    expect(A.christmasEnhancerPartConfig("ribbon")?.premiumFormula).toBe("1.5 yd");
    expect(A.christmasEnhancerPartConfig("Tree")).toBeUndefined();
    expect(A.christmasEnhancerPartIsOptional({ label: "x", note: "", fallbackQuantity: 1, optional: false, premiumOnly: true })).toBe(true);
    expect(A.christmasEnhancerPartIsOptional({ label: "x", note: "", fallbackQuantity: 1 })).toBe(false);
    expect(A.christmasEnhancerRegularFormula(A.CHRISTMAS_ENHANCER_PARTS[0])).toBe("2 each");
    expect(A.christmasEnhancerRegularFormula(A.CHRISTMAS_ENHANCER_PARTS[3])).toBe("");
    expect(A.christmasEnhancerPremiumFormula(A.CHRISTMAS_ENHANCER_PARTS[3])).toBe("1 each");
    expect(A.christmasEnhancerPartRequiredForPackage(A.CHRISTMAS_ENHANCER_PARTS[3], "regular")).toBe(false);
    expect(A.christmasEnhancerPartRequiredForPackage(A.CHRISTMAS_ENHANCER_PARTS[3], "premium")).toBe(true);
  });

  it("christmasEnhancerPartsForPackage from template and from the static fallback", () => {
    expect(A.christmasEnhancerPartsForPackage("regular").map((p) => p.label)).toEqual(["Assorted Branch", '4" Ornament', "Ribbon"]);
    expect(A.christmasEnhancerPartsForPackage("premium").map((p) => p.label)).toEqual([
      "Flower", "Assorted Branch", '4" Ornament', "Ribbon", "Premium Ribbon",
    ]);
    seedStorage({ [TEMPLATE_KEY]: [{ id: "rug", name: "Rug", slots: ["Pad"] }] });
    expect(A.christmasEnhancerPartsForPackage("regular").map((p) => p.label)).toEqual(["Assorted Branch", '4" Ornament', "Ribbon"]);
    expect(A.christmasEnhancerPartsForPackage("premium").map((p) => p.label)).toEqual([
      "Assorted Branch", '4" Ornament', "Ribbon", "Flower", "Premium Ribbon",
    ]);
  });

  it("christmasEnhancerPartSubIndex", () => {
    expect(A.christmasEnhancerPartSubIndex("Ribbon")).toBe(2);
    expect(A.christmasEnhancerPartSubIndex("Premium Ribbon")).toBe(4);
    expect(A.christmasEnhancerPartSubIndex("Nope")).toBe(0);
  });

  it("christmasEnhancerPartQuantity / PreviewText / TargetText", () => {
    const premium = bucket({ bucket_type: "Christmas Tree", scope_notes: 'Height: 9 ft\nWidth: 57"\nEnhancer package: Premium' });
    const regular = bucket({ bucket_type: "Christmas Tree", scope_notes: 'Height: 9 ft\nWidth: 57"' });
    expect(A.christmasEnhancerPartQuantity(premium, "Ribbon")).toBe(27);
    expect(A.christmasEnhancerPartQuantity(premium, "Assorted Branch")).toBe(36);
    expect(A.christmasEnhancerPartQuantity(regular, "Ribbon")).toBe(45);
    expect(A.christmasEnhancerPartQuantity(regular, "Flower")).toBe(18);
    expect(A.christmasEnhancerPartQuantity(null, "Ribbon")).toBe(20);
    expect(A.christmasEnhancerPartPreviewText("Ribbon", 14, "regular")).toBe("35 yd");
    expect(A.christmasEnhancerPartPreviewText("Flower", 14, "premium")).toBe("14 total");
    expect(A.christmasEnhancerPartPreviewText("Premium Ribbon", 10, "premium")).toBe("10 yd");
    expect(A.christmasEnhancerPartPreviewText("Flower", 14, "regular")).toBe("14 total");
    expect(A.christmasEnhancerPartTargetText(premium, "Ribbon")).toBe("27 yd");
  });

  it("christmasEnhancerPartItems uses the composite part index", () => {
    const b = bucket({ items: [item({ id: 1, part_key: "103-ribbon" }), item({ id: 2, part_key: "102-ribbon" }), item({ id: 3 })] });
    expect(A.christmasEnhancerPartItems(b, 1, 2).map((i: Loose) => i.id)).toEqual([1]);
    expect(A.christmasEnhancerPartItems(b, 1, 9)).toEqual([]);
  });
});

describe("garland and wreath enhancers", () => {
  it("garlandEnhancerRule", () => {
    expect(A.garlandEnhancerRule("regular", "9")).toEqual({ label: "regular", regularEnhancers: 5, premiumEnhancers: 0, extraOrnaments: 0 });
    expect(A.garlandEnhancerRule("premium", "18")).toEqual({ label: "premium", regularEnhancers: 4, premiumEnhancers: 6, extraOrnaments: 4 });
  });

  it("garland part config lookups", () => {
    expect(A.garlandEnhancerPartConfig("flower")).toEqual({
      label: "Flower", note: "Only needed for premium garland", premiumOnly: true, searchTerms: "christmas flower floral pick",
    });
    expect(A.garlandEnhancerPartConfig("nope")).toBeUndefined();
    expect(A.garlandEnhancerPartsForPackage("regular").map((p) => p.label)).toEqual(["Assorted Branches", '4" Ornament', "Ribbon"]);
    expect(A.garlandEnhancerPartsForPackage("premium").map((p) => p.label)).toEqual([
      "Flower", "Assorted Branches", '4" Ornament', "Ribbon", "Premium Ribbon", "Extra Ornaments",
    ]);
    expect(A.garlandEnhancerPartSubIndex("Extra Ornaments")).toBe(5);
    expect(A.garlandEnhancerPartSubIndex("x")).toBe(0);
  });

  it("formatGarlandQuantity", () => {
    expect(A.formatGarlandQuantity(12.5, "yd")).toBe("12.5 yd");
    expect(A.formatGarlandQuantity(10, "total")).toBe("10 total");
    expect(A.formatGarlandQuantity(2.04, "yd")).toBe("2 yd");
  });

  it("garlandEnhancerPartQuantity by label", () => {
    expect(A.garlandEnhancerPartQuantity("premium", "Assorted Branches", "18")).toBe(20);
    expect(A.garlandEnhancerPartQuantity("premium", '4" Ornament', "18")).toBe(10);
    expect(A.garlandEnhancerPartQuantity("premium", "Ribbon", "18")).toBe(19);
    expect(A.garlandEnhancerPartQuantity("premium", "Flower", "18")).toBe(6);
    expect(A.garlandEnhancerPartQuantity("premium", "Premium Ribbon", "18")).toBe(6);
    expect(A.garlandEnhancerPartQuantity("premium", "Extra Ornaments", "18")).toBe(4);
    expect(A.garlandEnhancerPartQuantity("premium", "Tree Skirt", "18")).toBe(10);
    expect(A.garlandEnhancerPartQuantity("regular", "Ribbon", "9")).toBe(12.5);
    expect(A.garlandEnhancerPartQuantity("regular", "Assorted Branches")).toBe(10);
  });

  it("garland preview/target text, items and summary", () => {
    expect(A.garlandEnhancerPartPreviewText("Ribbon", "regular", "9")).toBe("12.5 yd");
    expect(A.garlandEnhancerPartPreviewText("Premium Ribbon", "premium", "18")).toBe("6 yd");
    expect(A.garlandEnhancerPartPreviewText("Flower", "regular", null)).toBe("0 total");
    expect(A.garlandEnhancerPartTargetText(bucket({ scope_notes: "Garland package: Premium\nGarland length: 18 ft" }), "Ribbon")).toBe("19 yd");
    const b = bucket({ items: [item({ id: 1, part_key: "3-ribbon" }), item({ id: 2 })] });
    expect(A.garlandEnhancerPartItems(b, 0, 2).map((i: Loose) => i.id)).toEqual([1]);
    expect(A.garlandEnhancerPartItems(b, 0, 99)).toEqual([]);
    expect(A.garlandEnhancerCountSummary("regular", "9", "14")).toBe('5 regular enhancers needed for the Regular Garland 9 ft x 14" selected.');
    expect(A.garlandEnhancerCountSummary("premium", "18", "18")).toBe(
      '6 premium enhancers, 4 regular enhancers, and 4 extra ornaments needed for the Premium Garland 18 ft x 18" selected.'
    );
  });

  it("wreath decor helpers", () => {
    expect(A.wreathDecorPartConfig("ribbon")?.note).toBe("Ribbon yardage changes with wreath size");
    expect(A.wreathDecorPartsForSize("24")).toEqual([
      { label: "Assorted Branches", note: "Branch count changes with wreath size", searchTerms: "christmas assorted branch pine berry pick spray", quantity: 4, unit: "total" },
      { label: "Ribbon", note: "Ribbon yardage changes with wreath size", searchTerms: "christmas ribbon wired ribbon", quantity: 3, unit: "yd" },
      { label: '4" Ornaments', note: "Small ornaments for 24 and 30 inch wreaths", searchTerms: "christmas 4 inch ornament ball", quantity: 3, unit: "total" },
    ]);
    expect(A.wreathDecorPartSubIndex('6" Ornaments')).toBe(5);
    expect(A.wreathDecorPartSubIndex("nope")).toBe(0);
    const b = bucket({ items: [item({ id: 7, part_key: "101-assorted-branches" })] });
    expect(A.wreathDecorPartItems(b, 1, 0).map((i: Loose) => i.id)).toEqual([7]);
    expect(A.wreathDecorPartPreviewText("Ribbon", "36")).toBe("6 yd");
    expect(A.wreathDecorPartPreviewText('8" Ornaments', "24")).toBe("");
    expect(A.wreathDecorCountSummary("30")).toBe('5 total assorted branches, 4 yd ribbon, 5 total 4" ornaments needed for the 30" wreath selected.');
  });
});

describe("part keys and items", () => {
  it("partKey slugs the label", () => {
    expect(A.partKey("Trunks & Branches", 1)).toBe("1-trunks-branches");
    expect(A.partKey('4" Ornament', 101)).toBe("101-4-ornament");
    expect(A.partKey("Container/Base", 3)).toBe("3-container-base");
    expect(A.partKey("!!!", 0)).toBe("0-part");
  });

  it("legacySlotIndex / partKeysForSlot", () => {
    expect(A.legacySlotIndex("Container", 3)).toBe(0);
    expect(A.legacySlotIndex("Leaves", 0)).toBe(3);
    expect(A.legacySlotIndex("container ", 1)).toBe(2);
    expect(A.legacySlotIndex("Tree", 0)).toBeNull();
    expect(A.legacySlotIndex("Container", 4)).toBeNull();
    expect(A.partKeysForSlot("Leaves", 0)).toEqual(["0-leaves", "3-leaves"]);
    expect(A.partKeysForSlot("Tree", 0)).toEqual(["0-tree"]);
  });

  it("itemsForPart honours legacy keys and untagged items", () => {
    const b = bucket({
      items: [
        item({ id: 1, part_key: "0-leaves" }),
        item({ id: 2, part_key: "3-leaves" }),
        item({ id: 3 }),
        item({ id: 4, part_key: "3-container" }),
        item({ id: 5, part_key: "0-container" }),
      ],
    });
    const ids = (label: string, index: number) => A.itemsForPart(b, label, index).map((i: Loose) => i.id);
    expect(ids("Leaves", 0)).toEqual([1, 2]);
    expect(ids("Container", 3)).toEqual([3, 4, 5]);
    expect(ids("Tree", 0)).toEqual([3]);
    expect(A.itemsForPart(null, "Tree", 0)).toEqual([]);
  });

  it("primarySelectedForPart prefers selected items", () => {
    const b = bucket({ items: [item({ id: 1, part_key: "0-tree", status: "candidate" }), item({ id: 2, part_key: "0-tree", status: "selected" })] });
    expect(A.primarySelectedForPart(b, "Tree", 0)?.id).toBe(2);
    const candidates = bucket({ items: [item({ id: 1, part_key: "0-tree", status: "candidate" })] });
    expect(A.primarySelectedForPart(candidates, "Tree", 0)?.id).toBe(1);
    expect(A.primarySelectedForPart(bucket(), "Tree", 0)).toBeNull();
  });

  it("partIsComplete for plain parts", () => {
    const candidate = item({ id: 1, part_key: "0-leaves", status: "candidate" });
    expect(A.partIsComplete(bucket({ bucket_type: "Tree", items: [candidate] }), "Leaves", 0)).toBe(false);
    expect(A.partIsComplete(bucket({ bucket_type: "Tree", items: [candidate, item({ id: 2, part_key: "3-leaves" })] }), "Leaves", 0)).toBe(true);
  });

  it("partIsComplete for christmas tree, garland and wreath sub-parts", () => {
    const treeItems = [item({ part_key: "101-assorted-branch" }), item({ part_key: "102-4-ornament" }), item({ part_key: "103-ribbon" })];
    expect(A.partIsComplete(bucket({ bucket_type: "Christmas Tree", items: treeItems }), "Enhancers", 1)).toBe(true);
    expect(A.partIsComplete(bucket({ bucket_type: "Christmas Tree", items: treeItems.slice(0, 2) }), "Enhancers", 1)).toBe(false);
    const garlandItems = [item({ part_key: "101-assorted-branches" }), item({ part_key: "102-4-ornament" }), item({ part_key: "103-ribbon" })];
    expect(A.partIsComplete(bucket({ bucket_type: "Garland", items: garlandItems }), "Enhancers", 1)).toBe(true);
    expect(
      A.partIsComplete(bucket({ bucket_type: "Garland", scope_notes: "Garland package: Premium", items: garlandItems }), "Enhancers", 1)
    ).toBe(false);
    const wreathItems = [item({ part_key: "101-assorted-branches" }), item({ part_key: "102-ribbon" }), item({ part_key: "103-4-ornaments" })];
    expect(A.partIsComplete(bucket({ bucket_type: "Wreath", scope_notes: "Wreath size: 24", items: wreathItems }), "Decor Package", 1)).toBe(true);
    expect(A.partIsComplete(bucket({ bucket_type: "Wreath", scope_notes: "Wreath size: 48", items: wreathItems }), "Decor Package", 1)).toBe(false);
  });
});

describe("suggestions, search terms and guidance", () => {
  const components = [
    { label: "Container", suggested_quantity: 1, evidence_count: 3, search_terms: ["pot", "planter"] },
    { label: "Spanish moss", suggested_quantity: 2.6, evidence_count: 5, average_extended_total: 3.25 },
    { label: "Sheet moss", suggested_quantity: 1, evidence_count: 9 },
    { label: "Orchid", suggested_quantity: 3, evidence_count: 2, average_extended_total: 40 },
    { label: "Pad", suggested_quantity: 1, evidence_count: 1, search_terms: ["felt pad", ""] },
  ];
  const intelBucket = bucket({
    bucket_type: "Planter",
    scope_notes: `LL_BUILD_INTELLIGENCE:${JSON.stringify({ build_type: "Planter", evidence_count: 1, confidence: "low", components })}`,
  });

  it("componentLooksLikePart", () => {
    expect(A.componentLooksLikePart("Fraser Fir 9ft", "Tree")).toBe(true);
    expect(A.componentLooksLikePart("Red ribbon", "Enhancers")).toBe(true);
    expect(A.componentLooksLikePart("Moss", "Finish/Top Dressing")).toBe(true);
    expect(A.componentLooksLikePart("Ceramic container", "Container/Base")).toBe(true);
    expect(A.componentLooksLikePart("Orchid", "Focal Material")).toBe(true);
    expect(A.componentLooksLikePart("Warm lights", "Tree Lights")).toBe(true);
    expect(A.componentLooksLikePart("Leaf", "Accent Material")).toBe(false);
    expect(A.componentLooksLikePart("Pad", "Rug")).toBe(false);
  });

  it("suggestionForPart finds direct then best-evidence mapped components", () => {
    expect(A.suggestionForPart(intelBucket, "container", 3)?.label).toBe("Container");
    expect(A.suggestionForPart(intelBucket, "Finish/Top Dressing", 2)?.label).toBe("Sheet moss");
    expect(A.suggestionForPart(intelBucket, "Rug", 0)).toBeNull();
    expect(A.suggestionForPart(null, "Tree", 0)).toBeNull();
  });

  it("searchTermsForPart for christmas builds", () => {
    const tree = bucket({ bucket_type: "Christmas Tree" });
    expect(A.searchTermsForPart(tree, "Ribbon", 0)).toBe("christmas ribbon enhancer");
    expect(A.searchTermsForPart(tree, "Tree", 0)).toBe("christmas tree lit unlit pine fir spruce");
    expect(A.searchTermsForPart(tree, "Tree Skirt", 2)).toBe("christmas tree skirt");
    const garland = bucket({ bucket_type: "Garland" });
    expect(A.searchTermsForPart(garland, "Garland", 0)).toBe("christmas garland lighted unlit pine mixed greenery");
    expect(A.searchTermsForPart(garland, "Premium Ribbon", 0)).toBe("premium christmas ribbon wired ribbon");
    const wreath = bucket({ bucket_type: "Wreath" });
    expect(A.searchTermsForPart(wreath, "Wreath Base", 0)).toBe("wreath");
    expect(A.searchTermsForPart(wreath, "Decor Package", 1)).toBe("christmas wreath branch ribbon ornament flower");
  });

  it("searchTermsForPart for green builds and suggestions", () => {
    const tree = bucket({ bucket_type: "Tree" });
    expect(A.searchTermsForPart(tree, "Top Dressing", 2)).toBe("moss");
    expect(A.searchTermsForPart(tree, "Leaves", 0)).toBe("leaf");
    expect(A.searchTermsForPart(tree, "Main Plant", 1)).toBe("orchid");
    expect(A.searchTermsForPart(intelBucket, "Container", 3)).toBe("container");
    expect(A.searchTermsForPart(intelBucket, "Pad", 4)).toBe("felt pad");
    expect(A.searchTermsForPart(intelBucket, "Rug", 5)).toBe("Rug");
  });

  it("suggestedQuantityForPart", () => {
    const tree = bucket({ bucket_type: "Christmas Tree", scope_notes: 'Height: 9 ft\nWidth: 57"\nEnhancer package: Premium' });
    expect(A.suggestedQuantityForPart(tree, "Ribbon", 0)).toBe(27);
    expect(A.suggestedQuantityForPart(tree, "Tree Topper", 3)).toBe(1);
    const garland = bucket({ bucket_type: "Garland", scope_notes: "Garland package: Premium\nGarland length: 18 ft" });
    expect(A.suggestedQuantityForPart(garland, "Ribbon", 0)).toBe(19);
    expect(A.suggestedQuantityForPart(garland, "Flower", 0)).toBe(6);
    expect(A.suggestedQuantityForPart(bucket({ bucket_type: "Garland" }), "Ribbon", 0)).toBe(13);
    const wreath = bucket({ bucket_type: "Wreath", scope_notes: "Wreath size: 48" });
    expect(A.suggestedQuantityForPart(wreath, '8" Ornaments', 1)).toBe(2);
    expect(A.suggestedQuantityForPart(wreath, "Wreath Base", 0)).toBe(1);
    expect(A.suggestedQuantityForPart(intelBucket, "Spanish moss", 2)).toBe(3);
  });

  it("christmasPartGuidance", () => {
    const garland = bucket({ bucket_type: "Garland", scope_notes: 'Garland package: Premium\nGarland length: 18 ft\nGarland diameter: 18"' });
    expect(A.christmasPartGuidance(garland, "Garland")).toBe("Choose the base garland, lighted or unlit.");
    expect(A.christmasPartGuidance(garland, "Enhancers")).toBe(
      '6 premium enhancers, 4 regular enhancers, and 4 extra ornaments needed for the Premium Garland 18 ft x 18" selected.'
    );
    expect(A.christmasPartGuidance(garland, "Other")).toBe("");
    const wreath = bucket({ bucket_type: "Wreath", scope_notes: 'Wreath size: 36"' });
    expect(A.christmasPartGuidance(wreath, "Wreath Base")).toBe('Choose the 36" wreath base.');
    expect(A.christmasPartGuidance(wreath, "Decor Package")).toBe(
      '2 total flowers, 7 total assorted branches, 6 yd ribbon needed for the 36" wreath selected.'
    );
    const tree = bucket({ bucket_type: "Christmas Tree", scope_notes: "Height: 7.5 ft" });
    expect(A.christmasPartGuidance(tree, "Enhancers")).toBe(
      "Regular enhancers use assorted branches, 4-inch ornaments, and ribbon. Premium adds flowers and premium ribbon. Size guide: 14 enhancer sets and 60 loose ornaments/clusters."
    );
    expect(A.christmasPartGuidance(bucket({ bucket_type: "Christmas Tree" }), "Enhancers")).toBe(
      "Regular enhancers use assorted branches, 4-inch ornaments, and ribbon. Premium adds flowers and premium ribbon."
    );
    expect(A.christmasPartGuidance(tree, "Tree")).toBe("Choose the tree, lit or unlit.");
    expect(A.christmasPartGuidance(tree, "Tree Skirt")).toBe("Sized to the tree diameter.");
    expect(A.christmasPartGuidance(bucket({ bucket_type: "Tree" }), "Leaves")).toBe("");
  });

  it("christmasPreviewGuidance", () => {
    expect(A.christmasPreviewGuidance("Christmas Tree", "Enhancers", "9", "50")).toBe("16 enhancers · regular/premium recipe");
    expect(A.christmasPreviewGuidance("Christmas Tree", "Enhancers")).toBe("regular/premium material recipe");
    expect(A.christmasPreviewGuidance("Christmas Tree", "Tree Topper")).toBe("final topper");
    expect(A.christmasPreviewGuidance("Garland", "Garland")).toBe("lighted or unlit base");
    expect(A.christmasPreviewGuidance("Wreath", "Decor")).toBe("branches/ribbon/flowers/ornaments by size");
    expect(A.christmasPreviewGuidance("Planter", "Container")).toBe("");
  });

  it("mechanicsEstimate sums mechanics component totals", () => {
    const notes = `LL_BUILD_INTELLIGENCE:${JSON.stringify({
      components: [
        { label: "Floral foam", average_extended_total: 12.5 },
        { label: "Spanish Moss", average_extended_total: "3.25" },
        { label: "Orchid", average_extended_total: 40 },
        { label: "Wire", average_extended_total: null },
      ],
    })}`;
    expect(A.mechanicsEstimate(bucket({ scope_notes: notes }))).toBe(15.75);
    expect(A.mechanicsEstimate(null)).toBe(0);
  });
});

describe("SKU and evidence helpers", () => {
  beforeAll(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-03-01T12:00:00.000Z"));
  });
  afterAll(() => {
    vi.useRealTimers();
  });

  it("skuCodeForBuildType", () => {
    expect(A.skuCodeForBuildType("Wreath")).toBe("CH-WRE");
    expect(A.skuCodeForBuildType("Rug")).toBe("GR-CUS");
  });

  it("selectedSkuSource prefers a selected base item", () => {
    expect(A.selectedSkuSource(null)).toBe("");
    expect(
      A.selectedSkuSource(bucket({
        items: [
          item({ status: "selected", part_label: "Focal Material", supplier_sku: "ORC-1" }),
          item({ status: "selected", part_label: "Container/Base", product_name: "Pot" }),
        ],
      }))
    ).toBe("Pot");
    expect(
      A.selectedSkuSource(bucket({
        items: [
          item({ status: "candidate", part_label: "Container", supplier_sku: "C1" }),
          item({ part_label: "Moss", product_name: "Moss sheet" }),
        ],
      }))
    ).toBe("Moss sheet");
  });

  it("suggestedSkuForType", () => {
    expect(A.suggestedSkuForType("Wreath", "Front", { name: "Grand Hyatt" } as Loose)).toBe("CH-WRE-GRAND-2026");
    expect(A.suggestedSkuForType("Rug", null, null, "christmas")).toBe("CH-CUS-RUG-2026");
    expect(A.suggestedSkuForType("Rug")).toBe("GR-CUS-RUG-2026");
    expect(A.suggestedSkuForType("", "", null)).toBe("GR-CUS-BUILD-2026");
  });

  it("suggestedFinishedSku", () => {
    expect(
      A.suggestedFinishedSku(
        bucket({ bucket_type: "Planter", label: "Lobby", items: [item({ status: "selected", part_label: "Container/Planter", supplier_sku: "cp-2210" })] }),
        null
      )
    ).toBe("GR-PLN-CP221-2026");
    expect(A.suggestedFinishedSku(bucket({ bucket_type: "Wreath" }), { name: "Acme" } as Loose)).toBe("CH-WRE-WREAT-2026");
    expect(A.suggestedFinishedSku(null, { name: "Acme" } as Loose)).toBe("GR-CUS-ACME-2026");
  });

  it("evidenceForConfig sums label or prefix matches", () => {
    expect(
      A.evidenceForConfig(A.BUILD_TYPE_CONFIGS[0], [
        { label: "tree / plant", evidence_count: 4 },
        { label: "Other", prefixes: ["TL"], evidence_count: "3" as Loose },
        { label: "Orchid", prefixes: ["OR"], evidence_count: 10 },
        { label: "Tree" },
      ])
    ).toBe(7);
  });

  it("builderProductName", () => {
    expect(A.builderProductName({ raw_data: { Description: " Magnolia Garland " }, description: "x", name: "y" } as Loose)).toBe("Magnolia Garland");
    expect(A.builderProductName({ name: "Pine", raw_data: {} } as Loose)).toBe("Pine");
    expect(A.builderProductName({} as Loose)).toBe("");
  });
});
