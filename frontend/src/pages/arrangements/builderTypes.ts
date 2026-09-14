// Builder build-type cache and /api/builder helpers.
import type {
  BuilderFieldKey,
  BuilderTypeSlot,
  BuilderBuildType,
  CanopyTier,
  SilhouetteOption,
  ScopeFilterTerm,
} from "./types";
import { BUILDER_TYPES_CACHE_KEY, BUILDER_FIELD_KEYS } from "./constants";
import { normalizeLabel } from "./textHelpers";

// Every field a type could declare. Used when the API is unreachable so Step 1
// degrades to the pre-Phase-C behaviour (plain height/width/depth) rather than
// showing canopy and density with nothing behind them.
export const BUILDER_FIELDS_FALLBACK: Record<BuilderFieldKey, boolean> = {
  height: true, width: true, canopy: false, silhouette: false, depth: true, species: false, density: false,
};

let builderTypesMemo: BuilderBuildType[] | null = null;

export function cleanBuilderBuildTypes(value: unknown): BuilderBuildType[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((row) => {
      const item = row as Partial<BuilderBuildType>;
      const label = String(item?.label || "").trim();
      if (!label) return null;
      return {
        key: String(item.key || label),
        label,
        aliases: Array.isArray(item.aliases) ? item.aliases.map(String) : [],
        recipe_count: Number(item.recipe_count) || 0,
        usable_recipe_count: Number(item.usable_recipe_count) || 0,
        has_history: Boolean(item.has_history),
        slots: Array.isArray(item.slots)
          ? item.slots
              .map((slot, index) => ({
                order: Number((slot as BuilderTypeSlot)?.order ?? index),
                label: String((slot as BuilderTypeSlot)?.label || "").trim(),
                scope: String((slot as BuilderTypeSlot)?.scope || ""),
                scope_label: String((slot as BuilderTypeSlot)?.scope_label || ""),
              }))
              .filter((slot) => Boolean(slot.label))
              .sort((a, b) => a.order - b.order)
          : [],
        fields: item.fields && typeof item.fields === "object" ? item.fields : undefined,
        applies: Array.isArray(item.applies) ? item.applies.map(String) : [],
        notes: item.notes ?? null,
        seed_from: item.seed_from,
        data_note: item.data_note,
      } satisfies BuilderBuildType;
    })
    .filter(Boolean) as BuilderBuildType[];
}

export function readBuilderBuildTypes(): BuilderBuildType[] {
  if (builderTypesMemo) return builderTypesMemo;
  if (typeof window === "undefined") return [];
  try {
    builderTypesMemo = cleanBuilderBuildTypes(JSON.parse(window.localStorage.getItem(BUILDER_TYPES_CACHE_KEY) || "null"));
  } catch {
    builderTypesMemo = [];
  }
  return builderTypesMemo;
}

export function writeBuilderBuildTypes(types: BuilderBuildType[]) {
  builderTypesMemo = types;
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(BUILDER_TYPES_CACHE_KEY, JSON.stringify(types));
  } catch {
    // The cache only saves a round trip; the live fetch already succeeded.
  }
}

/**
 * The API build type behind a label, matched through its alias list.
 *
 * Deliberately consulted only where the existing config/template lookup comes
 * up empty, so the four historical green types keep the exact slot labels and
 * order they already save under (their API slots are identical anyway) and only
 * the newly added types - Plant & Bush, Container Only, Topiary - are driven
 * from the API template.
 */
export function builderApiTypeFor(buildType: string, known?: BuilderBuildType[]): BuilderBuildType | null {
  const normalized = normalizeLabel(buildType);
  if (!normalized) return null;
  // The module-level cache is the fallback so the synchronous slot lookup
  // (designPartsForBuildType) can answer during the first render after a reload;
  // callers inside the component pass the live state instead.
  const types = known?.length ? known : readBuilderBuildTypes();
  if (!types.length) return null;
  const exact = types.find((type) =>
    [type.label, ...(type.aliases || [])].some((value) => normalizeLabel(value) === normalized)
  );
  if (exact) return exact;
  return (
    types.find((type) =>
      [type.label, ...(type.aliases || [])]
        .map(normalizeLabel)
        .some((value) => value.length > 3 && (normalized.includes(value) || value.includes(normalized)))
    ) || null
  );
}

