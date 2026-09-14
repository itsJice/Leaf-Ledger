// Scope-notes parsers and writers.
import type {
  Container,
  ChristmasEnhancerPackage,
  GarlandPackage,
  GarlandDiameter,
  WreathSize,
  BuildSuggestion,
  BuilderFieldKey,
  BuildScopeValues,
} from "./types";
import { INTELLIGENCE_NOTE_PREFIX, CUSTOM_SECTIONS_PREFIX } from "./constants";
import { normalizeLabel, firstNumber, scopeNoteValue } from "./textHelpers";

export function scopeTitle(bucket?: Container | null) {
  if (!bucket) return "Scope";
  return bucket.label || bucket.bucket_type || `Scope ${bucket.sort_order + 1}`;
}

export function scopeQuantity(bucket?: Container | null) {
  return Math.max(1, Number(bucket?.requested_quantity || 1));
}

export function parseScopeIntelligence(notes?: string | null): BuildSuggestion | null {
  const line = (notes || "").split("\n").find((part) => part.startsWith(INTELLIGENCE_NOTE_PREFIX));
  if (!line) return null;
  try {
    return JSON.parse(line.slice(INTELLIGENCE_NOTE_PREFIX.length));
  } catch {
    return null;
  }
}

export function parseCustomSections(notes?: string | null) {
  const line = (notes || "").split("\n").find((part) => part.startsWith(CUSTOM_SECTIONS_PREFIX));
  if (!line) return [];
  try {
    const parsed = JSON.parse(line.slice(CUSTOM_SECTIONS_PREFIX.length));
    return Array.isArray(parsed) ? parsed.map((value) => String(value).trim()).filter(Boolean) : [];
  } catch {
    return [];
  }
}

export function displayScopeNotes(notes?: string | null) {
  return (notes || "")
    .split("\n")
    .filter((line) => !line.startsWith(INTELLIGENCE_NOTE_PREFIX))
    .filter((line) => !line.startsWith(CUSTOM_SECTIONS_PREFIX))
    .join("\n")
    .trim();
}

export function editableScopeNotes(notes?: string | null) {
  return displayScopeNotes(notes)
    .split("\n")
    .filter((line) => !MANAGED_SCOPE_LINE_RE.test(line.trim()))
    .join("\n")
    .trim();
}

// Every scope-note key the builder owns, so a managed value is never duplicated
// into the free-text notes. `width / canopy` and `depth / density` are the
// pre-Phase-C keys: they are no longer written, but they are still stripped here
// and still read below, so a design saved under them keeps its values.
export const MANAGED_SCOPE_LINE_RE = /^(tree type|tree source|tree lights|height|width \/ canopy|depth \/ density|width|depth|species|canopy|silhouette|density|enhancer package|garland package|garland light|garland size|garland length|garland diameter|wreath size):/i;

/**
 * Reading the Step 1 dimensions out of `scope_notes`.
 *
 * Phase C replaced the free-text "Width / canopy" and "Depth / density" boxes -
 * words that appear in zero of 223 recipes - with `Width` / `Depth` plus the
 * measured `Species`, `Canopy`, `Silhouette` and `Density`. Only the new keys
 * are written, but every reader falls back to the old key, so a design saved
 * before this change still shows its width and depth and round-trips without
 * losing them. `LL_BUILD_INTELLIGENCE:` / `LL_CUSTOM_SECTIONS:` lines are never
 * touched by any of this.
 */
export function buildHeightFromNotes(notes?: string | null) {
  return scopeNoteValue(notes, "Height");
}

export function buildWidthFromNotes(notes?: string | null) {
  return scopeNoteValue(notes, "Width") || scopeNoteValue(notes, "Width / canopy");
}

// The old "Depth / density" box was one field doing two jobs, and its own
// placeholder invited words ("light, medium, dense") rather than a measurement.
// So it only feeds Depth when it actually holds a number; otherwise it is read
// as a fullness word by buildDensityBandFromNotes below and nothing is lost.
export function buildDepthFromNotes(notes?: string | null) {
  const explicit = scopeNoteValue(notes, "Depth");
  if (explicit) return explicit;
  const legacy = scopeNoteValue(notes, "Depth / density");
  return firstNumber(legacy) ? legacy : "";
}

export function buildSpeciesFromNotes(notes?: string | null) {
  return scopeNoteValue(notes, "Species");
}

// Stored as `Canopy: M (42-45")`, so take the leading tier key.
export function buildCanopyTierFromNotes(notes?: string | null) {
  const value = scopeNoteValue(notes, "Canopy");
  const match = value.match(/^(XS|S|M|L|XL)\b/i);
  return match ? match[1].toUpperCase() : "";
}

export function buildSilhouetteFromNotes(notes?: string | null) {
  const value = normalizeLabel(scopeNoteValue(notes, "Silhouette"));
  if (!value) return "";
  if (value.includes("corner")) return "corner";
  if (value.includes("flat") || value.includes("3-sid") || value.includes("3 sid") || value.includes("wall")) return "flat_back";
  if (value.includes("round")) return "full_round";
  return "";
}

// `Density: Full (12 pieces)`. The legacy "Depth / density" box occasionally held
// a fullness word instead of a number, so it is read as a last resort.
export function buildDensityBandFromNotes(notes?: string | null) {
  const value = normalizeLabel(scopeNoteValue(notes, "Density") || scopeNoteValue(notes, "Depth / density"));
  if (!value) return "";
  if (value.includes("super")) return "super_full";
  if (value.includes("sparse")) return "sparse";
  if (value.includes("full")) return "full";
  if (value.includes("standard")) return "standard";
  // The words the old box's own placeholder asked for.
  if (value.includes("light") || value.includes("thin") || value.includes("slim")) return "sparse";
  if (value.includes("medium")) return "standard";
  if (value.includes("dense") || value.includes("heavy")) return "full";
  return "";
}

