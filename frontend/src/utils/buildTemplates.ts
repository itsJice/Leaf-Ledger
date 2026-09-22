/**
 * Build templates (stored under BUILD_TEMPLATE_STORAGE_KEY).
 *
 * pages/Settings.tsx and pages/Arrangements.tsx each ship their own default list,
 * and the two have DRIFTED:
 *   - Settings gives every template a `summary`; Arrangements has none.
 *   - Settings' "wreath" has regularMaterials/premiumMaterials (size-based decor
 *     packages); Arrangements' "wreath" has neither.
 * Every other field matches. Which list is correct is a product decision, so both
 * are exported under explicit names and nothing here picks a winner.
 *
 * The legacy slot orders and the cleaning logic are identical in both pages.
 * They are shared; only the fallback list differs (see buildTemplates.test.ts).
 */

/** Settings' template shape: `summary`, `usedFor` and `slots` always present. */
export type SettingsBuildTemplate = {
  id: string;
  section: "Green" | "Christmas";
  name: string;
  summary: string;
  usedFor: string[];
  slots: string[];
  regularMaterials?: string[];
  premiumMaterials?: string[];
};

/** Arrangements' template shape (`EditableBuildTemplate`). */
export type ArrangementsBuildTemplate = {
  id: string;
  section: "Green" | "Christmas";
  name: string;
  summary?: string;
  usedFor?: string[];
  slots?: string[];
  regularMaterials?: string[];
  premiumMaterials?: string[];
};

/** Verbatim copy of `DEFAULT_BUILD_TEMPLATES` in pages/Settings.tsx. */
export const SETTINGS_DEFAULT_BUILD_TEMPLATES: SettingsBuildTemplate[] = [
  {
    id: "christmas-tree",
    section: "Christmas",
    name: "Christmas Tree",
    summary: "Tree package builder with a base tree, enhancer materials, skirt, and topper.",
    usedFor: ["Christmas Tree", "Decor Packages"],
    slots: ["Tree", "Enhancers", "Tree Skirt", "Tree Topper"],
    regularMaterials: ["2 x Assorted Branch", '1 x 4" Ornament', "2 1/2 Yards of Ribbon"],
    premiumMaterials: ["1 Flower", "2 x Assorted Branch", '1 x 4" Ornament', "1 1/2 Yards of Ribbon", "1 Yard of Premium Ribbon"],
  },
  {
    id: "garland",
    section: "Christmas",
    name: "Garland",
    summary: "Nine-foot garland build with lighted/unlit setup and regular or premium enhancer packages.",
    usedFor: ["Garland", "Railings", "Mantels"],
    slots: ["Garland", "Enhancers"],
    regularMaterials: ["5 Regular Enhancers", "2 x Assorted Branches per enhancer", '1 x 4" Ornament per enhancer', "2 1/2 Yards of Ribbon per enhancer"],
    premiumMaterials: ["3 Premium Enhancers", "2 Regular Enhancers", "2 Extra Ornaments", "1 Flower per premium enhancer", "2 x Assorted Branches per enhancer", '1 x 4" Ornament per enhancer', "1 1/2 Yards of Ribbon per premium enhancer", "1 Yard of Premium Ribbon per premium enhancer"],
  },
  {
    id: "wreath",
    section: "Christmas",
    name: "Wreath",
    summary: "Circular hanging design built from a wreath base and a size-based decor package.",
    usedFor: ["Wreath", "Door Decor"],
    slots: ["Wreath Base", "Decor Package"],
    regularMaterials: ['24" Wreath: 4 assorted branches, 3 yd ribbon, 3 x 4" ornaments', '30" Wreath: 5 assorted branches, 4 yd ribbon, 5 x 4" ornaments'],
    premiumMaterials: ['36" Wreath: 2 flowers, 7 assorted branches, 6 yd ribbon', '48" Wreath: 3 flowers, 14 assorted branches, 2 x 8" ornaments, 3 x 6" ornaments'],
  },
  {
    id: "teardrop",
    section: "Christmas",
    name: "Vertical Spray",
    summary: "Upright holiday spray for doors, gates, lanterns, columns, or vertical accents.",
    usedFor: ["Vertical Spray", "Teardrop", "Door Drop", "Lantern Drop"],
    slots: ["Vertical Spray Base", "Greenery", "Ribbon", "Decor"],
  },
  {
    id: "swag",
    section: "Christmas",
    name: "Horizontal Swag",
    summary: "Horizontal holiday greenery piece for mantels, railings, signs, or architectural accents.",
    usedFor: ["Horizontal Swag", "Swag", "Holiday Accent"],
    slots: ["Horizontal Swag Base", "Greenery", "Ribbon", "Decor"],
  },
  {
    id: "green-tree",
    section: "Green",
    name: "Tree",
    summary: "Permanent green tree or plant build, designed from bottom to top.",
    usedFor: ["Tree", "Tree / Plant", "Fiddle Fig"],
    slots: ["Leaves", "Trunks & Branches", "Top Dressing", "Container"],
  },
  {
    id: "arrangement",
    section: "Green",
    name: "Arrangement",
    summary: "Smaller tabletop or vase-style design with a base, finish, focal material, and accents.",
    usedFor: ["Arrangement", "Orchid Arrangement", "Succulent Arrangement", "Foliage Arrangement"],
    slots: ["Accent Material", "Focal Material", "Finish/Top Dressing", "Container/Base"],
  },
  {
    id: "planter",
    section: "Green",
    name: "Planter",
    summary: "Larger floor container build, usually not a tree but bigger than a tabletop arrangement.",
    usedFor: ["Planter", "Container Garden", "Floor Container"],
    slots: ["Accent Plant", "Main Plant", "Finish/Top Dressing", "Container/Planter"],
  },
  {
    id: "drop-in",
    section: "Green",
    name: "Drop-in Arrangement",
    summary: "A build made to drop into a client-owned or separately purchased container.",
    usedFor: ["Drop-in Arrangement", "Client Container"],
    slots: ["Finish", "Accent Material", "Main Material", "Drop-in Base"],
  },
  {
    id: "succulent",
    section: "Green",
    name: "Succulent / Cactus",
    summary: "Succulent-focused arrangement pattern kept as an editable reference even when it rolls into Arrangement.",
    usedFor: ["Succulent Arrangement", "Cactus Arrangement"],
    slots: ["Accent Greenery", "Succulents/Cactus", "Finish/Top Dressing", "Container/Base"],
  },
];