export function builderApiSlotsForBuildType(buildType: string): string[] | null {
  const slots = builderApiTypeFor(buildType)?.slots || [];
  return slots.length ? slots.map((slot) => slot.label) : null;
}

export function builderFieldsForBuildType(buildType: string, known?: BuilderBuildType[]): Record<BuilderFieldKey, boolean> {
  const declared = builderApiTypeFor(buildType, known)?.fields;
  if (!declared) return { ...BUILDER_FIELDS_FALLBACK };
  return BUILDER_FIELD_KEYS.reduce((next, key) => {
    next[key] = Boolean(declared[key]);
    return next;
  }, {} as Record<BuilderFieldKey, boolean>);
}

// The scope slot a part label belongs to, so Choose Parts can ask the API for
// that slot's smart filters. Mirrors the backend's `_resolve_slot` vocabulary.
export function scopeSlotForPartLabel(label: string): string | null {
  const text = normalizeLabel(label);
  if (!text) return null;
  if (text.includes("container") || text.includes("planter") || text.includes("base") || text.includes("vessel")) return "container";
  if (text.includes("top dressing") || text === "finish" || text.includes("finish/")) return "top_dressing";
  if (text.includes("trunk") || text.includes("branches")) return "trunks";
  if (text.includes("accent")) return "accent";
  if (
    text.includes("leaves") || text.includes("plant") || text.includes("greenery") || text.includes("focal") ||
    text.includes("succulent") || text.includes("cactus") || text.includes("material")
  ) {
    return "plant_material";
  }
  return null;
}

export function builderApiUrl(path: string, params?: Record<string, string | number | undefined | null>) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params || {})) {
    if (value === undefined || value === null || value === "") continue;
    query.set(key, String(value));
  }
  const suffix = query.toString();
  return `/api/builder/${path}${suffix ? `?${suffix}` : ""}`;
}

export function silhouetteOption(key: string, options: SilhouetteOption[]) {
  return options.find((option) => option.key === key) || options.find((option) => option.default) || options[0] || null;
}

export function formatInches(value?: number | null) {
  if (value == null || !Number.isFinite(value)) return "";
  const rounded = Math.round(value * 10) / 10;
  return `${Number.isInteger(rounded) ? rounded : rounded.toFixed(1)}"`;
}

// The width a tier implies when the designer picks the tier instead of typing a
// number: the middle of the tier's own range, so "Medium" lands mid-Medium.
export function widthForCanopyTier(tier: CanopyTier | null | undefined) {
  if (!tier) return null;
  if (tier.min_in != null && tier.max_in != null) return (tier.min_in + tier.max_in) / 2;
  if (tier.max_in != null) return Math.max(1, tier.max_in - 3);
  if (tier.min_in != null) return tier.min_in + 3;
  return null;
}

export function confidenceLabel(confidence?: string | null) {
  const text = String(confidence || "").replace(/_/g, " ").trim();
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : "";
}

// Terms a search would return nothing for are demoted, never dropped - the
// shop's own vocabulary stays visible, it just sorts last so a pre-applied
// filter always comes back with products. `null` means the catalog index was
// cold and the term is simply unchecked.
export function sortedScopeTerms(terms: ScopeFilterTerm[]) {
  return [...terms].sort((a, b) => {
    const aUnverified = a.catalog_verified === false ? 1 : 0;
    const bUnverified = b.catalog_verified === false ? 1 : 0;
    if (aUnverified !== bUnverified) return aUnverified - bUnverified;
    return (Number(b.weight) || 0) - (Number(a.weight) || 0);
  });
}
