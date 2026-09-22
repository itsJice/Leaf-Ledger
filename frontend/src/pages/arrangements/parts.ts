// Pure part, enhancer, guidance and SKU helpers for the Arrangements builder.
import type { Product as LibraryProduct } from "../library/types";
import type {
  Container,
  Arrangement,
  BuildTypeOption,
  BuilderSection,
  ChristmasEnhancerPackage,
  GarlandPackage,
  GarlandDiameter,
  WreathSize,
  BuildSuggestionComponent,
  EnhancerPartConfig,
} from "./types";
import { builderApiSlotsForBuildType } from "./builderTypes";
import {
  parseScopeIntelligence,
  parseCustomSections,
  buildHeightFromNotes,
  buildWidthFromNotes,
  christmasEnhancerPackageFromNotes,
  garlandPackageFromNotes,
  garlandLengthFromNotes,
  garlandDiameterFromNotes,
  garlandLengthMultiplier,
  garlandSetupLabel,
  wreathSizeFromNotes,
} from "./scopeNotes";
import {
  FLIPPED_SLOT_COUNT,
  FLIPPED_SLOT_LABELS,
  templateSlotsForBuildType,
  parseMaterialQuantity,
  enhancerPartsFromTemplate,
} from "./templates";
import {
  BUILD_TYPE_CONFIGS,
  CHRISTMAS_ENHANCER_PARTS,
  WREATH_DECOR_PARTS,
  WREATH_DECOR_RECIPES,
  GARLAND_ENHANCER_PARTS,
  buildTypeConfigFor,
} from "./buildConfigs";
import { normalizeLabel, firstNumber } from "./textHelpers";

export function designPartsForBuildType(buildType: string) {
  const templateSlots = templateSlotsForBuildType(buildType);
  if (templateSlots) return templateSlots;
  const config = buildTypeConfigFor(buildType);
  if (config) return [...config.visibleParts];
  // Only the types the builder gained in Phase C - Plant & Bush, Container Only,
  // Topiary - reach this line. The four historical green types resolve above,
  // through their editable template, and keep the exact slot labels and display
  // order their saved `part_key`s were written under.
  return builderApiSlotsForBuildType(buildType);
}

export function baseScopePlaceholders(bucket: Container) {
  const designParts = designPartsForBuildType(`${bucket.bucket_type || ""} ${bucket.label || ""}`);
  if (designParts) return designParts.slice(0, 4);

  const intelligence = parseScopeIntelligence(bucket.scope_notes);
  const labels = intelligence?.components?.map((component) => component.label).filter(Boolean);
  const sections = labels && labels.length > 0 ? labels.slice(0, 4) : fallbackSectionsForBuildType(`${bucket.bucket_type || ""} ${bucket.label || ""}`);
  return sections.length >= 4 ? sections.slice(0, 4) : [...sections, "Product", "Product", "Product", "Product"].slice(0, 4);
}

export function fallbackSectionsForBuildType(buildType: string) {
  const designParts = designPartsForBuildType(buildType);
  if (designParts) return designParts;

  const text = buildType.toLowerCase();
  if (text.includes("wreath")) return ["Wreath Base", "Decor Package"];
  if (text.includes("garland")) return ["Base Garland", "Greenery", "Ribbon", "Decor"];
  if (text.includes("container") || text.includes("planter")) return ["Accent Plant", "Main Plant", "Finish/Top Dressing", "Container/Planter"];
  if (text.includes("arrangement")) return ["Accent Material", "Focal Material", "Finish/Top Dressing", "Container/Base"];
  return ["Products", "Notes", "Pricing"];
}

export function scopePlaceholders(bucket: Container) {
  return [...baseScopePlaceholders(bucket), ...parseCustomSections(bucket.scope_notes)];
}