/**
 * The Step 1 lines to persist, filtered to the fields the type actually
 * supports. Container Only carries no canopy/silhouette/density and Drop-in no
 * canopy/silhouette, so those lines are never written for them.
 */
export function buildScopeSetupLines(fields: Record<BuilderFieldKey, boolean>, values: BuildScopeValues) {
  const lines: string[] = [];
  const push = (field: BuilderFieldKey, line: string) => {
    if (fields[field] && line.trim()) lines.push(line.trim());
  };
  push("height", values.height.trim() ? `Height: ${values.height.trim()}` : "");
  push("species", values.species.trim() ? `Species: ${values.species.trim()}` : "");
  push("canopy", values.canopy ? `Canopy: ${values.canopy}${values.canopyRange ? ` (${values.canopyRange})` : ""}` : "");
  push("width", values.width.trim() ? `Width: ${values.width.trim()}` : "");
  push("silhouette", values.silhouette ? `Silhouette: ${values.silhouetteLabel || values.silhouette}` : "");
  push("depth", values.depth.trim() ? `Depth: ${values.depth.trim()}` : "");
  push(
    "density",
    values.density
      ? `Density: ${values.densityLabel || values.density}${values.densityPieces != null ? ` (${values.densityPieces} pieces)` : ""}`
      : ""
  );
  return lines;
}

export function scopeIntelligenceLine(notes?: string | null) {
  return (notes || "").split("\n").find((line) => line.startsWith(INTELLIGENCE_NOTE_PREFIX)) || "";
}

export function scopeNotesWithCustomSections(bucket: Container, customSections: string[]) {
  return [
    displayScopeNotes(bucket.scope_notes),
    scopeIntelligenceLine(bucket.scope_notes),
    customSections.length ? `${CUSTOM_SECTIONS_PREFIX}${JSON.stringify(customSections)}` : "",
  ].filter(Boolean).join("\n");
}

export function christmasEnhancerPackageFromNotes(notes?: string | null): ChristmasEnhancerPackage {
  return scopeNoteValue(notes, "Enhancer package").toLowerCase().includes("premium") ? "premium" : "regular";
}

export function scopeNotesWithEnhancerPackage(bucket: Container, packageType: ChristmasEnhancerPackage) {
  const nextLine = `Enhancer package: ${packageType === "premium" ? "Premium" : "Regular"}`;
  return [
    ...(bucket.scope_notes || "")
      .split("\n")
      .filter((line) => !line.trim().toLowerCase().startsWith("enhancer package:")),
    nextLine,
  ].filter(Boolean).join("\n");
}

export function garlandPackageFromNotes(notes?: string | null): GarlandPackage {
  return scopeNoteValue(notes, "Garland package").toLowerCase().includes("premium") ? "premium" : "regular";
}

export function garlandLengthFromNotes(notes?: string | null) {
  const explicit = firstNumber(scopeNoteValue(notes, "Garland length"));
  if (explicit) return String(explicit);
  const legacySize = scopeNoteValue(notes, "Garland size");
  return String(firstNumber(legacySize) || 9);
}

export function garlandDiameterFromNotes(notes?: string | null): GarlandDiameter {
  const explicit = scopeNoteValue(notes, "Garland diameter");
  const legacySize = scopeNoteValue(notes, "Garland size");
  return `${explicit} ${legacySize}`.includes("18") ? "18" : "14";
}

export function garlandLengthLabel(lengthValue?: string | null) {
  const length = firstNumber(lengthValue) || 9;
  return `${Number.isInteger(length) ? length : length.toFixed(1).replace(/\.0$/, "")} ft`;
}

export function garlandLengthMultiplier(lengthValue?: string | null) {
  const length = firstNumber(lengthValue) || 9;
  return Math.max(1, Math.ceil(length / 9));
}

export function garlandSetupLabel(lengthValue?: string | null, diameter: GarlandDiameter = "14") {
  return `${garlandLengthLabel(lengthValue)} x ${diameter}"`;
}

export function garlandSetupLines(packageType: GarlandPackage, lengthValue: string, diameter: GarlandDiameter) {
  return [
    `Garland package: ${packageType === "premium" ? "Premium" : "Regular"}`,
    `Garland length: ${garlandLengthLabel(lengthValue)}`,
    `Garland diameter: ${diameter}"`,
  ];
}

export function scopeNotesWithGarlandSetup(
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

export function wreathSizeFromNotes(notes?: string | null): WreathSize {
  const explicit = firstNumber(scopeNoteValue(notes, "Wreath size"));
  const canopy = firstNumber(buildWidthFromNotes(notes));
  const value = explicit || canopy || 24;
  if (value >= 48) return "48";
  if (value >= 36) return "36";
  if (value >= 30) return "30";
  return "24";
}

export function wreathSetupLines(size: WreathSize) {
  return [`Wreath size: ${size}" Wreath`];
}

export function scopeNotesWithWreathSetup(bucket: Container, size: WreathSize) {
  return [
    ...(bucket.scope_notes || "")
      .split("\n")
      .filter((line) => !/^(wreath size|height|width \/ canopy|depth \/ density|width|depth|canopy|silhouette|density|species):/i.test(line.trim())),
    ...wreathSetupLines(size),
  ].filter(Boolean).join("\n");
}
