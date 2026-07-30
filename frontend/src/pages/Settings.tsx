import React, { useEffect, useMemo, useState } from "react";
import {
  Check,
  CheckCircle2,
  Database,
  DollarSign,
  Grid3X3,
  Image,
  Monitor,
  Moon,
  Palette,
  Plus,
  RefreshCw,
  Save,
  Settings as SettingsIcon,
  Sun,
  Tags,
  Trash2,
  Users,
} from "lucide-react";
import Layout from "components/Layout";
import SidebarTabsEditor from "components/SidebarTabsEditor";
import { apiClient } from "app";
import { ContentType } from "../apiclient/http-client";
import { categoryLabel } from "utils/format";
import { THEME_ACCENTS, useTheme } from "utils/theme";
import { toast } from "sonner";

const CATEGORIES = ["plant", "container", "filler", "accent", "other"];

type CategoryMarkup = { id: number; category: string; markup_percentage: number; updated_at: string };
type ImportStatus = {
  source_root: string;
  statuses: Array<{ status: string; count: number }>;
  extensions: Array<{ extension: string; count: number }>;
  recipe_count: number;
  component_count: number;
  asset_count: number;
  failures: Array<{ relative_path: string; status: string; error_message?: string }>;
  parser_version: string;
};
type PricingRules = { global_rules: Record<string, unknown>; project_rules?: Record<string, unknown> | null; source_rules: Array<{ scope: string; rules: Record<string, unknown>; updated_at: string }> };
type SkuStandard = { prefix: string; label: string; description?: string; inferred_count: number; examples?: string[]; active: boolean; updated_at: string };
type VisualReference = { id: number; item_code?: string; file_name: string; extension: string; asset_type: string; status: string; file_path: string };
type PricingRuleKey = "landed_cost_multiplier" | "retail_multiplier" | "wholesale_multiplier" | "arrangement_markup_multiplier";
type PricingRuleForm = Record<PricingRuleKey, string>;
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
type BuildTemplateListKey = "slots" | "usedFor" | "regularMaterials" | "premiumMaterials";

const TABS = [
  { id: "markup", label: "Markup", icon: DollarSign },
  { id: "pricing", label: "Pricing Rules", icon: SettingsIcon },
  { id: "sku", label: "SKU Standards", icon: Tags },
  { id: "ai", label: "AI Reference Data", icon: Image },
  { id: "import", label: "Import Status", icon: Database },
  { id: "templates", label: "Build Templates", icon: Grid3X3 },
  { id: "appearance", label: "Appearance", icon: Palette },
] as const;

type SettingsTab = typeof TABS[number]["id"];

const THEME_MODE_CHOICES = [
  {
    mode: "system" as const,
    label: "System",
    icon: Monitor,
    helper: "Follow the light or dark setting on this device.",
  },
  {
    mode: "light" as const,
    label: "Light",
    icon: Sun,
    helper: "Warm cream pages with dark text.",
  },
  {
    mode: "dark" as const,
    label: "Dark",
    icon: Moon,
    helper: "Deep forest pages for low-light work.",
  },
];

const PRICING_FIELDS: Array<{ key: PricingRuleKey; label: string; helper: string; example: string }> = [
  {
    key: "landed_cost_multiplier",
    label: "Landed cost factor",
    helper: "Landed cost is the total price of a product once it reaches a buyer's doorstep. This turns supplier cost into our real cost after shipping, freight, and handling.",
    example: "If the supplier price is $100, 1.20 makes our real cost $120.",
  },
  {
    key: "retail_multiplier",
    label: "Retail price factor",
    helper: "Retail price is the standard price a client sees and pays. This turns our real cost into the customer-facing selling price.",
    example: "If our real cost is $120, 6.00 makes the retail price $720.",
  },
  {
    key: "wholesale_multiplier",
    label: "Wholesale price factor",
    helper: "Wholesale price is a lower trade price for designers, dealers, or bulk buyers. This sets the discounted selling price.",
    example: "If our real cost is $120, 3.00 makes the wholesale price $360.",
  },
  {
    key: "arrangement_markup_multiplier",
    label: "Arrangement build factor",
    helper: "Arrangement build means the labor, mechanics, design time, and skill needed to turn parts into a finished custom piece.",
    example: "If the build subtotal is $400, 1.25 makes the final price $500.",
  },
];

const DEFAULT_PRICING_FORM: PricingRuleForm = {
  landed_cost_multiplier: "1.2",
  retail_multiplier: "6",
  wholesale_multiplier: "3",
  arrangement_markup_multiplier: "1.25",
};

const BUILD_TEMPLATE_STORAGE_KEY = "leaf-ledger:build-templates:v1";

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

// The green templates above used to list their slots top-down (container first). They now
// read bottom-up to match how a build is physically assembled. Only the ORDER changed - no
// slot label was renamed. A stored copy that still holds the old order verbatim is migrated
// in cleanTemplateList; any order the user customised is left untouched.
const LEGACY_TOP_DOWN_SLOT_ORDERS: Record<string, string[]> = {
  "green-tree": ["Container", "Top Dressing", "Trunks & Branches", "Leaves"],
  arrangement: ["Container/Base", "Finish/Top Dressing", "Focal Material", "Accent Material"],
  planter: ["Container/Planter", "Finish/Top Dressing", "Main Plant", "Accent Plant"],
  "drop-in": ["Drop-in Base", "Main Material", "Accent Material", "Finish"],
  succulent: ["Container/Base", "Finish/Top Dressing", "Succulents/Cactus", "Accent Greenery"],
};

const PREVIEWABLE_VISUAL_EXTENSIONS = new Set([".png", ".jpg", ".jpeg", ".gif", ".webp", ".psd"]);
const SKU_FAMILY_LABELS: Record<string, string> = {
  TT: "Tree",
  OR: "Orchid Arrangement",
  WG: "Greenery Arrangement",
  SG: "Succulent Arrangement",
  CG: "Container Garden",
  FP: "Foliage Arrangement",
  TL: "Tree / Plant",
  SM: "Moss Arrangement",
  DR: "Drop-in Arrangement",
  CT: "Container Arrangement",
  DI: "Drop-in Arrangement",
  GT: "Greenery Tree",
  PV: "Plant / Vase",
  PM: "Premade",
};

function parseHistoricalSku(code?: string) {
  const normalized = String(code || "").trim().toUpperCase();
  if (!normalized) return null;
  const parts = normalized.split("-").filter(Boolean);
  if (parts.length < 3) return null;
  const familyMatch = parts[0].match(/^([A-Z]+)(.*)$/);
  if (!familyMatch) return null;
  return {
    fullCode: normalized,
    family: familyMatch[1],
    series: familyMatch[2],
    identifier: parts.slice(1, -1).join("-"),
    year: parts[parts.length - 1],
  };
}

function itemCodePrefix(itemCode?: string) {
  const match = String(itemCode || "").trim().toUpperCase().match(/^([A-Z]+)/);
  return match?.[1] || "";
}

