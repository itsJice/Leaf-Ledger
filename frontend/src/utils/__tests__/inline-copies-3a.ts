/* eslint-disable @typescript-eslint/no-explicit-any */
// Oracle copies for work package 3a (shared modules). Same rules as
// inline-copies.ts: verbatim, only `export`/names changed. Tests check the
// source-text blocks marked "verbatim" against the page files, so they cannot
// silently drift.
import { CircleDashed, Flower2, Leaf, Package, Shapes, Shrub, Sparkle, Spline, Sprout, TreeDeciduous, TreePine, Waves } from "components/icons";

// ─── pages/Settings.tsx build templates (verbatim, source-checked) ──────────

type BuildTemplate = {
  id: string;
  section: "Green" | "Christmas";
  name: string;
  summary: string;
  usedFor: string[];
  slots: string[];
  regularMaterials?: string[];
  premiumMaterials?: string[];
};

const DEFAULT_BUILD_TEMPLATES: BuildTemplate[] = [
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

const LEGACY_TOP_DOWN_SLOT_ORDERS: Record<string, string[]> = {
  "green-tree": ["Container", "Top Dressing", "Trunks & Branches", "Leaves"],
  arrangement: ["Container/Base", "Finish/Top Dressing", "Focal Material", "Accent Material"],
  planter: ["Container/Planter", "Finish/Top Dressing", "Main Plant", "Accent Plant"],
  "drop-in": ["Drop-in Base", "Main Material", "Accent Material", "Finish"],
  succulent: ["Container/Base", "Finish/Top Dressing", "Succulents/Cactus", "Accent Greenery"],
};

function cleanTemplateList(values: unknown, fallback = DEFAULT_BUILD_TEMPLATES): BuildTemplate[] {
  if (!Array.isArray(values)) return fallback;
  const cleaned = values
    .map((value) => {
      const template = value as Partial<BuildTemplate>;
      const id = String(template.id || "").trim();
      const name = String(template.name || "").trim();
      if (!id || !name) return null;
      let slots = Array.isArray(template.slots) ? template.slots.map(String).map((item) => item.trim()).filter(Boolean) : [];
      if (id === "wreath" && slots.map((slot) => slot.toLowerCase()).join("|") === "wreath base|greenery|ribbon|decor") {
        slots = ["Wreath Base", "Decor Package"];
      }
      const legacyOrder = LEGACY_TOP_DOWN_SLOT_ORDERS[id];
      if (legacyOrder && slots.map((slot) => slot.toLowerCase()).join("|") === legacyOrder.map((slot) => slot.toLowerCase()).join("|")) {
        slots = [...legacyOrder].reverse();
      }
      return {
        id,
        section: template.section === "Christmas" ? "Christmas" : "Green",
        name,
        summary: String(template.summary || ""),
        usedFor: Array.isArray(template.usedFor) ? template.usedFor.map(String).map((item) => item.trim()).filter(Boolean) : [],
        slots,
        regularMaterials: Array.isArray(template.regularMaterials) ? template.regularMaterials.map(String).map((item) => item.trim()).filter(Boolean) : undefined,
        premiumMaterials: Array.isArray(template.premiumMaterials) ? template.premiumMaterials.map(String).map((item) => item.trim()).filter(Boolean) : undefined,
      } satisfies BuildTemplate;
    })
    .filter(Boolean) as BuildTemplate[];
  return cleaned.length ? cleaned : fallback;
}

export {
  DEFAULT_BUILD_TEMPLATES as SETTINGS_COPY_DEFAULT_BUILD_TEMPLATES,
  LEGACY_TOP_DOWN_SLOT_ORDERS as SETTINGS_COPY_LEGACY_TOP_DOWN_SLOT_ORDERS,
  cleanTemplateList as settingsCopyCleanTemplateList,
};

// ─── pages/Designs.tsx buildTypeIcon (verbatim, source-checked) ─────────────

type IconComponent = typeof TreePine;
const BUILD_TYPE_ICONS: [RegExp, IconComponent][] = [
  [/christmas tree|holiday tree/, TreePine],
  [/wreath/, CircleDashed],
  [/garland/, Spline],
  [/swag/, Waves],
  [/spray|teardrop|door drop/, Sprout],
  [/planter|container garden/, Shrub],
  [/ornament/, Sparkle],
  [/branch|stem/, Leaf],
  [/tree|fig/, TreeDeciduous],
  [/centerpiece|arrangement|floral|orchid|succulent/, Flower2],
];

export function buildTypeIcon(buildType?: string | null): IconComponent {
  const normalized = (buildType || "").trim().toLowerCase();
  if (!normalized) return Shapes;
  for (const [pattern, Icon] of BUILD_TYPE_ICONS) {
    if (pattern.test(normalized)) return Icon;
  }
  return Shapes;
}

// ─── pages/App.tsx buildTypeIcon (verbatim apart from the name, source-checked) ─

export function buildTypeIconApp(buildType?: string | null) {
  const t = (buildType || "").toLowerCase();
  if (t.includes("wreath")) return CircleDashed;
  if (t.includes("tree")) return TreePine;
  if (t.includes("plant") || t.includes("bush") || t.includes("planter")) return Sprout;
  return Package;
}

// ─── localStorage cache readers/writers (verbatim bodies, key passed in) ─────
// Each takes the key as a parameter so one test can drive them all. `trimProductForCache`
// is omitted from the Library writer (it maps products before the write).

export function readDashboardCacheApp(KEY: string): any {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function writeDashboardCacheApp(KEY: string, patch: any) {
  try {
    const prev = readDashboardCacheApp(KEY) || {};
    localStorage.setItem(KEY, JSON.stringify({ ...prev, ...patch, cachedAt: Date.now() }));
  } catch {
    // Ignore storage issues.
  }
}

/** Mockups.tsx and Invoice.tsx are character-identical apart from the key constant. */
export function readProjectsCacheMockupsInvoice(KEY: string): any[] {
  try {
    const raw = localStorage.getItem(KEY);
    const parsed = raw ? JSON.parse(raw) : null;
    return Array.isArray(parsed?.arrangements) ? parsed.arrangements : [];
  } catch {
    return [];
  }
}

export function writeProjectsCacheMockupsInvoice(KEY: string, arrangements: any[]) {
  try {
    localStorage.setItem(
      KEY,
      JSON.stringify({ arrangements, cachedAt: Date.now() })
    );
  } catch {
    // Ignore storage issues.
  }
}

export function readProjectsListCacheArrangements(KEY: string): any {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(KEY) || "null");
    if (!parsed || !Array.isArray(parsed.arrangements)) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function writeProjectsListCacheArrangements(KEY: string, arrangements: any[]) {
  try {
    window.localStorage.setItem(KEY, JSON.stringify({ arrangements, cachedAt: Date.now() }));
  } catch {
    // localStorage is only a speed cache; failures should not block the app.
  }
}

export function readLibraryCacheLibrary(KEY: string): any {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed?.products) || !Array.isArray(parsed?.suppliers)) return null;
    return { suppliers: parsed.suppliers, products: parsed.products, productTotal: parsed.productTotal };
  } catch {
    return null;
  }
}

