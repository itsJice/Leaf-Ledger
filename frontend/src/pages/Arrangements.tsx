import React, { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import {
  ArrowLeft,
  CheckCircle2,
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
import DesignDestinationPicker, {
  EMPTY_DESIGN_DESTINATION,
  destinationIsComplete,
  type DesignDestination,
  type DesignHierarchy,
} from "components/DesignDestinationPicker";
import { apiClient } from "app";
import { apiFetch } from "utils/apiFetch";
import { ContentType } from "../apiclient/http-client";
import { formatCurrency, unitLabel } from "utils/format";
import { toast } from "sonner";
import { notifyProjectsChanged } from "utils/projectsChanged";
import { ProductDetailModal } from "./library/ProductDetailModal";
import { productDisplayImageUrl } from "./library/display";
import type { Product as LibraryProduct } from "./library/types";
import type {
  ItemStatus,
  Container,
  ProjectRoom,
  Arrangement,
  ArrangementSummary,
  BuildTypeOption,
  BuilderSection,
  ChristmasEnhancerPackage,
  GarlandPackage,
  GarlandDiameter,
  WreathSize,
  BuildSuggestion,
  BuilderBuildType,
  BuilderSpecies,
  CanopyTiersResponse,
  DensityResponse,
  CommonBuild,
  ScopeFilterSlot,
} from "./arrangements/types";
import {
  INTELLIGENCE_NOTE_PREFIX,
  CUSTOM_SECTIONS_PREFIX,
  BUILDER_CATALOG_WIDTH_KEY,
  BUILDER_CATALOG_EXPANDED_KEY,
  SILHOUETTE_FALLBACK,
} from "./arrangements/constants";
import {
  cleanBuilderBuildTypes,
  readBuilderBuildTypes,
  writeBuilderBuildTypes,
  builderApiTypeFor,
  builderFieldsForBuildType,
  scopeSlotForPartLabel,
  builderApiUrl,
  silhouetteOption,
  formatInches,
  widthForCanopyTier,
} from "./arrangements/builderTypes";
import {
  readProjectsListCache,
  writeProjectsListCache,
  formatProjectsCacheStamp,
  arrangementShellFromSummary,
  arrangementRouteShell,
} from "./arrangements/projects";
import {
  scopeTitle,
  scopeQuantity,
  parseScopeIntelligence,
  parseCustomSections,
  displayScopeNotes,
  editableScopeNotes,
  buildHeightFromNotes,
  buildWidthFromNotes,
  buildDepthFromNotes,
  buildSpeciesFromNotes,
  buildCanopyTierFromNotes,
  buildSilhouetteFromNotes,
  buildDensityBandFromNotes,
  buildScopeSetupLines,
  scopeIntelligenceLine,
  scopeNotesWithCustomSections,
  christmasEnhancerPackageFromNotes,
  scopeNotesWithEnhancerPackage,
  garlandPackageFromNotes,
  garlandLengthFromNotes,
  garlandDiameterFromNotes,
  garlandLengthLabel,
  garlandSetupLines,
  scopeNotesWithGarlandSetup,
  wreathSizeFromNotes,
  wreathSetupLines,
  scopeNotesWithWreathSetup,
} from "./arrangements/scopeNotes";
import {
  BUILD_TYPE_CONFIGS,
  GARLAND_DIAMETER_OPTIONS,
  WREATH_SIZE_OPTIONS,
  CHRISTMAS_TREE_SIZE_OPTIONS,
  buildTypeConfigFor,
} from "./arrangements/buildConfigs";
import { normalizeLabel, firstNumber, scopeNoteValue } from "./arrangements/textHelpers";
import {
  designPartsForBuildType,
  baseScopePlaceholders,
  fallbackSectionsForBuildType,
  scopePlaceholders,
  christmasTreeDecorRule,
  christmasTreeDecorRuleForBucket,
  christmasEnhancerCountSummary,
  isChristmasTreeBuild,
  isChristmasTreeBucket,
  isGarlandBuild,
  isGarlandBucket,
  isWreathBuild,
  isWreathBucket,
  isStructuredChristmasBucket,
  isEnhancersPart,
  isWreathDecorPart,
  christmasEnhancerPartIndex,
  christmasEnhancerPartIsOptional,
  christmasEnhancerPartsForPackage,
  christmasEnhancerPartSubIndex,
  christmasEnhancerPartPreviewText,
  christmasEnhancerPartTargetText,
  christmasEnhancerPartItems,
  garlandEnhancerRule,
  garlandEnhancerPartsForPackage,
  garlandEnhancerPartSubIndex,
  garlandEnhancerPartPreviewText,
  garlandEnhancerPartItems,
  garlandEnhancerCountSummary,
  wreathDecorPartsForSize,
  wreathDecorPartSubIndex,
  wreathDecorPartItems,
  wreathDecorPartPreviewText,
  wreathDecorCountSummary,
  partKey,
  partKeysForSlot,
  itemsForPart,
  partIsComplete,
  suggestionForPart,
  searchTermsForPart,
  suggestedQuantityForPart,
  christmasPartGuidance,
  christmasPreviewGuidance,
  suggestedSkuForType,
  suggestedFinishedSku,
  mechanicsEstimate,
  evidenceForConfig,
} from "./arrangements/parts";
import { BuilderProductPicker } from "./arrangements/BuilderProductPicker";
import { MeasuredScopeFields } from "./arrangements/MeasuredScopeFields";
import { NewProjectModal } from "./arrangements/NewProjectModal";

// Re-exported for existing importers of this page (components/Clients.tsx, utils/__tests__/buildTemplates.test.ts).
export { NewProjectModal };
export { DEFAULT_EDITABLE_BUILD_TEMPLATES, LEGACY_TOP_DOWN_SLOT_ORDERS, cleanEditableBuildTemplates } from "./arrangements/templates";


async function fetchBuilderJson<T>(path: string, params?: Record<string, string | number | undefined | null>): Promise<T | null> {
  try {
    const response = await apiFetch(builderApiUrl(path, params));
    if (!response.ok) return null;
    return (await response.json()) as T;
  } catch {
    return null;
  }
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

/**
 * Props are optional. The `/designs/new` route may render this page either as
 * `<Arrangements newDesign />` or plainly as `<Arrangements />` - the pathname
 * is checked too, so both wiring styles land in the standalone builder.
 */
export default function Arrangements({ newDesign, mode, embedded }: { newDesign?: boolean; mode?: string; embedded?: boolean } = {}) {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedId = searchParams.get("id") ? Number(searchParams.get("id")) : null;
  const clientFilter = searchParams.get("client") || "";
  const isClientPath = location.pathname.includes("/clients/project");
  const isNewDesignPath = /\/designs\/new\/?$/.test(location.pathname);
  // Standalone "New Design" mode: open the builder immediately, no project picked yet.
  // Reachable three ways so the route owner can wire it however they prefer:
  // a `newDesign` / `mode="new-design"` prop, the /designs/new pathname, or ?newDesign=1.
  const standaloneNewDesign = Boolean(newDesign)
    || mode === "new-design"
    || isNewDesignPath
    || searchParams.get("newDesign") === "1";
  const cachedProjectsList = useMemo(() => readProjectsListCache(), []);

  const [arrangements, setArrangements] = useState<ArrangementSummary[]>(() => cachedProjectsList?.arrangements || []);
  const [arrangement, setArrangement] = useState<Arrangement | null>(null);
  const [detailProduct, setDetailProduct] = useState<LibraryProduct | null>(null);

  // The fast search index returns a lean row (id/name/sku/price/images), so the
  // detail modal is filled from /detail like Catalog Search does. The lean row is
  // shown immediately and replaced when the full record lands.
  const openBuilderProductDetail = (product: LibraryProduct) => {
    setDetailProduct(product);
    void apiFetch(`/api/products/detail/${product.id}`)
      .then((response) => (response.ok ? response.json() : null))
      .then((full) => { if (full) setDetailProduct(full as LibraryProduct); })
      .catch(() => {});
  };
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
  // --- Phase C: measured Step 1 fields (see app/docs/TREE_SCOPE_SPEC.md) ---
  // treeCanopySize / treeDensity stay behind, still holding the Christmas tree's
  // diameter and profile. The green builds now use these instead.
  const [buildSpecies, setBuildSpecies] = useState("");
  const [buildWidth, setBuildWidth] = useState("");
  const [buildDepth, setBuildDepth] = useState("");
  const [buildCanopyTier, setBuildCanopyTier] = useState("");
  const [buildSilhouette, setBuildSilhouette] = useState("full_round");
  const [buildDensityBand, setBuildDensityBand] = useState("");
  const [commonBuildPick, setCommonBuildPick] = useState("");
  const [builderTypes, setBuilderTypes] = useState<BuilderBuildType[]>(() => readBuilderBuildTypes());
  const [speciesOptions, setSpeciesOptions] = useState<BuilderSpecies[]>([]);
  const [canopyTiers, setCanopyTiers] = useState<CanopyTiersResponse | null>(null);
  const [densityInfo, setDensityInfo] = useState<DensityResponse | null>(null);
  const [commonBuilds, setCommonBuilds] = useState<CommonBuild[]>([]);
  const [scopeFilters, setScopeFilters] = useState<ScopeFilterSlot | null>(null);
  // --- Phase D: catalog pane sizing ---
  const [catalogWidth, setCatalogWidth] = useState<number>(() => {
    const stored = Number(window.localStorage.getItem(BUILDER_CATALOG_WIDTH_KEY));
    return Number.isFinite(stored) && stored >= 320 ? stored : 460;
  });
  const [catalogExpanded, setCatalogExpanded] = useState<boolean>(
    () => window.localStorage.getItem(BUILDER_CATALOG_EXPANDED_KEY) === "1"
  );
  const [wideLayout, setWideLayout] = useState<boolean>(
    () => typeof window !== "undefined" && window.matchMedia("(min-width: 1024px)").matches
  );
  const [resizingCatalog, setResizingCatalog] = useState(false);
  const splitRef = useRef<HTMLDivElement>(null);
  // --- Standalone "New Design" destination (client / project / group) ---
  // Nothing here is persisted until the design is saved in materializeDestination().
  const [designHierarchy, setDesignHierarchy] = useState<DesignHierarchy>({ clients: [], projects: [], groups: [] });
  const [hierarchyLoading, setHierarchyLoading] = useState(false);
  const [designDestination, setDesignDestination] = useState<DesignDestination>(EMPTY_DESIGN_DESTINATION);
  const [destinationSaved, setDestinationSaved] = useState(false);
  const loadedGroupProjectsRef = useRef<Set<number>>(new Set());
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
  /**
   * The Step 1 type list.
   *
   * Green types come from `/api/builder/build-types`, which already orders them
   * by how much history backs each one, so the most-built product leads. That is
   * what adds Plant & Bush, Container Only and Topiary. Counts are always read
   * live - never hardcoded - because the recipe classifier is still being
   * refined and the numbers move.
   *
   * A type that already exists in the builder keeps its existing label (the API's
   * "Floral Arrangement" stays "Arrangement", "Drop-in" stays "Drop-in
   * Arrangement"), so a saved `bucket_type` still resolves to the same slots and
   * SKU code. Christmas is unmeasured and stays on the hardcoded configs.
   */
  const productTypeOptions = useMemo(() => {
    const configFallback = BUILD_TYPE_CONFIGS
      .filter((config) => config.section === selectedProductSection)
      .map((config) => ({
        label: config.label,
        icon: config.icon,
        evidence_count: evidenceForConfig(config, buildTypes),
        prefixes: [...config.prefixes],
      }));
    const customOption = { label: "Custom", icon: Plus, evidence_count: undefined as number | undefined, prefixes: [] as string[] };

    // The API only measures green work, and a failed/401 fetch must never blank
    // out the picker - fall back to the hardcoded configs.
    if (selectedProductSection !== "green" || builderTypes.length === 0) {
      return [...configFallback, customOption];
    }

    const measured = builderTypes
      .filter((type) => normalizeLabel(type.label) !== "custom")
      .map((type) => {
        const config = buildTypeConfigFor(type.label);
        return {
          label: config?.label || type.label,
          icon: config?.icon || (type.slots?.length ? Leaf : Package),
          evidence_count: Number(type.recipe_count) || 0,
          prefixes: config ? [...config.prefixes] : [],
        };
      })
      .filter((option, index, list) => list.findIndex((other) => other.label === option.label) === index);

    // Any green config the API does not know about still has to be selectable.
    const missing = configFallback.filter((option) => !measured.some((row) => row.label === option.label));
    return [...measured, ...missing, customOption];
  }, [buildTypes, builderTypes, selectedProductSection]);
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
    // Driven by productTypeOptions, not BUILD_TYPE_CONFIGS, so a type that only
    // exists in the API (Plant & Bush, Container Only, Topiary) is not bounced
    // back to Tree the moment it is picked.
    const sectionLabels = productTypeOptions.filter((option) => option.label !== "Custom").map((option) => option.label);
    if (selectedScopeType !== "Custom" && !sectionLabels.includes(selectedScopeType)) {
      const nextType = sectionLabels[0] || "Custom";
      setSelectedScopeType(nextType);
      setNewScopeName(nextType);
      setPreviewType(nextType);
      setBuildSuggestion(null);
    }
    setProductTypeSearch("");
  }, [selectedProductSection, selectedScopeType, productTypeOptions]);

  useEffect(() => {
    if (!skuEdited) setFinishedSku(activeDraftSku);
  }, [activeDraftSku, skuEdited]);

  // ─── Phase C: the measured Step 1 fields ───────────────────────────────────

  // The build type's own declaration of which dimension fields it can use. A
  // field a type cannot use is never rendered: Container Only has no canopy,
  // silhouette or density, Drop-in no canopy or silhouette.
  const activeBuilderType = useMemo(
    () => builderApiTypeFor(selectedScopeType === "Custom" ? "Custom" : selectedBuildTypeLabel, builderTypes),
    [builderTypes, selectedScopeType, selectedBuildTypeLabel]
  );
  const activeBuildFields = useMemo(
    () => builderFieldsForBuildType(selectedScopeType === "Custom" ? "Custom" : selectedBuildTypeLabel, builderTypes),
    [builderTypes, selectedScopeType, selectedBuildTypeLabel]
  );
  const usesMeasuredScopeFields = !["Christmas Tree", "Garland", "Wreath"].includes(selectedScopeType);
  const silhouetteOptions = canopyTiers?.silhouettes?.length ? canopyTiers.silhouettes : SILHOUETTE_FALLBACK;
  const activeSilhouette = silhouetteOption(buildSilhouette, silhouetteOptions);
  const activeSpecies = useMemo(
    () => speciesOptions.find((option) => normalizeLabel(option.name) === normalizeLabel(buildSpecies)) || null,
    [speciesOptions, buildSpecies]
  );
  // Never prompt for density on a specimen species: an Areca Palm is ~1 stem at
  // any height, one large potted plant with nothing to build up.
  const densityApplies =
    activeBuildFields.density &&
    activeSpecies?.density_applies !== false &&
    densityInfo?.density_applies !== false;
  const activeCanopyTier = canopyTiers?.tiers?.find((tier) => tier.key === buildCanopyTier) || null;
  const activeDensityBand = densityInfo?.bands?.find((band) => band.key === buildDensityBand) || null;

  // One place that turns the current field values into scope-note lines, so the
  // create path and the update path can never drift apart.
  const measuredScopeLines = (buildTypeOverride?: string) =>
    buildScopeSetupLines(buildTypeOverride ? builderFieldsForBuildType(buildTypeOverride, builderTypes) : activeBuildFields, {
      height: treeHeight,
      width: buildWidth,
      depth: buildDepth,
      species: buildSpecies,
      canopy: buildCanopyTier,
      canopyRange: activeCanopyTier?.range_label || "",
      silhouette: buildSilhouette,
      silhouetteLabel: activeSilhouette?.label || "",
      density: densityApplies ? buildDensityBand : "",
      densityLabel: activeDensityBand?.label || "",
      densityPieces: activeDensityBand?.pieces ?? null,
    });

  // Silhouette sets depth from width (full-round 1.0, corner ~0.66, flat-back
  // ~0.5). History is uniformly round - median depth:width 1.00 - so this is
  // capture-going-forward and it computes the depth rather than asking for it.
  const applySilhouette = (key: string, widthValue = buildWidth) => {
    setBuildSilhouette(key);
    const ratio = silhouetteOption(key, silhouetteOptions)?.depth_ratio ?? 1;
    const widthIn = firstNumber(widthValue);
    if (widthIn) setBuildDepth(formatInches(widthIn * ratio));
  };

  const applyCanopyTier = (key: string) => {
    setBuildCanopyTier(key);
    const tier = canopyTiers?.tiers?.find((row) => row.key === key) || null;
    const width = key === canopyTiers?.default_tier && canopyTiers?.default_width_in != null
      ? canopyTiers.default_width_in
      : widthForCanopyTier(tier);
    if (width == null) return;
    setBuildWidth(formatInches(width));
    const ratio = activeSilhouette?.depth_ratio ?? 1;
    setBuildDepth(formatInches(width * ratio));
  };

  const applyWidth = (value: string) => {
    setBuildWidth(value);
    const widthIn = firstNumber(value);
    if (!widthIn) return;
    setBuildDepth(formatInches(widthIn * (activeSilhouette?.depth_ratio ?? 1)));
    // Retier as the number is typed, so the tier always describes the width.
    const tier = (canopyTiers?.tiers || []).find(
      (row) => (row.min_in == null || widthIn >= row.min_in) && (row.max_in == null || widthIn < row.max_in)
    );
    if (tier) setBuildCanopyTier(tier.key);
  };

  const applyCommonBuild = (name: string) => {
    setCommonBuildPick(name);
    const pick = commonBuilds.find((build) => build.name === name);
    if (!pick) return;
    if (pick.height_display) setTreeHeight(pick.height_display);
    if (pick.species) setBuildSpecies(pick.species);
    if (pick.canopy_tier) setBuildCanopyTier(pick.canopy_tier);
    if (pick.silhouette) setBuildSilhouette(pick.silhouette);
    if (pick.width_in != null) setBuildWidth(formatInches(pick.width_in));
    if (pick.depth_in != null) setBuildDepth(formatInches(pick.depth_in));
    else if (pick.width_in != null) {
      setBuildDepth(formatInches(pick.width_in * (silhouetteOption(pick.silhouette || "full_round", silhouetteOptions)?.depth_ratio ?? 1)));
    }
  };

  const resetMeasuredScopeFields = () => {
    setBuildSpecies("");
    setBuildWidth("");
    setBuildDepth("");
    setBuildCanopyTier("");
    setBuildSilhouette("full_round");
    setBuildDensityBand("");
    setCommonBuildPick("");
    setCanopyTiers(null);
    setDensityInfo(null);
  };

  // Build types + their slot templates, once. Cached to localStorage so the
  // module-level slot lookup (designPartsForBuildType) can answer synchronously
  // during the very first render after a reload.
  useEffect(() => {
    let cancelled = false;
    void fetchBuilderJson<{ build_types?: BuilderBuildType[] }>("build-types").then((data) => {
      if (cancelled) return;
      const cleaned = cleanBuilderBuildTypes(data?.build_types);
      if (!cleaned.length) return;
      writeBuilderBuildTypes(cleaned);
      setBuilderTypes(cleaned);
    });
    return () => { cancelled = true; };
  }, []);

  // Species for the selected type. Explicit at Step 1 because it drives every
  // suggestion below it - density is f(species, height), never pooled.
  useEffect(() => {
    if (!usesMeasuredScopeFields || !activeBuildFields.species) {
      setSpeciesOptions([]);
      return;
    }
    let cancelled = false;
    const buildType = activeBuilderType?.label;
    void fetchBuilderJson<{ species?: BuilderSpecies[] }>("species", { build_type: buildType }).then((data) => {
      if (cancelled) return;
      setSpeciesOptions(Array.isArray(data?.species) ? data.species : []);
    });
    return () => { cancelled = true; };
  }, [usesMeasuredScopeFields, activeBuildFields.species, activeBuilderType?.label]);

  // Canopy tiers for the height that was typed. Tiers are defined per height
  // band, so 42" reads "full" on a 6' tree and "standard" on a 9' one and
  // "Medium" means the same visual fullness at every height.
  useEffect(() => {
    if (!usesMeasuredScopeFields || !activeBuildFields.canopy || !treeHeight.trim()) {
      setCanopyTiers(null);
      return;
    }
    let cancelled = false;
    const handle = window.setTimeout(() => {
      void fetchBuilderJson<CanopyTiersResponse>("canopy-tiers", { height: treeHeight.trim() }).then((data) => {
        if (!cancelled) setCanopyTiers(data);
      });
    }, 300);
    return () => { cancelled = true; window.clearTimeout(handle); };
  }, [usesMeasuredScopeFields, activeBuildFields.canopy, treeHeight]);

  // Density for this species at this height. Species-keyed: at 7ft an Areca is
  // 1 stem and a Eucalyptus 16, so a pooled number would be meaningless.
  useEffect(() => {
    if (!usesMeasuredScopeFields || !activeBuildFields.density || !buildSpecies.trim()) {
      setDensityInfo(null);
      return;
    }
    let cancelled = false;
    const handle = window.setTimeout(() => {
      void fetchBuilderJson<DensityResponse>("density", {
        species: buildSpecies.trim(),
        height: treeHeight.trim() || undefined,
        build_type: activeBuilderType?.label,
      }).then((data) => {
        if (!cancelled) setDensityInfo(data);
      });
    }, 300);
    return () => { cancelled = true; window.clearTimeout(handle); };
  }, [usesMeasuredScopeFields, activeBuildFields.density, buildSpecies, treeHeight, activeBuilderType?.label]);

  // "Builds we make often" for this type + species.
  useEffect(() => {
    if (!usesMeasuredScopeFields || !activeBuilderType?.label) {
      setCommonBuilds([]);
      return;
    }
    let cancelled = false;
    void fetchBuilderJson<{ builds?: CommonBuild[] }>("common-builds", {
      build_type: activeBuilderType.label,
      species: buildSpecies.trim() || undefined,
    }).then((data) => {
      if (cancelled) return;
      setCommonBuilds(Array.isArray(data?.builds) ? data.builds : []);
    });
    return () => { cancelled = true; };
  }, [usesMeasuredScopeFields, activeBuilderType?.label, buildSpecies]);

  // Keep the band selection honest when the species/height cell changes under it.
  useEffect(() => {
    if (!densityInfo?.bands?.length) return;
    if (buildDensityBand && densityInfo.bands.some((band) => band.key === buildDensityBand)) return;
    setBuildDensityBand(densityInfo.default_band || "standard");
    // Runs when the species x height cell changes, not when the band does - the
    // current band is only read to decide whether it survives the new cell.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [densityInfo]);

  useEffect(() => {
    if (!canopyTiers?.tiers?.length || buildCanopyTier) return;
    if (canopyTiers.default_tier) setBuildCanopyTier(canopyTiers.default_tier);
  }, [canopyTiers, buildCanopyTier]);

  // ─── Phase D: scope-aware smart filters ────────────────────────────────────
  // The active slot's real vocabulary, so opening Container surfaces containers
  // and opening Top Dressing surfaces foam / moss / rocks. Pre-applied but
  // removable - the API's own contract says `mandatory: false`.
  const activeScopeSlot = activePart ? scopeSlotForPartLabel(activePart.label) : null;
  useEffect(() => {
    if (!activeScopeSlot) {
      setScopeFilters(null);
      return;
    }
    let cancelled = false;
    void fetchBuilderJson<{ slots?: ScopeFilterSlot[] }>("scope-filters", {
      slot: activeScopeSlot,
      build_type: activeBucket?.bucket_type || undefined,
    }).then((data) => {
      if (cancelled) return;
      setScopeFilters(data?.slots?.[0] || null);
    });
    return () => { cancelled = true; };
  }, [activeScopeSlot, activeBucket?.bucket_type]);

  // ─── Phase D: catalog pane size ────────────────────────────────────────────
  useEffect(() => {
    const query = window.matchMedia("(min-width: 1024px)");
    const onChange = () => setWideLayout(query.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  useEffect(() => {
    window.localStorage.setItem(BUILDER_CATALOG_WIDTH_KEY, String(Math.round(catalogWidth)));
  }, [catalogWidth]);

  useEffect(() => {
    window.localStorage.setItem(BUILDER_CATALOG_EXPANDED_KEY, catalogExpanded ? "1" : "0");
  }, [catalogExpanded]);

  // Drag the divider between the scope tree and the catalog. Tracked on window
  // so the pointer can leave the 6px handle mid-drag without the split sticking.
  useEffect(() => {
    if (!resizingCatalog) return;
    const onMove = (event: PointerEvent) => {
      const bounds = splitRef.current?.getBoundingClientRect();
      if (!bounds) return;
      const next = bounds.right - event.clientX;
      setCatalogWidth(Math.min(Math.max(next, 340), Math.max(360, bounds.width - 280)));
    };
    const stop = () => setResizingCatalog(false);
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", stop);
    window.addEventListener("pointercancel", stop);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", stop);
      window.removeEventListener("pointercancel", stop);
    };
  }, [resizingCatalog]);

  const showScopeCanvas = !(catalogExpanded && builderStep === "products");
  const builderGridStyle = wideLayout
    ? { gridTemplateColumns: showScopeCanvas ? `minmax(0,1fr) 6px ${Math.round(catalogWidth)}px` : "minmax(0,1fr)" }
    : undefined;
  const goToBuilderStep = (step: typeof builderSteps[number]) => {
    setBuilderStep(step);
    window.requestAnimationFrame(() => {
      const target = builderTopRef.current;
      if (target) {
        target.scrollIntoView({ behavior: "smooth", block: "start" });
        return;
      }
      // The page scrolls inside [data-scroll-root], not the window (see Layout);
      // scrolling the window here would be a silent no-op.
      (document.querySelector("[data-scroll-root]") ?? window).scrollTo({ top: 0, behavior: "smooth" });
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
    // A type the builder only gained in Phase C (Plant & Bush, Container Only,
    // Topiary) has no hardcoded config, so it is resolved from the API list
    // instead of falling through to "Custom".
    const apiType = config ? null : builderApiTypeFor(bucket.bucket_type || scopeTitle(bucket), builderTypes);
    const resolvedLabel = config?.label || apiType?.label || "";
    const nextType = resolvedLabel || bucket.bucket_type || scopeTitle(bucket);
    setSelectedProductSection(config?.section || "green");
    setSelectedScopeType(resolvedLabel || "Custom");
    setNewScopeName(nextType);
    setPreviewType(nextType);
    setBuildSuggestion(parseScopeIntelligence(bucket.scope_notes));
    setSelectedChristmasTreeCode("");
    setTreeHeight(buildHeightFromNotes(bucket.scope_notes));
    // The Christmas branch still owns these two, under the original keys.
    setTreeCanopySize(scopeNoteValue(bucket.scope_notes, "Width / canopy"));
    setTreeDensity(scopeNoteValue(bucket.scope_notes, "Depth / density"));
    // Green builds read the Phase C keys, each falling back to the pre-Phase-C
    // one, so a design saved before this change still loads with its width and
    // depth intact and round-trips without losing them.
    setBuildWidth(buildWidthFromNotes(bucket.scope_notes));
    setBuildDepth(buildDepthFromNotes(bucket.scope_notes));
    setBuildSpecies(buildSpeciesFromNotes(bucket.scope_notes));
    setBuildCanopyTier(buildCanopyTierFromNotes(bucket.scope_notes));
    setBuildSilhouette(buildSilhouetteFromNotes(bucket.scope_notes) || "full_round");
    setBuildDensityBand(buildDensityBandFromNotes(bucket.scope_notes));
    setCommonBuildPick("");
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
      // Christmas trees keep the original three keys - the enhancer/ornament
      // rules read "Width / canopy" as the diameter and "Depth / density" as the
      // profile. Green builds write the measured Phase C fields instead.
      ...(nextType === "Christmas Tree"
        ? [
            treeHeight.trim() ? `Height: ${treeHeight.trim()}` : "",
            treeCanopySize.trim() ? `Width / canopy: ${treeCanopySize.trim()}` : "",
            treeDensity.trim() ? `Depth / density: ${treeDensity.trim()}` : "",
          ]
        : !["Garland", "Wreath"].includes(nextType)
          ? measuredScopeLines(nextType)
          : []),
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

  // Phase D: the builder no longer pages the whole catalog into the browser
  // before the picker can open. Choose Parts queries /api/products/search - the
  // same warm in-memory index the Catalog Search page uses - so it answers per
  // keystroke instead of after a ~95k-row download.

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

  // Loads the Client -> Project -> Group hierarchy for the standalone builder.
  // Prefers the single-shot /designs/hierarchy endpoint and falls back to the
  // three legacy endpoints when it is not deployed yet.
  const loadDesignHierarchy = async () => {
    setHierarchyLoading(true);
    try {
      try {
        const res = await apiClient.request({ path: "/routes/designs/hierarchy", method: "GET" });
        if (res.ok) {
          const data = await res.json() as any;
          if (data && Array.isArray(data.clients) && Array.isArray(data.projects)) {
            loadedGroupProjectsRef.current = new Set(
              (Array.isArray(data.groups) ? data.groups : []).map((group: any) => Number(group.project_id))
            );
            setDesignHierarchy({
              clients: data.clients.map((client: any) => ({ id: client.id ?? null, name: String(client.name || "") })),
              projects: data.projects.map((project: any) => ({
                id: Number(project.id),
                name: String(project.name || ""),
                client_name: project.client_name || "",
              })),
              groups: (Array.isArray(data.groups) ? data.groups : []).map((group: any) => ({
                id: Number(group.id),
                name: String(group.name || ""),
                project_id: Number(group.project_id),
              })),
            });
            return;
          }
        }
      } catch {
        // Fall through to the legacy endpoints below.
      }

      const [clientResult, projectResult] = await Promise.allSettled([
        apiClient.request<{ id?: number; name: string }[]>({ path: "/routes/clients/list", method: "GET" }).then((r) => (r.ok ? r.json() : [])),
        apiClient.list_arrangements().then((r) => (r.ok ? r.json() : [])),
      ]);
      const clientRows = clientResult.status === "fulfilled" && Array.isArray(clientResult.value) ? clientResult.value : [];
      const projectRows = (projectResult.status === "fulfilled" && Array.isArray(projectResult.value)
        ? projectResult.value
        : []) as unknown as ArrangementSummary[];
      const namesFromProjects = projectRows
        .map((project) => (project.client_name || "").trim())
        .filter(Boolean)
        .map((name) => ({ id: null, name }));
      const mergedClients = [...clientRows.map((client) => ({ id: client.id ?? null, name: String(client.name || "") })), ...namesFromProjects]
        .filter((client) => Boolean(client.name.trim()))
        .filter((client, index, list) => list.findIndex((other) => other.name === client.name) === index);
      setDesignHierarchy((current) => ({
        clients: mergedClients,
        projects: projectRows.map((project) => ({ id: project.id, name: project.name, client_name: project.client_name || "" })),
        // Groups are not in the summary payload - they are lazily fetched per project.
        groups: current.groups,
      }));
    } finally {
      setHierarchyLoading(false);
    }
  };

  // Lazily hydrate the group (project_rooms) list for one project when the
  // /designs/hierarchy endpoint is unavailable or did not include it.
  const ensureGroupsForProject = async (projectId: number) => {
    if (loadedGroupProjectsRef.current.has(projectId)) return;
    loadedGroupProjectsRef.current.add(projectId);
    setHierarchyLoading(true);
    try {
      const res = await apiClient.get_arrangement({ arrangementId: projectId });
      if (!res.ok) return;
      const detail = await res.json() as unknown as Arrangement;
      const rooms = Array.isArray(detail?.rooms) ? detail.rooms : [];
      setDesignHierarchy((current) => ({
        ...current,
        groups: [
          ...current.groups.filter((group) => group.project_id !== projectId),
          ...rooms.map((room) => ({ id: room.id, name: room.name, project_id: projectId })),
        ],
      }));
    } catch {
      loadedGroupProjectsRef.current.delete(projectId);
    } finally {
      setHierarchyLoading(false);
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
    if (!standaloneNewDesign) return;
    void loadDesignHierarchy();
  }, [standaloneNewDesign]);
  useEffect(() => {
    if (!standaloneNewDesign) return;
    if (destinationSaved) return;
    if (designDestination.projectId === null) return;
    void ensureGroupsForProject(designDestination.projectId);
  }, [standaloneNewDesign, destinationSaved, designDestination.projectId]);
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

  const addBucket = async (options?: { arrangement?: Arrangement; roomId?: number | null }) => {
    const scopeName = (scopeNameRef.current?.value || newScopeName).trim();
    const quantityValue = scopeQuantityRef.current?.value || newScopeQuantity;
    const notesValue = scopeNotesRef.current?.value || newScopeNotes;
    // Overrides let the standalone builder create the scope against a project /
    // room that was created moments ago, before React state has caught up.
    const targetArrangement = options?.arrangement || arrangement;
    const targetRoomId = options && "roomId" in options ? options.roomId ?? null : activeRoomId;
    if (!targetArrangement || !scopeName) return;
    setSavingBucket(true);
    try {
      const suggestion = buildSuggestion || await requestBuildSuggestion();
      const setupNotes = [
        notesValue.trim(),
        selectedScopeType === "Christmas Tree" && activeChristmasTreeOption ? `Tree type: ${activeChristmasTreeOption.code} - ${activeChristmasTreeOption.label}` : "",
        selectedScopeType === "Christmas Tree" ? `Enhancer package: ${christmasEnhancerPackage === "premium" ? "Premium" : "Regular"}` : "",
        ...(selectedScopeType === "Garland" ? garlandSetupLines(garlandPackage, garlandLength, garlandDiameter) : []),
        ...(selectedScopeType === "Wreath" ? wreathSetupLines(wreathSize) : []),
        ...(selectedScopeType === "Christmas Tree"
          ? [
              treeHeight.trim() ? `Height: ${treeHeight.trim()}` : "",
              treeCanopySize.trim() ? `Width / canopy: ${treeCanopySize.trim()}` : "",
              treeDensity.trim() ? `Depth / density: ${treeDensity.trim()}` : "",
            ]
          : usesMeasuredScopeFields
            ? measuredScopeLines()
            : []),
        suggestion ? `${INTELLIGENCE_NOTE_PREFIX}${JSON.stringify(suggestion)}` : "",
      ].filter(Boolean).join("\n");
      const res = await apiClient.add_container(
        { arrangementId: targetArrangement.id },
        {
          label: scopeName,
          room_id: targetRoomId,
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
      resetMeasuredScopeFields();
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

  /**
   * The single write point for the standalone "New Design" flow.
   *
   * Everything the three dropdowns collected is kept in memory until this runs,
   * so abandoning a build leaves no orphan client / project / room rows behind.
   * Order: client -> project (arrangement) -> group (project_room). The design
   * itself (arrangement_container) is created right after by addBucket().
   */
  const materializeDestination = async (): Promise<{ arrangement: Arrangement; roomId: number | null } | null> => {
    const destination = designDestination;
    const clientName = destination.clientName.trim();

    if (destination.clientIsNew && clientName) {
      try {
        await apiClient.request({
          path: "/routes/clients/create",
          method: "POST",
          body: { name: clientName },
          type: ContentType.Json,
        });
      } catch {
        // A missing client record is not fatal - the project still stores client_name.
      }
    }

    let projectArrangement: Arrangement | null = null;
    if (destination.projectIsNew) {
      const projectName = destination.projectName.trim();
      if (!projectName) {
        toast.error("Name the new project first");
        return null;
      }
      const res = await apiClient.create_arrangement({
        name: projectName,
        client_name: clientName || undefined,
      });
      if (!res.ok) {
        toast.error("Could not create the project");
        return null;
      }
      projectArrangement = await res.json() as unknown as Arrangement;
    } else if (destination.projectId !== null) {
      const res = await apiClient.get_arrangement({ arrangementId: destination.projectId });
      if (!res.ok) {
        toast.error("Could not open the selected project");
        return null;
      }
      projectArrangement = await res.json() as unknown as Arrangement;
    }
    if (!projectArrangement) {
      toast.error("Select a project first");
      return null;
    }

    let roomId: number | null = destination.groupIsNew ? null : destination.groupId;
    if (destination.groupIsNew) {
      const groupName = destination.groupName.trim();
      if (!groupName) {
        toast.error("Name the new project group first");
        return null;
      }
      const res = await apiClient.request<Arrangement>({
        path: `/routes/arrangements/room/add/${projectArrangement.id}`,
        method: "POST",
        body: { name: groupName },
        type: ContentType.Json,
      });
      if (!res.ok) {
        toast.error("Could not create the project group");
        return null;
      }
      projectArrangement = await res.json() as unknown as Arrangement;
      const createdRoom = (projectArrangement.rooms || []).find(
        (room) => room.name.trim().toLowerCase() === groupName.toLowerCase()
      );
      roomId = createdRoom?.id ?? null;
      if (roomId === null) {
        toast.error("Could not create the project group");
        return null;
      }
    }

    return { arrangement: projectArrangement, roomId };
  };

  const goToProductParts = async () => {
    if (activeBucket) {
      const updatedBucket = await applySelectedTypeToActiveBucket();
      if (!updatedBucket) return;
      setActivePart({ label: scopePlaceholders(updatedBucket)[0] || "Products", index: 0 });
      enterProductPicker();
      return;
    }
    if (standaloneNewDesign && !arrangement) {
      if (!destinationIsComplete(designDestination)) {
        toast.error("Choose a client, project, and project group first");
        return;
      }
      setSavingBucket(true);
      let created: { arrangement: Arrangement; roomId: number | null } | null = null;
      try {
        created = await materializeDestination();
      } catch {
        toast.error("Could not save the design destination");
      } finally {
        setSavingBucket(false);
      }
      if (!created) return;
      setArrangement(created.arrangement);
      setActiveRoomId(created.roomId);
      setCreatingBuiltProduct(true);
      setDestinationSaved(true);
      notifyProjectsChanged();
      await addBucket({ arrangement: created.arrangement, roomId: created.roomId });
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
    const matchingKeys = partKeysForSlot(part.label, part.index);
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
            return item.product_id === product.id && matchingKeys.includes(existingKey);
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

  // Step 1's primary CTA is rendered twice (top and bottom of the "Select type" panel) so
  // it is reachable without scrolling. Both instances come from this one definition, so
  // they always share the same handler, label, and disabled/validation state.
  const typeStepContinueDisabled =
    savingBucket
    || (!activeBucket && !newScopeName.trim())
    || (standaloneNewDesign && !arrangement && !destinationIsComplete(designDestination));
  const typeStepContinueLabel = savingBucket
    ? "Saving..."
    : standaloneNewDesign && !arrangement
      ? "Save & continue →"
      : "Next step →";
  const renderTypeStepContinueButton = (spacingClassName: string) => (
    <button
      onClick={() => void goToProductParts()}
      disabled={typeStepContinueDisabled}
      className={`${spacingClassName} w-full rounded-lg bg-stone-950 px-4 py-3 text-sm font-semibold text-white disabled:opacity-50`}
    >
      {typeStepContinueLabel}
    </button>
  );

  // `embedded` renders the builder inside a host page that already supplies
  // <Layout> and its own header (the Designs tab), so the host's All Designs /
  // New Design toggle stays put instead of being replaced by a second page.
  // Nesting two <Layout>s would render the sidebar twice.
  const Shell = embedded ? React.Fragment : Layout;

  return (
    <Shell>
      {!selectedId && !standaloneNewDesign ? (
        <>
          <header className="sticky top-0 z-10 flex flex-wrap items-center justify-between gap-3 border-b border-stone-200 px-4 sm:px-10 py-4" style={{ backgroundColor: "rgb(var(--ll-page))" }}>
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
            <button onClick={() => setShowNewModal(true)} className="flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold text-white hover:opacity-90" style={{ backgroundColor: "rgb(var(--ll-brand))" }}>
              <Plus size={15} strokeWidth={2.2} /> New Project
            </button>
          </header>
          <div className="px-4 sm:px-10 py-6">
            {loading && filteredArrangements.length === 0 ? (
              <div className="flex items-center justify-center py-24">
                <div className="h-6 w-6 animate-spin rounded-full border-2 border-emerald-600 border-t-transparent" />
              </div>
            ) : listSettled && filteredArrangements.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-24 text-center">
                <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full" style={{ backgroundColor: "rgb(var(--ll-brand-soft))" }}>
                  <Package size={28} className="text-emerald-600" strokeWidth={1.5} />
                </div>
                <p className="mb-1 text-base font-medium text-stone-600">No projects yet</p>
                <p className="mb-4 max-w-xs text-sm leading-relaxed text-stone-400">Create a client project, then add scopes like Tree, Garland, or Bookshelf.</p>
                <button onClick={() => setShowNewModal(true)} className="rounded-lg px-4 py-2 text-sm font-semibold text-white hover:opacity-90" style={{ backgroundColor: "rgb(var(--ll-brand))" }}>Create First Project</button>
              </div>
            ) : (
              <div className="grid gap-3">
                {filteredArrangements.map((a) => (
                  <div key={a.id} onClick={() => selectProject(a.id)} className="group flex cursor-pointer items-center gap-3 rounded-xl border border-stone-200 bg-white px-4 py-3 transition hover:shadow-sm sm:gap-4 sm:px-6 sm:py-4">
                    <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg" style={{ backgroundColor: "rgb(var(--ll-brand-soft))" }}>
                      <Package size={18} className="text-emerald-700" strokeWidth={1.5} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-semibold text-stone-800">{a.name}</p>
                      <p className="mt-0.5 text-xs text-stone-400">{a.client_name || "No client"} · {a.container_count} scope{a.container_count !== 1 ? "s" : ""}</p>
                    </div>
                    <div className="text-right sm:mr-4">
                      <p className="text-sm font-semibold text-stone-800">{formatCurrency(a.total_cost)}</p>
                      <p className="text-xs text-stone-400">selected cost</p>
                    </div>
                    <p className="hidden text-xs text-stone-300 sm:block">{new Date(a.updated_at).toLocaleDateString()}</p>
                    <button onClick={(e) => { e.stopPropagation(); deleteProject(a.id); }} className="flex h-8 w-8 items-center justify-center rounded-lg text-stone-300 opacity-0 transition-colors hover:bg-red-50 hover:text-red-500 group-hover:opacity-100">
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      ) : arrangement || standaloneNewDesign ? (
        <>
          {!arrangement ? (
            // Embedded in the Designs tab, the host already renders the header
            // and the All Designs / New Design toggle — a second one would stack.
            embedded ? null : (
            <header className="sticky top-0 z-10 flex items-center gap-4 border-b border-stone-200 px-4 sm:px-10 py-4" style={{ backgroundColor: "rgb(var(--ll-page))" }}>
              <button onClick={() => navigate("/clients")} className="flex h-8 w-8 items-center justify-center rounded-lg text-stone-500 transition-colors hover:bg-stone-200" aria-label="Leave the new design builder">
                <ArrowLeft size={16} />
              </button>
              <div className="flex-1">
                <div className="mb-1 flex items-center gap-1 text-xs font-semibold text-emerald-700">
                  <span>Designs</span>
                  <span className="text-stone-300">/</span>
                  <span className="text-stone-500">New design</span>
                </div>
                <h1 className="text-lg font-semibold text-stone-800" style={{ fontFamily: "Georgia, serif" }}>New Design</h1>
                <p className="text-xs text-stone-400">Pick the client, project, and group beside the steps · nothing is saved until you continue past step 1.</p>
              </div>
            </header>
            )
          ) : (
          <header className="sticky top-0 z-10 flex items-center gap-4 border-b border-stone-200 px-4 sm:px-10 py-4" style={{ backgroundColor: "rgb(var(--ll-page))" }}>
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
            <button onClick={() => navigate(`/invoice?arrangement_id=${arrangement.id}`)} className="rounded-lg px-4 py-2 text-sm font-semibold text-white hover:opacity-90" style={{ backgroundColor: "rgb(var(--ll-brand))" }}>
              View Invoice
            </button>
          </header>
          )}

          {!activeRoomId && !standaloneNewDesign ? (
            <div className="px-4 sm:px-10 py-6">
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
                    style={{ backgroundColor: "rgb(var(--ll-brand))" }}
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
                      <div key={room.id} className="group rounded-2xl border border-stone-200 bg-white p-5 shadow-sm transition hover:border-emerald-200 hover:shadow-md">
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
                        <button onClick={() => openRoom(room.id)} className="w-full rounded-xl px-4 py-2 text-sm font-semibold text-white" style={{ backgroundColor: "rgb(var(--ll-brand))" }}>
                          Open package
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          ) : !activeBucket && !creatingBuiltProduct && !standaloneNewDesign ? (
            <div className="px-4 sm:px-10 py-6">
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
                      <div key={bucket.id} className="group rounded-2xl border border-stone-200 bg-white p-5 shadow-sm transition hover:border-emerald-200 hover:shadow-md">
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
                        <button onClick={() => openBuiltProduct(bucket)} className="w-full rounded-xl px-4 py-2 text-sm font-semibold text-white" style={{ backgroundColor: "rgb(var(--ll-brand))" }}>
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
                <div className="flex min-w-0 flex-1 flex-col gap-2">
                {standaloneNewDesign && (
                  <>
                    <DesignDestinationPicker
                      hierarchy={designHierarchy}
                      destination={designDestination}
                      onChange={setDesignDestination}
                      loading={hierarchyLoading}
                      locked={destinationSaved}
                    />
                    {!destinationSaved && (
                      <p className="text-[11px] text-stone-400">
                        Client, project, and group are only created when you continue to step 2.
                      </p>
                    )}
                  </>
                )}
                {(!standaloneNewDesign || destinationSaved) && (
                <div className="flex flex-wrap items-center gap-4 text-sm">
                  <span className="flex items-center gap-2 text-stone-500"><span className="h-2 w-2 rounded-full bg-emerald-700" /> Type: <strong className="text-stone-900">{activeBucket ? activeBucket.bucket_type || scopeTitle(activeBucket) : "No scope"}</strong></span>
                  <span className="text-stone-300">|</span>
                  <span className="text-stone-500">Parts: <strong className="text-stone-900">{partsComplete}/{activeParts.length || 0} selected</strong></span>
                  <span className="text-stone-300">|</span>
                  <span className="text-stone-500">Draft SKU: <strong className="text-stone-900">{activeDraftSku}</strong></span>
                  <span className="text-stone-300">|</span>
                  <span className="text-stone-500">Order: <strong className="text-emerald-800">{orderItems.length ? "ready" : "draft"}</strong></span>
                </div>
                )}
                </div>
                <div className="flex min-h-[34px] items-center gap-2 overflow-x-auto [scrollbar-width:none]">
                  <div
                    className="grid overflow-hidden transition-[grid-template-columns] duration-200"
                    style={{ gridTemplateColumns: builderStep !== "type" ? "78px" : "0px" }}
                  >
                    <button
                      type="button"
                      onClick={goBackBuilderStep}
                      tabIndex={builderStep !== "type" ? 0 : -1}
                      aria-hidden={builderStep === "type"}
                      className={`flex w-[78px] transform-gpu items-center justify-center gap-1 rounded-full border border-stone-200 bg-white px-3 py-1.5 text-xs font-semibold text-stone-700 shadow-sm transition duration-200 hover:-translate-y-0.5 hover:bg-stone-50 hover:shadow-md ${
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
                      className={`transform-gpu whitespace-nowrap rounded-full px-3 py-1.5 text-xs font-semibold transition duration-200 hover:-translate-y-0.5 ${
                        builderStep === step
                          ? "scale-[1.02] bg-stone-900 text-white shadow-[0_0_0_2px_rgb(var(--ll-focus-gold))]"
                          : "scale-100 bg-stone-100 text-stone-500 shadow-none hover:bg-stone-200 hover:text-stone-700"
                      }`}
                    >
                      {index + 1}. {step === "type" ? "Select type" : step === "products" ? "Choose parts" : step === "mockup" ? "Mockup" : step === "review" ? "Review" : "Order"}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div
              ref={splitRef}
              style={builderGridStyle}
              className={`grid overflow-hidden rounded-2xl border border-stone-200 bg-white shadow-sm lg:grid-cols-[minmax(0,1fr)_440px] xl:grid-cols-[minmax(0,1fr)_460px] ${
                catalogExpanded && builderStep === "products" ? "h-[calc(100vh-190px)] min-h-[560px]" : "h-[720px]"
              } ${resizingCatalog ? "select-none" : ""}`}
            >
              {showScopeCanvas && (
              <section className="relative h-full overflow-x-hidden overflow-y-auto border-r border-stone-100 bg-[radial-gradient(circle_at_1px_1px,rgb(var(--ns-200))_1px,transparent_0)] [background-size:22px_22px] p-6 pb-28 md:p-8 md:pb-28 lg:px-10">
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
                                  className={`relative rounded-[1.75rem] border border-dashed px-4 py-5 shadow-sm transition ${
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
                                              className={`grid items-center gap-3 rounded-2xl border px-3 py-2.5 text-xs transition sm:grid-cols-[minmax(0,1fr)_120px] ${
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
                                                className="rounded-xl border border-dashed border-stone-300 bg-white px-3 py-2 text-center text-xs font-semibold text-stone-400 transition hover:-translate-y-0.5 hover:border-emerald-600 hover:text-emerald-900 hover:shadow-sm"
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
                                  className={`relative rounded-[1.75rem] border border-dashed px-4 py-5 shadow-sm transition ${
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
                                              className={`grid items-center gap-3 rounded-2xl border px-3 py-2.5 text-xs transition sm:grid-cols-[minmax(0,1fr)_120px] ${
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
                                                className="rounded-xl border border-dashed border-stone-300 bg-white px-3 py-2 text-center text-xs font-semibold text-stone-400 transition hover:-translate-y-0.5 hover:border-emerald-600 hover:text-emerald-900 hover:shadow-sm"
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
                                className={`relative rounded-2xl border border-dashed bg-white px-4 py-4 shadow-sm transition ${
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
                                    className="min-w-[132px] rounded-xl border border-dashed border-stone-300 bg-stone-50 px-3 py-2 text-center text-xs font-semibold text-stone-400 transition hover:-translate-y-0.5 hover:border-emerald-600 hover:bg-white hover:text-emerald-900 hover:shadow-sm"
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
                              className={`group relative rounded-3xl border bg-white/95 px-6 py-6 text-left shadow-sm transition ${selectedSubpart ? "border-stone-900 ring-2 ring-stone-100" : "border-dashed border-emerald-200"}`}
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
                                          className={`flex min-h-[58px] items-center justify-between gap-4 rounded-2xl border px-4 py-3 text-left transition hover:border-stone-900 hover:shadow-sm ${
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
                                              className="rounded-xl border border-stone-200 bg-white px-4 py-2 text-xs font-semibold text-stone-700 shadow-sm transition hover:-translate-y-0.5 hover:border-stone-900 hover:shadow-md"
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
                          className={`group relative flex min-h-[128px] items-center gap-4 rounded-2xl border bg-white/95 px-6 py-5 text-left shadow-sm transition hover:border-stone-900 hover:shadow-md ${selectedPart ? "border-stone-900 ring-2 ring-stone-100" : "border-dashed border-stone-300"}`}
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
              )}

              {/* Drag to trade width between the scope tree and the catalog. */}
              {showScopeCanvas && wideLayout && (
                <div
                  role="separator"
                  aria-orientation="vertical"
                  aria-label="Resize the catalog pane"
                  onPointerDown={(event) => { event.preventDefault(); setResizingCatalog(true); }}
                  onDoubleClick={() => setCatalogWidth(460)}
                  title="Drag to resize · double-click to reset"
                  className={`group hidden h-full cursor-col-resize items-center justify-center lg:flex ${
                    resizingCatalog ? "bg-emerald-300" : "bg-stone-100 hover:bg-emerald-200"
                  }`}
                >
                  <span className="h-10 w-0.5 rounded-full bg-stone-300 group-hover:bg-emerald-600" />
                </div>
              )}

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
                        {renderTypeStepContinueButton("mb-4")}
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
                        <MeasuredScopeFields
                          buildTypeLabel={activeBuilderType?.label || selectedBuildTypeLabel}
                          fields={activeBuildFields}
                          recipeCount={activeBuilderType?.recipe_count}
                          typeNotes={activeBuilderType?.notes}
                          height={treeHeight}
                          onHeightChange={setTreeHeight}
                          species={buildSpecies}
                          onSpeciesChange={setBuildSpecies}
                          speciesOptions={speciesOptions}
                          activeSpecies={activeSpecies}
                          canopyTiers={canopyTiers}
                          canopyTier={buildCanopyTier}
                          onCanopyTier={applyCanopyTier}
                          width={buildWidth}
                          onWidthChange={applyWidth}
                          silhouetteOptions={silhouetteOptions}
                          silhouette={buildSilhouette}
                          onSilhouette={applySilhouette}
                          depth={buildDepth}
                          onDepthChange={setBuildDepth}
                          densityInfo={densityInfo}
                          densityApplies={densityApplies}
                          densityBand={buildDensityBand}
                          onDensityBand={setBuildDensityBand}
                          commonBuilds={commonBuilds}
                          commonBuildPick={commonBuildPick}
                          onCommonBuild={applyCommonBuild}
                        />
                      )}
                      {standaloneNewDesign && !arrangement && !destinationIsComplete(designDestination) && (
                        <p className="mt-4 rounded-xl border border-dashed border-amber-200 bg-amber-50/60 px-3 py-2 text-xs font-medium text-amber-900">
                          Pick a client, project, and project group above to continue.
                        </p>
                      )}
                      {renderTypeStepContinueButton("mt-5")}
                    </div>
                  </div>
                )}

                {builderStep === "products" && activeBucket && (
                  <div ref={catalogRef} className="min-h-0 flex-1">
                    <BuilderProductPicker
                      activePartLabel={activePart ? activePart.label : "Products"}
                      initialQuery={searchTermsForPart(activeBucket, activePart?.label || "Products", activePart?.index || 0)}
                      scopeFilters={scopeFilters}
                      selectedProductIds={new Set(itemsForPart(activeBucket, activePart?.label || "Products", activePart?.index || 0).map((item) => item.product_id))}
                      selectedProductItemIds={new Map(itemsForPart(activeBucket, activePart?.label || "Products", activePart?.index || 0).map((item) => [item.product_id, item.id]))}
                      onAdd={addProductToActiveBucket}
                      onRemove={removeItem}
                      onOpenProduct={openBuilderProductDetail}
                      onContinue={() => goToBuilderStep("mockup")}
                      expanded={catalogExpanded}
                      onToggleExpanded={() => setCatalogExpanded((value) => !value)}
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
        <div className="flex flex-col items-center justify-center px-4 sm:px-10 py-40 text-center">
          <p className="text-base font-medium text-stone-700">Project could not load</p>
          <p className="mt-1 max-w-sm text-sm leading-relaxed text-stone-400">
            Go back to All Projects and open it again. The catalog add button will stay on the page when the project is loaded.
          </p>
          <button
            onClick={clearSelection}
            className="mt-4 rounded-lg px-4 py-2 text-sm font-semibold text-white hover:opacity-90"
            style={{ backgroundColor: "rgb(var(--ll-brand))" }}
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
    </Shell>
  );
}