function canPreviewVisualReference(asset: VisualReference) {
  return PREVIEWABLE_VISUAL_EXTENSIONS.has(String(asset.extension || "").toLowerCase());
}

function visualPreviewUrl(asset: VisualReference) {
  return `/api/recipe-intelligence/visual-references/${asset.id}/preview`;
}

function visualExtensionLabel(asset: VisualReference) {
  return String(asset.extension || "").replace(".", "").toUpperCase() || "FILE";
}

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

function readBuildTemplates() {
  try {
    return cleanTemplateList(JSON.parse(window.localStorage.getItem(BUILD_TEMPLATE_STORAGE_KEY) || "null"));
  } catch {
    return DEFAULT_BUILD_TEMPLATES;
  }
}

function writeBuildTemplates(templates: BuildTemplate[]) {
  window.localStorage.setItem(BUILD_TEMPLATE_STORAGE_KEY, JSON.stringify(cleanTemplateList(templates)));
}

function rulesToForm(rules?: Record<string, unknown>): PricingRuleForm {
  return PRICING_FIELDS.reduce((form, field) => {
    const value = Number(rules?.[field.key]);
    return { ...form, [field.key]: Number.isFinite(value) && value > 0 ? String(value) : DEFAULT_PRICING_FORM[field.key] };
  }, {} as PricingRuleForm);
}

function formatRuleValue(rules: Record<string, unknown>, key: PricingRuleKey) {
  const value = Number(rules?.[key]);
  return Number.isFinite(value) ? value.toFixed(2).replace(/\.00$/, "") : "Not set";
}

function sourceFormulaFor(field: PricingRuleKey, value: number) {
  const factor = value.toFixed(2).replace(/\.00$/, "");
  switch (field) {
    case "landed_cost_multiplier":
      return {
        title: "First cost to landed cost",
        formula: `First cost x ${factor} = landed cost`,
        meaning: value > 1 ? `This adds about ${Math.round((value - 1) * 100)}% for freight, handling, and landed cost.` : "This keeps landed cost equal to first cost.",
      };
    case "retail_multiplier":
      return {
        title: "Landed cost to retail",
        formula: `Landed cost x ${factor} = retail price`,
        meaning: "This is the standard retail pricing multiplier from the old formula sheet.",
      };
    case "wholesale_multiplier":
      return {
        title: "Landed cost to wholesale",
        formula: `Landed cost x ${factor} = wholesale price`,
        meaning: "This is the standard wholesale pricing multiplier from the old formula sheet.",
      };
    case "arrangement_markup_multiplier":
      return {
        title: "Build subtotal to arrangement price",
        formula: `Build subtotal x ${factor} = arrangement price`,
        meaning: value > 1 ? `This adds about ${Math.round((value - 1) * 100)}% for labor, mechanics, and build complexity.` : "This keeps the arrangement price equal to the build subtotal.",
      };
  }
}

async function readJson<T>(response: any): Promise<T> {
  if (!response.ok) throw new Error(await response.text().catch(() => "Request failed"));
  return response.json();
}

