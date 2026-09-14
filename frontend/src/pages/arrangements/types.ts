// Type declarations shared by pages/Arrangements.tsx and its extracted modules.

export type ItemStatus = "candidate" | "selected";

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

export type Container = {
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

export type ProjectRoom = {
  id: number;
  arrangement_id: number;
  name: string;
  notes?: string;
  sort_order: number;
  created_at: string;
  updated_at: string;
};

export type Arrangement = {
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

export type ArrangementSummary = {
  id: number;
  name: string;
  client_name?: string;
  created_at: string;
  updated_at: string;
  total_cost: number;
  container_count: number;
};

export type BuildTypeOption = {
  label: string;
  evidence_count?: number;
  prefixes?: string[];
};

export type EditableBuildTemplate = {
  id: string;
  section: "Green" | "Christmas";
  name: string;
  summary?: string;
  usedFor?: string[];
  slots?: string[];
  regularMaterials?: string[];
  premiumMaterials?: string[];
};

export type BuilderSection = "green" | "christmas";
export type ChristmasEnhancerPackage = "regular" | "premium";
export type GarlandPackage = "regular" | "premium";
export type GarlandDiameter = "14" | "18";
export type WreathSize = "24" | "30" | "36" | "48";

export type BuildSuggestionComponent = {
  label: string;
  suggested_quantity: number;
  average_quantity?: number;
  evidence_count: number;
  average_extended_total?: number | null;
  vendors?: string[];
  examples?: string[];
  search_terms?: string[];
};

export type BuildSuggestion = {
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

export type BuilderFieldKey = "height" | "width" | "canopy" | "silhouette" | "depth" | "species" | "density";

export type BuilderTypeSlot = { order: number; label: string; scope: string; scope_label?: string };

export type BuilderBuildType = {
  key: string;
  label: string;
  aliases?: string[];
  recipe_count?: number;
  usable_recipe_count?: number;
  has_history?: boolean;
  slots?: BuilderTypeSlot[];
  fields?: Partial<Record<BuilderFieldKey, boolean>>;
  applies?: string[];
  notes?: string | null;
  seed_from?: string;
  data_note?: string;
};

export type BuilderSpecies = {
  name: string;
  structural_class: "built_up" | "specimen" | string;
  density_applies?: boolean;
  recipe_count?: number;
  usable_recipe_count?: number;
  heights_ft?: number[];
  median_pieces?: number | null;
  median_structural_pieces?: number | null;
};

export type CanopyTier = {
  key: string;
  label: string;
  min_in: number | null;
  max_in: number | null;
  range_label: string;
};

export type SilhouetteOption = {
  key: string;
  label: string;
  depth_ratio: number;
  use?: string;
  default?: boolean;
};

export type CanopyTiersResponse = {
  band?: string | null;
  tiers?: CanopyTier[];
  default_tier?: string | null;
  default_width_in?: number | null;
  provisional?: boolean;
  n?: number;
  silhouettes?: SilhouetteOption[];
  height_display?: string | null;
  height_in?: number | null;
  spec_matches_measured?: boolean | null;
};

type DensityBand = {
  key: string;
  label: string;
  pieces: number;
  multiplier?: number;
  percentile?: number;
  basis?: string;
};

export type DensityResponse = {
  requested_species?: string | null;
  species?: string | null;
  structural_class?: string;
  density_applies?: boolean;
  height_display?: string | null;
  baseline_pieces?: number | null;
  n?: number;
  observed_min?: number | null;
  observed_max?: number | null;
  confidence?: string;
  source?: string;
  bands?: DensityBand[];
  default_band?: string | null;
  notes?: string[];
};

export type CommonBuild = {
  name: string;
  build_type?: string;
  species?: string | null;
  recipe_count?: number;
  height_in?: number | null;
  height_display?: string | null;
  width_in?: number | null;
  depth_in?: number | null;
  canopy_tier?: string | null;
  height_band?: string | null;
  silhouette?: string | null;
  pieces?: number | null;
  structural_pieces?: number | null;
  typical_component_cost?: number | null;
  typical_retail?: number | null;
};

export type ScopeFilterTerm = { term: string; recipes?: number; weight?: number; catalog_verified?: boolean | null };
type ScopeFilterFacet = { value: string; weight?: number; source?: string };

export type ScopeFilterSlot = {
  slot: string;
  label: string;
  filters?: { categories?: ScopeFilterFacet[]; product_types?: ScopeFilterFacet[]; colors?: ScopeFilterFacet[] };
  exclude_categories?: string[];
  search_terms?: ScopeFilterTerm[];
  recipe_lines?: number;
  ordering_note?: string;
};

export type ProjectsListCache = {
  arrangements: ArrangementSummary[];
  cachedAt: number;
};

export type BuildScopeValues = {
  height: string;
  width: string;
  depth: string;
  species: string;
  canopy: string;
  canopyRange: string;
  silhouette: string;
  silhouetteLabel: string;
  density: string;
  densityLabel: string;
  densityPieces: number | null;
};

export type EnhancerPartConfig = {
  label: string;
  note: string;
  regularFormula?: string;
  premiumFormula?: string;
  fallbackQuantity: number;
  searchTerms?: string;
  optional?: boolean;
  premiumOnly?: boolean;
};

export type BuilderCardSize = 1 | 2 | 3 | 4;

export type CatalogSelection = { categories: string[]; colors: string[]; product_types: string[] };