export function treeWidthNumber(value?: string | null) {
  const text = String(value || "");
  const xWidth = text.match(/x\s*(\d+(?:\.\d+)?)\s*(?:"|in|d\b)/i);
  if (xWidth) return Number(xWidth[1]);
  const diameter = text.match(/(\d+(?:\.\d+)?)\s*(?:"|in)?\s*d(?:iam|iameter)?\b/i);
  return diameter ? Number(diameter[1]) : firstNumber(value);
}

export function christmasTreeDecorRule(heightValue?: string | null, widthValue?: string | null) {
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

export function christmasTreeDecorRuleForBucket(bucket?: Container | null) {
  if (!bucket) return null;
  const selectedTree = itemsForPart(bucket, "Tree", 0)[0];
  const height = buildHeightFromNotes(bucket.scope_notes) || selectedTree?.product_name;
  const width = buildWidthFromNotes(bucket.scope_notes) || selectedTree?.product_name;
  return christmasTreeDecorRule(height, width);
}

export function christmasEnhancerCountSummary(rule: ReturnType<typeof christmasTreeDecorRule>, profile?: string | null) {
  if (!rule) return "Select a tree size to calculate how many enhancers are needed.";
  const profileLabel = String(profile || "").trim().toLowerCase();
  const selectedSize = profileLabel && !rule.label.toLowerCase().includes(profileLabel) ? `${rule.label} ${profileLabel}` : rule.label;
  return `${rule.enhancers} enhancers needed for the ${selectedSize} tree selected.`;
}

export function isChristmasTreeBuild(buildType?: string | null) {
  return buildTypeConfigFor(buildType || "")?.label === "Christmas Tree";
}

export function isChristmasTreeBucket(bucket?: Container | null) {
  return isChristmasTreeBuild(`${bucket?.bucket_type || ""} ${bucket?.label || ""}`);
}

export function isGarlandBuild(buildType?: string | null) {
  return buildTypeConfigFor(buildType || "")?.label === "Garland";
}

export function isGarlandBucket(bucket?: Container | null) {
  return isGarlandBuild(`${bucket?.bucket_type || ""} ${bucket?.label || ""}`);
}

export function isWreathBuild(buildType?: string | null) {
  return buildTypeConfigFor(buildType || "")?.label === "Wreath";
}

export function isWreathBucket(bucket?: Container | null) {
  return isWreathBuild(`${bucket?.bucket_type || ""} ${bucket?.label || ""}`);
}

export function isStructuredChristmasBucket(bucket?: Container | null) {
  return isChristmasTreeBucket(bucket) || isGarlandBucket(bucket) || isWreathBucket(bucket);
}

export function isEnhancersPart(label: string) {
  return normalizeLabel(label).includes("enhancer");
}

export function isWreathDecorPart(label: string) {
  const normalized = normalizeLabel(label);
  return normalized.includes("decor package") || normalized === "decor";
}

export function christmasEnhancerPartIndex(parentIndex: number, subIndex: number) {
  return parentIndex * 100 + subIndex + 1;
}

export function christmasEnhancerBaseCount(bucket: Container | null | undefined) {
  return christmasTreeDecorRuleForBucket(bucket)?.enhancers || 8;
}

export function mergeEnhancerParts(parts: EnhancerPartConfig[]) {
  const byLabel = new Map<string, EnhancerPartConfig>();
  parts.forEach((part) => {
    const key = normalizeLabel(part.label);
    const existing = byLabel.get(key);
    byLabel.set(key, existing ? { ...existing, ...part, regularFormula: existing.regularFormula || part.regularFormula, premiumFormula: existing.premiumFormula || part.premiumFormula } : part);
  });
  return Array.from(byLabel.values());
}

export function allChristmasEnhancerPartConfigs() {
  const regular = enhancerPartsFromTemplate("Christmas Tree", "regular") || [];
  const premium = enhancerPartsFromTemplate("Christmas Tree", "premium") || [];
  const merged = mergeEnhancerParts([...regular, ...premium]);
  return merged.length ? merged : CHRISTMAS_ENHANCER_PARTS;
}

export function christmasEnhancerPartConfig(label: string) {
  return allChristmasEnhancerPartConfigs().find((part) => normalizeLabel(part.label) === normalizeLabel(label));
}

export function christmasEnhancerPartIsOptional(part: EnhancerPartConfig) {
  return Boolean(part.optional || part.premiumOnly);
}

export function christmasEnhancerRegularFormula(part: EnhancerPartConfig) {
  return part.regularFormula || "";
}

export function christmasEnhancerPremiumFormula(part: EnhancerPartConfig) {
  return part.premiumFormula || "";
}

export function christmasEnhancerPartRequiredForPackage(part: EnhancerPartConfig, packageType: ChristmasEnhancerPackage) {
  return packageType === "premium" ? Boolean(christmasEnhancerPremiumFormula(part)) : Boolean(christmasEnhancerRegularFormula(part));
}

export function christmasEnhancerPartsForPackage(packageType: ChristmasEnhancerPackage) {
  const templateParts = enhancerPartsFromTemplate("Christmas Tree", packageType);
  if (templateParts?.length) return templateParts;
  return CHRISTMAS_ENHANCER_PARTS.filter((part) => christmasEnhancerPartRequiredForPackage(part, packageType));
}

export function christmasEnhancerPartSubIndex(label: string) {
  const index = allChristmasEnhancerPartConfigs().findIndex((part) => normalizeLabel(part.label) === normalizeLabel(label));
  return Math.max(0, index);
}

export function christmasEnhancerPartQuantity(bucket: Container | null | undefined, label: string) {
  const enhancers = christmasEnhancerBaseCount(bucket);
  const packageType = christmasEnhancerPackageFromNotes(bucket?.scope_notes);
  const part = christmasEnhancerPartConfig(label);
  const formula = packageType === "premium" ? part?.premiumFormula : part?.regularFormula;
  return Math.max(1, Math.ceil(enhancers * parseMaterialQuantity(formula || "1")));
}

export function christmasEnhancerPartPreviewText(label: string, enhancers: number, packageType: ChristmasEnhancerPackage) {
  const part = christmasEnhancerPartConfig(label);
  const formula = packageType === "premium" ? part?.premiumFormula : part?.regularFormula;
  const quantity = Math.max(1, Math.ceil(enhancers * parseMaterialQuantity(formula || "1")));
  return /yd|yard/i.test(formula || "") ? `${quantity} yd` : `${quantity} total`;
}

export function christmasEnhancerPartTargetText(bucket: Container | null | undefined, label: string) {
  return christmasEnhancerPartPreviewText(label, christmasEnhancerBaseCount(bucket), christmasEnhancerPackageFromNotes(bucket?.scope_notes));
}

export function christmasEnhancerPartItems(bucket: Container | null | undefined, parentIndex: number, subIndex: number) {
  const part = allChristmasEnhancerPartConfigs()[subIndex];
  return part ? itemsForPart(bucket, part.label, christmasEnhancerPartIndex(parentIndex, subIndex)) : [];
}

export function garlandEnhancerRule(packageType: GarlandPackage, lengthValue?: string | null) {
  const multiplier = garlandLengthMultiplier(lengthValue);
  return packageType === "premium"
    ? { label: "premium", regularEnhancers: 2 * multiplier, premiumEnhancers: 3 * multiplier, extraOrnaments: 2 * multiplier }
    : { label: "regular", regularEnhancers: 5 * multiplier, premiumEnhancers: 0, extraOrnaments: 0 };
}

export function garlandEnhancerPartConfig(label: string) {
  return GARLAND_ENHANCER_PARTS.find((part) => normalizeLabel(part.label) === normalizeLabel(label));
}

export function garlandEnhancerPartsForPackage(packageType: GarlandPackage) {
  const labels = packageType === "premium"
    ? ["Flower", "Assorted Branches", '4" Ornament', "Ribbon", "Premium Ribbon", "Extra Ornaments"]
    : ["Assorted Branches", '4" Ornament', "Ribbon"];
  return labels
    .map((label) => garlandEnhancerPartConfig(label))
    .filter(Boolean) as Array<(typeof GARLAND_ENHANCER_PARTS)[number]>;
}

export function garlandEnhancerPartSubIndex(label: string) {
  const index = GARLAND_ENHANCER_PARTS.findIndex((part) => normalizeLabel(part.label) === normalizeLabel(label));
  return Math.max(0, index);
}

export function formatGarlandQuantity(value: number, unit: "total" | "yd") {
  const rounded = Number.isInteger(value) ? String(value) : value.toFixed(1).replace(/\.0$/, "");
  return `${rounded} ${unit}`;
}

export function garlandEnhancerPartQuantity(packageType: GarlandPackage, label: string, lengthValue?: string | null) {
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

export function garlandEnhancerPartPreviewText(label: string, packageType: GarlandPackage, lengthValue?: string | null) {
  const normalized = normalizeLabel(label);
  const quantity = garlandEnhancerPartQuantity(packageType, label, lengthValue);
  if (normalized.includes("ribbon")) return formatGarlandQuantity(quantity, "yd");
  return formatGarlandQuantity(quantity, "total");
}

export function garlandEnhancerPartTargetText(bucket: Container | null | undefined, label: string) {
  return garlandEnhancerPartPreviewText(label, garlandPackageFromNotes(bucket?.scope_notes), garlandLengthFromNotes(bucket?.scope_notes));
}

export function garlandEnhancerPartItems(bucket: Container | null | undefined, parentIndex: number, subIndex: number) {
  const part = GARLAND_ENHANCER_PARTS[subIndex];
  return part ? itemsForPart(bucket, part.label, christmasEnhancerPartIndex(parentIndex, subIndex)) : [];
}

export function garlandEnhancerCountSummary(packageType: GarlandPackage, lengthValue: string, diameter: GarlandDiameter) {
  const rule = garlandEnhancerRule(packageType, lengthValue);
  const productLabel = `${packageType === "premium" ? "Premium" : "Regular"} Garland ${garlandSetupLabel(lengthValue, diameter)}`;
  if (packageType === "premium") {
    return `${rule.premiumEnhancers} premium enhancers, ${rule.regularEnhancers} regular enhancers, and ${rule.extraOrnaments} extra ornaments needed for the ${productLabel} selected.`;
  }
  return `${rule.regularEnhancers} regular enhancers needed for the ${productLabel} selected.`;
}

export function wreathDecorPartConfig(label: string) {
  return WREATH_DECOR_PARTS.find((part) => normalizeLabel(part.label) === normalizeLabel(label));
}

export function wreathDecorPartsForSize(size: WreathSize) {
  return WREATH_DECOR_RECIPES[size]
    .map((recipe) => {
      const config = wreathDecorPartConfig(recipe.label);
      return config ? { ...config, ...recipe } : null;
    })
    .filter(Boolean) as Array<(typeof WREATH_DECOR_PARTS)[number] & { quantity: number; unit: "total" | "yd" }>;
}

export function wreathDecorPartSubIndex(label: string) {
  const index = WREATH_DECOR_PARTS.findIndex((part) => normalizeLabel(part.label) === normalizeLabel(label));
  return Math.max(0, index);
}

export function wreathDecorPartItems(bucket: Container | null | undefined, parentIndex: number, subIndex: number) {
  const part = WREATH_DECOR_PARTS[subIndex];
  return part ? itemsForPart(bucket, part.label, christmasEnhancerPartIndex(parentIndex, subIndex)) : [];
}

export function wreathDecorPartPreviewText(label: string, size: WreathSize) {
  const recipe = WREATH_DECOR_RECIPES[size].find((item) => normalizeLabel(item.label) === normalizeLabel(label));
  if (!recipe) return "";
  return formatGarlandQuantity(recipe.quantity, recipe.unit);
}

export function wreathDecorCountSummary(size: WreathSize) {
  const parts = WREATH_DECOR_RECIPES[size]
    .map((part) => `${formatGarlandQuantity(part.quantity, part.unit)} ${part.label.toLowerCase()}`)
    .join(", ");
  return `${parts} needed for the ${size}" wreath selected.`;
}

export function partKey(label: string, index: number) {
  return `${index}-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "part"}`;
}

// Each flipped build type has exactly FLIPPED_SLOT_COUNT slots, so a label that moved
// sits at (FLIPPED_SLOT_COUNT - 1 - newIndex) in any part_key saved before the flip.
export function legacySlotIndex(label: string, index: number) {
  if (index < 0 || index >= FLIPPED_SLOT_COUNT) return null;
  if (!FLIPPED_SLOT_LABELS.has(label.trim().toLowerCase())) return null;
  return FLIPPED_SLOT_COUNT - 1 - index;
}

// Every part_key that should resolve to this slot: the current one first, plus the
// pre-flip key so designs saved under the old top-down order keep their products.
export function partKeysForSlot(label: string, index: number) {
  const legacyIndex = legacySlotIndex(label, index);
  const keys = [partKey(label, index)];
  if (legacyIndex !== null) keys.push(partKey(label, legacyIndex));
  return keys;
}

export function itemsForPart(bucket: Container | null | undefined, label: string, index: number) {
  if (!bucket) return [];
  const keys = partKeysForSlot(label, index);
  // Untagged legacy items were always treated as belonging to the first slot, which for a
  // flipped build type is now the last one - follow the pre-flip index, not the new one.
  const untaggedIndex = legacySlotIndex(label, index) ?? index;
  return bucket.items.filter((item) =>
    item.part_key ? keys.includes(item.part_key) : untaggedIndex === 0
  );
}

export function primarySelectedForPart(bucket: Container, label: string, index: number) {
  return (
    itemsForPart(bucket, label, index).find((item) => (item.status || "selected") === "selected") ||
    itemsForPart(bucket, label, index)[0] ||
    null
  );
}

export function partIsComplete(bucket: Container, label: string, index: number) {
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

export function componentLooksLikePart(componentLabel: string, partLabel: string) {
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

export function suggestionForPart(bucket: Container | null | undefined, label: string, index: number): BuildSuggestionComponent | null {
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

export function searchTermsForPart(bucket: Container | null | undefined, label: string, index: number) {
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

export function suggestedQuantityForPart(bucket: Container | null | undefined, label: string, index: number) {
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

export function christmasPartGuidance(bucket: Container | null | undefined, label: string) {
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

export function christmasPreviewGuidance(buildType: string, label: string, heightValue?: string | null, widthValue?: string | null) {
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

export function compactSkuPart(value?: string | null, fallback = "NEW", limit = 5) {
  return (value || "").replace(/[^a-z0-9]+/gi, "").slice(0, limit).toUpperCase() || fallback;
}

export function skuCodeForBuildType(buildType: string) {
  return buildTypeConfigFor(buildType)?.skuCode || "GR-CUS";
}

export function selectedSkuSource(bucket?: Container | null) {
  if (!bucket) return "";
  const baseLabels = ["container", "base", "planter", "tree/base", "garland", "wreath"];
  const baseItem = bucket.items.find((item) =>
    (item.status || "selected") === "selected" && baseLabels.some((label) => normalizeLabel(item.part_label).includes(label))
  );
  const focalItem = bucket.items.find((item) => (item.status || "selected") === "selected");
  return baseItem?.supplier_sku || baseItem?.product_name || focalItem?.supplier_sku || focalItem?.product_name || "";
}

export function suggestedSkuForType(buildType: string, label?: string | null, arrangement?: Arrangement | null, section: BuilderSection = "green") {
  const code = buildTypeConfigFor(buildType)?.skuCode || `${section === "christmas" ? "CH" : "GR"}-CUS`;
  const projectPart = compactSkuPart(arrangement?.name || arrangement?.client_name || label || buildType, "BUILD", 5);
  return `${code}-${projectPart}-${new Date().getFullYear()}`;
}

export function suggestedFinishedSku(bucket?: Container | null, arrangement?: Arrangement | null) {
  const code = skuCodeForBuildType(`${bucket?.bucket_type || ""} ${bucket?.label || ""}`);
  const sourcePart = compactSkuPart(selectedSkuSource(bucket) || bucket?.label || bucket?.bucket_type || arrangement?.name, "BUILD", 5);
  return `${code}-${sourcePart}-${new Date().getFullYear()}`;
}

export function mechanicsEstimate(bucket?: Container | null) {
  const components = parseScopeIntelligence(bucket?.scope_notes)?.components || [];
  return components
    .filter((component) => ["foam", "moss", "fiber", "mechanic", "stake", "clip", "wire", "filler", "stabil"].some((term) => normalizeLabel(component.label).includes(term)))
    .reduce((sum, component) => sum + (Number(component.average_extended_total) || 0), 0);
}

export function evidenceForConfig(config: typeof BUILD_TYPE_CONFIGS[number], buildTypes: BuildTypeOption[]) {
  return buildTypes.reduce((sum, option) => {
    const labelMatches = config.aliases.some((alias) => normalizeLabel(alias) === normalizeLabel(option.label));
    const prefixMatches = (option.prefixes || []).some((prefix) => config.prefixes.some((knownPrefix) => knownPrefix === prefix));
    return labelMatches || prefixMatches ? sum + (Number(option.evidence_count) || 0) : sum;
  }, 0);
}

export function builderProductName(product: LibraryProduct) {
  return String(product.raw_data?.Description || product.description || product.name || "").trim();
}
