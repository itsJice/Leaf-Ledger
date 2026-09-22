// Arrangements constants and storage keys.
import { PROJECTS_LIST_CACHE_KEY, BUILD_TEMPLATE_STORAGE_KEY } from "../../constants";
import type { BuilderFieldKey, SilhouetteOption, CatalogSelection } from "./types";

// Re-exported for callers that historically imported these from this page.
export { PROJECTS_LIST_CACHE_KEY, BUILD_TEMPLATE_STORAGE_KEY };
export const INTELLIGENCE_NOTE_PREFIX = "LL_BUILD_INTELLIGENCE:";
export const CUSTOM_SECTIONS_PREFIX = "LL_CUSTOM_SECTIONS:";

// ─── Builder intelligence (/api/builder) ─────────────────────────────────────
// The measured numbers behind Step 1. Every value the builder now asks for is
// backed by the 223 imported historical recipes: canopy tiers are defined per
// height band, density is keyed to species x height and never pooled, and each
// build type declares exactly which dimension fields it can use. See
// app/docs/TREE_SCOPE_SPEC.md.

export const BUILDER_TYPES_CACHE_KEY = "leaf-ledger:builder-build-types:v1";
// Builder-only view prefs. Deliberately NOT the Catalog Search keys - the two
// panes are different sizes and the user tunes them independently.
export const BUILDER_CATALOG_VIEW_KEY = "leaf-ledger:builder-catalog-view:v1";
export const BUILDER_CATALOG_SIZE_KEY = "leaf-ledger:builder-catalog-size:v1";
export const BUILDER_CATALOG_WIDTH_KEY = "leaf-ledger:builder-catalog-width:v1";
export const BUILDER_CATALOG_EXPANDED_KEY = "leaf-ledger:builder-catalog-expanded:v1";

export const BUILDER_FIELD_KEYS: BuilderFieldKey[] = ["height", "width", "canopy", "silhouette", "depth", "species", "density"];

// Falls back to the spec's table so the control still renders if the silhouette
// list has not arrived (it ships inside the canopy-tiers response).
export const SILHOUETTE_FALLBACK: SilhouetteOption[] = [
  { key: "full_round", label: "Full-round", depth_ratio: 1.0, use: "freestanding, viewed 360°", default: true },
  { key: "corner", label: "Corner", depth_ratio: 0.66, use: "tucked into a corner" },
  { key: "flat_back", label: "3-sided / flat-back", depth_ratio: 0.5, use: "flush against a wall" },
];

export const BUILDER_CATALOG_PAGE_SIZE = 48;
export const EMPTY_CATALOG_SELECTION: CatalogSelection = { categories: [], colors: [], product_types: [] };
