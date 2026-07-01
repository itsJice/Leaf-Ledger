import React, { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import {
  ArrowLeft,
  CheckCircle2,
  Circle,
  HelpCircle,
  Grid3X3,
  Leaf,
  Minus,
  Redo2,
  Package,
  Pencil,
  Plus,
  Save,
  Search,
  Trash2,
  Undo2,
  Upload,
  X,
} from "lucide-react";
import Layout from "components/Layout";
import { apiClient } from "app";
import { ContentType } from "../apiclient/http-client";
import { formatCurrency, categoryLabel, unitLabel } from "utils/format";
import { toast } from "sonner";
import { ProductDetailModal, hasNoSupplierImage, hasSupplierPlaceholderImage, productDisplayImageUrl, type Product as LibraryProduct } from "./Library";

type ItemStatus = "candidate" | "selected";

type ContainerItem = {
  id: number;
  product_id: number;
  product_name: string;
  product_category: string;
  unit: string;
  current_price?: number;
  supplier_name?: string;
  supplier_sku?: string;
  photo_url?: string;
  quantity: number;
  line_total?: number;
  status?: ItemStatus;
  part_key?: string;
  part_label?: string;
  part_order?: number;
};

type Container = {
  id: number;
  arrangement_id: number;
  container_product_id?: number;
  container_name?: string;
  label?: string;
  room_id?: number | null;
  bucket_type?: string;
  requested_quantity?: number;
  scope_notes?: string;
  sort_order: number;
  items: ContainerItem[];
  subtotal: number;
};

type ProjectRoom = {
  id: number;
  arrangement_id: number;
  name: string;
  notes?: string;
  sort_order: number;
  created_at: string;
  updated_at: string;
};

type Arrangement = {
  id: number;
  name: string;
  client_name?: string;
  notes?: string;
  created_by: string;
  created_at: string;
  updated_at: string;
  rooms?: ProjectRoom[];
  containers: Container[];
  total_cost: number;
  total_with_markup: number;
};

type ArrangementSummary = {
  id: number;
  name: string;
  client_name?: string;
  created_at: string;
  updated_at: string;
  total_cost: number;
  container_count: number;
};

type BuildTypeOption = {
  label: string;
  evidence_count?: number;
  prefixes?: string[];
};

type EditableBuildTemplate = {
  id: string;
  section: "Green" | "Christmas";
  name: string;
  summary?: string;
  usedFor?: string[];
  slots?: string[];
  regularMaterials?: string[];
  premiumMaterials?: string[];
};

type BuilderSection = "green" | "christmas";
type ChristmasEnhancerPackage = "regular" | "premium";
type GarlandPackage = "regular" | "premium";
type GarlandDiameter = "14" | "18";
type WreathSize = "24" | "30" | "36" | "48";

type BuildSuggestionComponent = {
  label: string;
  suggested_quantity: number;
  average_quantity?: number;
  evidence_count: number;
  average_extended_total?: number | null;
  vendors?: string[];
  examples?: string[];
  search_terms?: string[];
};

type BuildSuggestion = {
  build_type: string;
  evidence_count: number;
  confidence: string;
  components: BuildSuggestionComponent[];
  cost_range?: {
    avg_total?: number | null;
    min_total?: number | null;
    max_total?: number | null;
  };
};

const PROJECTS_LIST_CACHE_KEY = "leaf-ledger:projects-list-cache:v1";
const LIBRARY_CACHE_KEY = "leaf-ledger:library-cache:v1";
const BUILD_TEMPLATE_STORAGE_KEY = "leaf-ledger:build-templates:v1";
const INTELLIGENCE_NOTE_PREFIX = "LL_BUILD_INTELLIGENCE:";
const CUSTOM_SECTIONS_PREFIX = "LL_CUSTOM_SECTIONS:";

type ProductPage = {
  items: LibraryProduct[];
  total: number;
  limit: number;
  offset: number;
};

type LibraryProductCache = {
  products: LibraryProduct[];
  productTotal?: number;
};

const BUILDER_PRODUCT_PAGE_SIZE = 2000;
const BUILDER_PRODUCT_CONCURRENT_PAGE_LIMIT = 8;

const DEFAULT_EDITABLE_BUILD_TEMPLATES: EditableBuildTemplate[] = [
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
    slots: ["Container", "Top Dressing", "Trunks & Branches", "Leaves"],
  },
  {
    id: "arrangement",
    section: "Green",
    name: "Arrangement",
    usedFor: ["Arrangement", "Orchid Arrangement", "Succulent Arrangement", "Foliage Arrangement"],
    slots: ["Container/Base", "Finish/Top Dressing", "Focal Material", "Accent Material"],
  },
  {
    id: "planter",
    section: "Green",
    name: "Planter",
    usedFor: ["Planter", "Container Garden", "Floor Container"],
    slots: ["Container/Planter", "Finish/Top Dressing", "Main Plant", "Accent Plant"],
  },
  {
    id: "drop-in",
    section: "Green",
    name: "Drop-in Arrangement",
    usedFor: ["Drop-in Arrangement", "Client Container"],
    slots: ["Drop-in Base", "Main Material", "Accent Material", "Finish"],
  },
  {
    id: "succulent",
    section: "Green",
    name: "Succulent / Cactus",
    usedFor: ["Succulent Arrangement", "Cactus Arrangement"],
    slots: ["Container/Base", "Finish/Top Dressing", "Succulents/Cactus", "Accent Greenery"],
  },
];

type ProjectsListCache = {
  arrangements: ArrangementSummary[];
  cachedAt: number;
};

function readProjectsListCache(): ProjectsListCache | null {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(PROJECTS_LIST_CACHE_KEY) || "null");
    if (!parsed || !Array.isArray(parsed.arrangements)) return null;
    return parsed;
  } catch {
    return null;
  }
}

function readLibraryProductCache(): LibraryProductCache {
  if (typeof window === "undefined") return { products: [] };
  try {
    const parsed = JSON.parse(window.localStorage.getItem(LIBRARY_CACHE_KEY) || "null");
    return {
      products: Array.isArray(parsed?.products) ? parsed.products : [],
      productTotal: typeof parsed?.productTotal === "number" ? parsed.productTotal : undefined,
    };
  } catch {
    return { products: [] };
  }
}

function trimBuilderProductRawData(rawData: LibraryProduct["raw_data"]): LibraryProduct["raw_data"] {
  if (!rawData || typeof rawData !== "object") return rawData;
  const searchableKeys = [
    "Description",
    "Item",
    "Unit",
    "Country",
    "Country of Origin",
    "Height",
    "Width",
    "Diameter",
    "Length",
    "Availability",
    "ColorGrp",
    "Class",
    "Season",
    "UPC",
    "Material Breakdown",
    "Material_Breakdown",
  ];
  return searchableKeys.reduce<Record<string, unknown>>((next, key) => {
    if (key in rawData) next[key] = rawData[key];
    return next;
  }, {});
}

function trimBuilderProductForCache(product: LibraryProduct): LibraryProduct {
  return {
    ...product,
    raw_data: trimBuilderProductRawData(product.raw_data),
  };
}

function writeLibraryProductCache(products: LibraryProduct[], productTotal?: number) {
  if (typeof window === "undefined") return;
  try {
    const existing = JSON.parse(window.localStorage.getItem(LIBRARY_CACHE_KEY) || "null");
    window.localStorage.setItem(
      LIBRARY_CACHE_KEY,
      JSON.stringify({
        ...(existing && typeof existing === "object" ? existing : {}),
        products: products.map(trimBuilderProductForCache),
        productTotal,
        cachedAt: Date.now(),
      })
    );
  } catch {
    // Cache writes are best-effort; the live catalog load still succeeds.
  }
}

function writeProjectsListCache(arrangements: ArrangementSummary[]) {
  try {
    window.localStorage.setItem(PROJECTS_LIST_CACHE_KEY, JSON.stringify({ arrangements, cachedAt: Date.now() }));
  } catch {
    // localStorage is only a speed cache; failures should not block the app.
  }
}

function formatProjectsCacheStamp(ms?: number | null) {
  if (!ms) return "";
  return new Date(ms).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

function notifyProjectsChanged() {
  window.dispatchEvent(new Event("leaf-ledger-projects-changed"));
}

function arrangementShellFromSummary(summary: ArrangementSummary): Arrangement {
  return {
    id: summary.id,
    name: summary.name,
    client_name: summary.client_name,
    notes: "",
    created_by: "",
    created_at: summary.created_at,
    updated_at: summary.updated_at,
    rooms: [],
    containers: [],
    total_cost: summary.total_cost || 0,
    total_with_markup: summary.total_cost || 0,
  };
}

function arrangementRouteShell(id: number, clientName?: string): Arrangement {
  const now = new Date().toISOString();
  return {
    id,
    name: "Opening project...",
    client_name: clientName,
    notes: "",
    created_by: "",
    created_at: now,
    updated_at: now,
    rooms: [],
    containers: [],
    total_cost: 0,
    total_with_markup: 0,
  };
}

function withTimeout<T>(promise: Promise<T>, ms = 12000): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => reject(new Error("Request timed out")), ms);
    promise.then(
      (value) => {
        window.clearTimeout(timer);
        resolve(value);
      },
      (error) => {
        window.clearTimeout(timer);
        reject(error);
      }
    );
  });
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function scopeTitle(bucket?: Container | null) {
  if (!bucket) return "Scope";
  return bucket.label || bucket.bucket_type || `Scope ${bucket.sort_order + 1}`;
}

function scopeQuantity(bucket?: Container | null) {
  return Math.max(1, Number(bucket?.requested_quantity || 1));
}

function parseScopeIntelligence(notes?: string | null): BuildSuggestion | null {
  const line = (notes || "").split("\n").find((part) => part.startsWith(INTELLIGENCE_NOTE_PREFIX));
  if (!line) return null;
  try {
    return JSON.parse(line.slice(INTELLIGENCE_NOTE_PREFIX.length));
  } catch {
    return null;
  }
}

function parseCustomSections(notes?: string | null) {
  const line = (notes || "").split("\n").find((part) => part.startsWith(CUSTOM_SECTIONS_PREFIX));
  if (!line) return [];
  try {
    const parsed = JSON.parse(line.slice(CUSTOM_SECTIONS_PREFIX.length));
    return Array.isArray(parsed) ? parsed.map((value) => String(value).trim()).filter(Boolean) : [];
  } catch {
    return [];
  }
}

function displayScopeNotes(notes?: string | null) {
  return (notes || "")
    .split("\n")
    .filter((line) => !line.startsWith(INTELLIGENCE_NOTE_PREFIX))
    .filter((line) => !line.startsWith(CUSTOM_SECTIONS_PREFIX))
    .join("\n")
    .trim();
}

function editableScopeNotes(notes?: string | null) {
  return displayScopeNotes(notes)
    .split("\n")
    .filter((line) => !/^(tree type|tree source|tree lights|height|width \/ canopy|depth \/ density|enhancer package|garland package|garland light|garland size|garland length|garland diameter|wreath size):/i.test(line.trim()))
    .join("\n")
    .trim();
}

function scopeIntelligenceLine(notes?: string | null) {
  return (notes || "").split("\n").find((line) => line.startsWith(INTELLIGENCE_NOTE_PREFIX)) || "";
}

function scopeNotesWithCustomSections(bucket: Container, customSections: string[]) {
  return [
    displayScopeNotes(bucket.scope_notes),
    scopeIntelligenceLine(bucket.scope_notes),
    customSections.length ? `${CUSTOM_SECTIONS_PREFIX}${JSON.stringify(customSections)}` : "",
  ].filter(Boolean).join("\n");
}

function christmasEnhancerPackageFromNotes(notes?: string | null): ChristmasEnhancerPackage {
  return scopeNoteValue(notes, "Enhancer package").toLowerCase().includes("premium") ? "premium" : "regular";
}

function scopeNotesWithEnhancerPackage(bucket: Container, packageType: ChristmasEnhancerPackage) {
  const nextLine = `Enhancer package: ${packageType === "premium" ? "Premium" : "Regular"}`;
  return [
    ...(bucket.scope_notes || "")
      .split("\n")
      .filter((line) => !line.trim().toLowerCase().startsWith("enhancer package:")),
    nextLine,
  ].filter(Boolean).join("\n");
}

function garlandPackageFromNotes(notes?: string | null): GarlandPackage {
  return scopeNoteValue(notes, "Garland package").toLowerCase().includes("premium") ? "premium" : "regular";
}

function garlandLengthFromNotes(notes?: string | null) {
  const explicit = firstNumber(scopeNoteValue(notes, "Garland length"));
  if (explicit) return String(explicit);
  const legacySize = scopeNoteValue(notes, "Garland size");
  return String(firstNumber(legacySize) || 9);
}

function garlandDiameterFromNotes(notes?: string | null): GarlandDiameter {
  const explicit = scopeNoteValue(notes, "Garland diameter");
  const legacySize = scopeNoteValue(notes, "Garland size");
  return `${explicit} ${legacySize}`.includes("18") ? "18" : "14";
}

function garlandLengthLabel(lengthValue?: string | null) {
  const length = firstNumber(lengthValue) || 9;
  return `${Number.isInteger(length) ? length : length.toFixed(1).replace(/\.0$/, "")} ft`;
}

function garlandLengthMultiplier(lengthValue?: string | null) {
  const length = firstNumber(lengthValue) || 9;
  return Math.max(1, Math.ceil(length / 9));
}

function garlandSetupLabel(lengthValue?: string | null, diameter: GarlandDiameter = "14") {
  return `${garlandLengthLabel(lengthValue)} x ${diameter}"`;
}

function garlandSetupLines(packageType: GarlandPackage, lengthValue: string, diameter: GarlandDiameter) {
  return [
    `Garland package: ${packageType === "premium" ? "Premium" : "Regular"}`,
    `Garland length: ${garlandLengthLabel(lengthValue)}`,
    `Garland diameter: ${diameter}"`,
  ];
}

function scopeNotesWithGarlandSetup(
  bucket: Container,
  setup: { packageType: GarlandPackage; lengthValue: string; diameter: GarlandDiameter }
) {
  return [
    ...(bucket.scope_notes || "")
      .split("\n")
      .filter((line) => !/^(garland package|garland light|garland size|garland length|garland diameter):/i.test(line.trim())),
    ...garlandSetupLines(setup.packageType, setup.lengthValue, setup.diameter),
  ].filter(Boolean).join("\n");
}

function wreathSizeFromNotes(notes?: string | null): WreathSize {
  const explicit = firstNumber(scopeNoteValue(notes, "Wreath size"));
  const canopy = firstNumber(scopeNoteValue(notes, "Width / canopy"));
  const value = explicit || canopy || 24;
  if (value >= 48) return "48";
  if (value >= 36) return "36";
  if (value >= 30) return "30";
  return "24";
}

function wreathSetupLines(size: WreathSize) {
  return [`Wreath size: ${size}" Wreath`];
}

function scopeNotesWithWreathSetup(bucket: Container, size: WreathSize) {
  return [
    ...(bucket.scope_notes || "")
      .split("\n")
      .filter((line) => !/^(wreath size|height|width \/ canopy|depth \/ density):/i.test(line.trim())),
    ...wreathSetupLines(size),
  ].filter(Boolean).join("\n");
}

function cleanEditableBuildTemplates(values: unknown, fallback = DEFAULT_EDITABLE_BUILD_TEMPLATES): EditableBuildTemplate[] {
  if (!Array.isArray(values)) return fallback;
  const cleaned = values
    .map((value) => {
      const template = value as Partial<EditableBuildTemplate>;
      const id = String(template.id || "").trim();
      const name = String(template.name || "").trim();
      if (!id || !name) return null;
      let slots = Array.isArray(template.slots) ? template.slots.map(String).map((item) => item.trim()).filter(Boolean) : [];
      if (id === "wreath" && slots.map(normalizeLabel).join("|") === "wreath base|greenery|ribbon|decor") {
        slots = ["Wreath Base", "Decor Package"];
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
      } satisfies EditableBuildTemplate;
    })
    .filter(Boolean) as EditableBuildTemplate[];
  return cleaned.length ? cleaned : fallback;
}

function readEditableBuildTemplates() {
  if (typeof window === "undefined") return DEFAULT_EDITABLE_BUILD_TEMPLATES;
  try {
    return cleanEditableBuildTemplates(JSON.parse(window.localStorage.getItem(BUILD_TEMPLATE_STORAGE_KEY) || "null"));
  } catch {
    return DEFAULT_EDITABLE_BUILD_TEMPLATES;
  }
}

function buildTemplateMatches(template: EditableBuildTemplate, buildType: string) {
  const values = [template.name, ...(template.usedFor || [])];
  return values.some((value) => normalizeLabel(value) === normalizeLabel(buildType));
}

function editableTemplateForBuildType(buildType: string) {
  const normalized = normalizeLabel(buildType);
  const templates = readEditableBuildTemplates();
  const exact = templates.find((template) => buildTemplateMatches(template, buildType));
  if (exact) return exact;
  const config = buildTypeConfigFor(buildType);
  const aliasMatch = config?.aliases
    .map((alias) => templates.find((template) => buildTemplateMatches(template, alias)))
    .find(Boolean);
  if (aliasMatch) return aliasMatch;
  return templates.find((template) => {
    const values = [template.name, ...(template.usedFor || [])].map(normalizeLabel);
    return values.some((value) => value && (normalized.includes(value) || value.includes(normalized)));
  }) || null;
}

function templateSlotsForBuildType(buildType: string) {
  const slots = editableTemplateForBuildType(buildType)?.slots?.map((slot) => slot.trim()).filter(Boolean) || [];
  return slots.length ? slots : null;
}

function parseMaterialQuantity(line: string) {
  const mixed = line.trim().match(/^(\d+)(?:\s+(\d+)\/(\d+)|\.(\d+))?/);
  if (!mixed) return 1;
  const whole = Number(mixed[1]) || 0;
  if (mixed[2] && mixed[3]) return whole + (Number(mixed[2]) || 0) / (Number(mixed[3]) || 1);
  if (mixed[4]) return Number(`${mixed[1]}.${mixed[4]}`);
  return whole || 1;
}

function templateMaterialLabel(line: string) {
  return line
    .replace(/\bper\s+(premium\s+)?enhancer\b/gi, "")
    .replace(/^\s*\d+(?:\s+\d+\/\d+|\.\d+)?\s*(?:x\b|yards?\s+of\b|yards?\b|yd\s+of\b|yd\b)?\s*/i, "")
    .replace(/^of\s+/i, "")
    .trim();
}

type EnhancerPartConfig = {
  label: string;
  note: string;
  regularFormula?: string;
  premiumFormula?: string;
  fallbackQuantity: number;
  searchTerms?: string;
  optional?: boolean;
  premiumOnly?: boolean;
};

function enhancerPartFromTemplateLine(
  line: string,
  packageType: ChristmasEnhancerPackage,
  regularLabels: Set<string>
): EnhancerPartConfig | null {
  const label = templateMaterialLabel(line);
  if (!label || normalizeLabel(label).includes("enhancer")) return null;
  const quantity = parseMaterialQuantity(line);
  const unit = /yards?|yd/i.test(line) ? "yd" : "each";
  const formula = `${Number.isInteger(quantity) ? quantity : quantity.toFixed(2).replace(/0$/, "").replace(/\.0$/, "")} ${unit}`;
  const premiumOnly = packageType === "premium" && !regularLabels.has(normalizeLabel(label));
  return {
    label,
    note: premiumOnly ? "Only needed for premium enhancers" : "Used in this enhancer package",
    regularFormula: packageType === "regular" ? formula : undefined,
    premiumFormula: packageType === "premium" ? formula : undefined,
    fallbackQuantity: 8,
    searchTerms: `christmas ${label.toLowerCase()} enhancer`,
    optional: premiumOnly,
    premiumOnly,
  };
}

function enhancerPartsFromTemplate(buildType: string, packageType: ChristmasEnhancerPackage) {
  const template = editableTemplateForBuildType(buildType);
  const regularLines = template?.regularMaterials || [];
  const packageLines = packageType === "premium" ? template?.premiumMaterials || [] : regularLines;
  const regularLabels = new Set(regularLines.map(templateMaterialLabel).filter(Boolean).map(normalizeLabel));
  const parts = packageLines
    .map((line) => enhancerPartFromTemplateLine(line, packageType, regularLabels))
    .filter(Boolean) as EnhancerPartConfig[];
  return parts.length ? parts : null;
}

const BUILD_TYPE_CONFIGS = [
  {
    section: "green",
    label: "Tree",
    skuCode: "GR-TREE",
    icon: Leaf,
    aliases: ["Tree", "Tree / Plant", "Greenery Tree"],
    prefixes: ["TT", "TL", "GT"],
    visibleParts: ["Container", "Top Dressing", "Trunks & Branches", "Leaves"],
  },
  {
    section: "green",
    label: "Arrangement",
    skuCode: "GR-ARR",
    icon: Leaf,
    aliases: ["Arrangement", "Orchid Arrangement", "Succulent Arrangement", "Greenery Arrangement", "Foliage Arrangement"],
    prefixes: ["OR", "SG", "WG", "FP"],
    visibleParts: ["Container/Base", "Finish/Top Dressing", "Focal Material", "Accent Material"],
  },
  {
    section: "green",
    label: "Planter",
    skuCode: "GR-PLN",
    icon: Grid3X3,
    aliases: ["Planter", "Container Garden", "Plant / Vase", "Container Arrangement"],
    prefixes: ["CG", "PV", "CT"],
    visibleParts: ["Container/Planter", "Finish/Top Dressing", "Main Plant", "Accent Plant"],
  },
  {
    section: "green",
    label: "Drop-in Arrangement",
    skuCode: "GR-DRP",
    icon: Package,
    aliases: ["Drop-in Arrangement", "Drop in", "Drop-in", "Dropin Arrangement"],
    prefixes: ["DR", "DI"],
    visibleParts: ["Drop-in Base", "Main Material", "Accent Material", "Finish"],
  },
  {
    section: "christmas",
    label: "Christmas Tree",
    skuCode: "CH-TREE",
    icon: Leaf,
    aliases: ["Christmas Tree"],
    prefixes: [],
    visibleParts: ["Tree", "Enhancers", "Tree Skirt", "Tree Topper"],
  },
  {
    section: "christmas",
    label: "Garland",
    skuCode: "CH-GAR",
    icon: Leaf,
    aliases: ["Garland"],
    prefixes: [],
    visibleParts: ["Garland", "Enhancers"],
  },
  {
    section: "christmas",
    label: "Wreath",
    skuCode: "CH-WRE",
    icon: Circle,
    aliases: ["Wreath"],
    prefixes: [],
    visibleParts: ["Wreath Base", "Decor Package"],
  },
  {
    section: "christmas",
    label: "Vertical Spray",
    skuCode: "CH-VSP",
    icon: Leaf,
    aliases: ["Vertical Spray", "Teardrop", "Door Drop", "Lantern Drop"],
    prefixes: [],
    visibleParts: ["Vertical Spray Base", "Greenery", "Ribbon", "Decor"],
  },
  {
    section: "christmas",
    label: "Horizontal Swag",
    skuCode: "CH-HSW",
    icon: Leaf,
    aliases: ["Horizontal Swag", "Swag", "Holiday Accent"],
    prefixes: [],
    visibleParts: ["Horizontal Swag Base", "Greenery", "Ribbon", "Decor"],
  },
] as const;

const CHRISTMAS_ENHANCER_PARTS: EnhancerPartConfig[] = [
  {
    label: "Assorted Branch",
    note: "Used in both enhancer packages",
    regularFormula: "2 each",
    premiumFormula: "2 each",
    fallbackQuantity: 8,
    searchTerms: "christmas assorted branch pine berry pick spray",
  },
  {
    label: '4" Ornament',
    note: "Used in both enhancer packages",
    regularFormula: "1 each",
    premiumFormula: "1 each",
    fallbackQuantity: 8,
    searchTerms: "christmas 4 inch ornament ball",
  },
  {
    label: "Ribbon",
    note: "Ribbon amount changes with the package",
    regularFormula: "2.5 yd",
    premiumFormula: "1.5 yd",
    fallbackQuantity: 20,
    searchTerms: "christmas ribbon wired ribbon",
  },
  {
    label: "Flower",
    note: "Only needed for premium enhancers",
    premiumFormula: "1 each",
    fallbackQuantity: 8,
    optional: true,
    searchTerms: "christmas flower floral pick",
  },
  {
    label: "Premium Ribbon",
    note: "Only needed for premium enhancers",
    premiumFormula: "1 yd",
    fallbackQuantity: 8,
    optional: true,
    searchTerms: "premium christmas ribbon wired ribbon",
  },
];

const GARLAND_DIAMETER_OPTIONS: GarlandDiameter[] = ["14", "18"];

const WREATH_SIZE_OPTIONS: WreathSize[] = ["24", "30", "36", "48"];

const WREATH_DECOR_PARTS = [
  {
    label: "Assorted Branches",
    note: "Branch count changes with wreath size",
    searchTerms: "christmas assorted branch pine berry pick spray",
  },
  {
    label: "Ribbon",
    note: "Ribbon yardage changes with wreath size",
    searchTerms: "christmas ribbon wired ribbon",
  },
  {
    label: '4" Ornaments',
    note: "Small ornaments for 24 and 30 inch wreaths",
    searchTerms: "christmas 4 inch ornament ball",
  },
  {
    label: "Flowers",
    note: "Floral accents for larger wreaths",
    searchTerms: "christmas flower floral pick",
  },
  {
    label: '8" Ornaments',
    note: "Large ornaments for 48 inch wreaths",
    searchTerms: "christmas 8 inch ornament ball",
  },
  {
    label: '6" Ornaments',
    note: "Medium ornaments for 48 inch wreaths",
    searchTerms: "christmas 6 inch ornament ball",
  },
] as const;

const WREATH_DECOR_RECIPES: Record<WreathSize, Array<{ label: string; quantity: number; unit: "total" | "yd" }>> = {
  "24": [
    { label: "Assorted Branches", quantity: 4, unit: "total" },
    { label: "Ribbon", quantity: 3, unit: "yd" },
    { label: '4" Ornaments', quantity: 3, unit: "total" },
  ],
  "30": [
    { label: "Assorted Branches", quantity: 5, unit: "total" },
    { label: "Ribbon", quantity: 4, unit: "yd" },
    { label: '4" Ornaments', quantity: 5, unit: "total" },
  ],
  "36": [
    { label: "Flowers", quantity: 2, unit: "total" },
    { label: "Assorted Branches", quantity: 7, unit: "total" },
    { label: "Ribbon", quantity: 6, unit: "yd" },
  ],
  "48": [
    { label: "Flowers", quantity: 3, unit: "total" },
    { label: "Assorted Branches", quantity: 14, unit: "total" },
    { label: '8" Ornaments', quantity: 2, unit: "total" },
    { label: '6" Ornaments', quantity: 3, unit: "total" },
  ],
};

const GARLAND_ENHANCER_PARTS = [
  {
    label: "Assorted Branches",
    note: "Branches used to build out the garland body",
    searchTerms: "christmas assorted branch pine berry pick spray",
  },
  {
    label: '4" Ornament',
    note: "Main ornament inside each enhancer set",
    searchTerms: "christmas 4 inch ornament ball",
  },
  {
    label: "Ribbon",
    note: "Ribbon yardage based on the selected package",
    searchTerms: "christmas ribbon wired ribbon",
  },
  {
    label: "Flower",
    note: "Only needed for premium garland",
    premiumOnly: true,
    searchTerms: "christmas flower floral pick",
  },
  {
    label: "Premium Ribbon",
    note: "Only needed for premium garland",
    premiumOnly: true,
    searchTerms: "premium christmas ribbon wired ribbon",
  },
  {
    label: "Extra Ornaments",
    note: "Extra ornaments added to the premium garland package",
    premiumOnly: true,
    searchTerms: "christmas ornament cluster decor",
  },
] as const;