export function writeLibraryCacheLibrary(KEY: string, suppliers: any[], products: any[], productTotal?: number) {
  try {
    const payload = {
      suppliers,
      products,
      productTotal,
      cachedAt: Date.now(),
    };
    localStorage.setItem(KEY, JSON.stringify(payload));
  } catch {
    // Ignore cache quota/storage issues.
  }
}

export function readLibraryMetadataCacheLibrary(KEY: string): any {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return null;
    return parsed;
  } catch {
    return null;
  }
}

export function writeLibraryMetadataCacheLibrary(KEY: string, metadata: any) {
  try {
    localStorage.setItem(KEY, JSON.stringify({ ...metadata, cachedAt: Date.now() }));
  } catch {
    // Ignore cache quota/storage issues.
  }
}

export function readFavoritesCacheFavorites(KEY: string): any[] | null {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed?.products) ? parsed.products : null;
  } catch {
    return null;
  }
}

export function writeFavoritesCacheFavorites(KEY: string, products: any[]) {
  try {
    localStorage.setItem(
      KEY,
      JSON.stringify({ products, cachedAt: Date.now() })
    );
  } catch {
    // Ignore storage issues.
  }
}

export function readLibraryProductsFromCacheFavorites(KEY: string): any[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(KEY) || "{}");
    return Array.isArray(parsed?.products) ? parsed.products : [];
  } catch {
    return [];
  }
}

export function readClientsPageCacheClients(KEY: string): any {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(KEY) || "null");
    if (!parsed || !Array.isArray(parsed.clientRows) || !Array.isArray(parsed.projects)) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function writeClientsPageCacheClients(KEY: string, clientRows: any[], projects: any[]) {
  try {
    window.localStorage.setItem(KEY, JSON.stringify({ clientRows, projects, cachedAt: Date.now() }));
  } catch {
    // localStorage is only a speed cache; failures should not block the app.
  }
}

export function readLocalClientsClients(KEY: string): any[] {
  try {
    const rows = JSON.parse(window.localStorage.getItem(KEY) || "[]");
    return Array.isArray(rows) ? rows : [];
  } catch {
    return [];
  }
}

export function writeLocalClientsClients(KEY: string, rows: any[]) {
  window.localStorage.setItem(KEY, JSON.stringify(rows));
}

export function writeJsonCacheLayout(key: string, value: unknown) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Cache writes should never block navigation.
  }
}

/** Layout.tsx sidebar-projects useState initializer body. */
export function readSidebarProjectsLayout(KEY: string): any[] {
  try {
    const cached = JSON.parse(window.localStorage.getItem(KEY) || "[]");
    return Array.isArray(cached) ? cached : [];
  } catch {
    return [];
  }
}