/** Verbatim copy of `DEFAULT_EDITABLE_BUILD_TEMPLATES` in pages/Arrangements.tsx. */
export const ARRANGEMENTS_DEFAULT_BUILD_TEMPLATES: ArrangementsBuildTemplate[] = [
  {
    id: "christmas-tree",
    section: "Christmas",
    name: "Christmas Tree",
    usedFor: ["Christmas Tree", "Decor Packages"],
    slots: ["Tree", "Enhancers", "Tree Skirt", "Tree Topper"],
    regularMaterials: ["2 x Assorted Branch", '1 x 4" Ornament', "2 1/2 Yards of Ribbon"],
    premiumMaterials: ["1 Flower", "2 x Assorted Branch", '1 x 4" Ornament', "1 1/2 Yards of Ribbon", "1 Yard of Premium Ribbon"],
  },
  {
    id: "garland",
    section: "Christmas",
    name: "Garland",
    usedFor: ["Garland", "Railings", "Mantels"],
    slots: ["Garland", "Enhancers"],
    regularMaterials: ["5 Regular Enhancers", "2 x Assorted Branches per enhancer", '1 x 4" Ornament per enhancer', "2 1/2 Yards of Ribbon per enhancer"],
    premiumMaterials: ["3 Premium Enhancers", "2 Regular Enhancers", "2 Extra Ornaments", "1 Flower per premium enhancer", "2 x Assorted Branches per enhancer", '1 x 4" Ornament per enhancer', "1 1/2 Yards of Ribbon per premium enhancer", "1 Yard of Premium Ribbon per premium enhancer"],
  },
  {
    id: "wreath",
    section: "Christmas",
    name: "Wreath",
    usedFor: ["Wreath", "Door Decor"],
    slots: ["Wreath Base", "Decor Package"],
  },
  {
    id: "teardrop",
    section: "Christmas",
    name: "Vertical Spray",
    usedFor: ["Vertical Spray", "Teardrop", "Door Drop", "Lantern Drop"],
    slots: ["Vertical Spray Base", "Greenery", "Ribbon", "Decor"],
  },
  {
    id: "swag",
    section: "Christmas",
    name: "Horizontal Swag",
    usedFor: ["Horizontal Swag", "Swag", "Holiday Accent"],
    slots: ["Horizontal Swag Base", "Greenery", "Ribbon", "Decor"],
  },
  {
    id: "green-tree",
    section: "Green",
    name: "Tree",
    usedFor: ["Tree", "Tree / Plant", "Fiddle Fig"],
    slots: ["Leaves", "Trunks & Branches", "Top Dressing", "Container"],
  },
  {
    id: "arrangement",
    section: "Green",
    name: "Arrangement",
    usedFor: ["Arrangement", "Orchid Arrangement", "Succulent Arrangement", "Foliage Arrangement"],
    slots: ["Accent Material", "Focal Material", "Finish/Top Dressing", "Container/Base"],
  },
  {
    id: "planter",
    section: "Green",
    name: "Planter",
    usedFor: ["Planter", "Container Garden", "Floor Container"],
    slots: ["Accent Plant", "Main Plant", "Finish/Top Dressing", "Container/Planter"],
  },
  {
    id: "drop-in",
    section: "Green",
    name: "Drop-in Arrangement",
    usedFor: ["Drop-in Arrangement", "Client Container"],
    slots: ["Finish", "Accent Material", "Main Material", "Drop-in Base"],
  },
  {
    id: "succulent",
    section: "Green",
    name: "Succulent / Cactus",
    usedFor: ["Succulent Arrangement", "Cactus Arrangement"],
    slots: ["Accent Greenery", "Succulents/Cactus", "Finish/Top Dressing", "Container/Base"],
  },
];

