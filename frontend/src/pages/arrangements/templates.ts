// Editable build-template readers (with their memo) and build-template re-exports.
import {
  ARRANGEMENTS_DEFAULT_BUILD_TEMPLATES,
  LEGACY_TOP_DOWN_SLOT_ORDERS,
  cleanArrangementsBuildTemplates as cleanEditableBuildTemplates,
} from "utils/buildTemplates";
import { BUILD_TEMPLATE_STORAGE_KEY } from "../../constants";
import type { EditableBuildTemplate, ChristmasEnhancerPackage, EnhancerPartConfig } from "./types";
import { buildTypeConfigFor } from "./buildConfigs";
import { normalizeLabel } from "./textHelpers";

export const DEFAULT_EDITABLE_BUILD_TEMPLATES: EditableBuildTemplate[] = ARRANGEMENTS_DEFAULT_BUILD_TEMPLATES;

// The green build slots above used to read top-down (container first). They now read
// bottom-up so the builder mirrors how the piece is physically assembled.
// DISPLAY ORDER ONLY changed - no slot label string was renamed. Saved part data is
// keyed by `partKey(label, displayIndex)`, so the pre-flip index for these labels is
// recorded here and honoured when resolving already-saved items (see itemsForPart).
export { LEGACY_TOP_DOWN_SLOT_ORDERS };

export const FLIPPED_SLOT_COUNT = 4;

// Labels whose display index moved when the green slots were flipped. No Christmas slot
// or enhancer sub-part label appears here, so the legacy lookup can never cross over.
export const FLIPPED_SLOT_LABELS = new Set(
  Object.values(LEGACY_TOP_DOWN_SLOT_ORDERS)
    .flat()
    .map((label) => label.trim().toLowerCase())
);

export { cleanEditableBuildTemplates };

// The JSX reaches this through the enhancer/slot helpers once per part on every
// render. Parsing + cleaning is keyed on the raw stored string, so a write from any
// route (Settings, another tab, devtools) is picked up on the next read. Callers only
// read the result; nothing mutates the cached templates.
let editableTemplatesMemo: { raw: string | null; templates: EditableBuildTemplate[] } | null = null;

export function readEditableBuildTemplates() {
  if (typeof window === "undefined") return DEFAULT_EDITABLE_BUILD_TEMPLATES;
  let raw: string | null;
  try {
    raw = window.localStorage.getItem(BUILD_TEMPLATE_STORAGE_KEY);
  } catch {
    return DEFAULT_EDITABLE_BUILD_TEMPLATES;
  }
  if (editableTemplatesMemo && editableTemplatesMemo.raw === raw) return editableTemplatesMemo.templates;
  let templates: EditableBuildTemplate[];
  try {
    templates = cleanEditableBuildTemplates(JSON.parse(raw || "null"));
  } catch {
    templates = DEFAULT_EDITABLE_BUILD_TEMPLATES;
  }
  editableTemplatesMemo = { raw, templates };
  return templates;
}

export function buildTemplateMatches(template: EditableBuildTemplate, buildType: string) {
  const values = [template.name, ...(template.usedFor || [])];
  return values.some((value) => normalizeLabel(value) === normalizeLabel(buildType));
}

export function editableTemplateForBuildType(buildType: string) {
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

export function templateSlotsForBuildType(buildType: string) {
  const slots = editableTemplateForBuildType(buildType)?.slots?.map((slot) => slot.trim()).filter(Boolean) || [];
  return slots.length ? slots : null;
}

export function parseMaterialQuantity(line: string) {
  const mixed = line.trim().match(/^(\d+)(?:\s+(\d+)\/(\d+)|\.(\d+))?/);
  if (!mixed) return 1;
  const whole = Number(mixed[1]) || 0;
  if (mixed[2] && mixed[3]) return whole + (Number(mixed[2]) || 0) / (Number(mixed[3]) || 1);
  if (mixed[4]) return Number(`${mixed[1]}.${mixed[4]}`);
  return whole || 1;
}

export function templateMaterialLabel(line: string) {
  return line
    .replace(/\bper\s+(premium\s+)?enhancer\b/gi, "")
    .replace(/^\s*\d+(?:\s+\d+\/\d+|\.\d+)?\s*(?:x\b|yards?\s+of\b|yards?\b|yd\s+of\b|yd\b)?\s*/i, "")
    .replace(/^of\s+/i, "")
    .trim();
}

export function enhancerPartFromTemplateLine(
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

export function enhancerPartsFromTemplate(buildType: string, packageType: ChristmasEnhancerPackage) {
  const template = editableTemplateForBuildType(buildType);
  const regularLines = template?.regularMaterials || [];
  const packageLines = packageType === "premium" ? template?.premiumMaterials || [] : regularLines;
  const regularLabels = new Set(regularLines.map(templateMaterialLabel).filter(Boolean).map(normalizeLabel));
  const parts = packageLines
    .map((line) => enhancerPartFromTemplateLine(line, packageType, regularLabels))
    .filter(Boolean) as EnhancerPartConfig[];
  return parts.length ? parts : null;
}