const CHRISTMAS_TREE_OPTIONS = [
  { code: "C164176LED", name: "Oregon Fir WA 900LED Warm White", source: "Vickerman", heightFeet: 7.5, heightLabel: "7.5 ft", diameterIn: 65, profile: "Standard", lightStatus: "Lit" },
  { code: "K184076LED", name: "Kamas Fraser Dura-Lit 450WW", source: "Vickerman", heightFeet: 7.5, heightLabel: "7.5 ft", diameterIn: 48, profile: "Standard", lightStatus: "Lit" },
  { code: "K194076LED", name: "Slim Natural Fraser Dura-Lit 700WW", source: "Vickerman", heightFeet: 7.5, heightLabel: "7.5 ft", diameterIn: 45, profile: "Slim", lightStatus: "Lit" },
  { code: "K201276LED", name: "Brighton Pine Dura-Lit 650WW", source: "Vickerman", heightFeet: 7.5, heightLabel: "7.5 ft", diameterIn: 48, profile: "Standard", lightStatus: "Lit" },
  { code: "A118277LED", name: "Cashmere Pine LED 700WW", source: "Vickerman", heightFeet: 7.5, heightLabel: "7.5 ft", diameterIn: 55, profile: "Standard", lightStatus: "Lit" },
  { code: "D172376LED", name: "Mixed Brussels Pine 1300LED", source: "Vickerman", heightFeet: 7.5, heightLabel: "7.5 ft", diameterIn: 61, profile: "Standard", lightStatus: "Lit" },
  { code: "K194081LED", name: "Natural Fraser Dura-Lit 850WW", source: "Vickerman", heightFeet: 8.5, heightLabel: "8.5 ft", diameterIn: 50, profile: "Slim", lightStatus: "Lit" },
  { code: "K173381LED", name: "Flocked Kiana Dura-Lit 1000WW", source: "Vickerman", heightFeet: 9, heightLabel: "9 ft", diameterIn: 66, profile: "Standard", lightStatus: "Lit" },
  { code: "K184081LED", name: "Kamas Fraser Fir Dura-Lit 650WW", source: "Vickerman", heightFeet: 9, heightLabel: "9 ft", diameterIn: 57, profile: "Standard", lightStatus: "Lit" },
  { code: "K201281LED", name: "Brighton Pine Dura-Lit 900WW", source: "Vickerman", heightFeet: 9, heightLabel: "9 ft", diameterIn: 57, profile: "Standard", lightStatus: "Lit" },
  { code: "A118286LED", name: "Cashmere Pine LED 1150WW", source: "Vickerman", heightFeet: 9.5, heightLabel: "9.5 ft", diameterIn: 67, profile: "Standard", lightStatus: "Lit" },
  { code: "C164186LED", name: "Oregon Fir WA 1400LED Warm White", source: "Vickerman", heightFeet: 9.5, heightLabel: "9.5 ft", diameterIn: 82, profile: "Full", lightStatus: "Lit" },
  { code: "K201286LED", name: "Brighton Pine Dura-Lit 1100WW", source: "Vickerman", heightFeet: 10, heightLabel: "10 ft", diameterIn: 63, profile: "Standard", lightStatus: "Lit" },
  { code: "C164191LED", name: "Oregon Fir WA 2400LED Warm White", source: "Vickerman", heightFeet: 12, heightLabel: "12 ft", diameterIn: 86, profile: "Standard", lightStatus: "Lit" },
  { code: "K194091LED", name: "Natural Fraser Dura-Lit 1350WW", source: "Vickerman", heightFeet: 12, heightLabel: "12 ft", diameterIn: 72, profile: "Slim", lightStatus: "Lit" },
  { code: "K201291LED", name: "Brighton Pine Dura-Lit", source: "Vickerman", heightFeet: 12, heightLabel: "12 ft", diameterIn: 73, profile: "Standard", lightStatus: "Lit" },
  { code: "A118291LED", name: "Brighton Pine Dura-Lit 1400WW", source: "Vickerman", heightFeet: 12, heightLabel: "12 ft", diameterIn: 85, profile: "Standard", lightStatus: "Lit" },
  { code: "D172391LED", name: "Mixed Brussels Pine 2400LED", source: "Vickerman", heightFeet: 12, heightLabel: "12 ft", diameterIn: 86, profile: "Standard", lightStatus: "Lit" },
  { code: "K201296LED", name: "Brighton Pine Dura-Lit 2000WW", source: "Vickerman", heightFeet: 14, heightLabel: "14 ft", diameterIn: 87, profile: "Standard", lightStatus: "Lit" },
  { code: "C164196LED", name: "Oregon Fir WA 3450LED Warm White", source: "Vickerman", heightFeet: 15, heightLabel: "15 ft", diameterIn: 114, profile: "Full", lightStatus: "Lit" },
  { code: "G194218WW", name: "Grand Teton Frame LED 7200WW", source: "Vickerman", heightFeet: 18, heightLabel: "18 ft", diameterIn: 131, profile: "Full", lightStatus: "Lit" },
  { code: "MTX70096B-TGCB", name: "Lit Asheville Alpine Tree 150L", source: "Regency", heightFeet: 4, heightLabel: "4 ft", diameterIn: 24, profile: "Pencil", lightStatus: "Lit" },
  { code: "MTX43286L", name: "LED Slim Belgium Tree 450L", source: "Regency", heightFeet: 7.5, heightLabel: "7.5 ft", diameterIn: 41, profile: "Slim", lightStatus: "Lit" },
  { code: "MTX45177L", name: "LED Deluxe Belgium Tree 950LT", source: "Regency", heightFeet: 7.5, heightLabel: "7.5 ft", diameterIn: 61, profile: "Standard", lightStatus: "Lit" },
  { code: "MTX43287B", name: "Lit Slim Belgium Mix Tree 650L", source: "Regency", heightFeet: 9, heightLabel: "9 ft", diameterIn: 49, profile: "Slim", lightStatus: "Lit" },
  { code: "MTX43283B", name: "Lit Belgium Mix Tree 900L", source: "Regency", heightFeet: 9, heightLabel: "9 ft", diameterIn: 57, profile: "Standard", lightStatus: "Lit" },
  { code: "MTX45178L", name: "LED Belgium Mix Tree 1400L", source: "Regency", heightFeet: 9, heightLabel: "9 ft", diameterIn: 73, profile: "Full", lightStatus: "Lit" },
  { code: "MTX43284L", name: "LED Belgium Mix Tree 1050L", source: "Regency", heightFeet: 10, heightLabel: "10 ft", diameterIn: 63, profile: "Standard", lightStatus: "Lit" },
  { code: "MTX47019N", name: "LED Deluxe Mix Belgium Tree 2150L", source: "Regency", heightFeet: 10, heightLabel: "10 ft", diameterIn: 75, profile: "Full", lightStatus: "Lit" },
  { code: "MTX43289L", name: "LED Slim Belgium 1300L", source: "Regency", heightFeet: 12, heightLabel: "12 ft", diameterIn: 63, profile: "Slim", lightStatus: "Lit" },
  { code: "MTX32248L", name: "LED Flock Bear Mountain Tree 1100LT", source: "Regency", heightFeet: 9.9, heightLabel: "9 ft 11 in", diameterIn: 73, profile: "Full", lightStatus: "Lit" },
] as const;

const CHRISTMAS_TREE_SIZE_OPTIONS = [
  { code: "6-PENCIL", label: "6' Pencil", heightFeet: 6, heightLabel: "6 ft", diameterIn: 30, profile: "Pencil" },
  { code: "7-5-PENCIL", label: "7.5' Pencil", heightFeet: 7.5, heightLabel: "7.5 ft", diameterIn: 30, profile: "Pencil" },
  { code: "7-SLIM", label: "7' Slim", heightFeet: 7, heightLabel: "7 ft", diameterIn: 42, profile: "Slim" },
  { code: "7-5-8-STANDARD", label: "7.5-8' Standard", heightFeet: 7.5, heightLabel: "7.5-8 ft", diameterIn: 55, profile: "Standard" },
  { code: "9-PENCIL", label: "9' Pencil", heightFeet: 9, heightLabel: "9 ft", diameterIn: 32, profile: "Pencil" },
  { code: "9-SLIM", label: "9' Slim", heightFeet: 9, heightLabel: "9 ft", diameterIn: 50, profile: "Slim" },
  { code: "9-STANDARD", label: "9' Standard", heightFeet: 9, heightLabel: "9 ft", diameterIn: 57, profile: "Standard" },
  { code: "10-STANDARD", label: "10'", heightFeet: 10, heightLabel: "10 ft", diameterIn: 63, profile: "Standard" },
  { code: "12-SLIM", label: "12' Slim", heightFeet: 12, heightLabel: "12 ft", diameterIn: 72, profile: "Slim" },
  { code: "12-STANDARD", label: "12' Standard", heightFeet: 12, heightLabel: "12 ft", diameterIn: 86, profile: "Standard" },
  { code: "14-STANDARD", label: "14'", heightFeet: 14, heightLabel: "14 ft", diameterIn: 87, profile: "Standard" },
  { code: "15-STANDARD", label: "15'", heightFeet: 15, heightLabel: "15 ft", diameterIn: 114, profile: "Standard" },
] as const;

function normalizeLabel(value?: string | null) {
  return (value || "").trim().toLowerCase();
}

function buildTypeConfigFor(buildType: string) {
  const normalized = normalizeLabel(buildType);
  const exact = BUILD_TYPE_CONFIGS.find((config) =>
    normalizeLabel(config.label) === normalized || config.aliases.some((alias) => normalizeLabel(alias) === normalized)
  );
  if (exact) return exact;
  if (normalized.includes("christmas tree")) return BUILD_TYPE_CONFIGS.find((config) => config.label === "Christmas Tree") || null;
  if (normalized.includes("garland")) return BUILD_TYPE_CONFIGS.find((config) => config.label === "Garland") || null;
  if (normalized.includes("wreath")) return BUILD_TYPE_CONFIGS.find((config) => config.label === "Wreath") || null;
  if (normalized.includes("vertical spray") || normalized.includes("teardrop") || normalized.includes("door drop")) return BUILD_TYPE_CONFIGS.find((config) => config.label === "Vertical Spray") || null;
  if (normalized.includes("horizontal swag") || normalized.includes("swag")) return BUILD_TYPE_CONFIGS.find((config) => config.label === "Horizontal Swag") || null;
  if (normalized.includes("drop")) return BUILD_TYPE_CONFIGS.find((config) => config.label === "Drop-in Arrangement") || null;
  if (normalized.includes("container garden") || normalized.includes("plant / vase") || normalized.includes("planter")) {
    return BUILD_TYPE_CONFIGS.find((config) => config.label === "Planter") || null;
  }
  if (normalized.includes("tree") || normalized.includes("fig")) return BUILD_TYPE_CONFIGS.find((config) => config.label === "Tree") || null;
  if (["orchid", "succulent", "greenery", "foliage"].some((word) => normalized.includes(word)) || normalized.includes("arrangement")) {
    return BUILD_TYPE_CONFIGS.find((config) => config.label === "Arrangement") || null;
  }
  return null;
}

function designPartsForBuildType(buildType: string) {
  const templateSlots = templateSlotsForBuildType(buildType);
  if (templateSlots) return templateSlots;
  const config = buildTypeConfigFor(buildType);
  if (config) return [...config.visibleParts];
  return null;
}

function baseScopePlaceholders(bucket: Container) {
  const designParts = designPartsForBuildType(`${bucket.bucket_type || ""} ${bucket.label || ""}`);
  if (designParts) return designParts.slice(0, 4);

  const intelligence = parseScopeIntelligence(bucket.scope_notes);
  const labels = intelligence?.components?.map((component) => component.label).filter(Boolean);
  const sections = labels && labels.length > 0 ? labels.slice(0, 4) : fallbackSectionsForBuildType(`${bucket.bucket_type || ""} ${bucket.label || ""}`);
  return sections.length >= 4 ? sections.slice(0, 4) : [...sections, "Product", "Product", "Product", "Product"].slice(0, 4);
}

function fallbackSectionsForBuildType(buildType: string) {
  const designParts = designPartsForBuildType(buildType);
  if (designParts) return designParts;

  const text = buildType.toLowerCase();
  if (text.includes("wreath")) return ["Wreath Base", "Decor Package"];
  if (text.includes("garland")) return ["Base Garland", "Greenery", "Ribbon", "Decor"];
  if (text.includes("container") || text.includes("planter")) return ["Container/Planter", "Finish/Top Dressing", "Main Plant", "Accent Plant"];
  if (text.includes("arrangement")) return ["Container/Base", "Finish/Top Dressing", "Focal Material", "Accent Material"];
  return ["Products", "Notes", "Pricing"];
}

function scopePlaceholders(bucket: Container) {
  return [...baseScopePlaceholders(bucket), ...parseCustomSections(bucket.scope_notes)];
}

function firstNumber(value?: string | null) {
  const match = String(value || "").match(/(\d+(?:\.\d+)?)/);
  return match ? Number(match[1]) : null;
}