// The green templates used to list their slots top-down (container first). They now
// read bottom-up to match how a build is physically assembled. Only the ORDER changed -
// no slot label was renamed. Identical in Settings.tsx and Arrangements.tsx.
export const LEGACY_TOP_DOWN_SLOT_ORDERS: Record<string, string[]> = {
  "green-tree": ["Container", "Top Dressing", "Trunks & Branches", "Leaves"],
  arrangement: ["Container/Base", "Finish/Top Dressing", "Focal Material", "Accent Material"],
  planter: ["Container/Planter", "Finish/Top Dressing", "Main Plant", "Accent Plant"],
  "drop-in": ["Drop-in Base", "Main Material", "Accent Material", "Finish"],
  succulent: ["Container/Base", "Finish/Top Dressing", "Succulents/Cactus", "Accent Greenery"],
};

const normalizeSlot = (value?: string | null) => (value || "").trim().toLowerCase();

const cleanStringList = (values: unknown[]) => values.map(String).map((item) => item.trim()).filter(Boolean);

/**
 * The cleaning logic shared by Settings' `cleanTemplateList` and Arrangements'
 * `cleanEditableBuildTemplates`. Returns `null` when the caller should use its
 * fallback (non-array input, or no entry with both an id and a name).
 * Like both originals, a `null` entry throws a TypeError.
 */
export function cleanBuildTemplateList(values: unknown): SettingsBuildTemplate[] | null {
  if (!Array.isArray(values)) return null;
  const cleaned = values
    .map((value) => {
      const template = value as Partial<SettingsBuildTemplate>;
      const id = String(template.id || "").trim();
      const name = String(template.name || "").trim();
      if (!id || !name) return null;
      let slots = Array.isArray(template.slots) ? cleanStringList(template.slots) : [];
      if (id === "wreath" && slots.map(normalizeSlot).join("|") === "wreath base|greenery|ribbon|decor") {
        slots = ["Wreath Base", "Decor Package"];
      }
      // A stored copy that still holds the old top-down order verbatim is migrated;
      // any order the user customised is left untouched.
      const legacyOrder = LEGACY_TOP_DOWN_SLOT_ORDERS[id];
      if (legacyOrder && slots.map(normalizeSlot).join("|") === legacyOrder.map(normalizeSlot).join("|")) {
        slots = [...legacyOrder].reverse();
      }
      return {
        id,
        section: template.section === "Christmas" ? "Christmas" : "Green",
        name,
        summary: String(template.summary || ""),
        usedFor: Array.isArray(template.usedFor) ? cleanStringList(template.usedFor) : [],
        slots,
        regularMaterials: Array.isArray(template.regularMaterials) ? cleanStringList(template.regularMaterials) : undefined,
        premiumMaterials: Array.isArray(template.premiumMaterials) ? cleanStringList(template.premiumMaterials) : undefined,
      } satisfies SettingsBuildTemplate;
    })
    .filter(Boolean) as SettingsBuildTemplate[];
  return cleaned.length ? cleaned : null;
}

/** Same output as Settings' `cleanTemplateList` (fallback returned by reference). */
export function cleanSettingsBuildTemplates(values: unknown, fallback = SETTINGS_DEFAULT_BUILD_TEMPLATES): SettingsBuildTemplate[] {
  return cleanBuildTemplateList(values) ?? fallback;
}

/** Same output as Arrangements' `cleanEditableBuildTemplates` (fallback returned by reference). */
export function cleanArrangementsBuildTemplates(values: unknown, fallback = ARRANGEMENTS_DEFAULT_BUILD_TEMPLATES): ArrangementsBuildTemplate[] {
  return cleanBuildTemplateList(values) ?? fallback;
}