export default function Settings() {
  const [activeTab, setActiveTab] = useState<SettingsTab>("markup");
  const { mode, accent, setMode, setAccent } = useTheme();
  const [globalMarkup, setGlobalMarkup] = useState(30);
  const [categoryMarkups, setCategoryMarkups] = useState<CategoryMarkup[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [addingCategory, setAddingCategory] = useState(false);
  const [newCat, setNewCat] = useState("");
  const [newCatMarkup, setNewCatMarkup] = useState("30");
  const [importStatus, setImportStatus] = useState<ImportStatus | null>(null);
  const [importing, setImporting] = useState(false);
  const [pricingRules, setPricingRules] = useState<PricingRules | null>(null);
  const [pricingForm, setPricingForm] = useState<PricingRuleForm>(DEFAULT_PRICING_FORM);
  const [skuStandards, setSkuStandards] = useState<SkuStandard[]>([]);
  const [visualRefs, setVisualRefs] = useState<VisualReference[]>([]);
  const [buildTemplates, setBuildTemplates] = useState<BuildTemplate[]>(() => readBuildTemplates());
  const [templateFilter, setTemplateFilter] = useState<"All" | "Green" | "Christmas">("All");

  const statusTotal = useMemo(
    () => (importStatus?.statuses || []).reduce((sum, row) => sum + Number(row.count || 0), 0),
    [importStatus]
  );
  const skuLabelsByPrefix = useMemo(
    () => new Map(skuStandards.map((standard) => [standard.prefix, standard.label])),
    [skuStandards]
  );
  const visualReferenceGroups = useMemo(() => {
    const groups = new Map<string, { key: string; prefix: string; label: string; assets: VisualReference[]; previewableCount: number }>();
    visualRefs.forEach((asset) => {
      const prefix = itemCodePrefix(asset.item_code);
      const key = prefix || "unmatched";
      const label = prefix ? skuLabelsByPrefix.get(prefix) || SKU_FAMILY_LABELS[prefix] || `${prefix} Family` : "Unmatched / Needs Item Code";
      const existing = groups.get(key) || { key, prefix, label, assets: [], previewableCount: 0 };
      existing.assets.push(asset);
      if (canPreviewVisualReference(asset)) existing.previewableCount += 1;
      groups.set(key, existing);
    });
    return Array.from(groups.values())
      .map((group) => ({
        ...group,
        assets: [...group.assets].sort((a, b) => {
          const previewSort = Number(canPreviewVisualReference(b)) - Number(canPreviewVisualReference(a));
          if (previewSort !== 0) return previewSort;
          return `${a.item_code || ""} ${a.file_name}`.localeCompare(`${b.item_code || ""} ${b.file_name}`);
        }),
      }))
      .sort((a, b) => {
        if (a.key === "unmatched") return 1;
        if (b.key === "unmatched") return -1;
        return a.label.localeCompare(b.label);
      });
  }, [skuLabelsByPrefix, visualRefs]);
  const visibleBuildTemplates = useMemo(
    () => buildTemplates.filter((template) => templateFilter === "All" || template.section === templateFilter),
    [buildTemplates, templateFilter]
  );

  const loadMarkup = async () => {
    const data = await apiClient.get_markup_settings().then((r) => r.json());
    setGlobalMarkup(data.global_markup);
    setCategoryMarkups(data.category_markups);
  };

  const loadImportStatus = async () => {
    const data = await readJson<ImportStatus>(await apiClient.request({ path: "/routes/recipe-intelligence/import-status", method: "GET" }));
    setImportStatus(data);
  };

  const loadPricingRules = async () => {
    const data = await readJson<PricingRules>(await apiClient.request({ path: "/routes/pricing-rules", method: "GET" }));
    setPricingRules(data);
    setPricingForm(rulesToForm(data.global_rules));
  };

  const loadSkuStandards = async () => {
    const data = await readJson<SkuStandard[]>(await apiClient.request({ path: "/routes/sku-standards", method: "GET" }));
    setSkuStandards(Array.isArray(data) ? data : []);
  };

  const loadVisualRefs = async () => {
    const data = await readJson<VisualReference[]>(await apiClient.request({ path: "/routes/recipe-intelligence/visual-references?limit=200", method: "GET" }));
    setVisualRefs(Array.isArray(data) ? data : []);
  };

  const loadAll = async () => {
    try {
      await Promise.allSettled([loadMarkup(), loadImportStatus(), loadPricingRules(), loadSkuStandards(), loadVisualRefs()]);
    } catch {
      toast.error("Failed to load settings");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void loadAll(); }, []);

  const saveGlobal = async () => {
    setSaving(true);
    try {
      await apiClient.update_markup({ category: null, markup_percentage: globalMarkup });
      toast.success("Global markup saved");
    } catch {
      toast.error("Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const saveCategoryMarkup = async (category: string, value: number) => {
    try {
      await apiClient.update_markup({ category, markup_percentage: value });
      toast.success(`${categoryLabel(category)} markup saved`);
    } catch {
      toast.error("Failed to save");
    }
  };

  const deleteCategoryMarkup = async (category: string) => {
    try {
      await apiClient.delete_category_markup({ category });
      setCategoryMarkups((prev) => prev.filter((m) => m.category !== category));
      toast.success("Category override removed");
    } catch {
      toast.error("Failed to delete");
    }
  };

  const addCategoryMarkup = async () => {
    if (!newCat) { toast.error("Select a category"); return; }
    if (categoryMarkups.some((m) => m.category === newCat)) { toast.error("Override already exists for this category"); return; }
    try {
      await apiClient.update_markup({ category: newCat, markup_percentage: parseFloat(newCatMarkup) });
      await loadMarkup();
      setAddingCategory(false);
      setNewCat("");
      setNewCatMarkup("30");
      toast.success("Category markup added");
    } catch {
      toast.error("Failed to add");
    }
  };

  const runImportBatch = async () => {
    setImporting(true);
    try {
      const data = await readJson<{ processed: number; summary: ImportStatus }>(await apiClient.request({
        path: "/routes/recipe-intelligence/import",
        method: "POST",
        body: { limit: 50, include_assets: true },
        type: ContentType.Json,
      }));
      setImportStatus(data.summary);
      await Promise.allSettled([loadPricingRules(), loadSkuStandards(), loadVisualRefs()]);
      toast.success(`Processed ${data.processed} source file${data.processed === 1 ? "" : "s"}`);
    } catch (error: any) {
      toast.error(error?.message || "Import batch failed");
    } finally {
      setImporting(false);
    }
  };

  const savePricingRules = async () => {
    const parsedRules = PRICING_FIELDS.reduce((rules, field) => {
      const value = Number(pricingForm[field.key]);
      return { ...rules, [field.key]: value };
    }, {} as Record<PricingRuleKey, number>);
    if (Object.values(parsedRules).some((value) => !Number.isFinite(value) || value <= 0)) {
      toast.error("Pricing factors must be positive numbers");
      return;
    }
    try {
      const currentRules = pricingRules?.global_rules || {};
      await apiClient.request({
        path: "/routes/pricing-rules",
        method: "PUT",
        body: {
          rules: {
            ...currentRules,
            ...parsedRules,
            completed_history_policy: currentRules.completed_history_policy || "approved_paid_purchased_only",
          },
        },
        type: ContentType.Json,
      });
      await loadPricingRules();
      toast.success("Pricing rules saved");
    } catch {
      toast.error("Failed to save pricing rules");
    }
  };

  const updateBuildTemplate = (id: string, patch: Partial<BuildTemplate>) => {
    setBuildTemplates((prev) => prev.map((template) => template.id === id ? { ...template, ...patch } : template));
  };

  const updateBuildTemplateList = (id: string, key: BuildTemplateListKey, index: number, value: string) => {
    setBuildTemplates((prev) => prev.map((template) => {
      if (template.id !== id) return template;
      const current = [...((template[key] as string[] | undefined) || [])];
      current[index] = value;
      return { ...template, [key]: current };
    }));
  };

  const addBuildTemplateListItem = (id: string, key: BuildTemplateListKey, value = "") => {
    setBuildTemplates((prev) => prev.map((template) => {
      if (template.id !== id) return template;
      return { ...template, [key]: [...((template[key] as string[] | undefined) || []), value] };
    }));
  };

  const removeBuildTemplateListItem = (id: string, key: BuildTemplateListKey, index: number) => {
    setBuildTemplates((prev) => prev.map((template) => {
      if (template.id !== id) return template;
      return { ...template, [key]: ((template[key] as string[] | undefined) || []).filter((_, itemIndex) => itemIndex !== index) };
    }));
  };

  const addBuildTemplate = () => {
    const id = `custom-${Date.now()}`;
    setBuildTemplates((prev) => [
      ...prev,
      {
        id,
        section: templateFilter === "Christmas" ? "Christmas" : "Green",
        name: "New Build Template",
        summary: "Describe what this finished product is and when to use it.",
        usedFor: ["Custom"],
        slots: ["Base", "Main Material", "Accent Material", "Finish"],
      },
    ]);
    setTemplateFilter("All");
  };

  const saveBuildTemplates = () => {
    try {
      writeBuildTemplates(buildTemplates);
      toast.success("Build templates saved");
    } catch {
      toast.error("Could not save build templates");
    }
  };

  const resetBuildTemplates = () => {
    if (!window.confirm("Reset build templates back to the default template list?")) return;
    setBuildTemplates(DEFAULT_BUILD_TEMPLATES);
    writeBuildTemplates(DEFAULT_BUILD_TEMPLATES);
    toast.success("Build templates reset");
  };

  const sampleSkuStandard = skuStandards.find((standard) => Array.isArray(standard.examples) && standard.examples.length > 0) || skuStandards[0];
  const sampleHistoricalSku = parseHistoricalSku(sampleSkuStandard?.examples?.[0] || "OR7-73820-2023");
  const sampleFamily = sampleHistoricalSku?.family || sampleSkuStandard?.prefix || "OR";
  const sampleFamilyLabel = skuStandards.find((standard) => standard.prefix === sampleFamily)?.label || sampleSkuStandard?.label || "Orchid Arrangement";
  const finishedSkuExample = `TBDG-${sampleFamily}-30H-0001-26`;
  const finishedSkuSegments = [
    {
      value: "TBDG",
      label: "Company",
      meaning: "Marks this as a Branch Design Group finished product.",
    },
    {
      value: sampleFamily,
      label: "Family",
      meaning: `${sampleFamily} means ${sampleFamilyLabel}. This comes from the old recipe prefix language.`,
    },
    {
      value: "30H",
      label: "Size",
      meaning: "The main finished dimension, such as height, width, diameter, or tree size.",
    },
    {
      value: "0001",
      label: "Sequence",
      meaning: "The next finished-product number inside that family and year.",
    },
    {
      value: "26",
      label: "Year",
      meaning: "The year the finished product was created or completed.",
    },
  ];
  const historicalSkuSegments = sampleHistoricalSku ? [
    {
      value: sampleHistoricalSku.family,
      label: "Family prefix",
      meaning: `${sampleHistoricalSku.family} maps to ${sampleFamilyLabel}.`,
    },
    {
      value: sampleHistoricalSku.series || "none",
      label: "Old series marker",
      meaning: sampleHistoricalSku.series ? "A historical style, series, or internal grouping marker from the recipe file." : "Some old codes do not include a separate series marker.",
    },
    {
      value: sampleHistoricalSku.identifier,
      label: "Old recipe number",
      meaning: "The historical item or recipe identifier used before Leaf & Ledger.",
    },
    {
      value: sampleHistoricalSku.year,
      label: "Recipe year",
      meaning: "The year attached to the old source recipe.",
    },
  ] : [];

  return (
    <Layout>
      {/* `bg-background` (was a hardcoded #f7f4ef) so the sticky header follows the theme. */}
      <header className="sticky top-0 z-10 flex items-center justify-between border-b border-stone-200 bg-background px-10 py-4">
        <div>
          <h1 className="text-xl font-semibold text-stone-800" style={{ fontFamily: "Georgia, serif" }}>Settings</h1>
          <p className="mt-0.5 text-xs text-stone-500">Manage pricing, SKU standards, imports, and intelligence data</p>
        </div>
        <button onClick={() => void loadAll()} className="flex items-center gap-2 rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs font-semibold text-stone-600 hover:bg-stone-50">
          <RefreshCw size={13} />
          Refresh
        </button>
      </header>

      <div className="px-10 py-8">
        <div className="mb-6 flex flex-wrap gap-2">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setActiveTab(id)}
              className={`flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition-colors ${activeTab === id ? "bg-stone-900 text-white" : "border border-stone-200 bg-white text-stone-600 hover:bg-stone-50"}`}
            >
              <Icon size={15} />
              {label}
            </button>
          ))}
        </div>

        {/* Appearance is purely local preference state, so it must not wait on
            the markup / pricing / import fetches. */}
        {loading && activeTab !== "appearance" ? (
          <div className="flex items-center justify-center py-24">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-emerald-600 border-t-transparent" />
          </div>
        ) : (
          <div className="max-w-5xl">
            {activeTab === "markup" && (
              <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
                <div className="rounded-xl border border-stone-200 bg-white p-6">
                  <div className="mb-4 flex items-center gap-2">
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg" style={{ backgroundColor: "#e8f0e8" }}>
                      <DollarSign size={15} className="text-emerald-700" />
                    </div>
                    <h2 className="text-sm font-semibold text-stone-800">Global Markup</h2>
                  </div>
                  <p className="mb-4 text-xs leading-relaxed text-stone-500">
                    Applied to project totals by default. Pricing Rules stores the deeper landed cost and retail math used by recipe intelligence.
                  </p>
                  <div className="flex items-center gap-4">
                    <div className="flex flex-1 items-center gap-2">
                      <input
                        type="number"
                        min="0"
                        max="500"
                        step="0.5"
                        className="w-24 rounded-lg border border-stone-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
                        value={globalMarkup}
                        onChange={(e) => setGlobalMarkup(parseFloat(e.target.value))}
                      />
                      <span className="text-sm font-medium text-stone-600">%</span>
                    </div>
                    <button onClick={saveGlobal} disabled={saving} className="flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:opacity-60 hover:opacity-90" style={{ backgroundColor: "#2d5a33" }}>
                      <Save size={13} />
                      {saving ? "Saving..." : "Save"}
                    </button>
                  </div>
                </div>

                <div className="rounded-xl border border-stone-200 bg-white p-6">
                  <div className="mb-4 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className="flex h-8 w-8 items-center justify-center rounded-lg" style={{ backgroundColor: "#e8f0e8" }}>
                        <SettingsIcon size={15} className="text-emerald-700" />
                      </div>
                      <h2 className="text-sm font-semibold text-stone-800">Category Overrides</h2>
                    </div>
                    <button onClick={() => setAddingCategory(true)} className="flex items-center gap-1.5 rounded-lg border border-stone-200 px-3 py-1.5 text-xs font-medium text-stone-600 transition-colors hover:bg-stone-50">
                      <Plus size={12} /> Add override
                    </button>
                  </div>
                  {addingCategory && (
                    <div className="mb-4 flex items-center gap-3 rounded-lg border border-stone-200 bg-stone-50 p-3">
                      <select className="flex-1 rounded-lg border border-stone-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300" value={newCat} onChange={(e) => setNewCat(e.target.value)}>
                        <option value="">Select category</option>
                        {CATEGORIES.filter((c) => !categoryMarkups.some((m) => m.category === c)).map((c) => <option key={c} value={c}>{categoryLabel(c)}</option>)}
                      </select>
                      <input type="number" className="w-20 rounded-lg border border-stone-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300" value={newCatMarkup} onChange={(e) => setNewCatMarkup(e.target.value)} />
                      <span className="text-sm text-stone-400">%</span>
                      <button onClick={addCategoryMarkup} className="rounded-lg px-3 py-1.5 text-xs font-semibold text-white hover:opacity-90" style={{ backgroundColor: "#2d5a33" }}>Add</button>
                      <button onClick={() => setAddingCategory(false)} className="text-xs text-stone-400 hover:text-stone-600">Cancel</button>
                    </div>
                  )}
                  <div className="space-y-2">
                    {categoryMarkups.length === 0 && !addingCategory ? (
                      <p className="py-6 text-center text-sm text-stone-400">No category overrides. Using global markup for all categories.</p>
                    ) : categoryMarkups.map((m) => (
                      <div key={m.category} className="flex items-center gap-4 rounded-lg border border-stone-100 p-3 transition-colors hover:bg-stone-50">
                        <span className="flex-1 text-sm font-medium text-stone-700">{categoryLabel(m.category)}</span>
                        <input type="number" className="w-20 rounded-lg border border-stone-200 px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300" defaultValue={m.markup_percentage} onBlur={(e) => saveCategoryMarkup(m.category, parseFloat(e.target.value))} />
                        <span className="text-sm text-stone-400">%</span>
                        <button onClick={() => deleteCategoryMarkup(m.category)} className="flex h-7 w-7 items-center justify-center rounded-lg text-stone-300 transition-colors hover:bg-red-50 hover:text-red-400">
                          <Trash2 size={13} />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {activeTab === "pricing" && (
              <div className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
                <div className="rounded-xl border border-stone-200 bg-white p-6">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <h2 className="text-sm font-semibold text-stone-800">Universal Pricing Rules</h2>
                      <p className="mt-1 max-w-xl text-xs leading-relaxed text-stone-500">
                        These are the app's default pricing recipes. They tell Leaf & Ledger how to turn product costs into suggested selling prices.
                      </p>
                    </div>
                    <span className="rounded-full bg-emerald-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-wide text-emerald-800">Global default</span>
                  </div>
                  <div className="mt-5 grid gap-3">
                    {PRICING_FIELDS.map((field) => (
                      <label key={field.key} className="rounded-xl border border-stone-100 bg-stone-50 p-4">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <span className="block text-sm font-semibold text-stone-800">{field.label}</span>
                            <span className="mt-1 block text-xs leading-relaxed text-stone-500">{field.helper}</span>
                          </div>
                          <div className="flex items-center gap-2">
                            <input
                              type="number"
                              min="0"
                              step="0.01"
                              value={pricingForm[field.key]}
                              onChange={(event) => setPricingForm((prev) => ({ ...prev, [field.key]: event.target.value }))}
                              className="w-24 rounded-lg border border-stone-200 bg-white px-3 py-2 text-right text-sm font-semibold text-stone-800 focus:outline-none focus:ring-2 focus:ring-emerald-300"
                            />
                            <span className="text-sm font-semibold text-stone-500">x</span>
                          </div>
                        </div>
                        <p className="mt-2 text-[11px] text-stone-400">{field.example}</p>
                      </label>
                    ))}
                  </div>
                  <div className="mt-4 rounded-xl border border-emerald-100 bg-emerald-50/50 p-3">
                    <p className="text-xs font-semibold text-emerald-900">Historical learning rule</p>
                    <p className="mt-1 text-xs leading-relaxed text-emerald-900/70">
                      Historical learning means finished jobs become examples for future suggestions. The app only learns from jobs that were approved, paid for, purchased, and completed. Draft ideas stay out.
                    </p>
                  </div>
                  <button onClick={savePricingRules} className="mt-4 flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold text-white hover:opacity-90" style={{ backgroundColor: "#2d5a33" }}>
                    <Save size={13} />
                    Save pricing rules
                  </button>
                </div>
                <div className="rounded-xl border border-stone-200 bg-white p-6">
                  <h2 className="text-sm font-semibold text-stone-800">Imported Formula Sources</h2>
                  <p className="mt-1 text-xs leading-relaxed text-stone-500">These were read from old pricing files and are shown here as reference math.</p>
                  <div className="mt-4 space-y-3">
                    {(pricingRules?.source_rules || []).length === 0 ? (
                      <p className="text-sm text-stone-400">Formula documents will appear here after import batches run.</p>
                    ) : pricingRules?.source_rules.map((rule) => (
                      <div key={rule.scope} className="rounded-xl border border-stone-100 bg-stone-50 p-4">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <p className="text-sm font-semibold text-stone-800">{rule.scope.replace("source:", "")}</p>
                            <p className="mt-1 text-xs text-stone-500">Imported reference for the universal pricing rules.</p>
                          </div>
                          <span className="rounded-full bg-white px-2.5 py-1 text-[11px] font-semibold text-stone-500">Formula source</span>
                        </div>
                        <div className="mt-4 grid gap-3">
                          {PRICING_FIELDS.filter((field) => rule.rules?.[field.key] != null).map((field) => {
                            const value = Number(rule.rules?.[field.key]);
                            if (!Number.isFinite(value)) return null;
                            const sourceFormula = sourceFormulaFor(field.key, value);

                            return (
                              <div key={`${rule.scope}-${field.key}`} className="rounded-xl bg-white p-3">
                                <div className="flex flex-wrap items-start justify-between gap-3">
                                  <div>
                                    <p className="text-xs font-semibold text-stone-700">{sourceFormula.title}</p>
                                    <p className="mt-1 text-sm font-semibold text-emerald-900">{sourceFormula.formula}</p>
                                  </div>
                                  <span className="rounded-full bg-emerald-50 px-2 py-1 text-[11px] font-semibold text-emerald-800">
                                    {formatRuleValue(rule.rules, field.key)}x
                                  </span>
                                </div>
                                <p className="mt-2 text-[11px] leading-relaxed text-stone-500">{sourceFormula.meaning}</p>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {activeTab === "sku" && (
              <div className="space-y-6">
                <div className="rounded-xl border border-stone-200 bg-white p-6">
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                      <h2 className="text-sm font-semibold text-stone-800">Finished SKU Code Standard</h2>
                      <p className="mt-1 max-w-2xl text-xs leading-relaxed text-stone-500">
                        Finished-product SKUs should tell the team what it is, how big it is, when it was completed, and where it belongs in the sequence.
                        The old recipe codes inform the family prefix, but the new code is easier to read across projects, invoices, and purchase orders.
                      </p>
                    </div>
                    <span className="rounded-full bg-emerald-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-wide text-emerald-800">
                      New standard
                    </span>
                  </div>

                  <div className="mt-5 rounded-xl bg-stone-900 px-4 py-4">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-stone-400">Example full code</p>
                    <p className="mt-1 break-all font-mono text-xl font-semibold text-white">{finishedSkuExample}</p>
                  </div>

                  <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                    {finishedSkuSegments.map((segment) => (
                      <div key={`${segment.label}-${segment.value}`} className="rounded-xl border border-stone-100 bg-stone-50 p-3">
                        <p className="font-mono text-sm font-bold text-stone-900">{segment.value}</p>
                        <p className="mt-1 text-xs font-semibold text-stone-700">{segment.label}</p>
                        <p className="mt-2 text-[11px] leading-relaxed text-stone-500">{segment.meaning}</p>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="grid gap-6 lg:grid-cols-[0.9fr_1.1fr]">
                  <div className="rounded-xl border border-stone-200 bg-white p-6">
                    <h2 className="text-sm font-semibold text-stone-800">How a New Code Gets Made</h2>
                    <div className="mt-4 space-y-3">
                      {[
                        ["1", "Choose the family", `Use the build type, such as ${sampleFamilyLabel}, to pick the prefix ${sampleFamily}.`],
                        ["2", "Add the main size", "Use the clearest finished dimension: height, width, diameter, tree size, or container size."],
                        ["3", "Assign the sequence", "Give it the next available number for that family and year."],
                        ["4", "Stamp the year", "Use the completion year so finished work can be sorted historically."],
                      ].map(([step, title, detail]) => (
                        <div key={step} className="flex gap-3 rounded-xl border border-stone-100 bg-stone-50 p-3">
                          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-white text-xs font-bold text-emerald-800">{step}</div>
                          <div>
                            <p className="text-xs font-semibold text-stone-800">{title}</p>
                            <p className="mt-1 text-[11px] leading-relaxed text-stone-500">{detail}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="rounded-xl border border-stone-200 bg-white p-6">
                    <h2 className="text-sm font-semibold text-stone-800">How to Read an Old Recipe Code</h2>
                    <p className="mt-1 text-xs leading-relaxed text-stone-500">
                      Old recipe codes are still useful, but they are source history. They tell Leaf & Ledger the family language and where the recipe came from.
                    </p>
                    {sampleHistoricalSku ? (
                      <>
                        <div className="mt-4 rounded-xl bg-stone-50 px-4 py-3">
                          <p className="text-[11px] font-semibold uppercase tracking-wide text-stone-400">Imported example</p>
                          <p className="mt-1 break-all font-mono text-lg font-semibold text-stone-900">{sampleHistoricalSku.fullCode}</p>
                        </div>
                        <div className="mt-4 grid gap-3 sm:grid-cols-2">
                          {historicalSkuSegments.map((segment) => (
                            <div key={`${segment.label}-${segment.value}`} className="rounded-xl border border-stone-100 bg-white p-3">
                              <p className="font-mono text-sm font-bold text-stone-900">{segment.value}</p>
                              <p className="mt-1 text-xs font-semibold text-stone-700">{segment.label}</p>
                              <p className="mt-2 text-[11px] leading-relaxed text-stone-500">{segment.meaning}</p>
                            </div>
                          ))}
                        </div>
                      </>
                    ) : (
                      <p className="mt-4 text-sm text-stone-400">Run import batches to show dissected historical recipe code examples.</p>
                    )}
                  </div>
                </div>

                <div className="rounded-xl border border-stone-200 bg-white p-6">
                  <div className="flex flex-wrap items-end justify-between gap-3">
                    <div>
                      <h2 className="text-sm font-semibold text-stone-800">Old Prefix Library</h2>
                      <p className="mt-1 text-xs leading-relaxed text-stone-500">
                        These prefixes were inferred from imported recipe files and become the family choices for new finished-product SKUs.
                      </p>
                    </div>
                    <span className="text-xs font-semibold text-stone-400">{skuStandards.length} families identified</span>
                  </div>
                  <div className="mt-4 grid gap-3 md:grid-cols-2">
                    {skuStandards.length === 0 ? (
                      <p className="text-sm text-stone-400">Prefix standards will appear here after recipe files are imported.</p>
                    ) : skuStandards.map((standard) => (
                      <div key={standard.prefix} className="rounded-xl border border-stone-100 bg-stone-50 p-4">
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <p className="text-lg font-bold text-stone-900">{standard.prefix}</p>
                            <p className="text-sm font-semibold text-stone-700">{standard.label}</p>
                          </div>
                          <span className="rounded-full bg-white px-2 py-1 text-[11px] font-semibold text-stone-500">{standard.inferred_count} files</span>
                        </div>
                        {standard.description && <p className="mt-2 text-xs leading-relaxed text-stone-500">{standard.description}</p>}
                        {Array.isArray(standard.examples) && standard.examples.length > 0 && (
                          <p className="mt-3 text-[11px] text-stone-400">Examples: {standard.examples.slice(0, 4).join(", ")}</p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {activeTab === "ai" && (
              <div className="space-y-6">
                <div className="rounded-xl border border-stone-200 bg-white p-6">
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                      <h2 className="text-sm font-semibold text-stone-800">AI Reference Data</h2>
                      <p className="mt-1 max-w-2xl text-xs leading-relaxed text-stone-500">
                        Historical images are indexed as product-realism references for mockup prompts. They are grouped by inferred product family so trees, orchids, greenery, and other categories are easy to scan.
                      </p>
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-right">
                      <div className="rounded-xl bg-emerald-50 px-3 py-2">
                        <p className="text-lg font-bold text-emerald-900">{importStatus?.asset_count || visualRefs.length}</p>
                        <p className="text-[11px] font-semibold uppercase text-emerald-700">assets indexed</p>
                      </div>
                      <div className="rounded-xl bg-stone-50 px-3 py-2">
                        <p className="text-lg font-bold text-stone-900">{visualReferenceGroups.length}</p>
                        <p className="text-[11px] font-semibold uppercase text-stone-500">categories</p>
                      </div>
                    </div>
                  </div>
                  <div className="mt-4 rounded-xl border border-stone-100 bg-stone-50 p-3">
                    <p className="text-xs font-semibold text-stone-700">Preview rules</p>
                    <p className="mt-1 text-[11px] leading-relaxed text-stone-500">
                      JPG, PNG, GIF, and WebP files load directly. PSD files are converted into temporary PNG previews when the local preview service is available.
                    </p>
                  </div>
                </div>

                {visualRefs.length === 0 ? (
                  <div className="rounded-xl border border-stone-200 bg-white p-6">
                    <p className="text-sm text-stone-400">Run import batches to index historical product images.</p>
                  </div>
                ) : visualReferenceGroups.map((group) => (
                  <section key={group.key} className="rounded-xl border border-stone-200 bg-white p-5">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          {group.prefix && <span className="rounded-full bg-emerald-50 px-2 py-1 text-[11px] font-bold text-emerald-800">{group.prefix}</span>}
                          <h3 className="text-sm font-semibold text-stone-800">{group.label}</h3>
                        </div>
                        <p className="mt-1 text-xs text-stone-500">
                          {group.assets.length} reference file{group.assets.length === 1 ? "" : "s"} · {group.previewableCount} thumbnail{group.previewableCount === 1 ? "" : "s"} available
                        </p>
                      </div>
                      <span className="rounded-full bg-stone-50 px-3 py-1 text-[11px] font-semibold text-stone-500">Sorted by category</span>
                    </div>
                    <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                      {group.assets.map((asset) => (
                        <VisualReferenceCard key={asset.id} asset={asset} />
                      ))}
                    </div>
                  </section>
                ))}
              </div>
            )}

            {activeTab === "import" && (
              <div className="space-y-6">
                <div className="rounded-xl border border-stone-200 bg-white p-6">
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                      <h2 className="text-sm font-semibold text-stone-800">Recipe Intelligence Import</h2>
                      <p className="mt-1 text-xs leading-relaxed text-stone-500">Source root: {importStatus?.source_root || "Not scanned yet"}</p>
                      <p className="mt-1 text-xs text-stone-400">Parser: {importStatus?.parser_version || "Waiting for first scan"}</p>
                    </div>
                    <button onClick={runImportBatch} disabled={importing} className="flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:opacity-60" style={{ backgroundColor: "#2d5a33" }}>
                      {importing ? <RefreshCw size={14} className="animate-spin" /> : <Database size={14} />}
                      {importing ? "Processing..." : "Run next 50 files"}
                    </button>
                  </div>
                  <div className="mt-5 grid gap-3 md:grid-cols-4">
                    <Metric label="Files tracked" value={statusTotal} />
                    <Metric label="Recipes" value={importStatus?.recipe_count || 0} />
                    <Metric label="Components" value={importStatus?.component_count || 0} />
                    <Metric label="Assets" value={importStatus?.asset_count || 0} />
                  </div>
                  <div className="mt-5 flex flex-wrap gap-2">
                    {(importStatus?.statuses || []).map((row) => (
                      <span key={row.status} className="rounded-full border border-stone-200 bg-stone-50 px-3 py-1 text-xs font-semibold text-stone-600">{row.status}: {row.count}</span>
                    ))}
                  </div>
                </div>
                <div className="rounded-xl border border-stone-200 bg-white p-6">
                  <h2 className="text-sm font-semibold text-stone-800">Needs Review / Deferred</h2>
                  <div className="mt-4 space-y-2">
                    {(importStatus?.failures || []).length === 0 ? (
                      <p className="flex items-center gap-2 text-sm text-emerald-700"><CheckCircle2 size={15} /> No failures or deferred files reported yet.</p>
                    ) : importStatus?.failures.map((failure) => (
                      <div key={`${failure.relative_path}-${failure.status}`} className="rounded-xl border border-stone-100 bg-stone-50 p-3">
                        <p className="text-xs font-semibold text-stone-800">{failure.relative_path}</p>
                        <p className="mt-1 text-[11px] text-stone-500">{failure.status}{failure.error_message ? ` · ${failure.error_message}` : ""}</p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {activeTab === "templates" && (
              <div className="space-y-6">
                <div className="rounded-xl border border-stone-200 bg-white p-6">
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                      <h2 className="text-sm font-semibold text-stone-800">Build Template Library</h2>
                      <p className="mt-1 max-w-2xl text-xs leading-relaxed text-stone-500">
                        These are the fill-in-the-blank templates used to build products. Edit the sections a designer sees, plus the material recipes behind enhancer packages.
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <button onClick={addBuildTemplate} className="flex items-center gap-2 rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs font-semibold text-stone-600 hover:bg-stone-50">
                        <Plus size={13} />
                        Add template
                      </button>
                      <button onClick={resetBuildTemplates} className="rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs font-semibold text-stone-500 hover:bg-stone-50">
                        Reset defaults
                      </button>
                      <button onClick={saveBuildTemplates} className="flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-semibold text-white hover:opacity-90" style={{ backgroundColor: "#2d5a33" }}>
                        <Save size={13} />
                        Save templates
                      </button>
                    </div>
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    {(["All", "Green", "Christmas"] as const).map((filter) => (
                      <button
                        key={filter}
                        onClick={() => setTemplateFilter(filter)}
                        className={`rounded-full px-3 py-1.5 text-xs font-semibold transition-colors ${templateFilter === filter ? "bg-stone-900 text-white" : "bg-stone-50 text-stone-600 hover:bg-stone-100"}`}
                      >
                        {filter}
                      </button>
                    ))}
                  </div>
                  <div className="mt-4 rounded-xl border border-emerald-100 bg-emerald-50/50 p-3">
                    <p className="text-xs font-semibold text-emerald-900">How to read this</p>
                    <p className="mt-1 text-xs leading-relaxed text-emerald-900/70">
                      Fill-in sections are the bubbles in the builder. Standard and premium materials are the recipe rules behind larger grouped bubbles like Enhancers.
                    </p>
                  </div>
                </div>

                {visibleBuildTemplates.map((template) => (
                  <section key={template.id} className="rounded-xl border border-stone-200 bg-white p-5">
                    <div className="grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide ${template.section === "Christmas" ? "bg-emerald-50 text-emerald-800" : "bg-stone-100 text-stone-600"}`}>
                            {template.section}
                          </span>
                          <span className="rounded-full bg-stone-50 px-2.5 py-1 text-[11px] font-semibold text-stone-500">Global template</span>
                        </div>
                        <input
                          value={template.name}
                          onChange={(event) => updateBuildTemplate(template.id, { name: event.target.value })}
                          className="mt-3 w-full rounded-lg border border-stone-200 px-3 py-2 text-lg font-semibold text-stone-900 focus:outline-none focus:ring-2 focus:ring-emerald-300"
                        />
                        <textarea
                          value={template.summary}
                          onChange={(event) => updateBuildTemplate(template.id, { summary: event.target.value })}
                          rows={3}
                          className="mt-3 w-full resize-none rounded-lg border border-stone-200 px-3 py-2 text-sm leading-relaxed text-stone-600 focus:outline-none focus:ring-2 focus:ring-emerald-300"
                        />
                        <div className="mt-3">
                          <label className="mb-1 block text-xs font-semibold text-stone-500">Template group</label>
                          <select
                            value={template.section}
                            onChange={(event) => updateBuildTemplate(template.id, { section: event.target.value === "Christmas" ? "Christmas" : "Green" })}
                            className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
                          >
                            <option value="Green">Green</option>
                            <option value="Christmas">Christmas</option>
                          </select>
                        </div>
                        <div className="mt-3">
                          <TemplateListEditor
                            title="Used in"
                            helper="Names, aliases, or product types this template can apply to."
                            items={template.usedFor}
                            placeholder="e.g. Mantel Garland"
                            onChange={(index, value) => updateBuildTemplateList(template.id, "usedFor", index, value)}
                            onAdd={() => addBuildTemplateListItem(template.id, "usedFor", "")}
                            onRemove={(index) => removeBuildTemplateListItem(template.id, "usedFor", index)}
                          />
                        </div>
                      </div>

                      <div className="grid gap-4">
                        <TemplateListEditor
                          title="Fill-in sections"
                          helper="These are the product bubbles a designer fills in from top to bottom."
                          items={template.slots}
                          placeholder="e.g. Accent Decor"
                          onChange={(index, value) => updateBuildTemplateList(template.id, "slots", index, value)}
                          onAdd={() => addBuildTemplateListItem(template.id, "slots", "")}
                          onRemove={(index) => removeBuildTemplateListItem(template.id, "slots", index)}
                        />
                        <div className="grid gap-3 md:grid-cols-2">
                          <TemplateListEditor
                            title="Standard / regular materials"
                            helper="Recipe parts for the normal version of this build or enhancer."
                            items={template.regularMaterials || []}
                            placeholder="e.g. 2 x Assorted Branch"
                            onChange={(index, value) => updateBuildTemplateList(template.id, "regularMaterials", index, value)}
                            onAdd={() => addBuildTemplateListItem(template.id, "regularMaterials", "")}
                            onRemove={(index) => removeBuildTemplateListItem(template.id, "regularMaterials", index)}
                          />
                          <TemplateListEditor
                            title="Premium materials"
                            helper="Recipe parts for upgraded or premium versions."
                            items={template.premiumMaterials || []}
                            placeholder="e.g. 1 Yard of Premium Ribbon"
                            onChange={(index, value) => updateBuildTemplateList(template.id, "premiumMaterials", index, value)}
                            onAdd={() => addBuildTemplateListItem(template.id, "premiumMaterials", "")}
                            onRemove={(index) => removeBuildTemplateListItem(template.id, "premiumMaterials", index)}
                          />
                        </div>
                      </div>
                    </div>
                  </section>
                ))}
              </div>
            )}

            {activeTab === "appearance" && (
              <div className="space-y-6">
                <div className="rounded-xl border border-stone-200 bg-white p-6">
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                      <h2 className="text-sm font-semibold text-stone-800">Theme</h2>
                      <p className="mt-1 max-w-2xl text-xs leading-relaxed text-stone-500">
                        Pick how Leaf &amp; Ledger looks on this account. The sidebar stays dark green in
                        both themes; dark mode changes the page area behind it.
                      </p>
                    </div>
                    <span className="rounded-full bg-emerald-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-wide text-emerald-800">
                      Saved to your account
                    </span>
                  </div>
                  <div className="mt-5 grid gap-3 sm:grid-cols-3">
                    {THEME_MODE_CHOICES.map((choice) => {
                      const ChoiceIcon = choice.icon;
                      const selected = mode === choice.mode;
                      return (
                        <button
                          key={choice.mode}
                          type="button"
                          onClick={() => setMode(choice.mode)}
                          aria-pressed={selected}
                          aria-label={`Use the ${choice.label.toLowerCase()} theme`}
                          className={`rounded-xl border p-4 text-left transition-colors ${
                            selected
                              ? "border-emerald-300 bg-emerald-50/60"
                              : "border-stone-100 bg-stone-50 hover:bg-stone-100"
                          }`}
                        >
                          <span className="flex items-center gap-2">
                            <span className={`flex h-7 w-7 items-center justify-center rounded-lg ${selected ? "bg-white text-emerald-700" : "bg-white text-stone-400"}`}>
                              <ChoiceIcon size={14} />
                            </span>
                            <span className="text-sm font-semibold text-stone-800">{choice.label}</span>
                            {selected && <Check size={14} className="ml-auto text-emerald-700" />}
                          </span>
                          <span className="mt-2 block text-[11px] leading-relaxed text-stone-500">{choice.helper}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="rounded-xl border border-stone-200 bg-white p-6">
                  <h2 className="text-sm font-semibold text-stone-800">Accent Colour</h2>
                  <p className="mt-1 max-w-2xl text-xs leading-relaxed text-stone-500">
                    Used for active tabs, buttons, and highlights across the app.
                  </p>
                  {(THEME_ACCENTS || []).length === 0 ? (
                    <p className="mt-4 text-sm text-stone-400">No accent colours are available.</p>
                  ) : (
                    <div className="mt-4 flex flex-wrap gap-3">
                      {THEME_ACCENTS.map((option) => {
                        const selected = accent === option.key;
                        return (
                          <button
                            key={option.key}
                            type="button"
                            onClick={() => setAccent(option.key)}
                            aria-pressed={selected}
                            aria-label={`Use the ${option.label} accent`}
                            title={option.label}
                            className={`flex items-center gap-2 rounded-xl border px-3 py-2 transition-colors ${
                              selected ? "border-emerald-300 bg-emerald-50/60" : "border-stone-100 bg-stone-50 hover:bg-stone-100"
                            }`}
                          >
                            <span
                              className="flex h-6 w-6 items-center justify-center rounded-full ring-1 ring-inset ring-black/10"
                              style={{ backgroundColor: option.swatch }}
                            >
                              {selected && <Check size={12} className="text-white" />}
                            </span>
                            <span className="text-xs font-semibold text-stone-700">{option.label}</span>
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>

                <SidebarTabsEditor />
              </div>
            )}

            {activeTab !== "appearance" && (
              <div className="mt-6 rounded-xl border border-stone-200 bg-white p-6">
                <div className="mb-2 flex items-center gap-2">
                  <div className="flex h-8 w-8 items-center justify-center rounded-lg" style={{ backgroundColor: "#e8f0e8" }}>
                    <Users size={15} className="text-emerald-700" />
                  </div>
                  <h2 className="text-sm font-semibold text-stone-800">Supplier Management</h2>
                </div>
                <p className="mb-4 text-xs text-stone-500">Manage supplier profiles, contacts, and credentials.</p>
                <a href="/suppliers" className="inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold text-white hover:opacity-90" style={{ backgroundColor: "#2d5a33" }}>
                  Manage Suppliers
                </a>
              </div>
            )}
          </div>
        )}
      </div>
    </Layout>
  );
}

function TemplateListEditor({
  title,
  helper,
  items,
  placeholder,
  onChange,
  onAdd,
  onRemove,
}: {
  title: string;
  helper: string;
  items: string[];
  placeholder: string;
  onChange: (index: number, value: string) => void;
  onAdd: () => void;
  onRemove: (index: number) => void;
}) {
  return (
    <div className="rounded-xl border border-stone-100 bg-stone-50 p-3">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">{title}</p>
          <p className="mt-1 text-[11px] leading-relaxed text-stone-400">{helper}</p>
        </div>
        <button
          type="button"
          onClick={onAdd}
          className="flex shrink-0 items-center gap-1 rounded-lg border border-stone-200 bg-white px-2 py-1 text-[11px] font-semibold text-stone-600 hover:bg-stone-50"
        >
          <Plus size={11} />
          Add
        </button>
      </div>
      <div className="space-y-2">
        {items.length === 0 ? (
          <p className="rounded-lg border border-dashed border-stone-200 bg-white px-3 py-2 text-xs text-stone-400">No lines yet. Add one to start.</p>
        ) : items.map((item, index) => (
          <div key={`${title}-${index}`} className="flex items-center gap-2">
            <input
              value={item}
              onChange={(event) => onChange(index, event.target.value)}
              placeholder={placeholder}
              className="min-w-0 flex-1 rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs text-stone-700 focus:outline-none focus:ring-2 focus:ring-emerald-300"
            />
            <button
              type="button"
              onClick={() => onRemove(index)}
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-stone-300 hover:bg-red-50 hover:text-red-500"
              aria-label={`Remove ${item || title} line`}
            >
              <Trash2 size={13} />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl bg-stone-50 p-4">
      <p className="text-2xl font-bold text-stone-900">{Number(value || 0).toLocaleString()}</p>
      <p className="mt-1 text-[11px] font-semibold uppercase tracking-wide text-stone-400">{label}</p>
    </div>
  );
}

function VisualReferenceCard({ asset }: { asset: VisualReference }) {
  const [previewFailed, setPreviewFailed] = useState(false);
  const canPreview = canPreviewVisualReference(asset) && !previewFailed;
  const extensionLabel = visualExtensionLabel(asset);

  return (
    <article className="overflow-hidden rounded-xl border border-stone-100 bg-stone-50">
      <div className="aspect-[4/3] bg-stone-100">
        {canPreview ? (
          <img
            src={visualPreviewUrl(asset)}
            alt={`${asset.item_code || "Reference"} ${asset.file_name}`}
            loading="lazy"
            onError={() => setPreviewFailed(true)}
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-2 px-4 text-center">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-white text-emerald-700">
              <Image size={18} />
            </div>
            <p className="text-xs font-semibold text-stone-700">{extensionLabel} source file</p>
            <p className="text-[11px] leading-relaxed text-stone-400">
              {previewFailed ? "Preview could not load." : "Preview needs source conversion."}
            </p>
          </div>
        )}
      </div>
      <div className="p-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-stone-800">{asset.file_name}</p>
            <p className="mt-1 text-xs text-stone-500">{asset.item_code || "No linked code"}</p>
          </div>
          <span className="shrink-0 rounded-full bg-white px-2 py-1 text-[10px] font-bold text-stone-500">{extensionLabel}</span>
        </div>
        <p className="mt-2 truncate text-[11px] text-stone-400">{asset.file_path}</p>
      </div>
    </article>
  );
}