function treeWidthNumber(value?: string | null) {
  const text = String(value || "");
  const xWidth = text.match(/x\s*(\d+(?:\.\d+)?)\s*(?:"|in|d\b)/i);
  if (xWidth) return Number(xWidth[1]);
  const diameter = text.match(/(\d+(?:\.\d+)?)\s*(?:"|in)?\s*d(?:iam|iameter)?\b/i);
  return diameter ? Number(diameter[1]) : firstNumber(value);
}

function scopeNoteValue(notes: string | null | undefined, label: string) {
  const prefix = `${label}:`;
  const line = (notes || "").split("\n").find((part) => part.trim().toLowerCase().startsWith(prefix.toLowerCase()));
  return line ? line.slice(prefix.length).trim() : "";
}

function christmasTreeDecorRule(heightValue?: string | null, widthValue?: string | null) {
  const height = firstNumber(heightValue);
  const width = treeWidthNumber(widthValue);
  if (!height && !width) return null;

  if ((height || 0) >= 15) return { label: "15 ft", enhancers: 60, ornaments: 200 };
  if ((height || 0) >= 14) return { label: "14 ft", enhancers: 48, ornaments: 160 };
  if ((height || 0) >= 12) {
    return (width || 0) >= 73
      ? { label: "12 ft standard", enhancers: 36, ornaments: 126 }
      : { label: "12 ft slim", enhancers: 30, ornaments: 108 };
  }
  if ((height || 0) >= 9.5) return { label: "9.5-10 ft", enhancers: 24, ornaments: 84 };
  if ((height || 0) >= 8.5) {
    return (width || 0) >= 57
      ? { label: "8.5-9 ft standard", enhancers: 18, ornaments: 72 }
      : { label: "8.5-9 ft slim", enhancers: 16, ornaments: 60 };
  }
  if ((height || 0) >= 7) {
    if ((width || 0) <= 32 && width) return { label: "7.5 ft pencil", enhancers: 8, ornaments: 30 };
    if ((width || 0) <= 45 && width) return { label: "7-7.5 ft slim", enhancers: 8, ornaments: 36 };
    return { label: "7.5 ft standard", enhancers: 14, ornaments: 60 };
  }
  return { label: "small tree", enhancers: 8, ornaments: 30 };
}

function christmasTreeDecorRuleForBucket(bucket?: Container | null) {
  if (!bucket) return null;
  const selectedTree = itemsForPart(bucket, "Tree", 0)[0];
  const height = scopeNoteValue(bucket.scope_notes, "Height") || selectedTree?.product_name;
  const width = scopeNoteValue(bucket.scope_notes, "Width / canopy") || selectedTree?.product_name;
  return christmasTreeDecorRule(height, width);
}

function christmasEnhancerCountSummary(rule: ReturnType<typeof christmasTreeDecorRule>, profile?: string | null) {
  if (!rule) return "Select a tree size to calculate how many enhancers are needed.";
  const profileLabel = String(profile || "").trim().toLowerCase();
  const selectedSize = profileLabel && !rule.label.toLowerCase().includes(profileLabel) ? `${rule.label} ${profileLabel}` : rule.label;
  return `${rule.enhancers} enhancers needed for the ${selectedSize} tree selected.`;
}

function isChristmasTreeBuild(buildType?: string | null) {
  return buildTypeConfigFor(buildType || "")?.label === "Christmas Tree";
}

function isChristmasTreeBucket(bucket?: Container | null) {
  return isChristmasTreeBuild(`${bucket?.bucket_type || ""} ${bucket?.label || ""}`);
}

function isGarlandBuild(buildType?: string | null) {
  return buildTypeConfigFor(buildType || "")?.label === "Garland";
}

function isGarlandBucket(bucket?: Container | null) {
  return isGarlandBuild(`${bucket?.bucket_type || ""} ${bucket?.label || ""}`);
}

function isWreathBuild(buildType?: string | null) {
  return buildTypeConfigFor(buildType || "")?.label === "Wreath";
}

function isWreathBucket(bucket?: Container | null) {
  return isWreathBuild(`${bucket?.bucket_type || ""} ${bucket?.label || ""}`);
}

function isStructuredChristmasBucket(bucket?: Container | null) {
  return isChristmasTreeBucket(bucket) || isGarlandBucket(bucket) || isWreathBucket(bucket);
}

function isEnhancersPart(label: string) {
  return normalizeLabel(label).includes("enhancer");
}

function isWreathDecorPart(label: string) {
  const normalized = normalizeLabel(label);
  return normalized.includes("decor package") || normalized === "decor";
}

function christmasEnhancerPartIndex(parentIndex: number, subIndex: number) {
  return parentIndex * 100 + subIndex + 1;
}

function christmasEnhancerBaseCount(bucket: Container | null | undefined) {
  return christmasTreeDecorRuleForBucket(bucket)?.enhancers || 8;
}

function mergeEnhancerParts(parts: EnhancerPartConfig[]) {
  const byLabel = new Map<string, EnhancerPartConfig>();
  parts.forEach((part) => {
    const key = normalizeLabel(part.label);
    const existing = byLabel.get(key);
    byLabel.set(key, existing ? { ...existing, ...part, regularFormula: existing.regularFormula || part.regularFormula, premiumFormula: existing.premiumFormula || part.premiumFormula } : part);
  });
  return Array.from(byLabel.values());
}

function allChristmasEnhancerPartConfigs() {
  const regular = enhancerPartsFromTemplate("Christmas Tree", "regular") || [];
  const premium = enhancerPartsFromTemplate("Christmas Tree", "premium") || [];
  const merged = mergeEnhancerParts([...regular, ...premium]);
  return merged.length ? merged : CHRISTMAS_ENHANCER_PARTS;
}

function christmasEnhancerPartConfig(label: string) {
  return allChristmasEnhancerPartConfigs().find((part) => normalizeLabel(part.label) === normalizeLabel(label));
}

function christmasEnhancerPartIsOptional(part: EnhancerPartConfig) {
  return Boolean(part.optional || part.premiumOnly);
}

function christmasEnhancerRegularFormula(part: EnhancerPartConfig) {
  return part.regularFormula || "";
}

function christmasEnhancerPremiumFormula(part: EnhancerPartConfig) {
  return part.premiumFormula || "";
}

function christmasEnhancerPartRequiredForPackage(part: EnhancerPartConfig, packageType: ChristmasEnhancerPackage) {
  return packageType === "premium" ? Boolean(christmasEnhancerPremiumFormula(part)) : Boolean(christmasEnhancerRegularFormula(part));
}

function christmasEnhancerPartsForPackage(packageType: ChristmasEnhancerPackage) {
  const templateParts = enhancerPartsFromTemplate("Christmas Tree", packageType);
  if (templateParts?.length) return templateParts;
  return CHRISTMAS_ENHANCER_PARTS.filter((part) => christmasEnhancerPartRequiredForPackage(part, packageType));
}

function christmasEnhancerPartSubIndex(label: string) {
  const index = allChristmasEnhancerPartConfigs().findIndex((part) => normalizeLabel(part.label) === normalizeLabel(label));
  return Math.max(0, index);
}

function christmasEnhancerPartQuantity(bucket: Container | null | undefined, label: string) {
  const enhancers = christmasEnhancerBaseCount(bucket);
  const packageType = christmasEnhancerPackageFromNotes(bucket?.scope_notes);
  const part = christmasEnhancerPartConfig(label);
  const formula = packageType === "premium" ? part?.premiumFormula : part?.regularFormula;
  return Math.max(1, Math.ceil(enhancers * parseMaterialQuantity(formula || "1")));
}

function christmasEnhancerPartPreviewText(label: string, enhancers: number, packageType: ChristmasEnhancerPackage) {
  const part = christmasEnhancerPartConfig(label);
  const formula = packageType === "premium" ? part?.premiumFormula : part?.regularFormula;
  const quantity = Math.max(1, Math.ceil(enhancers * parseMaterialQuantity(formula || "1")));
  return /yd|yard/i.test(formula || "") ? `${quantity} yd` : `${quantity} total`;
}

function christmasEnhancerPartTargetText(bucket: Container | null | undefined, label: string) {
  return christmasEnhancerPartPreviewText(label, christmasEnhancerBaseCount(bucket), christmasEnhancerPackageFromNotes(bucket?.scope_notes));
}

function christmasEnhancerPartItems(bucket: Container | null | undefined, parentIndex: number, subIndex: number) {
  const part = allChristmasEnhancerPartConfigs()[subIndex];
  return part ? itemsForPart(bucket, part.label, christmasEnhancerPartIndex(parentIndex, subIndex)) : [];
}

function garlandEnhancerRule(packageType: GarlandPackage, lengthValue?: string | null) {
  const multiplier = garlandLengthMultiplier(lengthValue);
  return packageType === "premium"
    ? { label: "premium", regularEnhancers: 2 * multiplier, premiumEnhancers: 3 * multiplier, extraOrnaments: 2 * multiplier }
    : { label: "regular", regularEnhancers: 5 * multiplier, premiumEnhancers: 0, extraOrnaments: 0 };
}

function garlandEnhancerPartConfig(label: string) {
  return GARLAND_ENHANCER_PARTS.find((part) => normalizeLabel(part.label) === normalizeLabel(label));
}

function garlandEnhancerPartsForPackage(packageType: GarlandPackage) {
  const labels = packageType === "premium"
    ? ["Flower", "Assorted Branches", '4" Ornament', "Ribbon", "Premium Ribbon", "Extra Ornaments"]
    : ["Assorted Branches", '4" Ornament', "Ribbon"];
  return labels
    .map((label) => garlandEnhancerPartConfig(label))
    .filter(Boolean) as Array<(typeof GARLAND_ENHANCER_PARTS)[number]>;
}

function garlandEnhancerPartSubIndex(label: string) {
  const index = GARLAND_ENHANCER_PARTS.findIndex((part) => normalizeLabel(part.label) === normalizeLabel(label));
  return Math.max(0, index);
}

function formatGarlandQuantity(value: number, unit: "total" | "yd") {
  const rounded = Number.isInteger(value) ? String(value) : value.toFixed(1).replace(/\.0$/, "");
  return `${rounded} ${unit}`;
}

function garlandEnhancerPartQuantity(packageType: GarlandPackage, label: string, lengthValue?: string | null) {
  const rule = garlandEnhancerRule(packageType, lengthValue);
  const normalized = normalizeLabel(label);
  const totalEnhancers = rule.regularEnhancers + rule.premiumEnhancers;
  if (normalized.includes("assorted branch")) return rule.regularEnhancers * 2 + rule.premiumEnhancers * 2;
  if (normalized === '4" ornament' || normalized.includes("4 ornament")) return totalEnhancers;
  if (normalized === "ribbon") return rule.regularEnhancers * 2.5 + rule.premiumEnhancers * 1.5;
  if (normalized.includes("flower")) return rule.premiumEnhancers;
  if (normalized.includes("premium ribbon")) return rule.premiumEnhancers;
  if (normalized.includes("extra ornament")) return rule.extraOrnaments;
  return totalEnhancers;
}

function garlandEnhancerPartPreviewText(label: string, packageType: GarlandPackage, lengthValue?: string | null) {
  const normalized = normalizeLabel(label);
  const quantity = garlandEnhancerPartQuantity(packageType, label, lengthValue);
  if (normalized.includes("ribbon")) return formatGarlandQuantity(quantity, "yd");
  return formatGarlandQuantity(quantity, "total");
}

function garlandEnhancerPartTargetText(bucket: Container | null | undefined, label: string) {
  return garlandEnhancerPartPreviewText(label, garlandPackageFromNotes(bucket?.scope_notes), garlandLengthFromNotes(bucket?.scope_notes));
}

function garlandEnhancerPartItems(bucket: Container | null | undefined, parentIndex: number, subIndex: number) {
  const part = GARLAND_ENHANCER_PARTS[subIndex];
  return part ? itemsForPart(bucket, part.label, christmasEnhancerPartIndex(parentIndex, subIndex)) : [];
}

function garlandEnhancerCountSummary(packageType: GarlandPackage, lengthValue: string, diameter: GarlandDiameter) {
  const rule = garlandEnhancerRule(packageType, lengthValue);
  const productLabel = `${packageType === "premium" ? "Premium" : "Regular"} Garland ${garlandSetupLabel(lengthValue, diameter)}`;
  if (packageType === "premium") {
    return `${rule.premiumEnhancers} premium enhancers, ${rule.regularEnhancers} regular enhancers, and ${rule.extraOrnaments} extra ornaments needed for the ${productLabel} selected.`;
  }
  return `${rule.regularEnhancers} regular enhancers needed for the ${productLabel} selected.`;
}

function wreathDecorPartConfig(label: string) {
  return WREATH_DECOR_PARTS.find((part) => normalizeLabel(part.label) === normalizeLabel(label));
}

function wreathDecorPartsForSize(size: WreathSize) {
  return WREATH_DECOR_RECIPES[size]
    .map((recipe) => {
      const config = wreathDecorPartConfig(recipe.label);
      return config ? { ...config, ...recipe } : null;
    })
    .filter(Boolean) as Array<(typeof WREATH_DECOR_PARTS)[number] & { quantity: number; unit: "total" | "yd" }>;
}

function wreathDecorPartSubIndex(label: string) {
  const index = WREATH_DECOR_PARTS.findIndex((part) => normalizeLabel(part.label) === normalizeLabel(label));
  return Math.max(0, index);
}

function wreathDecorPartItems(bucket: Container | null | undefined, parentIndex: number, subIndex: number) {
  const part = WREATH_DECOR_PARTS[subIndex];
  return part ? itemsForPart(bucket, part.label, christmasEnhancerPartIndex(parentIndex, subIndex)) : [];
}

function wreathDecorPartPreviewText(label: string, size: WreathSize) {
  const recipe = WREATH_DECOR_RECIPES[size].find((item) => normalizeLabel(item.label) === normalizeLabel(label));
  if (!recipe) return "";
  return formatGarlandQuantity(recipe.quantity, recipe.unit);
}

function wreathDecorCountSummary(size: WreathSize) {
  const parts = WREATH_DECOR_RECIPES[size]
    .map((part) => `${formatGarlandQuantity(part.quantity, part.unit)} ${part.label.toLowerCase()}`)
    .join(", ");
  return `${parts} needed for the ${size}" wreath selected.`;
}

function partKey(label: string, index: number) {
  return `${index}-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "part"}`;
}

function itemsForPart(bucket: Container | null | undefined, label: string, index: number) {
  if (!bucket) return [];
  const key = partKey(label, index);
  return bucket.items.filter((item) => (item.part_key || "") === key || (!item.part_key && index === 0));
}

function primarySelectedForPart(bucket: Container, label: string, index: number) {
  return (
    itemsForPart(bucket, label, index).find((item) => (item.status || "selected") === "selected") ||
    itemsForPart(bucket, label, index)[0] ||
    null
  );
}

function partIsComplete(bucket: Container, label: string, index: number) {
  if (isChristmasTreeBucket(bucket) && isEnhancersPart(label)) {
    const packageType = christmasEnhancerPackageFromNotes(bucket.scope_notes);
    return christmasEnhancerPartsForPackage(packageType).every((part) => {
      const subIndex = christmasEnhancerPartSubIndex(part.label);
      return christmasEnhancerPartItems(bucket, index, subIndex).some((item) => (item.status || "selected") === "selected");
    });
  }
  if (isGarlandBucket(bucket) && isEnhancersPart(label)) {
    const packageType = garlandPackageFromNotes(bucket.scope_notes);
    return garlandEnhancerPartsForPackage(packageType).every((part) => {
      const subIndex = garlandEnhancerPartSubIndex(part.label);
      return garlandEnhancerPartItems(bucket, index, subIndex).some((item) => (item.status || "selected") === "selected");
    });
  }
  if (isWreathBucket(bucket) && isWreathDecorPart(label)) {
    const size = wreathSizeFromNotes(bucket.scope_notes);
    return wreathDecorPartsForSize(size).every((part) => {
      const subIndex = wreathDecorPartSubIndex(part.label);
      return wreathDecorPartItems(bucket, index, subIndex).some((item) => (item.status || "selected") === "selected");
    });
  }
  return itemsForPart(bucket, label, index).some((item) => (item.status || "selected") === "selected");
}

function componentLooksLikePart(componentLabel: string, partLabel: string) {
  const component = normalizeLabel(componentLabel);
  const part = normalizeLabel(partLabel);
  if (part === "tree") return ["tree", "pine", "fir", "spruce", "lit", "unlit"].some((term) => component.includes(term));
  if (part.includes("enhancer")) return ["ribbon", "pick", "spray", "ornament", "cluster", "branch", "flower", "berry", "decor"].some((term) => component.includes(term));
  if (part.includes("assorted branch")) return ["branch", "pine", "berry", "pick", "spray"].some((term) => component.includes(term));
  if (part.includes("flower")) return component.includes("flower") || component.includes("floral");
  if (part.includes("skirt")) return component.includes("skirt");
  if (part.includes("topper")) return component.includes("topper");
  if (part.includes("container") || part.includes("base")) return component.includes("container");
  if (part.includes("finish") || part.includes("top dressing")) return ["top dressing", "moss", "fiber"].some((term) => component.includes(term));
  if (part.includes("trunk") || part.includes("branch")) return component.includes("trunk") || component.includes("branch");
  if (part.includes("leaf") || part.includes("greenery")) return component.includes("leaf") || component.includes("greenery") || component.includes("foliage");
  if (part.includes("focal") || part.includes("main plant") || part.includes("main material")) {
    return ["orchid", "succulent", "cactus", "foliage", "greenery", "leaves", "product"].some((term) => component.includes(term));
  }
  if (part.includes("accent")) return ["branch", "foliage", "greenery", "leaves", "decor", "product"].some((term) => component.includes(term));
  if (part.includes("lights")) return component.includes("light");
  if (part.includes("ribbon")) return component.includes("ribbon");
  if (part.includes("decor") || part.includes("ornament")) return component.includes("decor");
  return false;
}

function suggestionForPart(bucket: Container | null | undefined, label: string, index: number): BuildSuggestionComponent | null {
  if (!bucket) return null;
  const intelligence = parseScopeIntelligence(bucket.scope_notes);
  const components = intelligence?.components || [];
  const direct = components.find((component) => partKey(component.label, index) === partKey(label, index) || normalizeLabel(component.label) === normalizeLabel(label));
  if (direct) return direct;
  const mapped = components
    .filter((component) => componentLooksLikePart(component.label, label))
    .sort((a, b) => (b.evidence_count || 0) - (a.evidence_count || 0))[0];
  return mapped || null;
}

function searchTermsForPart(bucket: Container | null | undefined, label: string, index: number) {
  const part = normalizeLabel(label);
  if (buildTypeConfigFor(`${bucket?.bucket_type || ""} ${bucket?.label || ""}`)?.label === "Christmas Tree") {
    const enhancerPart = christmasEnhancerPartConfig(label);
    if (enhancerPart?.searchTerms) return enhancerPart.searchTerms;
    if (part === "tree") return "christmas tree lit unlit pine fir spruce";
    if (part.includes("enhancer")) return "christmas assorted branch ribbon ornament flower pick spray decor";
    if (part.includes("ribbon")) return "christmas ribbon";
    if (part.includes("branch") || part.includes("pick") || part.includes("spray")) return "christmas branch pick spray enhancer";
    if (part.includes("ornament") || part.includes("cluster")) return "christmas ornament cluster";
    if (part.includes("skirt")) return "christmas tree skirt";
    if (part.includes("topper")) return "christmas tree topper";
  }
  if (buildTypeConfigFor(`${bucket?.bucket_type || ""} ${bucket?.label || ""}`)?.label === "Garland") {
    const enhancerPart = garlandEnhancerPartConfig(label);
    if (enhancerPart?.searchTerms) return enhancerPart.searchTerms;
    if (part === "garland") return "christmas garland lighted unlit pine mixed greenery";
    if (part.includes("enhancer")) return "christmas branch ribbon ornament flower pick spray";
    if (part.includes("ribbon")) return "christmas ribbon";
    if (part.includes("ornament")) return "christmas ornament";
  }
  if (buildTypeConfigFor(`${bucket?.bucket_type || ""} ${bucket?.label || ""}`)?.label === "Wreath") {
    const decorPart = wreathDecorPartConfig(label);
    if (decorPart?.searchTerms) return decorPart.searchTerms;
    if (part.includes("wreath") || part.includes("base")) return "wreath";
    if (part.includes("decor")) return "christmas wreath branch ribbon ornament flower";
  }
  if (part.includes("container") || part.includes("base") || part.includes("planter")) return "container";
  if (part.includes("finish") || part.includes("top dressing")) return "moss";
  if (part.includes("trunk") || part.includes("branch")) return "branch";
  if (part.includes("leaf") || part.includes("leaves")) return "leaf";
  if (part.includes("focal") || part.includes("main material") || part.includes("main plant")) return "orchid";
  if (part.includes("accent")) return "greenery";
  if (part.includes("ribbon")) return "ribbon";
  if (part.includes("decor") || part.includes("ornament")) return "ornament";
  const suggestion = suggestionForPart(bucket, label, index);
  const terms = suggestion?.search_terms?.filter(Boolean) || [];
  if (terms.length) return terms.join(" ");
  return label;
}

function suggestedQuantityForPart(bucket: Container | null | undefined, label: string, index: number) {
  if (isChristmasTreeBucket(bucket)) {
    const part = normalizeLabel(label);
    if (part.includes("branch") || part.includes("flower") || part.includes("ribbon") || part.includes("pick") || part.includes("spray") || part.includes("ornament") || part.includes("cluster")) {
      return christmasEnhancerPartQuantity(bucket, label);
    }
  }
  if (isGarlandBucket(bucket)) {
    const part = normalizeLabel(label);
    if (part.includes("branch") || part.includes("ribbon") || part.includes("ornament") || part.includes("flower")) {
      return Math.max(1, Math.ceil(garlandEnhancerPartQuantity(garlandPackageFromNotes(bucket?.scope_notes), label, garlandLengthFromNotes(bucket?.scope_notes))));
    }
  }
  if (isWreathBucket(bucket)) {
    const size = wreathSizeFromNotes(bucket?.scope_notes);
    const recipe = WREATH_DECOR_RECIPES[size].find((item) => normalizeLabel(item.label) === normalizeLabel(label));
    if (recipe) return Math.max(1, Math.ceil(recipe.quantity));
  }
  const raw = suggestionForPart(bucket, label, index)?.suggested_quantity;
  return Math.max(1, Math.round(Number(raw) || 1));
}

function christmasPartGuidance(bucket: Container | null | undefined, label: string) {
  const buildLabel = buildTypeConfigFor(`${bucket?.bucket_type || ""} ${bucket?.label || ""}`)?.label;
  if (buildLabel === "Garland") {
    const part = normalizeLabel(label);
    const packageType = garlandPackageFromNotes(bucket?.scope_notes);
    const lengthValue = garlandLengthFromNotes(bucket?.scope_notes);
    const diameter = garlandDiameterFromNotes(bucket?.scope_notes);
    if (part === "garland") return "Choose the base garland, lighted or unlit.";
    if (part.includes("enhancer")) return garlandEnhancerCountSummary(packageType, lengthValue, diameter);
    return "";
  }
  if (buildLabel === "Wreath") {
    const part = normalizeLabel(label);
    const size = wreathSizeFromNotes(bucket?.scope_notes);
    if (part.includes("wreath") || part.includes("base")) return `Choose the ${size}" wreath base.`;
    if (isWreathDecorPart(label)) return wreathDecorCountSummary(size);
    return "";
  }
  if (buildLabel !== "Christmas Tree") return "";
  const part = normalizeLabel(label);
  const rule = christmasTreeDecorRuleForBucket(bucket);
  if (part === "tree") return "Choose the tree, lit or unlit.";
  if (part.includes("enhancer")) {
    const sizeGuide = rule ? ` Size guide: ${rule.enhancers} enhancer sets and ${rule.ornaments} loose ornaments/clusters.` : "";
    return `Regular enhancers use assorted branches, 4-inch ornaments, and ribbon. Premium adds flowers and premium ribbon.${sizeGuide}`;
  }
  if (part.includes("skirt")) return "Sized to the tree diameter.";
  if (part.includes("topper")) return "Final topper for the decor package.";
  return "";
}

function christmasPreviewGuidance(buildType: string, label: string, heightValue?: string | null, widthValue?: string | null) {
  const buildLabel = buildTypeConfigFor(buildType)?.label;
  if (buildLabel === "Garland") {
    const part = normalizeLabel(label);
    if (part === "garland") return "lighted or unlit base";
    if (part.includes("enhancer")) return "regular/premium enhancer package";
    return "";
  }
  if (buildLabel === "Wreath") {
    const part = normalizeLabel(label);
    if (part.includes("wreath") || part.includes("base")) return "wreath size";
    if (isWreathDecorPart(label)) return "branches/ribbon/flowers/ornaments by size";
    return "";
  }
  if (buildLabel !== "Christmas Tree") return "";
  const part = normalizeLabel(label);
  const rule = christmasTreeDecorRule(heightValue, widthValue);
  if (part === "tree") return "lit or unlit";
  if (part.includes("enhancer")) return rule ? `${rule.enhancers} enhancers · regular/premium recipe` : "regular/premium material recipe";
  if (part.includes("skirt")) return "by tree diameter";
  if (part.includes("topper")) return "final topper";
  return "";
}

function compactSkuPart(value?: string | null, fallback = "NEW", limit = 5) {
  return (value || "").replace(/[^a-z0-9]+/gi, "").slice(0, limit).toUpperCase() || fallback;
}

function skuCodeForBuildType(buildType: string) {
  return buildTypeConfigFor(buildType)?.skuCode || "GR-CUS";
}

function selectedSkuSource(bucket?: Container | null) {
  if (!bucket) return "";
  const baseLabels = ["container", "base", "planter", "tree/base", "garland", "wreath"];
  const baseItem = bucket.items.find((item) =>
    (item.status || "selected") === "selected" && baseLabels.some((label) => normalizeLabel(item.part_label).includes(label))
  );
  const focalItem = bucket.items.find((item) => (item.status || "selected") === "selected");
  return baseItem?.supplier_sku || baseItem?.product_name || focalItem?.supplier_sku || focalItem?.product_name || "";
}

function suggestedSkuForType(buildType: string, label?: string | null, arrangement?: Arrangement | null, section: BuilderSection = "green") {
  const code = buildTypeConfigFor(buildType)?.skuCode || `${section === "christmas" ? "CH" : "GR"}-CUS`;
  const projectPart = compactSkuPart(arrangement?.name || arrangement?.client_name || label || buildType, "BUILD", 5);
  return `${code}-${projectPart}-${new Date().getFullYear()}`;
}

function suggestedFinishedSku(bucket?: Container | null, arrangement?: Arrangement | null) {
  const code = skuCodeForBuildType(`${bucket?.bucket_type || ""} ${bucket?.label || ""}`);
  const sourcePart = compactSkuPart(selectedSkuSource(bucket) || bucket?.label || bucket?.bucket_type || arrangement?.name, "BUILD", 5);
  return `${code}-${sourcePart}-${new Date().getFullYear()}`;
}

function mechanicsEstimate(bucket?: Container | null) {
  const components = parseScopeIntelligence(bucket?.scope_notes)?.components || [];
  return components
    .filter((component) => ["foam", "moss", "fiber", "mechanic", "stake", "clip", "wire", "filler", "stabil"].some((term) => normalizeLabel(component.label).includes(term)))
    .reduce((sum, component) => sum + (Number(component.average_extended_total) || 0), 0);
}

function evidenceForConfig(config: typeof BUILD_TYPE_CONFIGS[number], buildTypes: BuildTypeOption[]) {
  return buildTypes.reduce((sum, option) => {
    const labelMatches = config.aliases.some((alias) => normalizeLabel(alias) === normalizeLabel(option.label));
    const prefixMatches = (option.prefixes || []).some((prefix) => config.prefixes.some((knownPrefix) => knownPrefix === prefix));
    return labelMatches || prefixMatches ? sum + (Number(option.evidence_count) || 0) : sum;
  }, 0);
}

function builderProductName(product: LibraryProduct) {
  return String(product.raw_data?.Description || product.description || product.name || "").trim();
}

function builderProductSearchText(product: LibraryProduct) {
  const raw = product.raw_data || {};
  return [
    builderProductName(product),
    product.name,
    product.description,
    product.supplier_sku,
    product.supplier_name,
    product.category,
    product.unit,
    product.material,
    product.finish,
    product.style,
    product.color,
    product.country_of_origin,
    product.availability,
    product.height_in,
    product.width_in,
    product.diameter_in,
    product.length_in,
    raw.name,
    raw.sku,
    raw.price,
    raw.Category,
    raw.Color,
    raw["Primary Color"],
    raw.Material,
    raw.Materials,
    raw.Finish,
    raw.Style,
    raw["Unit of Measure"],
    raw.Unit,
    raw.Country,
    raw["Country of Origin"],
    raw.Height,
    raw.Width,
    raw.Diameter,
    raw.Length,
    raw.Availability,
    raw.ColorGrp,
    raw.Class,
    raw.Season,
    raw.UPC,
    raw["Material Breakdown"],
    raw.Material_Breakdown,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function BuilderProductPicker({
  products,
  loadingCatalog = false,
  activePartLabel,
  initialQuery = "",
  selectedProductIds,
  selectedProductItemIds,
  onAdd,
  onRemove,
  onOpenProduct,
  onContinue,
  onReloadCatalog,
  catalogTotal,
}: {
  products: LibraryProduct[];
  loadingCatalog?: boolean;
  activePartLabel: string;
  initialQuery?: string;
  selectedProductIds: Set<number>;
  selectedProductItemIds: Map<number, number>;
  onAdd: (product: LibraryProduct) => void;
  onRemove: (itemId: number) => void;
  onOpenProduct: (product: LibraryProduct) => void;
  onContinue: () => void;
  onReloadCatalog?: () => void;
  catalogTotal?: number | null;
}) {
  const [query, setQuery] = useState("");
  const [activeQuery, setActiveQuery] = useState("");
  const [category, setCategory] = useState("All");
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(25);
  const suggestedQuery = initialQuery.trim();
  const fullCatalogLoaded = !catalogTotal || products.length >= catalogTotal;

  useEffect(() => {
    setQuery("");
    setActiveQuery("");
    setCategory("All");
  }, [activePartLabel, initialQuery]);

  useEffect(() => {
    const handle = window.setTimeout(() => setActiveQuery(query), 180);
    return () => window.clearTimeout(handle);
  }, [query]);

  const indexed = useMemo(
    () =>
      products.map((product) => ({
        product,
        name: builderProductName(product),
        search: builderProductSearchText(product),
      })),
    [products]
  );

  const categories = useMemo(() => {
    const values = Array.from(new Set(products.map((product) => product.category).filter(Boolean)));
    return ["All", ...values.sort((a, b) => categoryLabel(a).localeCompare(categoryLabel(b)))].slice(0, 12);
  }, [products]);

  const { filtered, showingQueryFallback } = useMemo(() => {
    const terms = activeQuery.toLowerCase().trim().split(/\s+/).filter(Boolean);
    const categoryMatches = indexed.filter(({ product }) => category === "All" || product.category === category);
    const strictMatches = categoryMatches.filter(({ search }) => terms.every((term) => search.includes(term)));
    const showingFallback = terms.length > 0 && strictMatches.length === 0 && categoryMatches.length > 0;
    return {
      filtered: showingFallback ? categoryMatches : strictMatches,
      showingQueryFallback: showingFallback,
    };
  }, [indexed, activeQuery, category]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / perPage));
  const currentPage = Math.min(page, totalPages);
  const visible = useMemo(
    () => filtered.slice((currentPage - 1) * perPage, currentPage * perPage),
    [filtered, currentPage, perPage]
  );

  useEffect(() => {
    setPage(1);
  }, [activeQuery, category, perPage]);

  return (
    <div className="flex h-full flex-col">
      <div className="space-y-3 border-b border-stone-100 p-5">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-400" size={16} />
	          <input
	            value={query}
	            onChange={(event) => setQuery(event.target.value)}
	            placeholder={suggestedQuery ? `Search full catalog, or try "${suggestedQuery}"` : "Search full catalog"}
	            className="w-full rounded-xl border border-stone-200 py-2.5 pl-9 pr-9 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
	          />
          {query && (
            <button
              type="button"
              onClick={() => setQuery("")}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-stone-400 hover:text-stone-700"
            >
              <X size={15} />
            </button>
          )}
        </div>
	        <div className="flex flex-wrap gap-2">
	          {categories.map((value) => (
            <button
              key={value}
              type="button"
              onClick={() => setCategory(value)}
              className={`rounded-full px-3 py-1.5 text-xs font-medium ${
                category === value ? "bg-stone-900 text-white" : "bg-stone-100 text-stone-600 hover:bg-stone-200"
              }`}
            >
              {value === "All" ? "All" : categoryLabel(value)}
            </button>
	          ))}
	        </div>
        <div className="flex flex-wrap items-center gap-2">
          {suggestedQuery && !activeQuery && (
            <button
              type="button"
              onClick={() => setQuery(suggestedQuery)}
              className="rounded-full border border-emerald-100 bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-900 transition hover:border-emerald-200 hover:bg-emerald-100"
            >
              Use suggested search
            </button>
          )}
          {(activeQuery || category !== "All") && (
            <button
              type="button"
              onClick={() => {
                setQuery("");
                setActiveQuery("");
                setCategory("All");
              }}
              className="rounded-full border border-stone-200 bg-white px-3 py-1.5 text-xs font-semibold text-stone-600 transition hover:border-emerald-200 hover:text-emerald-800"
            >
              Show full catalog
            </button>
          )}
          {!fullCatalogLoaded && onReloadCatalog && (
            <button
              type="button"
              onClick={onReloadCatalog}
              disabled={loadingCatalog}
              className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs font-semibold text-amber-900 transition hover:border-amber-300 disabled:opacity-50"
            >
              {loadingCatalog ? "Loading full catalog..." : "Load full catalog"}
            </button>
          )}
        </div>
	        <p className="text-xs text-stone-400">
	          {showingQueryFallback ? "No exact matches for this search. Showing the full catalog so you can keep browsing. " : ""}
	          Showing {visible.length} of {filtered.length.toLocaleString()} matches from {products.length.toLocaleString()} loaded catalog products{catalogTotal && catalogTotal > products.length ? ` (${catalogTotal.toLocaleString()} total)` : ""}. Add keeps you in this builder.
	        </p>
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-xs text-stone-500">
            <span>View</span>
            <select
              value={perPage}
              onChange={(event) => setPerPage(Number(event.target.value))}
              className="rounded-lg border border-stone-200 bg-white px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-emerald-300"
            >
              {[25, 50, 100].map((value) => (
                <option key={value} value={value}>{value}</option>
              ))}
            </select>
            <span>per page</span>
          </div>
          <div className="text-xs text-stone-500">
            Page {currentPage} of {totalPages}
          </div>
        </div>
        <button
          type="button"
          onClick={onContinue}
          className="w-full rounded-xl bg-stone-900 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-40"
          disabled={selectedProductIds.size === 0}
        >
          Continue to mockup →
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-auto p-5">
        {loadingCatalog && products.length === 0 ? (
          <div className="flex min-h-[360px] items-center justify-center rounded-2xl border border-dashed border-stone-300 bg-stone-50 text-center">
            <div>
              <div className="mx-auto h-8 w-8 animate-spin rounded-full border-2 border-emerald-700 border-t-transparent" />
              <p className="mt-4 font-semibold text-stone-800">Loading catalog</p>
              <p className="mt-1 text-sm text-stone-400">This only loads inside the product picker.</p>
            </div>
          </div>
        ) : visible.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-stone-300 p-8 text-center">
            <p className="font-semibold text-stone-800">No matching products</p>
            <p className="mt-1 text-sm text-stone-400">Try a broader word, SKU, color, or category.</p>
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {visible.map(({ product, name }) => {
              const selectedItemId = selectedProductItemIds.get(product.id);
              const added = selectedItemId != null;
              const price = product.current_price != null ? formatCurrency(product.current_price) : "No price";
              const displayImageUrl = productDisplayImageUrl(product);
              return (
                <div
                  key={product.id}
                  className={`rounded-2xl border bg-white p-3 shadow-sm transition-all ${
                    added ? "border-emerald-700 ring-1 ring-emerald-100" : "border-stone-200 hover:border-stone-300"
                  }`}
                >
                  <button type="button" onClick={() => onOpenProduct(product)} className="block w-full text-left">
                    <div className="mb-3 flex h-32 items-center justify-center rounded-xl bg-stone-50">
                      {displayImageUrl && !hasSupplierPlaceholderImage(product) ? (
                        <img src={displayImageUrl} alt={name} className="h-full w-full object-contain" />
                      ) : (
                        <span className="text-xs font-semibold text-stone-400">
                          {hasNoSupplierImage(product) ? "No supplier image" : hasSupplierPlaceholderImage(product) ? "Supplier placeholder" : "Image pending"}
                        </span>
                      )}
                    </div>
                    <p className="line-clamp-2 min-h-[40px] text-sm font-semibold leading-snug text-stone-900">{name || product.name}</p>
                    <p className="mt-1 truncate text-xs text-stone-400">{product.supplier_sku || product.supplier_name}</p>
                    <p className="mt-2 text-sm font-bold text-stone-900">
                      {price} <span className="text-xs font-medium text-stone-400">/ {unitLabel(product.unit)}</span>
                    </p>
                  </button>
                  <button
                    type="button"
                    onClick={(event) => {
                      event.preventDefault();
                      event.stopPropagation();
                      if (added && selectedItemId != null) {
                        onRemove(selectedItemId);
                      } else {
                        onAdd(product);
                      }
                    }}
                    className={`mt-3 flex w-full items-center justify-center gap-2 rounded-xl px-3 py-2 text-sm font-semibold ${
                      added ? "bg-emerald-900 text-white" : "border border-stone-200 bg-white text-stone-800 hover:bg-stone-50"
                    }`}
                  >
                    {added ? <CheckCircle2 size={15} /> : <Plus size={15} />}
                    {added ? "Added" : "Add"}
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="flex items-center justify-between gap-3 border-t border-stone-100 bg-white px-5 py-4">
        <div className="flex items-center gap-4 text-xs text-stone-500">
          <span>{categories.length - 1} filter groups</span>
          <span className="flex items-center gap-1 font-semibold text-emerald-800">
            <CheckCircle2 size={14} />
            {selectedProductIds.size} saved to this part
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setPage((value) => Math.max(1, value - 1))}
            disabled={currentPage <= 1}
            className="rounded-lg border border-stone-200 px-3 py-2 text-xs font-semibold text-stone-700 disabled:opacity-40"
          >
            Prev
          </button>
          <span className="min-w-16 text-center text-xs text-stone-500">{currentPage} / {totalPages}</span>
          <button
            type="button"
            onClick={() => setPage((value) => Math.min(totalPages, value + 1))}
            disabled={currentPage >= totalPages}
            className="rounded-lg border border-stone-200 px-3 py-2 text-xs font-semibold text-stone-700 disabled:opacity-40"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}

export function NewProjectModal({
  onClose,
  onCreated,
  initialClientName = "",
}: {
  onClose: () => void;
  onCreated: (a: Arrangement) => void;
  initialClientName?: string;
}) {
  const [form, setForm] = useState({ name: "", client_name: initialClientName, notes: "" });
  const [saving, setSaving] = useState(false);
  const nameRef = useRef<HTMLInputElement>(null);
  const clientRef = useRef<HTMLInputElement>(null);
  const notesRef = useRef<HTMLTextAreaElement>(null);
  const savingRef = useRef(false);
  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));

  const handleCreate = async () => {
    if (savingRef.current) return;
    const payload = {
      name: (nameRef.current?.value || form.name).trim(),
      client_name: (clientRef.current?.value || form.client_name).trim(),
      notes: (notesRef.current?.value || form.notes).trim(),
    };
    if (!payload.name) {
      toast.error("Project name required");
      return;
    }
    savingRef.current = true;
    setSaving(true);
    try {
      const res = await apiClient.create_arrangement({
        name: payload.name,
        client_name: payload.client_name || undefined,
        notes: payload.notes || undefined,
      });
      const arr = await res.json();
      onCreated(arr as unknown as Arrangement);
      notifyProjectsChanged();
      onClose();
      toast.success("Project created");
    } catch {
      toast.error("Failed to create project");
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/40">
      <div className="mx-4 w-full max-w-md rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-stone-100 px-6 py-4">
          <h2 className="font-semibold text-stone-800" style={{ fontFamily: "Georgia, serif" }}>New Project</h2>
          <button type="button" onClick={onClose} className="text-stone-400 hover:text-stone-600"><X size={18} /></button>
        </div>
        <form onSubmit={(event) => { event.preventDefault(); void handleCreate(); }}>
          <div className="space-y-4 px-6 py-5">
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-stone-600">Project/job name *</span>
              <input ref={nameRef} className="w-full rounded-lg border border-stone-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300" value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="e.g. Bookshelf" />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-stone-600">Person / client</span>
              <input ref={clientRef} className="w-full rounded-lg border border-stone-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300" value={form.client_name} onChange={(e) => set("client_name", e.target.value)} placeholder="e.g. Joe Smith" />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-stone-600">Notes</span>
              <textarea ref={notesRef} rows={3} className="w-full resize-none rounded-lg border border-stone-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300" value={form.notes} onChange={(e) => set("notes", e.target.value)} placeholder="Design goals, dimensions, preferences..." />
            </label>
          </div>
          <div className="flex items-center justify-end gap-3 border-t border-stone-100 px-6 py-4">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-stone-500 hover:text-stone-700">Cancel</button>
            <button
              type="button"
              onClick={() => void handleCreate()}
              disabled={saving}
              className="rounded-lg px-5 py-2 text-sm font-semibold text-white disabled:opacity-60 hover:opacity-90"
              style={{ backgroundColor: "#2d5a33" }}
            >
              {saving ? "Creating..." : "Create project"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function Arrangements() {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedId = searchParams.get("id") ? Number(searchParams.get("id")) : null;
  const clientFilter = searchParams.get("client") || "";
  const isClientPath = location.pathname.includes("/clients/project");
  const cachedProjectsList = useMemo(() => readProjectsListCache(), []);

  const [arrangements, setArrangements] = useState<ArrangementSummary[]>(() => cachedProjectsList?.arrangements || []);
  const [arrangement, setArrangement] = useState<Arrangement | null>(null);
  const [products, setProducts] = useState<LibraryProduct[]>([]);
  const [detailProduct, setDetailProduct] = useState<LibraryProduct | null>(null);
  const [activeRoomId, setActiveRoomId] = useState<number | null>(null);
  const [newRoomName, setNewRoomName] = useState("");
  const [newRoomNotes, setNewRoomNotes] = useState("");
  const [activeBucketId, setActiveBucketId] = useState<number | null>(null);
  const [creatingBuiltProduct, setCreatingBuiltProduct] = useState(false);
  const [newScopeName, setNewScopeName] = useState("Tree");
  const [newScopeQuantity, setNewScopeQuantity] = useState("1");
  const [newScopeNotes, setNewScopeNotes] = useState("");
  const [selectedScopeType, setSelectedScopeType] = useState("Tree");
  const [selectedProductSection, setSelectedProductSection] = useState<BuilderSection>("green");
  const [buildTypes, setBuildTypes] = useState<BuildTypeOption[]>([]);
  const [buildSuggestion, setBuildSuggestion] = useState<BuildSuggestion | null>(null);
  const [suggestionLoading, setSuggestionLoading] = useState(false);
  const [finishedSku, setFinishedSku] = useState("");
  const [skuEdited, setSkuEdited] = useState(false);
  const [productTypeSearch, setProductTypeSearch] = useState("");
  const [showAllProductTypes, setShowAllProductTypes] = useState(false);
  const [previewType, setPreviewType] = useState<string | null>(null);
  const [previewSuggestions, setPreviewSuggestions] = useState<Record<string, BuildSuggestion>>({});
  const [previewLoadingType, setPreviewLoadingType] = useState<string | null>(null);
  const [newCustomSectionName, setNewCustomSectionName] = useState("");
  const [loading, setLoading] = useState(() => !cachedProjectsList);
  const [listSettled, setListSettled] = useState(() => Boolean(cachedProjectsList));
  const [listRefreshing, setListRefreshing] = useState(() => Boolean(cachedProjectsList));
  const [listCachedAt, setListCachedAt] = useState<number | null>(() => cachedProjectsList?.cachedAt || null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [projectHydrating, setProjectHydrating] = useState(false);
  const [productsLoading, setProductsLoading] = useState(false);
  const [productsLoaded, setProductsLoaded] = useState(false);
  const [productCatalogTotal, setProductCatalogTotal] = useState<number | null>(null);
  const [savingRoom, setSavingRoom] = useState(false);
  const [savingBucket, setSavingBucket] = useState(false);
  const [showNewModal, setShowNewModal] = useState(false);
  const [editingName, setEditingName] = useState(false);
  const [nameEdit, setNameEdit] = useState("");
  const [editingRoom, setEditingRoom] = useState(false);
  const [roomNameEdit, setRoomNameEdit] = useState("");
  const [roomNotesEdit, setRoomNotesEdit] = useState("");
  const [builderStep, setBuilderStep] = useState<"type" | "products" | "mockup" | "review" | "po">("type");
  const [activePart, setActivePart] = useState<{ label: string; index: number } | null>(null);
  const [selectedChristmasTreeCode, setSelectedChristmasTreeCode] = useState("");
  const [treeHeight, setTreeHeight] = useState("");
  const [treeCanopySize, setTreeCanopySize] = useState("");
  const [treeDensity, setTreeDensity] = useState("");
  const [christmasEnhancerPackage, setChristmasEnhancerPackage] = useState<ChristmasEnhancerPackage>("regular");
  const [garlandPackage, setGarlandPackage] = useState<GarlandPackage>("regular");
  const [garlandLength, setGarlandLength] = useState("9");
  const [garlandDiameter, setGarlandDiameter] = useState<GarlandDiameter>("14");
  const [wreathSize, setWreathSize] = useState<WreathSize>("24");
  const builderTopRef = useRef<HTMLDivElement>(null);
  const catalogRef = useRef<HTMLDivElement>(null);
  const previewPartsRef = useRef<HTMLDivElement>(null);
  const scopeNameRef = useRef<HTMLInputElement>(null);
  const scopeQuantityRef = useRef<HTMLInputElement>(null);
  const scopeNotesRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (searchParams.get("new") !== "1") return;
    setShowNewModal(true);
    const next = new URLSearchParams(searchParams);
    next.delete("new");
    setSearchParams(next);
  }, [searchParams, setSearchParams]);

  const filteredArrangements = useMemo(() => {
    if (!clientFilter) return arrangements;
    return arrangements.filter((a) => (a.client_name || "Unassigned") === clientFilter);
  }, [arrangements, clientFilter]);

  const projectRooms = arrangement?.rooms || [];
  const roomContainers = activeRoomId ? (arrangement?.containers || []).filter((c) => c.room_id === activeRoomId) : [];
  const activeRoom = projectRooms.find((room) => room.id === activeRoomId) || null;
  const projectRoomsLoading = Boolean(
    selectedId && projectRooms.length === 0 && (projectHydrating || arrangement?.name === "Opening project...")
  );
  const activeBucket = roomContainers.find((c) => c.id === activeBucketId) || null;
  const orderItems = activeBucket?.items || [];
  const orderSubtotal = orderItems.reduce((sum, item) => {
    const quantity = Number(item.quantity) || 1;
    const price = Number(item.current_price) || 0;
    return sum + quantity * price;
  }, 0);
  const activeParts = activeBucket ? scopePlaceholders(activeBucket) : [];
  const partsComplete = activeBucket
    ? activeParts.filter((label, index) => partIsComplete(activeBucket, label, index)).length
    : 0;
  const builderSteps = ["type", "products", "mockup", "review", "po"] as const;
  const productTypeOptions = useMemo(() => {
    const canonical = BUILD_TYPE_CONFIGS
      .filter((config) => config.section === selectedProductSection)
      .map((config) => ({
        label: config.label,
        icon: config.icon,
        evidence_count: evidenceForConfig(config, buildTypes),
        prefixes: [...config.prefixes],
      }));
    return [...canonical, { label: "Custom", icon: Plus, evidence_count: undefined, prefixes: [] }];
  }, [buildTypes, selectedProductSection]);
  const historicalProductTypeCount = productTypeOptions.filter((option) => option.label !== "Custom").length;
  const filteredProductTypeOptions = useMemo(() => {
    const query = productTypeSearch.trim().toLowerCase();
    const historical = productTypeOptions.filter((option) => option.label !== "Custom");
    const custom = productTypeOptions.find((option) => option.label === "Custom");
    const matching = historical.filter((option) => {
      if (!query) return true;
      return [
        option.label,
        ...(option.prefixes || []),
        String(option.evidence_count || ""),
      ].some((value) => value.toLowerCase().includes(query));
    });
    const visible = matching;
    return custom ? [...visible, custom] : visible;
  }, [productTypeOptions, productTypeSearch]);
  const visibleHistoricalProductTypeCount = filteredProductTypeOptions.filter((option) => option.label !== "Custom").length;
  const hiddenProductTypeCount = Math.max(0, historicalProductTypeCount - visibleHistoricalProductTypeCount);
  const activePreviewType = (previewType || (selectedScopeType === "Custom" ? newScopeName.trim() || "Custom" : selectedScopeType)).trim();
  const activePreviewKey = activePreviewType.toLowerCase();
  const activePreviewSuggestion = previewSuggestions[activePreviewKey] || (
    buildSuggestion?.build_type.toLowerCase() === activePreviewKey ? buildSuggestion : null
  );
  const activePreviewDesignParts = designPartsForBuildType(activePreviewType);
  const activePreviewComponents = (
    activePreviewDesignParts
      ? activePreviewDesignParts
      : activePreviewSuggestion?.components?.slice(0, 6) || fallbackSectionsForBuildType(activePreviewType)
  ).map((component) => (
    typeof component === "string"
      ? { label: component, suggested_quantity: 1, evidence_count: 0 }
      : component
  ));
  const activePreviewLoading = !activePreviewDesignParts && previewLoadingType?.toLowerCase() === activePreviewKey && !activePreviewSuggestion;
  const activeDraftSku = activeBucket ? suggestedFinishedSku(activeBucket, arrangement) : suggestedSkuForType(selectedScopeType, newScopeName, arrangement, selectedProductSection);
  const activeMechanicsEstimate = mechanicsEstimate(activeBucket);
  const activeBasePartCount = activeBucket ? baseScopePlaceholders(activeBucket).length : 0;
  const activeChristmasTreeOption = CHRISTMAS_TREE_SIZE_OPTIONS.find((option) => option.code === selectedChristmasTreeCode) || null;
  const activeChristmasTreeRule = selectedScopeType === "Christmas Tree" ? christmasTreeDecorRule(treeHeight, treeCanopySize) : null;
  const activeGarlandRule = selectedScopeType === "Garland" ? garlandEnhancerRule(garlandPackage, garlandLength) : null;
  const activeWreathParts = selectedScopeType === "Wreath" ? wreathDecorPartsForSize(wreathSize) : [];
  const selectedBuildTypeLabel = (selectedScopeType === "Custom" ? newScopeName.trim() || "Custom" : selectedScopeType).trim();

  useEffect(() => {
    previewPartsRef.current?.scrollTo({ top: 0 });
  }, [activePreviewKey]);

  useEffect(() => {
    const sectionLabels = BUILD_TYPE_CONFIGS.filter((config) => config.section === selectedProductSection).map((config) => config.label);
    if (selectedScopeType !== "Custom" && !(sectionLabels as string[]).includes(selectedScopeType)) {
      const nextType = sectionLabels[0] || "Custom";
      setSelectedScopeType(nextType);
      setNewScopeName(nextType);
      setPreviewType(nextType);
      setBuildSuggestion(null);
    }
    setProductTypeSearch("");
  }, [selectedProductSection, selectedScopeType]);

  useEffect(() => {
    if (!skuEdited) setFinishedSku(activeDraftSku);
  }, [activeDraftSku, skuEdited]);
  const goToBuilderStep = (step: typeof builderSteps[number]) => {
    setBuilderStep(step);
    window.requestAnimationFrame(() => {
      const target = builderTopRef.current;
      if (target) {
        target.scrollIntoView({ behavior: "smooth", block: "start" });
        return;
      }
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  };

  const fetchSuggestionForType = async (
    buildType: string,
    options?: { setActive?: boolean; quiet?: boolean }
  ): Promise<BuildSuggestion | null> => {
    const normalizedType = buildType.trim();
    if (!normalizedType || normalizedType === "Custom") return null;
    const cacheKey = normalizedType.toLowerCase();
    const cached = previewSuggestions[cacheKey];
    if (cached) {
      if (options?.setActive) setBuildSuggestion(cached);
      return cached;
    }
    setPreviewLoadingType(normalizedType);
    try {
      const response = await apiClient.request({
        path: "/routes/recipe-intelligence/suggest",
        method: "POST",
        body: {
          build_type: normalizedType,
          height: treeHeight || undefined,
          width: treeCanopySize || undefined,
          depth: treeDensity || undefined,
          quantity: Math.max(1, Number(newScopeQuantity) || 1),
          notes: newScopeNotes || undefined,
        },
        type: ContentType.Json,
      });
      if (!response.ok) throw new Error("Suggestion failed");
      const data = await response.json();
      setPreviewSuggestions((prev) => ({ ...prev, [cacheKey]: data }));
      if (options?.setActive) setBuildSuggestion(data);
      return data;
    } catch {
      if (!options?.quiet) toast.error("Could not load smart suggestion");
      return null;
    } finally {
      setPreviewLoadingType((current) => current === normalizedType ? null : current);
    }
  };

  const previewProductType = (label: string) => {
    setPreviewType(label);
    if (label !== "Custom") void fetchSuggestionForType(label, { quiet: true });
  };

  const resetProductTypePreview = () => {
    const selectedPreview = selectedScopeType === "Custom" ? newScopeName.trim() || "Custom" : selectedScopeType;
    setPreviewType(selectedPreview);
  };

  const selectChristmasTreeOption = (code: string) => {
    setSelectedChristmasTreeCode(code);
    const option = CHRISTMAS_TREE_SIZE_OPTIONS.find((tree) => tree.code === code);
    if (!option) return;
    setTreeHeight(`${option.heightFeet} ft`);
    setTreeCanopySize(`${option.diameterIn} in`);
    setTreeDensity(option.profile);
  };

  const syncBuilderSelectionFromBucket = (bucket: Container) => {
    const config = buildTypeConfigFor(`${bucket.bucket_type || ""} ${bucket.label || ""}`);
    const nextType = config?.label || bucket.bucket_type || scopeTitle(bucket);
    setSelectedProductSection(config?.section || "green");
    setSelectedScopeType(config ? config.label : "Custom");
    setNewScopeName(nextType);
    setPreviewType(nextType);
    setBuildSuggestion(parseScopeIntelligence(bucket.scope_notes));
    setSelectedChristmasTreeCode("");
    setTreeHeight(scopeNoteValue(bucket.scope_notes, "Height"));
    setTreeCanopySize(scopeNoteValue(bucket.scope_notes, "Width / canopy"));
    setTreeDensity(scopeNoteValue(bucket.scope_notes, "Depth / density"));
    setChristmasEnhancerPackage(christmasEnhancerPackageFromNotes(bucket.scope_notes));
    setGarlandPackage(garlandPackageFromNotes(bucket.scope_notes));
    setGarlandLength(garlandLengthFromNotes(bucket.scope_notes));
    setGarlandDiameter(garlandDiameterFromNotes(bucket.scope_notes));
    setWreathSize(wreathSizeFromNotes(bucket.scope_notes));
    const treeType = scopeNoteValue(bucket.scope_notes, "Tree type");
    if (treeType) {
      const matchedTree = CHRISTMAS_TREE_SIZE_OPTIONS.find((option) => treeType.includes(option.code));
      if (matchedTree) setSelectedChristmasTreeCode(matchedTree.code);
    }
    if (scopeNameRef.current) scopeNameRef.current.value = nextType;
  };

  const requestBuildSuggestion = async (): Promise<BuildSuggestion | null> => {
    const buildType = selectedScopeType === "Custom" ? newScopeName.trim() : selectedScopeType;
    if (!buildType) return null;
    setSuggestionLoading(true);
    try {
      return await fetchSuggestionForType(buildType, { setActive: true });
    } catch {
      toast.error("Could not load smart suggestion");
      return null;
    } finally {
      setSuggestionLoading(false);
    }
  };

  const applySelectedTypeToActiveBucket = async (nextTypeValue?: string): Promise<Container | null> => {
    if (!arrangement || !activeBucket) return activeBucket;
    const nextType = (nextTypeValue || selectedBuildTypeLabel).trim();
    if (!nextType || nextType === "Custom") return activeBucket;

    const currentType = activeBucket.bucket_type || scopeTitle(activeBucket);
    const currentTitle = scopeTitle(activeBucket);
    const sameType = normalizeLabel(currentType) === normalizeLabel(nextType);
    if (sameType) return activeBucket;
    const currentTitleIsType = BUILD_TYPE_CONFIGS.some((config) => normalizeLabel(config.label) === normalizeLabel(currentTitle));
    const nextLabel = currentTitleIsType || normalizeLabel(currentTitle) === normalizeLabel(currentType) ? nextType : currentTitle;

    const nextParts = designPartsForBuildType(nextType) || fallbackSectionsForBuildType(nextType);
    const nextActivePart = { label: nextParts[0] || "Products", index: 0 };
    const suggestion = await fetchSuggestionForType(nextType, { setActive: true, quiet: true });
    const customSections = parseCustomSections(activeBucket.scope_notes);
    const setupNotes = [
      newScopeNotes.trim() || editableScopeNotes(activeBucket.scope_notes),
      nextType === "Christmas Tree" && activeChristmasTreeOption ? `Tree type: ${activeChristmasTreeOption.code} - ${activeChristmasTreeOption.label}` : "",
      nextType === "Christmas Tree" ? `Enhancer package: ${christmasEnhancerPackage === "premium" ? "Premium" : "Regular"}` : "",
      ...(nextType === "Garland" ? garlandSetupLines(garlandPackage, garlandLength, garlandDiameter) : []),
      ...(nextType === "Wreath" ? wreathSetupLines(wreathSize) : []),
      !["Garland", "Wreath"].includes(nextType) && treeHeight.trim() ? `Height: ${treeHeight.trim()}` : "",
      !["Garland", "Wreath"].includes(nextType) && treeCanopySize.trim() ? `Width / canopy: ${treeCanopySize.trim()}` : "",
      !["Garland", "Wreath"].includes(nextType) && treeDensity.trim() ? `Depth / density: ${treeDensity.trim()}` : "",
      suggestion ? `${INTELLIGENCE_NOTE_PREFIX}${JSON.stringify(suggestion)}` : scopeIntelligenceLine(activeBucket.scope_notes),
      customSections.length ? `${CUSTOM_SECTIONS_PREFIX}${JSON.stringify(customSections)}` : "",
    ].filter(Boolean).join("\n");

    const optimisticBucket = {
      ...activeBucket,
      label: nextLabel,
      bucket_type: nextType,
      scope_notes: setupNotes || undefined,
    };
    setArrangement((current) => {
      if (!current) return current;
      return {
        ...current,
        containers: current.containers.map((bucket) => bucket.id === activeBucket.id ? optimisticBucket : bucket),
      };
    });
    setActivePart(nextActivePart);
    setSkuEdited(false);

    try {
      const res = await apiClient.request<Arrangement>({
        path: `/routes/arrangements/container/update/${activeBucket.id}`,
        method: "PUT",
        body: { label: nextLabel, bucket_type: nextType, scope_notes: setupNotes || null },
        type: ContentType.Json,
      });
      if (!res.ok) throw new Error(await res.text().catch(() => "Failed to update build type"));
      const updated = await res.json() as unknown as Arrangement;
      const updatedBucket = updated.containers.find((bucket) => bucket.id === activeBucket.id) || optimisticBucket;
      setArrangement(updated);
      setActivePart({ label: scopePlaceholders(updatedBucket)[0] || "Products", index: 0 });
      notifyProjectsChanged();
      return updatedBucket;
    } catch {
      toast.error("Could not update the selected build type");
      void loadDetail(arrangement.id, { silent: true });
      return activeBucket;
    }
  };

  const loadList = async () => {
    if (arrangements.length === 0) setLoading(true);
    else setListRefreshing(true);
    try {
      const response = await apiClient.list_arrangements();
      if (!response.ok) throw new Error("Failed to load projects");
      const data = await response.json();
      const rows = (Array.isArray(data) ? data : []) as unknown as ArrangementSummary[];
      setArrangements(rows);
      writeProjectsListCache(rows);
      setListCachedAt(Date.now());
      setListSettled(true);
    } catch {
      if (arrangements.length === 0) toast.error("Failed to load projects");
    } finally {
      setLoading(false);
      setListRefreshing(false);
    }
  };

  const loadProducts = async () => {
    if (productsLoading) return;
    if (productsLoaded && (!productCatalogTotal || products.length >= productCatalogTotal)) return;
    const cachedCatalog = readLibraryProductCache();
    const cachedProducts = cachedCatalog.products;
    if (cachedCatalog.productTotal) setProductCatalogTotal(cachedCatalog.productTotal);
    if (cachedProducts.length > 0 && products.length === 0) {
      setProducts(cachedProducts);
    }
    setProductsLoading(true);
    try {
      const fetchProductPage = async (offset: number) => {
        const pageResponse = await apiClient.request<ProductPage>({
          path: "/routes/products/page",
          method: "GET",
          query: {
            favorites_only: false,
            limit: BUILDER_PRODUCT_PAGE_SIZE,
            offset,
          },
        });
        if (!pageResponse.ok) throw new Error("Failed to load product library page");
        return pageResponse.json();
      };

      const firstPage = await fetchProductPage(0);
      const firstItems = Array.isArray(firstPage.items) ? firstPage.items : [];
      const total = Number(firstPage.total) || firstItems.length;
      const pageLimit = Number(firstPage.limit) || BUILDER_PRODUCT_PAGE_SIZE;
      setProductCatalogTotal(total);
      if (firstItems.length > cachedProducts.length || products.length === 0) {
        setProducts(firstItems);
      }

      const offsets: number[] = [];
      for (let offset = pageLimit; offset < total; offset += pageLimit) {
        offsets.push(offset);
      }

      const allProducts: LibraryProduct[] = [...firstItems];
      for (let index = 0; index < offsets.length; index += BUILDER_PRODUCT_CONCURRENT_PAGE_LIMIT) {
        const batch = offsets.slice(index, index + BUILDER_PRODUCT_CONCURRENT_PAGE_LIMIT);
        const pages = await Promise.all(batch.map((offset) => fetchProductPage(offset)));
        for (const page of pages) {
          if (Array.isArray(page.items)) allProducts.push(...page.items);
        }
      }

      const uniqueProducts = allProducts.filter((product, index, list) => list.findIndex((item) => item.id === product.id) === index);
      if (uniqueProducts.length > 0) {
        setProducts(uniqueProducts);
        setProductsLoaded(uniqueProducts.length >= total);
        writeLibraryProductCache(uniqueProducts, total);
      } else {
        const response = await apiClient.list_products({ favorites_only: false });
        if (!response.ok) throw new Error("Failed to load product library");
        const data = await response.json();
        const products = (Array.isArray(data) ? data : []) as unknown as LibraryProduct[];
        setProducts(products);
        setProductCatalogTotal(products.length);
        setProductsLoaded(true);
        writeLibraryProductCache(products, products.length);
      }
    } catch {
      if (cachedProducts.length > 0) {
        setProducts(cachedProducts);
        setProductsLoaded(false);
        if (!products.length) toast.error("Showing cached products while the full catalog loads. Try again in a moment.");
      } else {
        toast.error("Failed to load product library");
      }
    } finally {
      setProductsLoading(false);
    }
  };

  const loadBuildTypes = async () => {
    try {
      const response = await apiClient.request({ path: "/routes/recipe-intelligence/build-types", method: "GET" });
      if (!response.ok) return;
      const data = await response.json();
      if (Array.isArray(data) && data.length > 0) {
        setBuildTypes(data);
      }
    } catch {
      // The builder works with fallback product types before intelligence import runs.
    }
  };

  const loadDetail = async (id: number, options?: { silent?: boolean }) => {
    setProjectHydrating(true);
    if (!options?.silent) setDetailLoading(true);
    try {
      let data: Arrangement | null = null;
      let lastError: unknown = null;
      for (let attempt = 0; attempt < 3; attempt += 1) {
        try {
          data = await withTimeout(
            apiClient.get_arrangement({ arrangementId: id }).then((r) => {
              if (!r.ok) throw new Error("Failed to load project");
              return r.json() as Promise<Arrangement>;
            }),
            25000
          );
          break;
        } catch (error) {
          lastError = error;
          if (attempt < 2) await delay(600);
        }
      }
      if (!data) throw lastError || new Error("Failed to load project");
      setArrangement(data);
      setActiveBucketId((current) => {
        if (!activeRoomId) return null;
        const roomBuckets = data.containers.filter((c: Container) => c.room_id === activeRoomId);
        if (current && roomBuckets.some((c: Container) => c.id === current)) return current;
        return null;
      });
    } catch {
      const summary = arrangements.find((a) => a.id === id);
      if (arrangement?.id === id) {
        if (!options?.silent) toast.error("Project is still loading. Keeping the current view.");
        return;
      }
      if (summary && !arrangement) {
        setArrangement({
          id: summary.id,
          name: summary.name,
          client_name: summary.client_name,
          notes: "",
          created_by: "",
          created_at: summary.created_at,
          updated_at: summary.updated_at,
          rooms: [],
          containers: [],
          total_cost: summary.total_cost || 0,
          total_with_markup: summary.total_cost || 0,
        });
      }
      if (!options?.silent) toast.error("Project is taking too long to load. Try again.");
    } finally {
      setProjectHydrating(false);
      if (!options?.silent) setDetailLoading(false);
    }
  };

  useEffect(() => { loadList(); void loadBuildTypes(); }, []);
  useEffect(() => {
    if (selectedId) {
      const summary = arrangements.find((a) => a.id === selectedId);
      setArrangement((current) => {
        if (current?.id === selectedId) return current;
        return summary ? arrangementShellFromSummary(summary) : arrangementRouteShell(selectedId, clientFilter);
      });
      void loadDetail(selectedId, { silent: true });
    } else {
      setArrangement(null);
      setActiveRoomId(null);
      setActiveBucketId(null);
    }
  }, [selectedId]);

  useEffect(() => {
    if (selectedId && arrangement?.id === selectedId && arrangement.name === "Opening project..." && arrangements.length > 0) {
      const summary = arrangements.find((a) => a.id === selectedId);
      if (summary) setArrangement(arrangementShellFromSummary(summary));
    }
    if (selectedId && !arrangement && arrangements.length > 0 && !detailLoading) {
      void loadDetail(selectedId, { silent: true });
    }
  }, [arrangements.length, selectedId, arrangement?.id, arrangement?.name, detailLoading]);

  useEffect(() => {
    if (!activeBucket) {
      setActivePart(null);
      setFinishedSku("");
      setSkuEdited(false);
      return;
    }
    setActivePart((current) => current || { label: scopePlaceholders(activeBucket)[0] || "Products", index: 0 });
    setSkuEdited(false);
  }, [activeBucket?.id]);

  useEffect(() => {
    setBuildSuggestion(null);
  }, [selectedScopeType]);

  const enterProductPicker = () => {
    void loadProducts();
    goToBuilderStep("products");
  };

  const selectProject = (id: number) => setSearchParams(clientFilter ? { client: clientFilter, id: String(id) } : { id: String(id) });
  const clearSelection = () => {
    if (isClientPath) {
      navigate(clientFilter ? `/clients?client=${encodeURIComponent(clientFilter)}` : "/clients");
      return;
    }
    setSearchParams(clientFilter ? { client: clientFilter } : {});
  };
  const showAllProjects = () => setSearchParams({});
  const showClientProjects = () => setSearchParams({ client: clientFilter });
  const openRoom = (roomId: number) => {
    setActiveRoomId(roomId);
    setActiveBucketId(null);
    setActivePart(null);
    setEditingRoom(false);
    setCreatingBuiltProduct(false);
    goToBuilderStep("type");
  };
  const closeRoom = () => {
    setActiveRoomId(null);
    setActiveBucketId(null);
    setActivePart(null);
    setEditingRoom(false);
    setCreatingBuiltProduct(false);
    goToBuilderStep("type");
  };
  const openBucketCatalog = (bucketId: number, part?: { label: string; index: number }) => {
    setActiveBucketId(bucketId);
    setCreatingBuiltProduct(false);
    setActivePart(part || null);
    enterProductPicker();
  };
  const openBuiltProduct = (bucket: Container) => {
    syncBuilderSelectionFromBucket(bucket);
    setActiveBucketId(bucket.id);
    setCreatingBuiltProduct(false);
    setActivePart({ label: scopePlaceholders(bucket)[0] || "Products", index: 0 });
    enterProductPicker();
  };
  const startNewBuiltProduct = () => {
    setActiveBucketId(null);
    setActivePart(null);
    setCreatingBuiltProduct(true);
    goToBuilderStep("type");
  };
  const goBackBuilderStep = () => {
    const currentIndex = builderSteps.indexOf(builderStep);
    if (currentIndex > 0) {
      goToBuilderStep(builderSteps[currentIndex - 1]);
      return;
    }
    backToBuiltProducts();
  };
  const backToBuiltProducts = () => {
    setActiveBucketId(null);
    setActivePart(null);
    setCreatingBuiltProduct(false);
    goToBuilderStep("type");
  };

  const addRoom = async () => {
    const name = newRoomName.trim();
    if (!arrangement || !name || savingRoom) return;
    setSavingRoom(true);
    try {
      const res = await apiClient.request<Arrangement>({
        path: `/routes/arrangements/room/add/${arrangement.id}`,
        method: "POST",
        body: { name, notes: newRoomNotes.trim() || undefined },
        type: ContentType.Json,
      });
      if (!res.ok) throw new Error(await res.text().catch(() => "Failed to add room/design package"));
      const updated = await res.json() as unknown as Arrangement;
      setArrangement(updated);
      const rooms = Array.isArray(updated?.rooms) ? updated.rooms : [];
      const createdRoom = rooms.find((room: ProjectRoom) => room.name.trim().toLowerCase() === name.toLowerCase());
      if (!createdRoom) {
        await loadDetail(arrangement.id, { silent: true });
      }
      setNewRoomName("");
      setNewRoomNotes("");
      notifyProjectsChanged();
      toast.success("Room/design package added");
    } catch (error) {
      const message = error instanceof Error && error.message ? error.message : "Failed to add room/design package";
      toast.error(message.includes("Failed") ? message : "Failed to add room/design package");
    } finally {
      setSavingRoom(false);
    }
  };

  const startRoomEdit = () => {
    if (!activeRoom) return;
    setRoomNameEdit(activeRoom.name || "");
    setRoomNotesEdit(activeRoom.notes || "");
    setEditingRoom(true);
  };

  const cancelRoomEdit = () => {
    setEditingRoom(false);
    setRoomNameEdit("");
    setRoomNotesEdit("");
  };

  const saveRoomEdit = async () => {
    if (!arrangement || !activeRoom) return;
    const name = roomNameEdit.trim();
    if (!name) {
      toast.error("Add a design package name first");
      return;
    }
    try {
      const res = await apiClient.request<Arrangement>({
        path: `/routes/arrangements/room/update/${activeRoom.id}`,
        method: "PUT",
        body: { name, notes: roomNotesEdit.trim() || null },
        type: ContentType.Json,
      });
      if (!res.ok) throw new Error(await res.text().catch(() => "Failed to update design package"));
      const updated = await res.json();
      setArrangement(updated);
      setEditingRoom(false);
      notifyProjectsChanged();
      toast.success("Design package updated");
    } catch {
      toast.error("Failed to update design package");
    }
  };

  const removeRoom = async (roomId: number) => {
    if (!arrangement || !confirm("Delete this room/design package? Existing scopes will stay with the project but will no longer be assigned to this room.")) return;
    try {
      const res = await apiClient.request({ path: `/routes/arrangements/room/delete/${roomId}`, method: "DELETE" });
      if (!res.ok) throw new Error("Failed");
      if (activeRoomId === roomId) closeRoom();
      await loadDetail(arrangement.id, { silent: true });
      notifyProjectsChanged();
      toast.success("Room/design package deleted");
    } catch {
      toast.error("Failed to delete room/design package");
    }
  };

  const deleteProject = async (id: number) => {
    if (!confirm("Delete this project?")) return;
    try {
      await apiClient.delete_arrangement({ arrangementId: id });
      setArrangements((prev) => {
        const next = prev.filter((a) => a.id !== id);
        writeProjectsListCache(next);
        return next;
      });
      if (selectedId === id) clearSelection();
      notifyProjectsChanged();
      toast.success("Project deleted");
    } catch {
      toast.error("Failed to delete project");
    }
  };

  const addBucket = async () => {
    const scopeName = (scopeNameRef.current?.value || newScopeName).trim();
    const quantityValue = scopeQuantityRef.current?.value || newScopeQuantity;
    const notesValue = scopeNotesRef.current?.value || newScopeNotes;
    if (!arrangement || !scopeName) return;
    setSavingBucket(true);
    try {
      const suggestion = buildSuggestion || await requestBuildSuggestion();
      const setupNotes = [
        notesValue.trim(),
        selectedScopeType === "Christmas Tree" && activeChristmasTreeOption ? `Tree type: ${activeChristmasTreeOption.code} - ${activeChristmasTreeOption.label}` : "",
        selectedScopeType === "Christmas Tree" ? `Enhancer package: ${christmasEnhancerPackage === "premium" ? "Premium" : "Regular"}` : "",
        ...(selectedScopeType === "Garland" ? garlandSetupLines(garlandPackage, garlandLength, garlandDiameter) : []),
        ...(selectedScopeType === "Wreath" ? wreathSetupLines(wreathSize) : []),
        !["Garland", "Wreath"].includes(selectedScopeType) && treeHeight.trim() ? `Height: ${treeHeight.trim()}` : "",
        !["Garland", "Wreath"].includes(selectedScopeType) && treeCanopySize.trim() ? `Width / canopy: ${treeCanopySize.trim()}` : "",
        !["Garland", "Wreath"].includes(selectedScopeType) && treeDensity.trim() ? `Depth / density: ${treeDensity.trim()}` : "",
        suggestion ? `${INTELLIGENCE_NOTE_PREFIX}${JSON.stringify(suggestion)}` : "",
      ].filter(Boolean).join("\n");
      const res = await apiClient.add_container(
        { arrangementId: arrangement.id },
        {
          label: scopeName,
          room_id: activeRoomId,
          bucket_type: selectedScopeType === "Custom" ? scopeName : selectedScopeType,
          requested_quantity: Math.max(1, Number(quantityValue) || 1),
          scope_notes: setupNotes || undefined,
          items: [],
        } as any
      );
      if (!res.ok) {
        const message = await res.text().catch(() => "");
        throw new Error(message || "Failed to add scope");
      }
      const updated = await res.json() as unknown as Arrangement;
      if (!updated?.containers || !Array.isArray(updated.containers)) {
        throw new Error("Scope response was incomplete");
      }
      setArrangement(updated);
      const createdBucket = updated.containers[updated.containers.length - 1] || null;
      setCreatingBuiltProduct(false);
      setActiveBucketId(createdBucket?.id ?? null);
      if (createdBucket) {
        setActivePart({ label: scopePlaceholders(createdBucket)[0] || "Products", index: 0 });
        enterProductPicker();
      }
      setNewScopeName(selectedScopeType === "Custom" ? "" : selectedScopeType);
      setNewScopeQuantity("1");
      setNewScopeNotes("");
      setBuildSuggestion(null);
      setSelectedChristmasTreeCode("");
      setChristmasEnhancerPackage("regular");
      setGarlandPackage("regular");
      setGarlandLength("9");
      setGarlandDiameter("14");
      setWreathSize("24");
      setTreeHeight("");
      setTreeCanopySize("");
      setTreeDensity("");
      if (scopeNameRef.current) scopeNameRef.current.value = selectedScopeType === "Custom" ? "" : selectedScopeType;
      if (scopeQuantityRef.current) scopeQuantityRef.current.value = "1";
      if (scopeNotesRef.current) scopeNotesRef.current.value = "";
      notifyProjectsChanged();
      toast.success("Scope added");
    } catch (error) {
      console.error("Failed to add scope", error);
      toast.error("Failed to add scope");
    } finally {
      setSavingBucket(false);
    }
  };

  const goToProductParts = async () => {
    if (activeBucket) {
      const updatedBucket = await applySelectedTypeToActiveBucket();
      if (!updatedBucket) return;
      setActivePart({ label: scopePlaceholders(updatedBucket)[0] || "Products", index: 0 });
      enterProductPicker();
      return;
    }
    await addBucket();
  };

  const removeBucket = async (containerId: number) => {
    if (!arrangement) return;
    try {
      await apiClient.remove_container({ containerId });
      if (activeBucketId === containerId) backToBuiltProducts();
      await loadDetail(arrangement.id, { silent: true });
      notifyProjectsChanged();
      toast.success("Scope removed");
    } catch {
      toast.error("Failed to remove scope");
    }
  };

  const updateChristmasEnhancerPackage = async (packageType: ChristmasEnhancerPackage) => {
    setChristmasEnhancerPackage(packageType);
    if (!arrangement || !activeBucket || !isChristmasTreeBucket(activeBucket)) return;

    const nextNotes = scopeNotesWithEnhancerPackage(activeBucket, packageType);
    const optimisticBucket = { ...activeBucket, scope_notes: nextNotes || undefined };
    setArrangement((current) => {
      if (!current) return current;
      return {
        ...current,
        containers: current.containers.map((bucket) => bucket.id === activeBucket.id ? optimisticBucket : bucket),
      };
    });

    try {
      const res = await apiClient.request<Arrangement>({
        path: `/routes/arrangements/container/update/${activeBucket.id}`,
        method: "PUT",
        body: { scope_notes: nextNotes || null },
        type: ContentType.Json,
      });
      if (!res.ok) throw new Error(await res.text().catch(() => "Failed to update enhancer package"));
      const updated = await res.json();
      setArrangement(updated);
      notifyProjectsChanged();
    } catch {
      toast.error("Could not update enhancer package");
      void loadDetail(arrangement.id, { silent: true });
    }
  };

  const updateGarlandSetup = async (setup: Partial<{ packageType: GarlandPackage; lengthValue: string; diameter: GarlandDiameter }>) => {
    const nextSetup = {
      packageType: setup.packageType || garlandPackage,
      lengthValue: setup.lengthValue || garlandLength,
      diameter: setup.diameter || garlandDiameter,
    };
    setGarlandPackage(nextSetup.packageType);
    setGarlandLength(nextSetup.lengthValue);
    setGarlandDiameter(nextSetup.diameter);
    if (!arrangement || !activeBucket || !isGarlandBucket(activeBucket)) return;

    const nextNotes = scopeNotesWithGarlandSetup(activeBucket, nextSetup);
    const optimisticBucket = { ...activeBucket, scope_notes: nextNotes || undefined };
    setArrangement((current) => {
      if (!current) return current;
      return {
        ...current,
        containers: current.containers.map((bucket) => bucket.id === activeBucket.id ? optimisticBucket : bucket),
      };
    });

    try {
      const res = await apiClient.request<Arrangement>({
        path: `/routes/arrangements/container/update/${activeBucket.id}`,
        method: "PUT",
        body: { scope_notes: nextNotes || null },
        type: ContentType.Json,
      });
      if (!res.ok) throw new Error(await res.text().catch(() => "Failed to update garland setup"));
      const updated = await res.json();
      setArrangement(updated);
      notifyProjectsChanged();
    } catch {
      toast.error("Could not update garland setup");
      void loadDetail(arrangement.id, { silent: true });
    }
  };

  const updateWreathSetup = async (size: WreathSize) => {
    setWreathSize(size);
    if (!arrangement || !activeBucket || !isWreathBucket(activeBucket)) return;

    const nextNotes = scopeNotesWithWreathSetup(activeBucket, size);
    const optimisticBucket = { ...activeBucket, scope_notes: nextNotes || undefined };
    setArrangement((current) => {
      if (!current) return current;
      return {
        ...current,
        containers: current.containers.map((bucket) => bucket.id === activeBucket.id ? optimisticBucket : bucket),
      };
    });

    try {
      const res = await apiClient.request<Arrangement>({
        path: `/routes/arrangements/container/update/${activeBucket.id}`,
        method: "PUT",
        body: { scope_notes: nextNotes || null },
        type: ContentType.Json,
      });
      if (!res.ok) throw new Error(await res.text().catch(() => "Failed to update wreath setup"));
      const updated = await res.json();
      setArrangement(updated);
      notifyProjectsChanged();
    } catch {
      toast.error("Could not update wreath setup");
      void loadDetail(arrangement.id, { silent: true });
    }
  };

  const saveCustomSections = async (bucket: Container, sections: string[]) => {
    if (!arrangement) return;
    try {
      const res = await apiClient.request<Arrangement>({
        path: `/routes/arrangements/container/update/${bucket.id}`,
        method: "PUT",
        body: { scope_notes: scopeNotesWithCustomSections(bucket, sections) || null },
        type: ContentType.Json,
      });
      if (!res.ok) throw new Error(await res.text().catch(() => "Failed to update sections"));
      const updated = await res.json();
      setArrangement(updated);
      notifyProjectsChanged();
    } catch {
      toast.error("Failed to update sections");
    }
  };

  const addCustomSection = async () => {
    if (!activeBucket) return;
    const label = newCustomSectionName.trim();
    if (!label) return;
    const sections = parseCustomSections(activeBucket.scope_notes);
    if ([...baseScopePlaceholders(activeBucket), ...sections].some((section) => normalizeLabel(section) === normalizeLabel(label))) {
      toast.error("That section already exists");
      return;
    }
    await saveCustomSections(activeBucket, [...sections, label]);
    setNewCustomSectionName("");
    toast.success("Section added");
  };

  const moveCustomSection = async (sectionIndex: number, direction: -1 | 1) => {
    if (!activeBucket) return;
    const sections = parseCustomSections(activeBucket.scope_notes);
    const nextIndex = sectionIndex + direction;
    if (nextIndex < 0 || nextIndex >= sections.length) return;
    const absoluteIndex = baseScopePlaceholders(activeBucket).length + sectionIndex;
    const nextAbsoluteIndex = baseScopePlaceholders(activeBucket).length + nextIndex;
    if (
      itemsForPart(activeBucket, sections[sectionIndex], absoluteIndex).length > 0 ||
      itemsForPart(activeBucket, sections[nextIndex], nextAbsoluteIndex).length > 0
    ) {
      toast.error("Remove products from these sections before moving them");
      return;
    }
    const next = [...sections];
    [next[sectionIndex], next[nextIndex]] = [next[nextIndex], next[sectionIndex]];
    await saveCustomSections(activeBucket, next);
  };

  const removeCustomSection = async (sectionIndex: number) => {
    if (!activeBucket) return;
    const sections = parseCustomSections(activeBucket.scope_notes);
    const label = sections[sectionIndex];
    const absoluteIndex = baseScopePlaceholders(activeBucket).length + sectionIndex;
    if (itemsForPart(activeBucket, label, absoluteIndex).length > 0) {
      toast.error("Remove products from this section before deleting it");
      return;
    }
    await saveCustomSections(activeBucket, sections.filter((_, index) => index !== sectionIndex));
    toast.success("Section removed");
  };

  const addProductToActiveBucket = async (product: LibraryProduct) => {
    if (!arrangement || !activeBucket) {
      toast.error("Choose a scope first");
      return;
    }
    const bucketId = activeBucket.id;
    const bucketLabel = scopeTitle(activeBucket);
    const part = activePart || { label: scopePlaceholders(activeBucket)[0] || "Products", index: 0 };
    const key = partKey(part.label, part.index);
    const suggestedQty = suggestedQuantityForPart(activeBucket, part.label, part.index);
    const optimisticId = -Date.now();
    const displayImageUrl = productDisplayImageUrl(product);
    setArrangement((current) => {
      if (!current) return current;
      return {
        ...current,
        containers: current.containers.map((bucket) => {
          if (bucket.id !== bucketId) return bucket;
          const existing = bucket.items.find((item) => {
            const existingKey = item.part_key || partKey(item.part_label || "", item.part_order || 0);
            return item.product_id === product.id && existingKey === key;
          });
          if (existing) {
            return {
              ...bucket,
              items: bucket.items.map((item) =>
                item.id === existing.id
                  ? {
                      ...item,
                      quantity: item.quantity + suggestedQty,
                      line_total: (Number(item.current_price) || 0) * (item.quantity + suggestedQty),
                      status: "selected",
                    }
                  : item
              ),
              subtotal: (bucket.subtotal || 0) + (Number(product.current_price) || 0) * suggestedQty,
            };
          }
          const unitPrice = Number(product.current_price) || 0;
          return {
            ...bucket,
            items: [
              ...bucket.items,
              {
                id: optimisticId,
                product_id: product.id,
                product_name: product.name,
                product_category: product.category,
                unit: product.unit,
                current_price: product.current_price,
                supplier_name: product.supplier_name,
                supplier_sku: product.supplier_sku,
                photo_url: displayImageUrl,
                quantity: suggestedQty,
                line_total: unitPrice * suggestedQty,
                status: "selected",
                part_key: key,
                part_label: part.label,
                part_order: part.index,
              },
            ],
            subtotal: (bucket.subtotal || 0) + unitPrice * suggestedQty,
          };
        }),
      };
    });
    try {
      await apiClient.add_item_to_container(
        { containerId: bucketId },
        { product_id: product.id, quantity: suggestedQty, status: "selected", part_key: key, part_label: part.label, part_order: part.index } as any
      );
      void loadDetail(arrangement.id, { silent: true });
      notifyProjectsChanged();
      toast.success(`Saved ${product.name} to ${bucketLabel} · ${part.label}`);
    } catch {
      void loadDetail(arrangement.id, { silent: true });
      toast.error("Could not add product to scope");
    }
  };

  const removeItem = async (itemId: number) => {
    if (!arrangement) return;
    const itemToRemove = arrangement.containers.flatMap((bucket) => bucket.items).find((item) => item.id === itemId);
    if (!itemToRemove) return;

    setArrangement((current) => {
      if (!current) return current;
      return {
        ...current,
        containers: current.containers.map((bucket) => {
          const existsInBucket = bucket.items.some((item) => item.id === itemId);
          if (!existsInBucket) return bucket;
          const removedLineTotal = Number(itemToRemove.line_total) || (Number(itemToRemove.current_price) || 0) * (Number(itemToRemove.quantity) || 1);
          return {
            ...bucket,
            items: bucket.items.filter((item) => item.id !== itemId),
            subtotal: Math.max(0, (Number(bucket.subtotal) || 0) - removedLineTotal),
          };
        }),
      };
    });

    if (itemId < 0) return;

    try {
      await apiClient.remove_item({ itemId });
      await loadDetail(arrangement.id, { silent: true });
      notifyProjectsChanged();
    } catch {
      await loadDetail(arrangement.id, { silent: true });
      toast.error("Failed to remove item");
    }
  };

  const updateQty = async (itemId: number, qty: number) => {
    if (!arrangement) return;
    try {
      await apiClient.update_item_quantity({ itemId, quantity: qty });
      await loadDetail(arrangement.id, { silent: true });
      notifyProjectsChanged();
    } catch {
      toast.error("Failed to update quantity");
    }
  };

  const updateStatus = async (itemId: number, status: ItemStatus) => {
    if (!arrangement) return;
    try {
      await apiClient.request({
        path: `/routes/arrangements/item/status/${itemId}`,
        method: "PUT",
        body: { status },
        type: ContentType.Json,
      });
      await loadDetail(arrangement.id, { silent: true });
      notifyProjectsChanged();
    } catch {
      toast.error("Failed to update product status");
    }
  };

  const completeHistoricalBuild = async () => {
    if (!arrangement || !activeBucket) return;
    const sku = (finishedSku || suggestedFinishedSku(activeBucket, arrangement)).trim();
    if (!sku) {
      toast.error("Finished SKU required");
      return;
    }
    const selectedCount = activeBucket.items.filter((item) => (item.status || "selected") === "selected").length;
    if (selectedCount === 0) {
      toast.error("Select at least one product before adding to historical data");
      return;
    }
    const confirmed = window.confirm(
      "Add this built product to historical intelligence only if it is client approved, paid, purchased, and completed. Continue?"
    );
    if (!confirmed) return;
    try {
      const response = await apiClient.request({
        path: "/routes/historical/complete",
        method: "POST",
        body: {
          arrangement_id: arrangement.id,
          container_id: activeBucket.id,
          finished_sku: sku,
          completion_status: "approved_paid_purchased",
          notes: `Captured from ${arrangement.name} / ${scopeTitle(activeBucket)}`,
        },
        type: ContentType.Json,
      });
      if (!response.ok) throw new Error(await response.text().catch(() => "Failed"));
      const data = await response.json().catch(() => ({ components_added: selectedCount }));
      toast.success(`Added ${data.components_added || selectedCount} selected product${(data.components_added || selectedCount) === 1 ? "" : "s"} to historical data`);
    } catch {
      toast.error("Failed to add this build to historical data");
    }
  };

  const saveName = async () => {
    if (!arrangement || !nameEdit.trim()) return;
    try {
      await apiClient.update_arrangement({ arrangementId: arrangement.id }, { name: nameEdit.trim() });
      setArrangement((a) => a ? { ...a, name: nameEdit.trim() } : a);
      setArrangements((prev) => {
        const next = prev.map((a) => a.id === arrangement.id ? { ...a, name: nameEdit.trim() } : a);
        writeProjectsListCache(next);
        return next;
      });
      setEditingName(false);
      notifyProjectsChanged();
      toast.success("Project renamed");
    } catch {
      toast.error("Failed to rename project");
    }
  };

  return (
    <Layout>
      {!selectedId ? (
        <>
          <header className="sticky top-0 z-10 flex items-center justify-between border-b border-stone-200 px-10 py-4" style={{ backgroundColor: "#f7f4ef" }}>
            <div>
              <div className="mb-1 flex items-center gap-1 text-xs font-semibold text-emerald-700">
                <button onClick={showAllProjects} className="hover:underline">All Projects</button>
                {clientFilter && (
                  <>
                    <span className="text-stone-300">/</span>
                    <span className="text-stone-500">{clientFilter}</span>
                  </>
                )}
              </div>
              <h1 className="text-xl font-semibold text-stone-800" style={{ fontFamily: "Georgia, serif" }}>
                {clientFilter ? `${clientFilter} Projects` : "Projects"}
              </h1>
              <p className="mt-0.5 text-xs text-stone-500">
                {!listSettled && filteredArrangements.length === 0
                  ? "Checking projects..."
                  : `${filteredArrangements.length} project${filteredArrangements.length !== 1 ? "s" : ""} · clients, jobs, and scopes${listRefreshing ? " · Refreshing..." : listCachedAt ? ` · Updated ${formatProjectsCacheStamp(listCachedAt)}` : ""}`}
              </p>
            </div>
            <button onClick={() => setShowNewModal(true)} className="flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold text-white hover:opacity-90" style={{ backgroundColor: "#2d5a33" }}>
              <Plus size={15} strokeWidth={2.2} /> New Project
            </button>
          </header>
          <div className="px-10 py-6">
            {loading && filteredArrangements.length === 0 ? (
              <div className="flex items-center justify-center py-24">
                <div className="h-6 w-6 animate-spin rounded-full border-2 border-emerald-600 border-t-transparent" />
              </div>
            ) : listSettled && filteredArrangements.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-24 text-center">
                <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full" style={{ backgroundColor: "#e8f0e8" }}>
                  <Package size={28} className="text-emerald-600" strokeWidth={1.5} />
                </div>
                <p className="mb-1 text-base font-medium text-stone-600">No projects yet</p>
                <p className="mb-4 max-w-xs text-sm leading-relaxed text-stone-400">Create a client project, then add scopes like Tree, Garland, or Bookshelf.</p>
                <button onClick={() => setShowNewModal(true)} className="rounded-lg px-4 py-2 text-sm font-semibold text-white hover:opacity-90" style={{ backgroundColor: "#2d5a33" }}>Create First Project</button>
              </div>
            ) : (
              <div className="grid gap-3">
                {filteredArrangements.map((a) => (
                  <div key={a.id} onClick={() => selectProject(a.id)} className="group flex cursor-pointer items-center gap-4 rounded-xl border border-stone-200 bg-white px-6 py-4 transition-all hover:shadow-sm">
                    <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg" style={{ backgroundColor: "#e8f0e8" }}>
                      <Package size={18} className="text-emerald-700" strokeWidth={1.5} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-semibold text-stone-800">{a.name}</p>
                      <p className="mt-0.5 text-xs text-stone-400">{a.client_name || "No client"} · {a.container_count} scope{a.container_count !== 1 ? "s" : ""}</p>
                    </div>
                    <div className="mr-4 text-right">
                      <p className="text-sm font-semibold text-stone-800">{formatCurrency(a.total_cost)}</p>
                      <p className="text-xs text-stone-400">selected cost</p>
                    </div>
                    <p className="text-xs text-stone-300">{new Date(a.updated_at).toLocaleDateString()}</p>
                    <button onClick={(e) => { e.stopPropagation(); deleteProject(a.id); }} className="flex h-8 w-8 items-center justify-center rounded-lg text-stone-300 opacity-0 transition-colors hover:bg-red-50 hover:text-red-500 group-hover:opacity-100">
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      ) : arrangement ? (
        <>
          <header className="sticky top-0 z-10 flex items-center gap-4 border-b border-stone-200 px-10 py-4" style={{ backgroundColor: "#f7f4ef" }}>
            <button onClick={activeRoomId ? (activeBucket || creatingBuiltProduct ? backToBuiltProducts : closeRoom) : clearSelection} className="flex h-8 w-8 items-center justify-center rounded-lg text-stone-500 transition-colors hover:bg-stone-200">
              <ArrowLeft size={16} />
            </button>
            <div className="flex-1">
              {isClientPath && (
                <div className="mb-1 flex items-center gap-1 text-xs font-semibold text-emerald-700">
                  <button onClick={() => navigate("/clients")} className="hover:underline">Clients</button>
                  <span className="text-stone-300">/</span>
                  <button onClick={clearSelection} className="hover:underline">{arrangement.client_name || clientFilter || "Client"}</button>
                  <span className="text-stone-300">/</span>
                  <span className="text-stone-500">{arrangement.name}</span>
                  {activeRoom && (
                    <>
                      <span className="text-stone-300">/</span>
                      <span className="text-stone-500">{activeRoom.name}</span>
                    </>
                  )}
                </div>
              )}
              {!isClientPath && (
                <div className="mb-1 flex items-center gap-1 text-xs font-semibold text-emerald-700">
                  <button onClick={showAllProjects} className="hover:underline">All Projects</button>
                  {clientFilter && (
                    <>
                      <span className="text-stone-300">/</span>
                      <button onClick={showClientProjects} className="hover:underline">{clientFilter}</button>
                    </>
                  )}
                  <span className="text-stone-300">/</span>
                  <span className="text-stone-500">{arrangement.name}</span>
                  {activeRoom && (
                    <>
                      <span className="text-stone-300">/</span>
                      <span className="text-stone-500">{activeRoom.name}</span>
                    </>
                  )}
                </div>
              )}
              {editingName ? (
                <div className="flex items-center gap-2">
                  <input
                    autoFocus
                    className="rounded-lg border border-emerald-300 px-2 py-1 text-sm font-semibold text-stone-800 focus:outline-none focus:ring-2 focus:ring-emerald-300"
                    value={nameEdit}
                    onChange={(e) => setNameEdit(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") saveName(); if (e.key === "Escape") setEditingName(false); }}
                  />
                  <button onClick={saveName} className="p-1 text-emerald-600 hover:text-emerald-800"><Save size={14} /></button>
                  <button onClick={() => setEditingName(false)} className="p-1 text-stone-400 hover:text-stone-600"><X size={14} /></button>
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  <h1 className="text-lg font-semibold text-stone-800" style={{ fontFamily: "Georgia, serif" }}>{arrangement.name}</h1>
                  <button onClick={() => { setNameEdit(arrangement.name); setEditingName(true); }} className="text-stone-300 transition-colors hover:text-stone-500"><Pencil size={13} /></button>
                </div>
              )}
              <p className="text-xs text-stone-400">{arrangement.client_name || "No client"} · saved ideas do not affect pricing until selected</p>
            </div>
            <div className="text-right">
              <p className="text-sm font-bold text-stone-800">{formatCurrency(arrangement.total_with_markup)}</p>
              <p className="text-xs text-stone-400">quote estimate · selected base {formatCurrency(arrangement.total_cost)}</p>
            </div>
            <button onClick={() => navigate(`/invoice?arrangement_id=${arrangement.id}`)} className="rounded-lg px-4 py-2 text-sm font-semibold text-white hover:opacity-90" style={{ backgroundColor: "#2d5a33" }}>
              View Invoice
            </button>
          </header>

          {!activeRoomId ? (
            <div className="px-10 py-6">
              <div className="mb-6 rounded-2xl border border-stone-200 bg-white p-5 shadow-sm">
                <div className="mb-4">
                  <h2 className="text-lg font-semibold text-stone-900" style={{ fontFamily: "Georgia, serif" }}>Rooms & design packages</h2>
                  <p className="mt-1 text-sm text-stone-500">Add a room, area, or design package first. Then build individual products inside it.</p>
                </div>
                <div className="grid gap-3 md:grid-cols-[1fr_1fr_auto]">
                  <input
                    value={newRoomName}
                    onChange={(e) => setNewRoomName(e.target.value)}
                    placeholder="Living Room, Dining Room, Front Porch..."
                    className="rounded-xl border border-stone-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
                  />
                  <input
                    value={newRoomNotes}
                    onChange={(e) => setNewRoomNotes(e.target.value)}
                    placeholder="Optional notes"
                    className="rounded-xl border border-stone-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
                  />
                  <button
                    type="button"
                    onClick={addRoom}
                    disabled={!newRoomName.trim() || savingRoom}
                    className="rounded-xl px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
                    style={{ backgroundColor: "#2d5a33" }}
                  >
                    {savingRoom ? "Adding..." : "Add package"}
                  </button>
                </div>
              </div>

              {projectRoomsLoading ? (
                <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3" aria-live="polite" aria-label="Loading design packages">
                  {[0, 1, 2].map((index) => (
                    <div key={index} className="rounded-2xl border border-stone-200 bg-white p-5 shadow-sm">
                      <div className="mb-4 h-3 w-28 animate-pulse rounded bg-stone-100" />
                      <div className="h-6 w-44 animate-pulse rounded bg-stone-100" />
                      <div className="mt-2 h-4 w-60 max-w-full animate-pulse rounded bg-stone-100" />
                      <div className="mt-5 grid grid-cols-3 gap-2">
                        <div className="h-16 animate-pulse rounded-xl bg-stone-50" />
                        <div className="h-16 animate-pulse rounded-xl bg-stone-50" />
                        <div className="h-16 animate-pulse rounded-xl bg-stone-50" />
                      </div>
                      <div className="mt-4 h-10 animate-pulse rounded-xl bg-stone-100" />
                    </div>
                  ))}
                  <p className="sr-only">Loading design packages</p>
                </div>
              ) : projectRooms.length === 0 ? (
                <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-stone-300 bg-white px-6 py-16 text-center">
                  <Grid3X3 className="mb-3 text-emerald-700" size={28} />
                  <p className="font-semibold text-stone-800">No rooms or design packages yet</p>
                  <p className="mt-1 max-w-md text-sm text-stone-500">For a whole house, create packages like Living Room, Dining Room, Entry, Patio, or Christmas Install.</p>
                  {selectedId && (
                    <button
                      type="button"
                      onClick={() => void loadDetail(selectedId)}
                      disabled={projectHydrating || detailLoading}
                      className="mt-5 rounded-xl border border-stone-200 bg-white px-4 py-2 text-sm font-semibold text-stone-700 transition hover:border-emerald-200 hover:bg-emerald-50 disabled:opacity-50"
                    >
                      {projectHydrating || detailLoading ? "Refreshing..." : "Refresh packages"}
                    </button>
                  )}
                </div>
              ) : (
                <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
                  {projectRooms.map((room) => {
                    const scopes = (arrangement.containers || []).filter((bucket) => bucket.room_id === room.id);
                    const selectedTotal = scopes.reduce((sum, bucket) => sum + (bucket.subtotal || 0), 0);
                    const savedCount = scopes.reduce((sum, bucket) => sum + bucket.items.length, 0);
                    return (
                      <div key={room.id} className="group rounded-2xl border border-stone-200 bg-white p-5 shadow-sm transition-all hover:border-emerald-200 hover:shadow-md">
                        <div className="mb-4 flex items-start justify-between gap-3">
                          <div>
                            <p className="text-xs font-semibold uppercase tracking-wide text-emerald-700">Design package</p>
                            <h3 className="mt-1 text-lg font-semibold text-stone-900" style={{ fontFamily: "Georgia, serif" }}>{room.name}</h3>
                            {room.notes && <p className="mt-1 line-clamp-2 text-sm text-stone-500">{room.notes}</p>}
                          </div>
                          <button onClick={() => removeRoom(room.id)} className="rounded-lg p-1 text-stone-300 opacity-0 transition-colors hover:bg-stone-100 hover:text-stone-600 group-hover:opacity-100">
                            <Trash2 size={14} />
                          </button>
                        </div>
                        <div className="mb-4 grid grid-cols-3 gap-2">
                          <div className="rounded-xl bg-stone-50 p-3">
                            <p className="text-[11px] font-semibold uppercase text-stone-400">Products</p>
                            <p className="mt-1 font-semibold text-stone-900">{scopes.length}</p>
                          </div>
                          <div className="rounded-xl bg-stone-50 p-3">
                            <p className="text-[11px] font-semibold uppercase text-stone-400">Saved</p>
                            <p className="mt-1 font-semibold text-stone-900">{savedCount}</p>
                          </div>
                          <div className="rounded-xl bg-emerald-50 p-3">
                            <p className="text-[11px] font-semibold uppercase text-emerald-700">Selected</p>
                            <p className="mt-1 font-semibold text-emerald-900">{formatCurrency(selectedTotal)}</p>
                          </div>
                        </div>
                        <button onClick={() => openRoom(room.id)} className="w-full rounded-xl px-4 py-2 text-sm font-semibold text-white" style={{ backgroundColor: "#2d5a33" }}>
                          Open package
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          ) : !activeBucket && !creatingBuiltProduct ? (
            <div className="px-10 py-6">
              <div className="mb-6 flex flex-wrap items-start justify-between gap-4 rounded-2xl border border-stone-200 bg-white p-5 shadow-sm">
                {editingRoom ? (
                  <div className="w-full space-y-4">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wide text-emerald-700">Edit design package</p>
                      <p className="mt-1 text-sm text-stone-500">Name the room or package, then describe what should be built inside it.</p>
                    </div>
                    <div className="grid gap-3 md:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
                      <label className="block">
                        <span className="text-xs font-semibold uppercase tracking-wide text-stone-500">Package name</span>
                        <input
                          value={roomNameEdit}
                          onChange={(event) => setRoomNameEdit(event.target.value)}
                          className="mt-1 w-full rounded-xl border border-stone-200 px-3 py-2.5 text-sm text-stone-900 outline-none transition focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
                          placeholder="Main House, Dining Room, Holiday Install..."
                        />
                      </label>
                      <label className="block">
                        <span className="text-xs font-semibold uppercase tracking-wide text-stone-500">Description</span>
                        <textarea
                          value={roomNotesEdit}
                          onChange={(event) => setRoomNotesEdit(event.target.value)}
                          rows={3}
                          className="mt-1 w-full resize-none rounded-xl border border-stone-200 px-3 py-2.5 text-sm text-stone-900 outline-none transition focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
                          placeholder="What should be built in this package?"
                        />
                      </label>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        onClick={() => void saveRoomEdit()}
                        disabled={!roomNameEdit.trim()}
                        className="inline-flex items-center gap-2 rounded-lg bg-emerald-800 px-4 py-2 text-sm font-semibold text-white transition hover:bg-emerald-900 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        <Save size={15} /> Save package
                      </button>
                      <button onClick={cancelRoomEdit} className="rounded-lg border border-stone-200 px-4 py-2 text-sm font-semibold text-stone-600 transition hover:bg-stone-50">
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wide text-emerald-700">Design package</p>
                      <div className="mt-1 flex flex-wrap items-center gap-2">
                        <h2 className="text-xl font-semibold text-stone-900" style={{ fontFamily: "Georgia, serif" }}>{activeRoom?.name || "Package"}</h2>
                        <button
                          onClick={startRoomEdit}
                          className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-stone-400 transition hover:bg-stone-100 hover:text-emerald-800"
                          aria-label="Edit design package"
                          title="Edit design package"
                        >
                          <Pencil size={14} />
                        </button>
                      </div>
                      <p className="mt-1 max-w-2xl text-sm text-stone-500">
                        {activeRoom?.notes || "Create the individual things that need to be built for this room or package. Each one opens its own product builder."}
                      </p>
                    </div>
                    <button onClick={startRoomEdit} className="rounded-lg border border-stone-200 px-3 py-2 text-sm font-semibold text-stone-600 transition hover:bg-stone-50">
                      Edit
                    </button>
                  </>
                )}
              </div>

              {roomContainers.length === 0 ? (
                <button onClick={startNewBuiltProduct} className="flex min-h-[260px] w-full flex-col items-center justify-center rounded-2xl border border-dashed border-stone-300 bg-white text-center transition-colors hover:border-emerald-300 hover:bg-emerald-50/40">
                  <span className="mb-3 flex h-14 w-14 items-center justify-center rounded-full bg-stone-100 text-2xl text-stone-900">+</span>
                  <span className="font-semibold text-stone-900">Create the first built product</span>
                  <span className="mt-1 text-sm text-stone-500">Examples: 2 Fiddle Fig trees, 1 wreath, 1 sit around.</span>
                </button>
              ) : (
                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                  {roomContainers.map((bucket) => {
                    const selected = bucket.items.filter((item) => (item.status || "selected") === "selected");
                    const candidates = bucket.items.filter((item) => (item.status || "selected") === "candidate");
                    return (
                      <div key={bucket.id} className="group rounded-2xl border border-stone-200 bg-white p-5 shadow-sm transition-all hover:border-emerald-200 hover:shadow-md">
                        <div className="mb-4 flex items-start justify-between gap-3">
                          <div>
                            <p className="text-xs font-semibold uppercase tracking-wide text-stone-400">{bucket.bucket_type || "Built product"}</p>
                            <h3 className="mt-1 text-lg font-semibold text-stone-900" style={{ fontFamily: "Georgia, serif" }}>{scopeQuantity(bucket)}x {scopeTitle(bucket)}</h3>
                            {displayScopeNotes(bucket.scope_notes) && <p className="mt-1 line-clamp-2 text-sm text-stone-500">{displayScopeNotes(bucket.scope_notes)}</p>}
                          </div>
                          <button onClick={() => removeBucket(bucket.id)} className="rounded-lg p-1 text-stone-300 opacity-0 transition-colors hover:bg-stone-100 hover:text-stone-600 group-hover:opacity-100">
                            <Trash2 size={14} />
                          </button>
                        </div>
                        <div className="mb-4 grid grid-cols-3 gap-2">
                          <div className="rounded-xl bg-stone-50 p-3">
                            <p className="text-[11px] font-semibold uppercase text-stone-400">Ideas</p>
                            <p className="mt-1 font-semibold text-stone-900">{candidates.length}</p>
                          </div>
                          <div className="rounded-xl bg-emerald-50 p-3">
                            <p className="text-[11px] font-semibold uppercase text-emerald-700">Selected</p>
                            <p className="mt-1 font-semibold text-emerald-900">{selected.length}</p>
                          </div>
                          <div className="rounded-xl bg-stone-50 p-3">
                            <p className="text-[11px] font-semibold uppercase text-stone-400">Cost</p>
                            <p className="mt-1 font-semibold text-stone-900">{formatCurrency(bucket.subtotal)}</p>
                          </div>
                        </div>
                        <div className="mb-4 space-y-2">
                          {scopePlaceholders(bucket).map((label, index) => {
                            const partItems = itemsForPart(bucket, label, index);
                            return (
                              <div key={`${bucket.id}-${label}-${index}`} className="flex items-center justify-between rounded-xl border border-dashed border-stone-200 px-3 py-2 text-sm">
                                <span className="text-stone-600">{label}</span>
                                <span className={partItems.length ? "font-semibold text-emerald-700" : "text-stone-300"}>{partItems.length || "+"}</span>
                              </div>
                            );
                          })}
                        </div>
                        <button onClick={() => openBuiltProduct(bucket)} className="w-full rounded-xl px-4 py-2 text-sm font-semibold text-white" style={{ backgroundColor: "#2d5a33" }}>
                          Open builder
                        </button>
                      </div>
                    );
                  })}
                  <button onClick={startNewBuiltProduct} className="flex min-h-[320px] flex-col items-center justify-center rounded-2xl border border-dashed border-stone-300 bg-white text-center transition-colors hover:border-emerald-300 hover:bg-emerald-50/40">
                    <span className="mb-3 flex h-14 w-14 items-center justify-center rounded-full bg-stone-100 text-2xl text-stone-900">+</span>
                    <span className="font-semibold text-stone-900">New built product</span>
                  </button>
                </div>
              )}
            </div>
          ) : (
          <div ref={builderTopRef} className="px-6 py-5">
            <div className="mb-4 overflow-hidden rounded-2xl border border-stone-200 bg-white shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-stone-100 px-5 py-3">
                <div className="flex items-center gap-3">
                  <div className="flex h-8 w-8 items-center justify-center rounded-full border border-stone-200 text-emerald-800">
                    <Leaf size={16} />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-stone-900">Leaf & Ledger</p>
                    <p className="text-xs text-stone-400">{activeBucket ? scopeTitle(activeBucket) : "Product Builder"}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2 text-stone-400">
                  {[Undo2, Redo2, Upload, HelpCircle].map((Icon, index) => (
                    <button key={index} type="button" className="flex h-8 w-8 items-center justify-center rounded-lg hover:bg-stone-50 hover:text-stone-700">
                      <Icon size={15} strokeWidth={1.8} />
                    </button>
                  ))}
                  <span className="flex h-8 w-8 items-center justify-center rounded-full bg-stone-100 text-xs font-semibold text-stone-600">A</span>
                </div>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
                <div className="flex flex-wrap items-center gap-4 text-sm">
                  <span className="flex items-center gap-2 text-stone-500"><span className="h-2 w-2 rounded-full bg-emerald-700" /> Type: <strong className="text-stone-900">{activeBucket ? activeBucket.bucket_type || scopeTitle(activeBucket) : "No scope"}</strong></span>
                  <span className="text-stone-300">|</span>
                  <span className="text-stone-500">Parts: <strong className="text-stone-900">{partsComplete}/{activeParts.length || 0} selected</strong></span>
                  <span className="text-stone-300">|</span>
                  <span className="text-stone-500">Draft SKU: <strong className="text-stone-900">{activeDraftSku}</strong></span>
                  <span className="text-stone-300">|</span>
                  <span className="text-stone-500">Order: <strong className="text-emerald-800">{orderItems.length ? "ready" : "draft"}</strong></span>
                </div>
                <div className="flex min-h-[34px] items-center gap-2">
                  <div
                    className="grid overflow-hidden transition-all duration-300 ease-out"
                    style={{ gridTemplateColumns: builderStep !== "type" ? "78px" : "0px" }}
                  >
                    <button
                      type="button"
                      onClick={goBackBuilderStep}
                      tabIndex={builderStep !== "type" ? 0 : -1}
                      aria-hidden={builderStep === "type"}
                      className={`flex w-[78px] transform-gpu items-center justify-center gap-1 rounded-full border border-stone-200 bg-white px-3 py-1.5 text-xs font-semibold text-stone-700 shadow-sm transition-all duration-300 ease-out hover:-translate-y-0.5 hover:bg-stone-50 hover:shadow-md active:scale-[0.98] ${
                        builderStep !== "type" ? "translate-x-0 opacity-100" : "-translate-x-2 opacity-0"
                      }`}
                    >
                      <ArrowLeft size={13} />
                      Back
                    </button>
                  </div>
                  {builderSteps.map((step, index) => (
                    <button
                      key={step}
                      onClick={() => {
                        if (step === "products") {
                          void goToProductParts();
                          return;
                        }
                        goToBuilderStep(step);
                      }}
                      className={`transform-gpu whitespace-nowrap rounded-full px-3 py-1.5 text-xs font-semibold transition-all duration-300 ease-out hover:-translate-y-0.5 active:scale-[0.98] ${
                        builderStep === step
                          ? "scale-[1.02] bg-stone-900 text-white shadow-[0_0_0_2px_#f4b400]"
                          : "scale-100 bg-stone-100 text-stone-500 shadow-none hover:bg-stone-200 hover:text-stone-700"
                      }`}
                    >
                      {index + 1}. {step === "type" ? "Select type" : step === "products" ? "Choose parts" : step === "mockup" ? "Mockup" : step === "review" ? "Review" : "Order"}
                    </button>
                  ))}
                </div>
              </div>
            </div>

	            <div className="grid h-[720px] overflow-hidden rounded-2xl border border-stone-200 bg-white shadow-sm lg:grid-cols-[minmax(0,1fr)_440px] xl:grid-cols-[minmax(0,1fr)_460px]">
	              <section className="relative h-full overflow-x-hidden overflow-y-auto border-r border-stone-100 bg-[radial-gradient(circle_at_1px_1px,#e7e5e4_1px,transparent_0)] [background-size:22px_22px] p-6 pb-28 md:p-8 md:pb-28 lg:px-10">
	                {builderStep === "type" ? (
	                  <div className="mx-auto flex h-full max-w-3xl items-center">
	                    <div className="flex max-h-full w-full flex-col overflow-hidden rounded-3xl border border-stone-200 bg-white/95 p-6 shadow-sm">
		                      <div ref={previewPartsRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1" aria-label={`${activePreviewType || "Selected"} required parts`}>
		                        {activePreviewLoading ? (
		                          <div className="rounded-2xl border border-dashed border-emerald-200 bg-emerald-50/50 px-4 py-5 text-sm font-semibold text-emerald-900">
			                            Loading parts...
		                          </div>
		                        ) : (
		                          activePreviewComponents.map((component, index) => {
			                            const guidance = christmasPreviewGuidance(activePreviewType, component.label, treeHeight, treeCanopySize);
			                            const isTreePreview = isChristmasTreeBuild(activePreviewType);
			                            const isGarlandPreview = isGarlandBuild(activePreviewType);
                                      const isWreathPreview = isWreathBuild(activePreviewType);
			                            const isEnhancersPreview = (isTreePreview || isGarlandPreview) && isEnhancersPart(component.label);
                                      const isWreathDecorPreview = isWreathPreview && isWreathDecorPart(component.label);
			                            const previewRule = christmasTreeDecorRule(treeHeight, treeCanopySize);
                                      if (isWreathDecorPreview) {
                                        const wreathRows = wreathDecorPartsForSize(wreathSize).map((part) => ({
                                          label: part.label,
                                          note: part.note,
                                          target: wreathDecorPartPreviewText(part.label, wreathSize),
                                        }));
			                              return (
				                              <div key={`${component.label}-${index}`} className="relative rounded-[1.75rem] border border-dashed border-emerald-200 bg-white px-4 py-5 shadow-sm ring-1 ring-emerald-50">
				                                {index < activePreviewComponents.length - 1 && <span className="absolute left-7 top-[230px] h-6 border-l border-dashed border-stone-300" />}
				                                <div className="flex items-start gap-3">
				                                  <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-emerald-50 text-xs font-semibold text-emerald-900">{index + 1}</span>
				                                  <div className="min-w-0 flex-1">
				                                    <div className="flex flex-wrap items-start justify-between gap-3">
				                                      <div>
				                                        <p className="text-lg font-semibold text-stone-950">Decor Package</p>
				                                        <p className="mt-1 text-xs leading-relaxed text-stone-500">Build the wreath accents from these material lines.</p>
				                                      </div>
                                                <span className="rounded-xl bg-emerald-50 px-3 py-2 text-xs font-semibold text-emerald-900">
                                                  {wreathSize}" wreath
                                                </span>
				                                    </div>
                                            <div className="mt-3 rounded-2xl border border-emerald-100 bg-emerald-50/70 px-3 py-2 text-xs font-medium leading-relaxed text-emerald-900">
                                              {wreathDecorCountSummary(wreathSize)}
                                            </div>
				                                    <div className="mt-4 grid gap-2.5">
				                                      {wreathRows.map((part) => (
                                              <div key={part.label} className="grid items-center gap-3 rounded-2xl border border-emerald-100 bg-emerald-50/45 px-3 py-2.5 text-xs sm:grid-cols-[minmax(0,1fr)_120px]">
                                                <div className="min-w-0">
                                                  <p className="font-semibold text-emerald-950">{part.label}</p>
                                                  <p className="mt-0.5 text-[11px] font-medium text-emerald-800">{part.target}</p>
                                                  <p className="mt-1 text-[11px] text-stone-500">{part.note}</p>
                                                </div>
                                                <span className="rounded-xl border border-dashed border-stone-300 bg-white px-3 py-2 text-center text-xs font-semibold text-stone-400">
                                                  Product
                                                </span>
                                              </div>
                                            ))}
				                                    </div>
				                                  </div>
				                                </div>
				                              </div>
			                              );
                                      }
			                            if (isEnhancersPreview) {
                                      const activePackage = isGarlandPreview ? garlandPackage : christmasEnhancerPackage;
                                      const enhancerRows = isGarlandPreview
                                        ? garlandEnhancerPartsForPackage(garlandPackage).map((part) => ({
                                            label: part.label,
                                            target: garlandEnhancerPartPreviewText(part.label, garlandPackage, garlandLength),
                                            premiumOnly: "premiumOnly" in part && part.premiumOnly,
                                          }))
                                        : christmasEnhancerPartsForPackage(christmasEnhancerPackage).map((part) => ({
                                            label: part.label,
                                            target: christmasEnhancerPartPreviewText(part.label, previewRule?.enhancers || part.fallbackQuantity, christmasEnhancerPackage),
                                            premiumOnly: christmasEnhancerPartIsOptional(part),
                                          }));
		                              return (
			                              <div key={`${component.label}-${index}`} className="relative rounded-[1.75rem] border border-dashed border-emerald-200 bg-white px-4 py-5 shadow-sm ring-1 ring-emerald-50">
			                                {index < activePreviewComponents.length - 1 && <span className="absolute left-7 top-[250px] h-6 border-l border-dashed border-stone-300" />}
			                                <div className="flex items-start gap-3">
			                                  <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-emerald-50 text-xs font-semibold text-emerald-900">{index + 1}</span>
			                                  <div className="min-w-0 flex-1">
			                                    <div className="flex flex-wrap items-start justify-between gap-3">
			                                      <div>
			                                        <p className="text-lg font-semibold text-stone-950">Enhancers</p>
			                                        <p className="mt-1 text-xs leading-relaxed text-stone-500">Build regular or premium enhancer sets from these material lines.</p>
			                                      </div>
                                                <div className="flex flex-col items-end gap-2">
                                                  <div className="grid grid-cols-2 rounded-xl border border-emerald-100 bg-emerald-50 p-1 text-[11px] font-semibold">
                                                    {(["regular", "premium"] as const).map((packageType) => (
                                                      <button
                                                        key={packageType}
                                                        type="button"
                                                        onClick={() => isGarlandPreview ? setGarlandPackage(packageType) : setChristmasEnhancerPackage(packageType)}
                                                        className={`rounded-lg px-3 py-1.5 capitalize transition ${activePackage === packageType ? "bg-white text-stone-950 shadow-sm" : "text-emerald-800 hover:text-stone-950"}`}
                                                      >
                                                        {packageType}
                                                      </button>
                                                    ))}
                                                  </div>
                                                </div>
			                                    </div>
                                            <div className="mt-3 rounded-2xl border border-emerald-100 bg-emerald-50/70 px-3 py-2 text-xs font-medium leading-relaxed text-emerald-900">
                                              {isGarlandPreview
                                                ? garlandEnhancerCountSummary(garlandPackage, garlandLength, garlandDiameter)
                                                : christmasEnhancerCountSummary(previewRule, treeDensity)}
                                            </div>
			                                    <div className="mt-4 grid gap-2.5">
			                                      {enhancerRows.map((part) => {
			                                        return (
			                                          <div key={part.label} className="grid items-center gap-3 rounded-2xl border border-emerald-100 bg-emerald-50/45 px-3 py-2.5 text-xs sm:grid-cols-[minmax(0,1fr)_120px]">
			                                            <div className="min-w-0">
			                                              <div className="flex flex-wrap items-center gap-1.5">
                                                  <p className="font-semibold text-emerald-950">{part.label}</p>
                                                  {part.premiumOnly && (
                                                    <span className="rounded-full bg-white px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-800 ring-1 ring-emerald-100">Premium</span>
                                                  )}
                                                </div>
			                                              <p className="mt-0.5 text-[11px] font-medium text-emerald-800">{part.target}</p>
			                                            </div>
			                                            <span className="rounded-xl border border-dashed border-stone-300 bg-white px-3 py-2 text-center text-xs font-semibold text-stone-400">
			                                              Product
			                                            </span>
			                                          </div>
			                                        );
			                                      })}
			                                    </div>
			                                  </div>
			                                </div>
			                              </div>
		                              );
		                            }
		                            return (
			                            <div key={`${component.label}-${index}`} className="relative rounded-2xl border border-dashed border-stone-300 bg-white px-4 py-4 shadow-sm">
			                              {index < activePreviewComponents.length - 1 && <span className="absolute left-7 top-[58px] h-6 border-l border-dashed border-stone-300" />}
			                              <div className="flex items-center gap-3">
			                                <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-emerald-50 text-xs font-semibold text-emerald-900">{index + 1}</span>
			                                <div className="min-w-0 flex-1">
			                                  <p className="font-semibold text-stone-900">{component.label}</p>
			                                  {guidance && <p className="mt-1 text-xs text-stone-400">{guidance}</p>}
			                                </div>
			                                <span className="min-w-[132px] rounded-xl border border-dashed border-stone-300 bg-stone-50 px-3 py-2 text-center text-xs font-semibold text-stone-400">
			                                  Product
			                                </span>
			                              </div>
			                            </div>
		                            );
		                          })
		                        )}
		                      </div>
	                    </div>
	                  </div>
	                ) : !activeBucket ? (
                  <div className="flex h-full items-center justify-center text-center">
                    <div>
                      <Package className="mx-auto mb-3 text-emerald-700" size={32} />
                      <p className="font-semibold text-stone-800">Create a scope to start building</p>
                      <p className="mt-1 text-sm text-stone-400">Examples: Fiddle Fig, Wreath, Sitting Arrangement.</p>
                    </div>
                  </div>
                ) : (
                  <div className="mx-auto flex w-full max-w-[720px] flex-col gap-5">
                    {!isStructuredChristmasBucket(activeBucket) && (
                      <div className="mb-1 flex items-center justify-between">
                        <div>
                          <p className="text-xs font-semibold uppercase tracking-wide text-stone-400">Active scope</p>
                          <h2 className="text-xl font-semibold text-stone-900" style={{ fontFamily: "Georgia, serif" }}>{scopeQuantity(activeBucket)}x {scopeTitle(activeBucket)}</h2>
                        </div>
                        <button onClick={() => removeBucket(activeBucket.id)} className="rounded-lg px-2 py-1 text-xs text-stone-400 hover:bg-red-50 hover:text-red-500">Delete scope</button>
                      </div>
                    )}
                    {isStructuredChristmasBucket(activeBucket) ? (
                      <div className="w-full rounded-3xl border border-stone-200 bg-white/95 p-6 shadow-sm">
                        <div className="space-y-3">
                          {scopePlaceholders(activeBucket).map((label, index) => {
                            const partItems = itemsForPart(activeBucket, label, index);
                            const primary = partItems[0];
                            const primaryStatus = primary?.status || "selected";
                            const selectedPart = activePart?.index === index;
                            const guidance = christmasPartGuidance(activeBucket, label) || "Add a product for this slot.";
                            const customSectionIndex = index - activeBasePartCount;
	                            const isCustomSection = customSectionIndex >= 0;
	                            const hasNext = index < scopePlaceholders(activeBucket).length - 1;

                            if (isWreathBucket(activeBucket) && isWreathDecorPart(label)) {
                              const activeSize = wreathSizeFromNotes(activeBucket.scope_notes);
                              const wreathRows = wreathDecorPartsForSize(activeSize).map((part) => {
                                const subIndex = wreathDecorPartSubIndex(part.label);
                                const partIndex = christmasEnhancerPartIndex(index, subIndex);
                                const subItems = wreathDecorPartItems(activeBucket, index, subIndex);
                                return {
                                  label: part.label,
                                  note: part.note,
                                  target: wreathDecorPartPreviewText(part.label, activeSize),
                                  partIndex,
                                  subItems,
                                };
                              });
                              const selectedSubpart = wreathRows.some((part) => activePart?.index === part.partIndex);
                              return (
                                <div
                                  key={`${label}-${index}`}
                                  className={`relative rounded-[1.75rem] border border-dashed px-4 py-5 shadow-sm transition-all ${
                                    selectedSubpart ? "border-stone-900 bg-white ring-2 ring-stone-100" : "border-emerald-200 bg-white ring-1 ring-emerald-50"
                                  }`}
                                >
                                  {hasNext && <span className="absolute left-7 top-[230px] h-6 border-l border-dashed border-stone-300" />}
                                  <div className="flex items-start gap-3">
                                    <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-emerald-50 text-xs font-semibold text-emerald-900">
                                      {index + 1}
                                    </div>
                                    <div className="min-w-0 flex-1">
                                      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
                                        <div>
                                          <p className="text-lg font-semibold text-stone-950">Decor Package</p>
                                          <p className="mt-1 text-xs leading-relaxed text-stone-500">Build the wreath accents from these material lines.</p>
                                        </div>
                                        <span className="rounded-xl bg-emerald-50 px-3 py-2 text-xs font-semibold text-emerald-900">
                                          {activeSize}" wreath
                                        </span>
                                      </div>
                                      <div className="mb-3 rounded-2xl border border-emerald-100 bg-emerald-50/70 px-3 py-2 text-xs font-medium leading-relaxed text-emerald-900">
                                        {wreathDecorCountSummary(activeSize)}
                                      </div>
                                      <div className="grid gap-2.5">
                                        {wreathRows.map((part) => {
                                          const selectedItems = part.subItems.filter((item) => (item.status || "selected") === "selected");
                                          const selected = activePart?.index === part.partIndex;

                                          return (
                                            <div
                                              key={part.label}
                                              className={`grid items-center gap-3 rounded-2xl border px-3 py-2.5 text-xs transition-all sm:grid-cols-[minmax(0,1fr)_120px] ${
                                                selected ? "border-stone-900 bg-white shadow-sm ring-2 ring-stone-100" : "border-emerald-100 bg-emerald-50/45 hover:border-emerald-200"
                                              }`}
                                            >
                                              <div className="min-w-0">
                                                <p className="font-semibold text-emerald-950">{part.label}</p>
                                                <p className="mt-0.5 text-[11px] font-medium text-emerald-800">{part.target}</p>
                                                <p className="mt-1 text-[11px] text-stone-500">{part.note}</p>
                                                {part.subItems[0] && (
                                                  <p className="mt-1 truncate text-xs font-medium text-stone-500">
                                                    {part.subItems[0].product_name}{part.subItems.length > 1 ? ` +${part.subItems.length - 1} more` : ""}
                                                  </p>
                                                )}
                                              </div>
                                              <button
                                                type="button"
                                                onClick={() => openBucketCatalog(activeBucket.id, { label: part.label, index: part.partIndex })}
                                                className="rounded-xl border border-dashed border-stone-300 bg-white px-3 py-2 text-center text-xs font-semibold text-stone-400 transition-all hover:-translate-y-0.5 hover:border-emerald-600 hover:text-emerald-900 hover:shadow-sm active:scale-[0.98]"
                                              >
                                                {selectedItems.length ? "Add more" : "Product"}
                                              </button>
                                            </div>
                                          );
                                        })}
                                      </div>
                                    </div>
                                  </div>
                                </div>
                              );
                            }

	                            if (isEnhancersPart(label)) {
	                              const garlandEnhancers = isGarlandBucket(activeBucket);
                              const rule = christmasTreeDecorRuleForBucket(activeBucket);
                              const activePackage = garlandEnhancers ? garlandPackage : christmasEnhancerPackage;
                              const enhancerRows = garlandEnhancers
                                ? garlandEnhancerPartsForPackage(garlandPackage).map((part) => {
                                    const subIndex = garlandEnhancerPartSubIndex(part.label);
                                    const partIndex = christmasEnhancerPartIndex(index, subIndex);
                                    const subItems = garlandEnhancerPartItems(activeBucket, index, subIndex);
                                  return {
                                    label: part.label,
                                    note: part.note,
                                    target: garlandEnhancerPartPreviewText(part.label, garlandPackage, garlandLength),
                                    premiumOnly: "premiumOnly" in part && part.premiumOnly,
                                    partIndex,
                                    subItems,
                                  };
                                  })
                                : christmasEnhancerPartsForPackage(christmasEnhancerPackage).map((part) => {
                                    const subIndex = christmasEnhancerPartSubIndex(part.label);
                                    const partIndex = christmasEnhancerPartIndex(index, subIndex);
                                    const subItems = christmasEnhancerPartItems(activeBucket, index, subIndex);
                                    return {
                                      label: part.label,
                                      note: part.note,
                                      target: rule ? christmasEnhancerPartTargetText(activeBucket, part.label) : "Set tree height to calculate count",
                                      premiumOnly: christmasEnhancerPartIsOptional(part),
                                      partIndex,
                                      subItems,
                                    };
                                  });
                              const selectedSubpart = enhancerRows.some((part) => activePart?.index === part.partIndex);
                              return (
                                <div
                                  key={`${label}-${index}`}
                                  className={`relative rounded-[1.75rem] border border-dashed px-4 py-5 shadow-sm transition-all ${
                                    selectedSubpart ? "border-stone-900 bg-white ring-2 ring-stone-100" : "border-emerald-200 bg-white ring-1 ring-emerald-50"
                                  }`}
                                >
                                  {hasNext && <span className="absolute left-7 top-[250px] h-6 border-l border-dashed border-stone-300" />}
                                  <div className="flex items-start gap-3">
                                    <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-emerald-50 text-xs font-semibold text-emerald-900">
                                      {index + 1}
                                    </div>
                                    <div className="min-w-0 flex-1">
                                      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
                                        <div>
                                          <p className="text-lg font-semibold text-stone-950">Enhancers</p>
                                          <p className="mt-1 text-xs leading-relaxed text-stone-500">Build regular or premium enhancer sets from these material lines.</p>
                                        </div>
                                        <div className="flex flex-col items-end gap-2">
                                          <div className="grid grid-cols-2 rounded-xl border border-emerald-100 bg-emerald-50 p-1 text-[11px] font-semibold">
                                            {(["regular", "premium"] as const).map((packageType) => (
                                              <button
                                                key={packageType}
                                                type="button"
                                                onClick={() => garlandEnhancers ? void updateGarlandSetup({ packageType }) : void updateChristmasEnhancerPackage(packageType)}
                                                className={`rounded-lg px-3 py-1.5 capitalize transition ${activePackage === packageType ? "bg-white text-stone-950 shadow-sm" : "text-emerald-800 hover:text-stone-950"}`}
                                              >
                                                {packageType}
                                              </button>
                                            ))}
                                          </div>
                                        </div>
                                      </div>
                                      <div className="mb-3 rounded-2xl border border-emerald-100 bg-emerald-50/70 px-3 py-2 text-xs font-medium leading-relaxed text-emerald-900">
                                        {garlandEnhancers
                                          ? garlandEnhancerCountSummary(garlandPackage, garlandLength, garlandDiameter)
                                          : christmasEnhancerCountSummary(rule, scopeNoteValue(activeBucket.scope_notes, "Depth / density"))}
                                      </div>
                                      <div className="grid gap-2.5">
                                        {enhancerRows.map((part) => {
                                          const selectedItems = part.subItems.filter((item) => (item.status || "selected") === "selected");
                                          const selected = activePart?.index === part.partIndex;

                                          return (
                                            <div
                                              key={part.label}
                                              className={`grid items-center gap-3 rounded-2xl border px-3 py-2.5 text-xs transition-all sm:grid-cols-[minmax(0,1fr)_120px] ${
                                                selected ? "border-stone-900 bg-white shadow-sm ring-2 ring-stone-100" : "border-emerald-100 bg-emerald-50/45 hover:border-emerald-200"
                                              }`}
                                            >
                                              <div className="min-w-0">
                                                <div className="flex flex-wrap items-center gap-1.5">
                                                  <p className="font-semibold text-emerald-950">{part.label}</p>
                                                  {part.premiumOnly && (
                                                    <span className="rounded-full bg-white px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-800 ring-1 ring-emerald-100">Premium</span>
                                                  )}
                                                </div>
                                                <p className="mt-0.5 text-[11px] font-medium text-emerald-800">{part.target}</p>
                                                <p className="mt-1 text-[11px] text-stone-500">{part.note}</p>
                                                {part.subItems[0] && (
                                                  <p className="mt-1 truncate text-xs font-medium text-stone-500">
                                                    {part.subItems[0].product_name}{part.subItems.length > 1 ? ` +${part.subItems.length - 1} more` : ""}
                                                  </p>
                                                )}
                                              </div>
                                              <button
                                                type="button"
                                                onClick={() => openBucketCatalog(activeBucket.id, { label: part.label, index: part.partIndex })}
                                                className="rounded-xl border border-dashed border-stone-300 bg-white px-3 py-2 text-center text-xs font-semibold text-stone-400 transition-all hover:-translate-y-0.5 hover:border-emerald-600 hover:text-emerald-900 hover:shadow-sm active:scale-[0.98]"
                                              >
                                                {selectedItems.length ? "Add more" : "Product"}
                                              </button>
                                            </div>
                                          );
                                        })}
                                      </div>
                                    </div>
                                  </div>
                                </div>
                              );
                            }

                            return (
                              <div
                                key={`${label}-${index}`}
                                className={`relative rounded-2xl border border-dashed bg-white px-4 py-4 shadow-sm transition-all ${
                                  selectedPart ? "border-stone-900 ring-2 ring-stone-100" : "border-stone-300 hover:border-stone-400"
                                }`}
                              >
                                {hasNext && <span className="absolute left-7 top-[58px] h-6 border-l border-dashed border-stone-300" />}
                                {isCustomSection && (
                                  <span className="absolute right-4 top-4 z-10 flex gap-1">
                                    <button
                                      type="button"
                                      onClick={() => void moveCustomSection(customSectionIndex, -1)}
                                      className="rounded-md border border-stone-200 bg-white px-2 py-1 text-[10px] font-semibold text-stone-500 hover:text-stone-900"
                                    >
                                      Up
                                    </button>
                                    <button
                                      type="button"
                                      onClick={() => void moveCustomSection(customSectionIndex, 1)}
                                      className="rounded-md border border-stone-200 bg-white px-2 py-1 text-[10px] font-semibold text-stone-500 hover:text-stone-900"
                                    >
                                      Down
                                    </button>
                                    <button
                                      type="button"
                                      onClick={() => void removeCustomSection(customSectionIndex)}
                                      className="rounded-md border border-red-100 bg-white px-2 py-1 text-[10px] font-semibold text-red-500 hover:bg-red-50"
                                    >
                                      Remove
                                    </button>
                                  </span>
                                )}
                                <div className="flex items-center gap-3">
                                  <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-emerald-50 text-xs font-semibold text-emerald-900">
                                    {index + 1}
                                  </div>
                                  <div className="min-w-0 flex-1">
                                    <p className="font-semibold text-stone-900">{label}</p>
                                    <p className="mt-1 text-xs text-stone-400">{guidance}</p>
                                    {primary && (
                                      <div className="mt-2 flex flex-wrap items-center gap-2">
                                        <span className="max-w-full truncate rounded-full bg-stone-50 px-3 py-1 text-xs font-semibold text-stone-700 ring-1 ring-stone-200">
                                          {primary.product_name}
                                        </span>
                                        <button
                                          type="button"
                                          onClick={() => updateStatus(primary.id, primaryStatus === "selected" ? "candidate" : "selected")}
                                          className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${
                                            primaryStatus === "selected" ? "bg-emerald-50 text-emerald-800 ring-1 ring-emerald-200" : "bg-stone-50 text-stone-500 ring-1 ring-stone-200"
                                          }`}
                                        >
                                          {primaryStatus === "selected" ? "Selected" : "Idea"}
                                        </button>
                                        <button
                                          type="button"
                                          onClick={() => removeItem(primary.id)}
                                          className="rounded-full bg-stone-50 px-2.5 py-1 text-[11px] font-semibold text-stone-400 ring-1 ring-stone-200 hover:text-red-500"
                                        >
                                          Remove
                                        </button>
                                      </div>
                                    )}
                                  </div>
                                  <button
                                    type="button"
                                    onClick={() => openBucketCatalog(activeBucket.id, { label, index })}
                                    className="min-w-[132px] rounded-xl border border-dashed border-stone-300 bg-stone-50 px-3 py-2 text-center text-xs font-semibold text-stone-400 transition-all hover:-translate-y-0.5 hover:border-emerald-600 hover:bg-white hover:text-emerald-900 hover:shadow-sm active:scale-[0.98]"
                                  >
                                    {primary ? "Add more" : "Product"}
                                  </button>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    ) : (
	                    scopePlaceholders(activeBucket).map((label, index) => {
	                      const partItems = itemsForPart(activeBucket, label, index);
	                      const selectedPart = activePart?.index === index;
	                      const primary = partItems[0];
	                      const primaryStatus = primary?.status || "selected";
	                      const suggestion = suggestionForPart(activeBucket, label, index);
                        const partGuidance = christmasPartGuidance(activeBucket, label);
                        const customSectionIndex = index - activeBasePartCount;
                        const isCustomSection = customSectionIndex >= 0;
                        const isChristmasEnhancers = isChristmasTreeBucket(activeBucket) && isEnhancersPart(label);
                        if (isChristmasEnhancers) {
                          const rule = christmasTreeDecorRuleForBucket(activeBucket);
                          const enhancerParts = christmasEnhancerPartsForPackage(christmasEnhancerPackageFromNotes(activeBucket.scope_notes));
                          const selectedSubpart = enhancerParts.some((part) => activePart?.index === christmasEnhancerPartIndex(index, christmasEnhancerPartSubIndex(part.label)));
                          return (
                            <div
                              key={`${label}-${index}`}
                              className={`group relative rounded-3xl border bg-white/95 px-6 py-6 text-left shadow-sm transition-all ${selectedSubpart ? "border-stone-900 ring-2 ring-stone-100" : "border-dashed border-emerald-200"}`}
                            >
                              <span className="absolute -top-3 left-5 rounded-full border border-emerald-200 bg-white px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-emerald-800">
                                {label}
                              </span>
                              {index < scopePlaceholders(activeBucket).length - 1 && <span className="absolute left-[47px] top-[210px] h-10 border-l border-dashed border-stone-300" />}
                              <div className="flex items-start gap-4">
                                <div className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-full bg-emerald-50 text-sm font-semibold text-emerald-900">{index + 1}</div>
                                <div className="min-w-0 flex-1">
                                  <div className="flex flex-wrap items-start justify-between gap-3">
                                    <div>
                                      <p className="font-semibold text-stone-900">Enhancers</p>
                                      <p className="mt-1 text-sm text-stone-500">Ribbon, picks/sprays, ornaments, and clusters live inside this section.</p>
                                    </div>
                                    <span className="rounded-xl bg-emerald-50 px-3 py-2 text-xs font-semibold text-emerald-900">
                                      {rule ? `${rule.enhancers} enhancers · ${rule.ornaments} ornaments` : "Enter tree height"}
                                    </span>
                                  </div>
                                  <div className="mt-4 grid gap-2">
                                    {enhancerParts.map((part) => {
                                      const subIndex = christmasEnhancerPartSubIndex(part.label);
                                      const partIndex = christmasEnhancerPartIndex(index, subIndex);
                                      const subItems = christmasEnhancerPartItems(activeBucket, index, subIndex);
                                      const selectedItems = subItems.filter((item) => (item.status || "selected") === "selected");
                                      const selected = activePart?.index === partIndex;
                                      return (
                                        <div
                                          key={part.label}
                                          className={`flex min-h-[58px] items-center justify-between gap-4 rounded-2xl border px-4 py-3 text-left transition-all hover:border-stone-900 hover:shadow-sm ${
                                            selected ? "border-stone-900 bg-white ring-2 ring-stone-100" : "border-emerald-100 bg-emerald-50/40"
                                          }`}
                                        >
                                          <div className="min-w-0">
                                            <p className="font-semibold text-stone-900">{part.label}</p>
                                            <p className="mt-1 text-xs text-stone-500">{part.note} · {christmasEnhancerPartTargetText(activeBucket, part.label)}</p>
                                            {subItems[0] && (
                                              <p className="mt-1 truncate text-xs text-stone-400">
                                                {subItems[0].product_name}{subItems.length > 1 ? ` +${subItems.length - 1} more` : ""}
                                              </p>
                                            )}
                                          </div>
                                          <div className="flex flex-shrink-0 items-center gap-2">
                                            {selectedItems.length > 0 && (
                                              <span className="rounded-full bg-emerald-100 px-3 py-1 text-[11px] font-semibold text-emerald-900">
                                                {selectedItems.length} selected
                                              </span>
                                            )}
                                            <button
                                              type="button"
                                              onClick={() => openBucketCatalog(activeBucket.id, { label: part.label, index: partIndex })}
                                              className="rounded-xl border border-stone-200 bg-white px-4 py-2 text-xs font-semibold text-stone-700 shadow-sm transition-all hover:-translate-y-0.5 hover:border-stone-900 hover:shadow-md active:scale-[0.98]"
                                            >
                                              {selectedItems.length ? "Add more" : "Select product"}
                                            </button>
                                          </div>
                                        </div>
                                      );
                                    })}
                                  </div>
                                </div>
                              </div>
                            </div>
                          );
                        }
	                      return (
	                        <button
	                          key={`${label}-${index}`}
	                          type="button"
	                          onClick={() => openBucketCatalog(activeBucket.id, { label, index })}
                          className={`group relative flex min-h-[128px] items-center gap-4 rounded-2xl border bg-white/95 px-6 py-5 text-left shadow-sm transition-all hover:border-stone-900 hover:shadow-md ${selectedPart ? "border-stone-900 ring-2 ring-stone-100" : "border-dashed border-stone-300"}`}
                        >
	                          <span className="absolute -top-3 left-5 rounded-full border border-stone-200 bg-white px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-stone-400">
	                            {label}
	                          </span>
                            {isCustomSection && (
                              <span className="absolute right-3 top-3 z-10 flex gap-1">
                                <button
                                  type="button"
                                  onClick={(event) => {
                                    event.preventDefault();
                                    event.stopPropagation();
                                    void moveCustomSection(customSectionIndex, -1);
                                  }}
                                  className="rounded-md border border-stone-200 bg-white px-2 py-1 text-[10px] font-semibold text-stone-500 hover:text-stone-900"
                                >
                                  Up
                                </button>
                                <button
                                  type="button"
                                  onClick={(event) => {
                                    event.preventDefault();
                                    event.stopPropagation();
                                    void moveCustomSection(customSectionIndex, 1);
                                  }}
                                  className="rounded-md border border-stone-200 bg-white px-2 py-1 text-[10px] font-semibold text-stone-500 hover:text-stone-900"
                                >
                                  Down
                                </button>
                                <button
                                  type="button"
                                  onClick={(event) => {
                                    event.preventDefault();
                                    event.stopPropagation();
                                    void removeCustomSection(customSectionIndex);
                                  }}
                                  className="rounded-md border border-red-100 bg-white px-2 py-1 text-[10px] font-semibold text-red-500 hover:bg-red-50"
                                >
                                  Remove
                                </button>
                              </span>
                            )}
	                          {index < scopePlaceholders(activeBucket).length - 1 && <span className="absolute left-[47px] top-[88px] h-10 border-l border-dashed border-stone-300" />}
	                          <div className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-full bg-stone-100 text-2xl text-stone-900 group-hover:bg-emerald-50 group-hover:text-emerald-800">+</div>
	                          <div className="min-w-0 flex-1">
                            {primary ? (
                              <>
                                <p className="line-clamp-2 text-sm font-semibold text-stone-900">{primary.product_name}</p>
                                <p className="mt-1 text-xs text-stone-400">{primary.supplier_sku || primary.supplier_name} · {partItems.length} saved</p>
                                <div className="mt-2 flex flex-wrap gap-2">
                                  <button
                                    type="button"
                                    onClick={(event) => {
                                      event.preventDefault();
                                      event.stopPropagation();
                                      updateStatus(primary.id, primaryStatus === "selected" ? "candidate" : "selected");
                                    }}
                                    className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${
                                      primaryStatus === "selected" ? "bg-emerald-50 text-emerald-800 ring-1 ring-emerald-200" : "bg-stone-50 text-stone-500 ring-1 ring-stone-200"
                                    }`}
                                  >
                                    {primaryStatus === "selected" ? "Selected" : "Idea"}
                                  </button>
                                  <button
                                    type="button"
                                    onClick={(event) => {
                                      event.preventDefault();
                                      event.stopPropagation();
                                      openBucketCatalog(activeBucket.id, { label, index });
                                    }}
                                    className="rounded-full bg-stone-50 px-2.5 py-1 text-[11px] font-semibold text-stone-500 ring-1 ring-stone-200 hover:text-stone-800"
                                  >
                                    Change
                                  </button>
                                  <button
                                    type="button"
                                    onClick={(event) => {
                                      event.preventDefault();
                                      event.stopPropagation();
                                      removeItem(primary.id);
                                    }}
                                    className="rounded-full bg-stone-50 px-2.5 py-1 text-[11px] font-semibold text-stone-400 ring-1 ring-stone-200 hover:text-red-500"
                                  >
                                    Remove
                                  </button>
                                </div>
                              </>
                            ) : (
                              <>
                                <p className="font-semibold text-stone-900">{label}</p>
                                <p className="text-sm text-stone-400">
                                  {suggestion ? `Suggested qty ${suggestion.suggested_quantity}` : partGuidance || "Select product"}
                                </p>
                              </>
                            )}
                          </div>
                          <span className="rounded-lg border border-stone-200 bg-white px-4 py-2 text-xs font-semibold text-stone-700 shadow-sm">{primary ? "Add more" : "Select product"}</span>
                          {primary?.photo_url && (
                            <img src={primary.photo_url} alt={primary.product_name} className="h-16 w-16 flex-shrink-0 rounded-xl object-contain" />
                          )}
	                        </button>
	                      );
	                    })
                    )}
                      <div className="rounded-2xl border border-dashed border-emerald-200 bg-emerald-50/40 p-4">
                        <p className="text-xs font-semibold uppercase tracking-wide text-emerald-800">Add section</p>
                        <div className="mt-3 grid gap-2 sm:grid-cols-[1fr_auto]">
                          <input
                            value={newCustomSectionName}
                            onChange={(event) => setNewCustomSectionName(event.target.value)}
                            onKeyDown={(event) => {
                              if (event.key === "Enter") void addCustomSection();
                            }}
                            placeholder="Example: Berries, Branch Accent, Client Container"
                            className="rounded-xl border border-emerald-100 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-emerald-200"
                          />
                          <button
                            type="button"
                            onClick={() => void addCustomSection()}
                            disabled={!newCustomSectionName.trim()}
                            className="rounded-xl bg-emerald-800 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
                          >
                            Add section
                          </button>
                        </div>
                      </div>
	                  </div>
	                )}
                <div className="mt-5 flex w-fit items-center gap-2 rounded-2xl border border-stone-200 bg-white/90 px-3 py-2 text-sm text-stone-600 shadow-sm backdrop-blur">
                  <button type="button" className="flex h-7 w-7 items-center justify-center rounded-lg hover:bg-stone-100"><Minus size={14} /></button>
                  <span className="min-w-12 text-center text-xs font-semibold">100%</span>
                  <button type="button" className="flex h-7 w-7 items-center justify-center rounded-lg hover:bg-stone-100"><Plus size={14} /></button>
                </div>
              </section>

	              <aside className="flex h-full min-h-0 flex-col overflow-y-auto bg-white">
                <div className="border-b border-stone-100 px-5 py-4">
                  <div className="mb-3 flex items-center justify-between">
                    <div>
                      <p className="text-xs text-stone-400">Project / Builder</p>
                      <h3 className="text-lg font-semibold text-stone-900" style={{ fontFamily: "Georgia, serif" }}>
                        {builderStep === "type" && "Select type"}
                        {builderStep === "products" && (activePart ? `Select ${activePart.label}` : "Choose products")}
                        {builderStep === "mockup" && "Mockup setup"}
                        {builderStep === "review" && "Review selections"}
                        {builderStep === "po" && "Purchase Order Review"}
                      </h3>
                    </div>
                    <button onClick={() => setShowNewModal(false)} className="hidden text-stone-300"><X size={18} /></button>
                  </div>
                </div>

	                {builderStep === "type" && (
	                  <div className="space-y-4 p-5">
	                    <div>
                        <div className="mb-4 grid grid-cols-2 rounded-xl border border-stone-200 bg-stone-50 p-1">
                          {(["green", "christmas"] as BuilderSection[]).map((section) => (
                            <button
                              key={section}
                              type="button"
                              onClick={() => setSelectedProductSection(section)}
                              className={`rounded-lg px-3 py-2 text-sm font-semibold transition-colors ${
                                selectedProductSection === section ? "bg-white text-stone-950 shadow-sm" : "text-stone-500 hover:text-stone-800"
                              }`}
                            >
                              {section === "green" ? "Green" : "Christmas"}
                            </button>
                          ))}
                        </div>
	                      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
	                        <p className="text-xs font-semibold text-stone-500">Select a product type</p>
	                        {historicalProductTypeCount > 0 && (
	                          <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-emerald-800">
	                            {historicalProductTypeCount} build types
	                          </span>
	                        )}
	                      </div>
	                      {historicalProductTypeCount > 8 && (
	                        <label className="mb-3 flex items-center gap-2 rounded-xl border border-stone-200 bg-white px-3 py-2 text-sm text-stone-600">
	                          <Search size={15} className="text-stone-400" />
	                          <input
	                            value={productTypeSearch}
	                            onChange={(event) => setProductTypeSearch(event.target.value)}
	                            placeholder="Search product types"
	                            className="min-w-0 flex-1 bg-transparent outline-none placeholder:text-stone-400"
	                          />
	                        </label>
	                      )}
	                      <div className="max-h-[430px] space-y-3 overflow-y-auto pr-1" onMouseLeave={resetProductTypePreview}>
	                        {filteredProductTypeOptions.map(({ label, icon: Icon, evidence_count }) => {
	                          const selected = selectedScopeType === label;
	                          return (
	                            <button
	                              key={label}
	                              type="button"
	                              onMouseEnter={() => previewProductType(label)}
	                              onMouseLeave={resetProductTypePreview}
	                              onFocus={() => previewProductType(label)}
	                              onBlur={resetProductTypePreview}
	                              onClick={() => {
	                                previewProductType(label);
	                                setSelectedScopeType(label);
	                                if (label === "Custom") {
                                  setNewScopeName("");
                                  window.requestAnimationFrame(() => scopeNameRef.current?.focus());
                                  return;
                                }
                                if (!newScopeName.trim() || productTypeOptions.some((option) => option.label.toLowerCase() === newScopeName.trim().toLowerCase())) {
                                  setNewScopeName(label);
                                  if (scopeNameRef.current) scopeNameRef.current.value = label;
                                }
                                if (activeBucket) void applySelectedTypeToActiveBucket(label);
                              }}
	                              className={`flex min-h-[58px] w-full items-center justify-between rounded-xl border px-4 py-3 text-left transition-colors ${selected ? "border-stone-900 bg-white shadow-sm" : "border-stone-200 bg-white hover:border-stone-300"}`}
                            >
	                              <span className="flex items-center gap-3 text-sm font-semibold text-stone-800">
	                                <Icon size={17} strokeWidth={1.7} />
	                                <span>
	                                  {label}
	                                  {typeof evidence_count === "number" && evidence_count > 0 && (
		                                    <span className="ml-2 text-[11px] font-medium text-stone-400">{evidence_count} examples</span>
	                                  )}
	                                </span>
	                              </span>
                              {selected && <CheckCircle2 size={18} className="text-stone-900" />}
                            </button>
	                          );
	                        })}
	                      </div>
	                      {hiddenProductTypeCount > 0 && !productTypeSearch.trim() && (
	                        <button
	                          type="button"
	                          onClick={() => setShowAllProductTypes(true)}
	                          className="mt-3 w-full rounded-xl border border-dashed border-emerald-200 bg-emerald-50/40 px-4 py-2 text-sm font-semibold text-emerald-900 transition hover:bg-emerald-50"
	                        >
	                          Show {hiddenProductTypeCount} more build type{hiddenProductTypeCount === 1 ? "" : "s"}
	                        </button>
	                      )}
	                      {selectedScopeType === "Custom" && (
                        <div className="mt-4">
                          <label className="mb-2 block text-xs font-semibold text-stone-500">Custom product type</label>
                          <input ref={scopeNameRef} value={newScopeName} onChange={(e) => setNewScopeName(e.target.value)} placeholder="Type what you are building" className="w-full rounded-lg border border-stone-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300" />
                        </div>
                      )}
                      <div className="mt-4 grid grid-cols-[90px_1fr] gap-3">
                        <input ref={scopeQuantityRef} value={newScopeQuantity} onChange={(e) => setNewScopeQuantity(e.target.value)} type="number" min="1" aria-label="Quantity" className="rounded-lg border border-stone-200 px-3 py-2 text-sm" />
                        <input ref={scopeNotesRef} value={newScopeNotes} onChange={(e) => setNewScopeNotes(e.target.value)} placeholder="Optional notes" className="rounded-lg border border-stone-200 px-3 py-2 text-sm" />
                      </div>
                      {selectedScopeType === "Christmas Tree" ? (
                        <div className="mt-5 rounded-2xl border border-emerald-100 bg-emerald-50/40 p-4">
                          <div className="flex flex-wrap items-start justify-between gap-3">
                            <div>
                              <p className="text-xs font-semibold uppercase tracking-wide text-emerald-800">Christmas tree setup</p>
                              <p className="mt-1 text-xs text-emerald-900/70">Choose the tree size and shape. This sets the enhancer and ornament counts.</p>
                            </div>
                            <span className="rounded-full bg-white px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-emerald-800">
                              {CHRISTMAS_TREE_SIZE_OPTIONS.length} sizes
                            </span>
                          </div>
                          <label className="mt-4 block">
                            <span className="mb-1 block text-xs font-semibold text-stone-600">Tree size</span>
                            <select
                              value={selectedChristmasTreeCode}
                              onChange={(event) => selectChristmasTreeOption(event.target.value)}
                              className="w-full rounded-xl border border-emerald-100 bg-white px-3 py-2 text-sm font-medium text-stone-800 outline-none focus:ring-2 focus:ring-emerald-200"
                            >
                              <option value="">Select size and shape...</option>
                              {CHRISTMAS_TREE_SIZE_OPTIONS.map((tree) => (
                                <option key={tree.code} value={tree.code}>
                                  {tree.label}
                                </option>
                              ))}
                            </select>
                          </label>
                          {activeChristmasTreeOption ? (
                            <div className="mt-4 grid grid-cols-2 gap-2">
                              <div className="rounded-xl bg-white px-3 py-2">
                                <p className="text-[11px] font-semibold uppercase text-stone-400">Height</p>
                                <p className="mt-1 text-sm font-semibold text-stone-900">{activeChristmasTreeOption.heightLabel}</p>
                              </div>
                              <div className="rounded-xl bg-white px-3 py-2">
                                <p className="text-[11px] font-semibold uppercase text-stone-400">Diameter</p>
                                <p className="mt-1 text-sm font-semibold text-stone-900">{activeChristmasTreeOption.diameterIn}"</p>
                              </div>
                              <div className="rounded-xl bg-white px-3 py-2">
                                <p className="text-[11px] font-semibold uppercase text-stone-400">Shape</p>
                                <p className="mt-1 text-sm font-semibold text-stone-900">{activeChristmasTreeOption.profile}</p>
                              </div>
                              <div className="rounded-xl bg-white px-3 py-2">
                                <p className="text-[11px] font-semibold uppercase text-stone-400">Package counts</p>
                                <p className="mt-1 text-sm font-semibold text-stone-900">
                                  {activeChristmasTreeRule ? `${activeChristmasTreeRule.enhancers} enhancers / ${activeChristmasTreeRule.ornaments} ornaments` : "Set below"}
                                </p>
                              </div>
                            </div>
                          ) : (
                            <div className="mt-4 rounded-xl border border-dashed border-emerald-200 bg-white/70 px-3 py-3 text-xs text-emerald-900/70">
                              No tree size selected yet. Choose one above or use manual dimensions below.
                            </div>
                          )}
                          <div className="mt-4 grid gap-3 sm:grid-cols-3">
                            <label className="block">
                              <span className="mb-1 block text-xs font-semibold text-stone-500">Height override</span>
                              <input
                                value={treeHeight}
                                onChange={(event) => setTreeHeight(event.target.value)}
                                placeholder="e.g. 9.5 ft"
                                className="w-full rounded-lg border border-emerald-100 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
                              />
                            </label>
                            <label className="block">
                              <span className="mb-1 block text-xs font-semibold text-stone-500">Diameter override</span>
                              <input
                                value={treeCanopySize}
                                onChange={(event) => setTreeCanopySize(event.target.value)}
                                placeholder="e.g. 57 in"
                                className="w-full rounded-lg border border-emerald-100 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
                              />
                            </label>
                            <label className="block">
                              <span className="mb-1 block text-xs font-semibold text-stone-500">Profile</span>
                              <select
                                value={treeDensity}
                                onChange={(event) => setTreeDensity(event.target.value)}
                                className="w-full rounded-lg border border-emerald-100 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
                              >
                                <option value="">Select profile</option>
                                <option value="Pencil">Pencil</option>
                                <option value="Slim">Slim</option>
                                <option value="Standard">Standard</option>
                                <option value="Full">Full</option>
                              </select>
                            </label>
                          </div>
                        </div>
                      ) : selectedScopeType === "Garland" ? (
                        <div className="mt-5 rounded-2xl border border-emerald-100 bg-emerald-50/40 p-4">
                          <div className="flex flex-wrap items-start justify-between gap-3">
	                            <div>
	                              <p className="text-xs font-semibold uppercase tracking-wide text-emerald-800">Garland setup</p>
	                              <p className="mt-1 text-xs text-emerald-900/70">Choose the package and width. This sets the enhancer material counts.</p>
	                            </div>
	                            <span className="rounded-full bg-white px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-emerald-800">
	                              4 setups
	                            </span>
                          </div>
                          <div className="mt-4 grid gap-3">
                            <div>
                              <span className="mb-1 block text-xs font-semibold text-stone-600">Package</span>
                              <div className="grid grid-cols-2 rounded-xl border border-emerald-100 bg-white p-1 text-sm font-semibold">
                                {(["regular", "premium"] as GarlandPackage[]).map((packageType) => (
                                  <button
                                    key={packageType}
                                    aria-label={`Use ${packageType} garland package`}
                                    type="button"
                                    onClick={() => activeBucket && isGarlandBucket(activeBucket) ? void updateGarlandSetup({ packageType }) : setGarlandPackage(packageType)}
                                    className={`rounded-lg px-3 py-2 capitalize transition-colors ${
                                      garlandPackage === packageType ? "bg-emerald-50 text-stone-950 shadow-sm" : "text-stone-500 hover:text-stone-800"
                                    }`}
                                  >
                                    {packageType}
                                  </button>
                                ))}
                              </div>
                            </div>
	                            <div className="grid gap-3 sm:grid-cols-2">
                              <label className="block">
                                <span className="mb-1 block text-xs font-semibold text-stone-600">Length</span>
                                <input
                                  value={garlandLength}
                                  onChange={(event) => {
                                    const lengthValue = event.target.value;
                                    if (activeBucket && isGarlandBucket(activeBucket)) void updateGarlandSetup({ lengthValue });
                                    else setGarlandLength(lengthValue);
                                  }}
                                  placeholder="e.g. 9"
                                  className="w-full rounded-xl border border-emerald-100 bg-white px-3 py-2 text-sm font-medium text-stone-800 outline-none focus:ring-2 focus:ring-emerald-200"
                                />
                              </label>
                              <label className="block">
                                <span className="mb-1 block text-xs font-semibold text-stone-600">Diameter</span>
                                <select
                                  value={garlandDiameter}
                                  onChange={(event) => {
                                    const diameter = event.target.value as GarlandDiameter;
                                    if (activeBucket && isGarlandBucket(activeBucket)) void updateGarlandSetup({ diameter });
                                    else setGarlandDiameter(diameter);
                                  }}
                                  className="w-full rounded-xl border border-emerald-100 bg-white px-3 py-2 text-sm font-medium text-stone-800 outline-none focus:ring-2 focus:ring-emerald-200"
                                >
                                  {GARLAND_DIAMETER_OPTIONS.map((diameter) => (
                                    <option key={diameter} value={diameter}>
                                      {diameter}"
                                    </option>
                                  ))}
                                </select>
                              </label>
                            </div>
                          </div>
                          <div className="mt-4 grid grid-cols-2 gap-2">
                            <div className="rounded-xl bg-white px-3 py-2">
                              <p className="text-[11px] font-semibold uppercase text-stone-400">Length</p>
                              <p className="mt-1 text-sm font-semibold text-stone-900">{garlandLengthLabel(garlandLength)}</p>
                            </div>
                            <div className="rounded-xl bg-white px-3 py-2">
                              <p className="text-[11px] font-semibold uppercase text-stone-400">Diameter</p>
                              <p className="mt-1 text-sm font-semibold text-stone-900">{garlandDiameter}"</p>
                            </div>
                            <div className="rounded-xl bg-white px-3 py-2">
                              <p className="text-[11px] font-semibold uppercase text-stone-400">Enhancer mix</p>
                              <p className="mt-1 text-sm font-semibold text-stone-900">
                                {activeGarlandRule
                                  ? garlandPackage === "premium"
                                    ? `${activeGarlandRule.premiumEnhancers} premium + ${activeGarlandRule.regularEnhancers} regular`
                                    : `${activeGarlandRule.regularEnhancers} regular`
                                  : "Set above"}
                              </p>
                            </div>
                            <div className="rounded-xl bg-white px-3 py-2">
                              <p className="text-[11px] font-semibold uppercase text-stone-400">Extra ornaments</p>
                              <p className="mt-1 text-sm font-semibold text-stone-900">{activeGarlandRule?.extraOrnaments || 0}</p>
                            </div>
	                          </div>
		                          <div className="mt-4 rounded-2xl border border-emerald-100 bg-white px-3 py-2 text-xs font-medium leading-relaxed text-emerald-900">
		                            {garlandEnhancerCountSummary(garlandPackage, garlandLength, garlandDiameter)}
		                          </div>
                        </div>
                      ) : selectedScopeType === "Wreath" ? (
                        <div className="mt-5 rounded-2xl border border-emerald-100 bg-emerald-50/40 p-4">
                          <div className="flex flex-wrap items-start justify-between gap-3">
                            <div>
                              <p className="text-xs font-semibold uppercase tracking-wide text-emerald-800">Wreath setup</p>
                              <p className="mt-1 text-xs text-emerald-900/70">Choose the wreath diameter. This sets the branch, ribbon, flower, and ornament counts.</p>
                            </div>
                            <span className="rounded-full bg-white px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-emerald-800">
                              {WREATH_SIZE_OPTIONS.length} sizes
                            </span>
                          </div>
                          <div className="mt-4">
                            <span className="mb-1 block text-xs font-semibold text-stone-600">Wreath size</span>
                            <div className="grid grid-cols-2 gap-2">
                              {WREATH_SIZE_OPTIONS.map((size) => (
                                <button
                                  key={size}
                                  type="button"
                                  onClick={() => activeBucket && isWreathBucket(activeBucket) ? void updateWreathSetup(size) : setWreathSize(size)}
                                  className={`rounded-xl border px-3 py-2 text-sm font-semibold transition-colors ${
                                    wreathSize === size ? "border-emerald-200 bg-white text-stone-950 shadow-sm" : "border-emerald-100 bg-white/70 text-stone-500 hover:text-stone-800"
                                  }`}
                                >
                                  {size}" Wreath
                                </button>
                              ))}
                            </div>
                          </div>
                          <div className="mt-4 grid grid-cols-2 gap-2">
                            <div className="rounded-xl bg-white px-3 py-2">
                              <p className="text-[11px] font-semibold uppercase text-stone-400">Diameter</p>
                              <p className="mt-1 text-sm font-semibold text-stone-900">{wreathSize}"</p>
                            </div>
                            <div className="rounded-xl bg-white px-3 py-2">
                              <p className="text-[11px] font-semibold uppercase text-stone-400">Material lines</p>
                              <p className="mt-1 text-sm font-semibold text-stone-900">{activeWreathParts.length}</p>
                            </div>
                          </div>
                          <div className="mt-4 grid gap-2">
                            {activeWreathParts.map((part) => (
                              <div key={part.label} className="flex items-center justify-between gap-3 rounded-xl bg-white px-3 py-2 text-xs">
                                <span className="font-semibold text-emerald-950">{part.label}</span>
                                <span className="font-semibold text-emerald-800">{wreathDecorPartPreviewText(part.label, wreathSize)}</span>
                              </div>
                            ))}
                          </div>
                          <div className="mt-4 rounded-2xl border border-emerald-100 bg-white px-3 py-2 text-xs font-medium leading-relaxed text-emerald-900">
                            {wreathDecorCountSummary(wreathSize)}
                          </div>
                        </div>
                      ) : (
                        <div className="mt-5 rounded-2xl border border-stone-200 bg-stone-50/70 p-4">
                          <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Build dimensions</p>
                          <p className="mt-1 text-xs text-stone-400">These guide the recommendation before products are chosen.</p>
                          <div className="mt-4 grid gap-3">
                            <label className="block">
                              <span className="mb-1 block text-xs font-semibold text-stone-500">Height</span>
                              <input
                                value={treeHeight}
                                onChange={(event) => setTreeHeight(event.target.value)}
                                placeholder="e.g. 8 ft, 24 in, tabletop"
                                className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
                              />
                            </label>
                            <label className="block">
                              <span className="mb-1 block text-xs font-semibold text-stone-500">Width / canopy</span>
                              <input
                                value={treeCanopySize}
                                onChange={(event) => setTreeCanopySize(event.target.value)}
                                placeholder="e.g. full, narrow, 48 in"
                                className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
                              />
                            </label>
                            <label className="block">
                              <span className="mb-1 block text-xs font-semibold text-stone-500">Depth / density</span>
                              <input
                                value={treeDensity}
                                onChange={(event) => setTreeDensity(event.target.value)}
                                placeholder="e.g. light, medium, dense"
                                className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
                              />
                            </label>
                          </div>
                        </div>
                      )}
                      <button onClick={() => void goToProductParts()} disabled={savingBucket || (!activeBucket && !newScopeName.trim())} className="mt-5 w-full rounded-lg bg-stone-950 px-4 py-3 text-sm font-semibold text-white disabled:opacity-50">Next step →</button>
                    </div>
                  </div>
                )}

                {builderStep === "products" && activeBucket && (
                  <div ref={catalogRef} className="min-h-0 flex-1">
                    <BuilderProductPicker
                      products={products}
                      loadingCatalog={productsLoading}
                      activePartLabel={activePart ? activePart.label : "Products"}
                      initialQuery={searchTermsForPart(activeBucket, activePart?.label || "Products", activePart?.index || 0)}
                      selectedProductIds={new Set(itemsForPart(activeBucket, activePart?.label || "Products", activePart?.index || 0).map((item) => item.product_id))}
                      selectedProductItemIds={new Map(itemsForPart(activeBucket, activePart?.label || "Products", activePart?.index || 0).map((item) => [item.product_id, item.id]))}
                      onAdd={addProductToActiveBucket}
                      onRemove={removeItem}
                      onOpenProduct={setDetailProduct}
                      onContinue={() => goToBuilderStep("mockup")}
                      onReloadCatalog={() => void loadProducts()}
                      catalogTotal={productCatalogTotal}
                    />
                  </div>
                )}

                {builderStep === "mockup" && activeBucket && (
                  <div className="space-y-4 p-5">
                    <div className="rounded-2xl border border-stone-200 bg-white p-4">
                      <p className="text-sm font-semibold text-stone-900">AI mockup</p>
                      <p className="mt-1 text-xs text-stone-500">Mockup generation comes later. This page reserves the workflow for standalone product renders and room placement.</p>
                    </div>
                    <div className="grid grid-cols-3 gap-2">
                      {["Standalone product", "Place in a space", "Both"].map((label, index) => (
                        <button
                          key={label}
                          type="button"
                          className={`rounded-2xl border p-4 text-left text-xs transition-colors ${
                            index === 2 ? "border-emerald-300 bg-emerald-50/50 ring-1 ring-emerald-100" : "border-stone-200 bg-white hover:bg-stone-50"
                          }`}
                        >
                          <p className="font-semibold text-stone-900">{label}</p>
                          <p className="mt-2 text-stone-500">
                            {index === 0 ? "Clean product image." : index === 1 ? "Use a room photo later." : "Product and room view."}
                          </p>
                        </button>
                      ))}
                    </div>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div className="flex min-h-32 items-center justify-center rounded-2xl border border-dashed border-stone-300 bg-stone-50 text-center">
                        <div>
                          <Upload className="mx-auto text-stone-400" size={22} />
                          <p className="mt-2 text-sm font-semibold text-stone-700">Room photo placeholder</p>
                          <p className="mt-1 text-xs text-stone-400">Upload comes later.</p>
                        </div>
                      </div>
                      <label className="block">
                        <span className="mb-2 block text-xs font-semibold text-stone-500">Placement note</span>
                        <textarea
                          rows={5}
                          placeholder="Example: place near window, centered beside lounge chair."
                          className="w-full resize-none rounded-2xl border border-stone-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
                        />
                      </label>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <button onClick={() => goToBuilderStep("review")} className="rounded-lg border border-stone-200 px-4 py-2.5 text-sm font-semibold text-stone-700">Skip mockup</button>
                      <button onClick={() => goToBuilderStep("review")} className="rounded-lg bg-emerald-800 px-4 py-2.5 text-sm font-semibold text-white">Continue to review</button>
                    </div>
                  </div>
                )}

                {builderStep === "review" && activeBucket && (
                  <div className="space-y-4 p-5">
                    <div className="rounded-2xl border border-stone-200 bg-white p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="font-semibold text-stone-900">Review {scopeTitle(activeBucket)}</p>
                          <p className="mt-1 text-xs text-stone-400">Saved ideas stay as candidates. Selected products count toward cost and purchase order.</p>
                        </div>
	                        <div className="rounded-xl bg-emerald-50 px-3 py-2 text-right">
	                          <p className="text-[11px] font-semibold uppercase tracking-wide text-emerald-700">Selected cost</p>
	                          <p className="font-semibold text-emerald-900">{formatCurrency(activeBucket.subtotal)}</p>
                            {activeMechanicsEstimate > 0 && (
                              <p className="mt-1 text-[11px] font-medium text-emerald-800">+ {formatCurrency(activeMechanicsEstimate)} mechanics est.</p>
                            )}
	                        </div>
                      </div>
                    </div>
	                    {scopePlaceholders(activeBucket).map((label, index) => {
                      if (isWreathBucket(activeBucket) && isWreathDecorPart(label)) {
                        const activeSize = wreathSizeFromNotes(activeBucket.scope_notes);
                        const wreathRows = wreathDecorPartsForSize(activeSize).map((part) => {
                          const subIndex = wreathDecorPartSubIndex(part.label);
                          const partIndex = christmasEnhancerPartIndex(index, subIndex);
                          return {
                            label: part.label,
                            target: wreathDecorPartPreviewText(part.label, activeSize),
                            partIndex,
                            subItems: wreathDecorPartItems(activeBucket, index, subIndex),
                          };
                        });
                        return (
                          <div key={`${label}-review`} className="rounded-2xl border border-emerald-100 bg-white p-3">
                            <div className="mb-3 flex items-center justify-between">
                              <div>
                                <p className="text-xs font-semibold uppercase tracking-wide text-emerald-800">{activeSize}" Wreath Decor Package</p>
                                <p className="mt-1 text-xs text-stone-400">{wreathDecorCountSummary(activeSize)}</p>
                              </div>
                            </div>
                            <div className="space-y-3">
                              {wreathRows.map((part) => {
                                const subItems = part.subItems;
                                return (
                                  <div key={`${part.label}-review`} className="rounded-xl border border-emerald-50 bg-emerald-50/30 p-3">
                                    <div className="mb-2 flex items-center justify-between gap-3">
                                      <div>
                                        <p className="text-sm font-semibold text-stone-900">{part.label}</p>
                                        <p className="text-xs text-stone-500">{part.target}</p>
                                      </div>
                                      <button
                                        type="button"
                                        onClick={() => { setActivePart({ label: part.label, index: part.partIndex }); enterProductPicker(); }}
                                        className="text-xs font-semibold text-emerald-800 hover:text-emerald-900"
                                      >
                                        Edit
                                      </button>
                                    </div>
                                    {subItems.length === 0 ? (
                                      <button
                                        type="button"
                                        onClick={() => { setActivePart({ label: part.label, index: part.partIndex }); enterProductPicker(); }}
                                        className="flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-emerald-200 bg-white py-3 text-sm font-semibold text-stone-500 hover:border-emerald-300 hover:bg-emerald-50/40"
                                      >
                                        <Plus size={16} />
                                        Add {part.label}
                                      </button>
                                    ) : subItems.map((item) => {
                                      const status = item.status || "selected";
                                      return (
                                        <div key={item.id} className={`mb-2 flex items-center gap-3 rounded-xl border p-2 last:mb-0 ${status === "selected" ? "border-emerald-200 bg-white" : "border-stone-100 bg-stone-50"}`}>
                                          {item.photo_url ? <img src={item.photo_url} alt={item.product_name} className="h-12 w-12 rounded-lg object-contain" /> : <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-white text-[10px] font-semibold text-stone-400">No image</div>}
                                          <div className="min-w-0 flex-1">
                                            <p className="truncate text-sm font-medium text-stone-800">{item.product_name}</p>
                                            <p className="text-xs text-stone-400">{item.supplier_sku || item.supplier_name} · {formatCurrency(item.current_price)} / {unitLabel(item.unit)}</p>
                                          </div>
                                          <button onClick={() => updateStatus(item.id, status === "selected" ? "candidate" : "selected")} className={`rounded-full px-3 py-1 text-[11px] font-semibold ${status === "selected" ? "bg-emerald-800 text-white" : "bg-white text-stone-500 ring-1 ring-stone-200"}`}>{status === "selected" ? "Selected" : "Candidate"}</button>
                                        </div>
                                      );
                                    })}
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        );
                      }
	                      if (isStructuredChristmasBucket(activeBucket) && isEnhancersPart(label)) {
                        const garlandEnhancers = isGarlandBucket(activeBucket);
                        const packageType = garlandEnhancers
                          ? garlandPackageFromNotes(activeBucket.scope_notes)
                          : christmasEnhancerPackageFromNotes(activeBucket.scope_notes);
                        const enhancerRows = garlandEnhancers
                          ? garlandEnhancerPartsForPackage(packageType).map((part) => {
                              const subIndex = garlandEnhancerPartSubIndex(part.label);
                              const partIndex = christmasEnhancerPartIndex(index, subIndex);
                              return {
                                label: part.label,
                                target: garlandEnhancerPartPreviewText(part.label, packageType, garlandLengthFromNotes(activeBucket.scope_notes)),
                                partIndex,
                                subItems: garlandEnhancerPartItems(activeBucket, index, subIndex),
                              };
                            })
                          : christmasEnhancerPartsForPackage(packageType).map((part) => {
                              const subIndex = christmasEnhancerPartSubIndex(part.label);
                              const partIndex = christmasEnhancerPartIndex(index, subIndex);
                              return {
                                label: part.label,
                                target: christmasEnhancerPartTargetText(activeBucket, part.label),
                                partIndex,
                                subItems: christmasEnhancerPartItems(activeBucket, index, subIndex),
                              };
                            });
                        return (
                          <div key={`${label}-review`} className="rounded-2xl border border-emerald-100 bg-white p-3">
                            <div className="mb-3 flex items-center justify-between">
                              <div>
                                <p className="text-xs font-semibold uppercase tracking-wide text-emerald-800">{packageType === "premium" ? "Premium" : "Regular"} {label}</p>
                                <p className="mt-1 text-xs text-stone-400">{christmasPartGuidance(activeBucket, label)}</p>
                              </div>
                            </div>
                            <div className="space-y-3">
                              {enhancerRows.map((part) => {
                                const subItems = part.subItems;
                                return (
                                  <div key={`${part.label}-review`} className="rounded-xl border border-emerald-50 bg-emerald-50/30 p-3">
                                    <div className="mb-2 flex items-center justify-between gap-3">
                                      <div>
                                        <p className="text-sm font-semibold text-stone-900">{part.label}</p>
                                        <p className="text-xs text-stone-500">{part.target}</p>
                                      </div>
                                      <button
                                        type="button"
                                        onClick={() => { setActivePart({ label: part.label, index: part.partIndex }); enterProductPicker(); }}
                                        className="text-xs font-semibold text-emerald-800 hover:text-emerald-900"
                                      >
                                        Edit
                                      </button>
                                    </div>
                                    {subItems.length === 0 ? (
                                      <button
                                        type="button"
                                        onClick={() => { setActivePart({ label: part.label, index: part.partIndex }); enterProductPicker(); }}
                                        className="flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-emerald-200 bg-white py-3 text-sm font-semibold text-stone-500 hover:border-emerald-300 hover:bg-emerald-50/40"
                                      >
                                        <Plus size={16} />
                                        Add {part.label}
                                      </button>
                                    ) : subItems.map((item) => {
                                      const status = item.status || "selected";
                                      return (
                                        <div key={item.id} className={`mb-2 flex items-center gap-3 rounded-xl border p-2 last:mb-0 ${status === "selected" ? "border-emerald-200 bg-white" : "border-stone-100 bg-stone-50"}`}>
                                          {item.photo_url ? <img src={item.photo_url} alt={item.product_name} className="h-12 w-12 rounded-lg object-contain" /> : <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-white text-[10px] font-semibold text-stone-400">No image</div>}
                                          <div className="min-w-0 flex-1">
                                            <p className="truncate text-sm font-medium text-stone-800">{item.product_name}</p>
                                            <p className="text-xs text-stone-400">{item.supplier_sku || item.supplier_name} · {formatCurrency(item.current_price)} / {unitLabel(item.unit)}</p>
                                          </div>
                                          <button onClick={() => updateStatus(item.id, status === "selected" ? "candidate" : "selected")} className={`rounded-full px-3 py-1 text-[11px] font-semibold ${status === "selected" ? "bg-emerald-800 text-white" : "bg-white text-stone-500 ring-1 ring-stone-200"}`}>{status === "selected" ? "Selected" : "Candidate"}</button>
                                        </div>
                                      );
                                    })}
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        );
                      }
                      return (
                      <div key={`${label}-review`} className="rounded-2xl border border-stone-200 bg-white p-3">
                        <div className="mb-2 flex items-center justify-between">
                          <p className="text-xs font-semibold uppercase tracking-wide text-stone-400">{label}</p>
                          <button
                            type="button"
                            onClick={() => { setActivePart({ label, index }); enterProductPicker(); }}
                            className="text-xs font-semibold text-emerald-800 hover:text-emerald-900"
                          >
                            Edit product
                          </button>
                        </div>
                        {itemsForPart(activeBucket, label, index).length === 0 ? (
                          <button
                            type="button"
                            onClick={() => { setActivePart({ label, index }); enterProductPicker(); }}
                            className="flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-stone-300 py-4 text-sm font-semibold text-stone-500 hover:border-emerald-300 hover:bg-emerald-50/40"
                          >
                            <Plus size={16} />
                            Add product
                          </button>
                        ) : itemsForPart(activeBucket, label, index).map((item) => {
                          const status = item.status || "selected";
                          return (
                            <div key={item.id} className={`mb-2 flex items-center gap-3 rounded-xl border p-2 last:mb-0 ${status === "selected" ? "border-emerald-200 bg-emerald-50/40" : "border-stone-100 bg-stone-50"}`}>
                              {item.photo_url ? <img src={item.photo_url} alt={item.product_name} className="h-12 w-12 rounded-lg object-contain" /> : <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-white text-[10px] font-semibold text-stone-400">No image</div>}
                              <div className="min-w-0 flex-1">
                                <p className="truncate text-sm font-medium text-stone-800">{item.product_name}</p>
                                <p className="text-xs text-stone-400">{item.supplier_sku || item.supplier_name} · {formatCurrency(item.current_price)} / {unitLabel(item.unit)}</p>
                              </div>
                              <button onClick={() => updateStatus(item.id, status === "selected" ? "candidate" : "selected")} className={`rounded-full px-3 py-1 text-[11px] font-semibold ${status === "selected" ? "bg-emerald-800 text-white" : "bg-white text-stone-500 ring-1 ring-stone-200"}`}>{status === "selected" ? "Selected" : "Candidate"}</button>
                            </div>
                          );
                        })}
                      </div>
                      );
                    })}
                    <div className="grid grid-cols-2 gap-3">
                      <button onClick={() => goToBuilderStep("mockup")} className="rounded-lg border border-stone-200 px-4 py-2.5 text-sm font-semibold text-stone-700">Back to mockup</button>
                      <button onClick={() => goToBuilderStep("po")} className="rounded-lg bg-emerald-800 px-4 py-2.5 text-sm font-semibold text-white">Purchase order review</button>
                    </div>
                  </div>
                )}

                {builderStep === "po" && activeBucket && (
                  <div className="space-y-4 p-5">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <h3 className="text-lg font-semibold text-stone-900" style={{ fontFamily: "Georgia, serif" }}>Purchase Order Review</h3>
                        <p className="text-xs text-stone-400">Drafted from selected products only.</p>
                      </div>
                    </div>
                    <div className="overflow-hidden rounded-2xl border border-stone-200">
                      {orderItems.length > 0 && (
                        <div className="grid grid-cols-[1.3fr_1fr_52px_82px_86px] gap-3 border-b border-stone-100 bg-stone-50 px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-stone-400">
                          <span>Part</span>
                          <span>Vendor</span>
                          <span className="text-right">Qty</span>
                          <span className="text-right">Unit price</span>
                          <span className="text-right">Line total</span>
                        </div>
                      )}
                      {orderItems.length === 0 ? (
                        <p className="p-4 text-sm text-stone-400">No products selected for this built product yet.</p>
                      ) : orderItems.map((item) => (
                        <div key={item.id} className="grid grid-cols-[1.3fr_1fr_52px_82px_86px] gap-3 border-b border-stone-100 p-3 text-sm last:border-b-0">
                          <div className="flex min-w-0 items-center gap-3">
                            {item.photo_url ? <img src={item.photo_url} alt={item.product_name} className="h-11 w-11 rounded-lg object-contain" /> : <div className="h-11 w-11 rounded-lg bg-stone-100" />}
                            <div className="min-w-0">
                              <p className="truncate font-medium text-stone-800">{item.part_label || "Product"}</p>
                              <p className="truncate text-xs text-stone-500">{item.product_name}</p>
                              <p className="text-[11px] text-stone-400">{item.supplier_sku || ""}</p>
                            </div>
                          </div>
                          <div className="min-w-0 self-center">
                            <p className="truncate text-stone-700">{item.supplier_name || "Supplier"}</p>
                            <p className="text-xs text-stone-400">Source price</p>
                          </div>
                          <p className="self-center text-right text-stone-500">{Number(item.quantity) || 1}</p>
                          <p className="self-center text-right text-stone-700">{formatCurrency(item.current_price)}</p>
                          <p className="self-center text-right font-semibold text-stone-900">{formatCurrency((Number(item.current_price) || 0) * (Number(item.quantity) || 1))}</p>
                        </div>
                      ))}
                    </div>
	                    <div className="rounded-2xl border border-stone-200 p-4">
	                      <div className="flex justify-between text-sm"><span>Product subtotal</span><strong>{formatCurrency(orderSubtotal)}</strong></div>
                        {activeMechanicsEstimate > 0 && (
                          <div className="mt-2 flex justify-between text-sm text-stone-500"><span>Mechanics & materials estimate</span><span>{formatCurrency(activeMechanicsEstimate)}</span></div>
                        )}
	                      <div className="mt-2 flex justify-between text-sm text-stone-500"><span>Estimated freight</span><span>Set later</span></div>
	                      <div className="mt-2 flex justify-between text-sm text-stone-500"><span>Tax estimate</span><span>Set later</span></div>
	                      <div className="mt-3 flex justify-between border-t border-stone-100 pt-3 text-base"><span>Total estimate</span><strong>{formatCurrency(orderSubtotal + activeMechanicsEstimate)}</strong></div>
	                    </div>
                    <div className="rounded-2xl border border-emerald-100 bg-emerald-50/40 p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-stone-900">Finished product SKU</p>
                          <p className="mt-1 text-xs leading-relaxed text-stone-500">Use this after approval, payment, purchase, and fulfillment to add the finished build back into historical intelligence.</p>
                        </div>
                        <span className="rounded-full bg-white px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-emerald-800">Final only</span>
                      </div>
                      <div className="mt-4 grid gap-3 sm:grid-cols-[1fr_auto]">
	                        <input
	                          value={finishedSku}
	                          onChange={(event) => {
                              setSkuEdited(true);
                              setFinishedSku(event.target.value);
                            }}
	                          placeholder={suggestedFinishedSku(activeBucket, arrangement)}
	                          className="rounded-lg border border-emerald-100 bg-white px-3 py-2 text-sm font-semibold uppercase tracking-wide text-stone-800 focus:outline-none focus:ring-2 focus:ring-emerald-300"
	                        />
                        <button
                          type="button"
                          onClick={() => void completeHistoricalBuild()}
                          className="rounded-lg border border-emerald-200 bg-white px-4 py-2 text-sm font-semibold text-emerald-900 hover:bg-emerald-50"
                        >
                          Add to Historical Data
                        </button>
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <button onClick={() => goToBuilderStep("review")} className="rounded-lg border border-stone-200 px-4 py-2.5 text-sm font-semibold text-stone-700">Back to mockups</button>
                      <button onClick={() => navigate(`/invoice?arrangement_id=${arrangement.id}`)} className="rounded-lg bg-emerald-800 px-4 py-2.5 text-sm font-semibold text-white">Create purchase order</button>
                    </div>
                  </div>
                )}
              </aside>
            </div>
          </div>
          )}
        </>
      ) : (
        <div className="flex flex-col items-center justify-center px-10 py-40 text-center">
          <p className="text-base font-medium text-stone-700">Project could not load</p>
          <p className="mt-1 max-w-sm text-sm leading-relaxed text-stone-400">
            Go back to All Projects and open it again. The catalog add button will stay on the page when the project is loaded.
          </p>
          <button
            onClick={clearSelection}
            className="mt-4 rounded-lg px-4 py-2 text-sm font-semibold text-white hover:opacity-90"
            style={{ backgroundColor: "#2d5a33" }}
          >
            Back to projects
          </button>
        </div>
      )}

      {showNewModal && (
        <NewProjectModal
          initialClientName={clientFilter === "Unassigned" ? "" : clientFilter}
          onClose={() => setShowNewModal(false)}
          onCreated={(arr) => {
            setArrangements((prev) => {
              const next = [{ ...arr, container_count: 0 }, ...prev];
              writeProjectsListCache(next);
              return next;
            });
            setListSettled(true);
            setListCachedAt(Date.now());
            notifyProjectsChanged();
          }}
        />
      )}
      {detailProduct && <ProductDetailModal product={detailProduct} onClose={() => setDetailProduct(null)} />}
    </Layout>
  );
}
