/** AdminDashboardResponse */
export interface AdminDashboardResponse {
  summary: DashboardSummary;
  /** Supplier Health */
  supplier_health: SupplierHealth[];
  /** Recent Syncs */
  recent_syncs: SyncLogEntry[];
  /** Recent Price Changes */
  recent_price_changes: PriceChangeEntry[];
}

/** AllMarkupSettings */
export interface AllMarkupSettings {
  /** Global Markup */
  global_markup: number;
  /** Category Markups */
  category_markups: MarkupSettingOut[];
}

/** ArrangementCreate */
export interface ArrangementCreate {
  /** Name */
  name: string;
  /** Client Name */
  client_name?: string | null;
  /** Notes */
  notes?: string | null;
  /**
   * Containers
   * @default []
   */
  containers?: ContainerIn[];
}

/** ArrangementOut */
export interface ArrangementOut {
  /** Id */
  id: number;
  /** Name */
  name: string;
  /** Client Name */
  client_name: string | null;
  /** Notes */
  notes: string | null;
  /** Created By */
  created_by: string;
  /**
   * Created At
   * @format date-time
   */
  created_at: string;
  /**
   * Updated At
   * @format date-time
   */
  updated_at: string;
  /**
   * Containers
   * @default []
   */
  containers?: ContainerOut[];
  /**
   * Total Cost
   * @default 0
   */
  total_cost?: number;
  /**
   * Total With Markup
   * @default 0
   */
  total_with_markup?: number;
}

/** ArrangementSummary */
export interface ArrangementSummary {
  /** Id */
  id: number;
  /** Name */
  name: string;
  /** Client Name */
  client_name: string | null;
  /**
   * Created At
   * @format date-time
   */
  created_at: string;
  /**
   * Updated At
   * @format date-time
   */
  updated_at: string;
  /**
   * Total Cost
   * @default 0
   */
  total_cost?: number;
  /**
   * Container Count
   * @default 0
   */
  container_count?: number;
}

/** ArrangementUpdate */
export interface ArrangementUpdate {
  /** Name */
  name?: string | null;
  /** Client Name */
  client_name?: string | null;
  /** Notes */
  notes?: string | null;
}

/** BackfillStatusOut */
export interface BackfillStatusOut {
  /** Status */
  status: string;
  /** Total */
  total: number;
  /** Done */
  done: number;
  /** Stored */
  stored: number;
  /** Skipped */
  skipped: number;
  /** Failed */
  failed: number;
  /** Started At */
  started_at?: string | null;
  /** Completed At */
  completed_at?: string | null;
  /** Error */
  error?: string | null;
}

/** Body_upload_product_photo */
export interface BodyUploadProductPhoto {
  /**
   * File
   * @format binary
   */
  file: File;
}

/** Body_upload_product_photo_new */
export interface BodyUploadProductPhotoNew {
  /**
   * File
   * @format binary
   */
  file: File;
}

/** BulkPriceSyncRequest */
export interface BulkPriceSyncRequest {
  /** Supplier Ids */
  supplier_ids?: number[] | null;
}

/**
 * CatalogFilters
 * Saved catalog selection for a supplier — which sections/DDCODEs to scrape.
 */
export interface CatalogFilters {
  /**
   * Sections
   * @default []
   */
  sections?: string[];
  /**
   * Categories
   * @default []
   */
  categories?: string[];
  /** Updated At */
  updated_at?: string | null;
}

/** CatalogFiltersUpdate */
export interface CatalogFiltersUpdate {
  /**
   * Sections
   * @default []
   */
  sections?: string[];
  /**
   * Categories
   * @default []
   */
  categories?: string[];
}

/**
 * CatalogSection
 * A top-level section from live discovery.
 */
export interface CatalogSection {
  /** Name */
  name: string;
  /**
   * Subcategories
   * @default []
   */
  subcategories?: Record<string, any>[];
}

/** CategoryIndexResponse */
export interface CategoryIndexResponse {
  /** Suppliers */
  suppliers: SupplierCategoryIndex[];
}

/** CategoryIndexRow */
export interface CategoryIndexRow {
  /** Id */
  id: number;
  /** Category Name */
  category_name: string;
  /** Category Slug Or Url */
  category_slug_or_url: string;
  /** Product Count */
  product_count: number | null;
  /** Is Active */
  is_active: boolean;
  /** Last Verified At */
  last_verified_at: string | null;
  /** Created At */
  created_at: string | null;
}

/** ContainerIn */
export interface ContainerIn {
  /** Container Product Id */
  container_product_id?: number | null;
  /** Label */
  label?: string | null;
  /**
   * Items
   * @default []
   */
  items?: ContainerItemIn[];
}

/** ContainerItemIn */
export interface ContainerItemIn {
  /** Product Id */
  product_id: number;
  /**
   * Quantity
   * @default 1
   */
  quantity?: number;
}

/** ContainerItemOut */
export interface ContainerItemOut {
  /** Id */
  id: number;
  /** Product Id */
  product_id: number;
  /** Product Name */
  product_name: string;
  /** Product Category */
  product_category: string;
  /** Unit */
  unit: string;
  /** Current Price */
  current_price: number | null;
  /** Supplier Name */
  supplier_name: string | null;
  /** Quantity */
  quantity: number;
  /** Line Total */
  line_total: number | null;
}

/** ContainerOut */
export interface ContainerOut {
  /** Id */
  id: number;
  /** Arrangement Id */
  arrangement_id: number;
  /** Container Product Id */
  container_product_id: number | null;
  /** Container Name */
  container_name: string | null;
  /** Label */
  label: string | null;
  /** Sort Order */
  sort_order: number;
  /**
   * Items
   * @default []
   */
  items?: ContainerItemOut[];
  /**
   * Subtotal
   * @default 0
   */
  subtotal?: number;
}

/** DashboardSummary */
export interface DashboardSummary {
  /** Total Suppliers */
  total_suppliers: number;
  /** Suppliers With Scraper */
  suppliers_with_scraper: number;
  /** Suppliers With Credentials */
  suppliers_with_credentials: number;
  /** Suppliers Synced This Week */
  suppliers_synced_this_week: number;
  /** Total Products */
  total_products: number;
  /** Products Missing Images */
  products_missing_images: number;
  /** Products Missing Prices */
  products_missing_prices: number;
  /** Price Changes This Week */
  price_changes_this_week: number;
  /** Failed Syncs This Week */
  failed_syncs_this_week: number;
}

/** DiscoverCatalogResponse */
export interface DiscoverCatalogResponse {
  /** Sections */
  sections: CatalogSection[];
  /** Total Subcategories */
  total_subcategories: number;
  /** Total Products */
  total_products: number;
  /** From Cache */
  from_cache: boolean;
  /**
   * Section Listing Total
   * Accent Decor category appearances before dedupe.
   * @default 0
   */
  section_listing_total?: number;
  /**
   * Catalog Summary
   * Live supplier count metadata when available.
   */
  catalog_summary?: Record<string, any> | null;
}

/** HTTPValidationError */
export interface HTTPValidationError {
  /** Detail */
  detail?: ValidationError[];
}

/** HealthResponse */
export interface HealthResponse {
  /** Status */
  status: string;
}

/** ImportScrapedRequest */
export interface ImportScrapedRequest {
  /** Job Id */
  job_id: number;
  /** Supplier Id */
  supplier_id: number;
  /** Selected Skus */
  selected_skus?: string[] | null;
}

/** MarkupSettingOut */
export interface MarkupSettingOut {
  /** Id */
  id: number;
  /** Category */
  category: string | null;
  /** Markup Percentage */
  markup_percentage: number;
  /**
   * Updated At
   * @format date-time
   */
  updated_at: string;
}

/** MarkupUpdate */
export interface MarkupUpdate {
  /** Category */
  category?: string | null;
  /** Markup Percentage */
  markup_percentage: number;
}

/** MockupCreate */
export interface MockupCreate {
  /** Arrangement Id */
  arrangement_id: number;
  /** Style */
  style: string;
}

/** MockupOut */
export interface MockupOut {
  /** Id */
  id: number;
  /** Arrangement Id */
  arrangement_id: number;
  /** Style */
  style: string;
  /** Image Url */
  image_url: string | null;
  /** Prompt Used */
  prompt_used: string | null;
  /** Status */
  status: string;
  /**
   * Created At
   * @format date-time
   */
  created_at: string;
}

/** PriceChangeEntry */
export interface PriceChangeEntry {
  /** Id */
  id: number;
  /** Product Id */
  product_id: number;
  /** Product Name */
  product_name: string;
  /** Supplier Name */
  supplier_name: string;
  /** Old Price */
  old_price: number | null;
  /** New Price */
  new_price: number | null;
  /** Change Pct */
  change_pct: number | null;
  /** Source */
  source: string;
  /**
   * Changed At
   * @format date-time
   */
  changed_at: string;
}

/** PriceHistoryEntry */
export interface PriceHistoryEntry {
  /** Id */
  id: number;
  /** Product Id */
  product_id: number;
  /** Old Price */
  old_price?: number | null;
  /** New Price */
  new_price: number;
  /** Source */
  source: string;
  /**
   * Changed At
   * @format date-time
   */
  changed_at: string;
}

/** PriceSyncResponse */
export interface PriceSyncResponse {
  /** Ok */
  ok: boolean;
  /** Message */
  message: string;
}

/** ProductCreate */
export interface ProductCreate {
  /** Supplier Id */
  supplier_id: number;
  /** Name */
  name: string;
  /** Description */
  description?: string | null;
  /** Category */
  category: string;
  /** Unit */
  unit: string;
  /** Current Price */
  current_price?: number | null;
  /** Photo Url */
  photo_url?: string | null;
}

/** ProductOut */
export interface ProductOut {
  /** Id */
  id: number;
  /** Supplier Id */
  supplier_id: number;
  /** Supplier Name */
  supplier_name?: string | null;
  /** Supplier Sku */
  supplier_sku?: string | null;
  /** Name */
  name: string;
  /** Description */
  description: string | null;
  /** Category */
  category: string;
  /** Unit */
  unit: string;
  /** Current Price */
  current_price: number | null;
  /** Price Updated At */
  price_updated_at: string | null;
  /** Photo Url */
  photo_url: string | null;
  /** Moq */
  moq?: number | null;
  /** Box Qty */
  box_qty?: number | null;
  /** Case Qty */
  case_qty?: number | null;
  /** Availability */
  availability?: string | null;
  /** Availability Note */
  availability_note?: string | null;
  /** Upc */
  upc?: string | null;
  /** Length In */
  length_in?: number | null;
  /** Weight Lb */
  weight_lb?: number | null;
  /** Material */
  material?: string | null;
  /** Color */
  color?: string | null;
  /** Country Of Origin */
  country_of_origin?: string | null;
  /** Raw Data */
  raw_data?: Record<string, any> | null;
  /** Is Active */
  is_active: boolean;
  /**
   * Is Favorited
   * @default false
   */
  is_favorited?: boolean;
  /**
   * Created At
   * @format date-time
   */
  created_at: string;
  /**
   * Updated At
   * @format date-time
   */
  updated_at: string;
}

/** ProductPriceUpdate */
export interface ProductPriceUpdate {
  /** Current Price */
  current_price: number;
}

/** ProductUpdate */
export interface ProductUpdate {
  /** Name */
  name?: string | null;
  /** Description */
  description?: string | null;
  /** Category */
  category?: string | null;
  /** Unit */
  unit?: string | null;
  /** Current Price */
  current_price?: number | null;
  /** Photo Url */
  photo_url?: string | null;
  /** Supplier Id */
  supplier_id?: number | null;
}

/** RebuildIndexResponse */
export interface RebuildIndexResponse {
  /** Supplier Id */
  supplier_id: number;
  /** Scraper Key */
  scraper_key: string;
  /** Rows Deleted */
  rows_deleted: number;
  /** Message */
  message: string;
}

/** ScrapeJobOut */
export interface ScrapeJobOut {
  /** Id */
  id: number;
  /** Supplier Id */
  supplier_id: number;
  /** Supplier Name */
  supplier_name?: string | null;
  /** Status */
  status: string;
  /** Phase */
  phase?: string | null;
  /** Started At */
  started_at?: string | null;
  /** Completed At */
  completed_at?: string | null;
  /**
   * Products Found
   * @default 0
   */
  products_found?: number;
  /**
   * Products Imported
   * @default 0
   */
  products_imported?: number;
  /**
   * Products Importing
   * @default 0
   */
  products_importing?: number;
  /** Total Expected */
  total_expected?: number | null;
  /** Progress Message */
  progress_message?: string | null;
  /** Error Message */
  error_message?: string | null;
  /** Result Key */
  result_key?: string | null;
  /**
   * Created At
   * @format date-time
   */
  created_at: string;
  /** Milestone Log */
  milestone_log?: Record<string, any> | null;
}

/** ScrapedProductOut */
export interface ScrapedProductOut {
  /** Sku */
  sku: string;
  /** Name */
  name: string;
  /** Base Price */
  base_price?: number | null;
  /** Uom */
  uom?: string | null;
  /** Min Qty */
  min_qty?: number | null;
  /** Avail Qty */
  avail_qty?: string | null;
  /** Upc */
  upc?: string | null;
  /** Description */
  description?: string | null;
  /** Photo Url */
  photo_url?: string | null;
  /** Category */
  category?: string | null;
  /** Color Group */
  color_group?: string | null;
  /** Country Of Origin */
  country_of_origin?: string | null;
  /** Case Qty */
  case_qty?: number | null;
  /** Box Qty */
  box_qty?: number | null;
  /** Availability Note */
  availability_note?: string | null;
  /** Length In */
  length_in?: number | null;
  /** Weight Lb */
  weight_lb?: number | null;
  /** Material */
  material?: string | null;
  /**
   * Raw
   * @default {}
   */
  raw?: Record<string, any>;
}

/** StartScrapeRequest */
export interface StartScrapeRequest {
  /** Supplier Id */
  supplier_id: number;
  /** Max Products */
  max_products?: number | null;
}

/** SupplierCategoryIndex */
export interface SupplierCategoryIndex {
  /** Supplier Id */
  supplier_id: number;
  /** Supplier Name */
  supplier_name: string;
  /** Scraper Key */
  scraper_key: string | null;
  /** Total Categories */
  total_categories: number;
  /** Active Categories */
  active_categories: number;
  /** Total Cached Products */
  total_cached_products: number;
  /** Oldest Verified At */
  oldest_verified_at: string | null;
  /** Categories */
  categories: CategoryIndexRow[];
}

/** SupplierCreate */
export interface SupplierCreate {
  /** Name */
  name: string;
  /** Scraper Key */
  scraper_key?: string | null;
  /** Login Url */
  login_url?: string | null;
  /** Contact Name */
  contact_name?: string | null;
  /** Contact Email */
  contact_email?: string | null;
  /** Contact Phone */
  contact_phone?: string | null;
  /** Notes */
  notes?: string | null;
  /**
   * Categories
   * @default []
   */
  categories?: string[];
}

/** SupplierHealth */
export interface SupplierHealth {
  /** Id */
  id: number;
  /** Name */
  name: string;
  /** Scraper Key */
  scraper_key: string | null;
  /** Scraper Enabled */
  scraper_enabled: boolean;
  /** Credential Status */
  credential_status: string;
  /** Last Full Sync At */
  last_full_sync_at: string | null;
  /** Last Price Synced At */
  last_price_synced_at: string | null;
  /** Product Count */
  product_count: number;
  /** Missing Images */
  missing_images: number;
  /** Missing Prices */
  missing_prices: number;
  /** Sync Frequency Hours */
  sync_frequency_hours: number | null;
  /** Last Sync Status */
  last_sync_status: string | null;
  /** Last Sync Inserted */
  last_sync_inserted: number | null;
  /** Last Sync Updated */
  last_sync_updated: number | null;
  /** Last Sync Failed */
  last_sync_failed: number | null;
  /** Last Sync Price Changes */
  last_sync_price_changes: number | null;
  /** Last Sync Error */
  last_sync_error: string | null;
  /** Last Sync Duration S */
  last_sync_duration_s: number | null;
}

/** SupplierOut */
export interface SupplierOut {
  /** Id */
  id: number;
  /** Name */
  name: string;
  /** Scraper Key */
  scraper_key?: string | null;
  /** Login Url */
  login_url: string | null;
  /**
   * Has Credentials
   * @default false
   */
  has_credentials?: boolean;
  /** Contact Name */
  contact_name: string | null;
  /** Contact Email */
  contact_email: string | null;
  /** Contact Phone */
  contact_phone: string | null;
  /** Notes */
  notes: string | null;
  /**
   * Categories
   * @default []
   */
  categories?: string[];
  /**
   * Created At
   * @format date-time
   */
  created_at: string;
  /**
   * Updated At
   * @format date-time
   */
  updated_at: string;
  /**
   * Product Count
   * @default 0
   */
  product_count?: number;
  /** Last Price Synced At */
  last_price_synced_at?: string | null;
  /** Last Full Sync At */
  last_full_sync_at?: string | null;
}

/** SupplierUpdate */
export interface SupplierUpdate {
  /** Name */
  name?: string | null;
  /** Scraper Key */
  scraper_key?: string | null;
  /** Login Url */
  login_url?: string | null;
  /** Login Username */
  login_username?: string | null;
  /** Login Password */
  login_password?: string | null;
  /** Contact Name */
  contact_name?: string | null;
  /** Contact Email */
  contact_email?: string | null;
  /** Contact Phone */
  contact_phone?: string | null;
  /** Notes */
  notes?: string | null;
  /** Categories */
  categories?: string[] | null;
}

/** SyncLogEntry */
export interface SyncLogEntry {
  /** Id */
  id: number;
  /** Supplier Id */
  supplier_id: number;
  /** Supplier Name */
  supplier_name: string;
  /** Sync Type */
  sync_type: string;
  /** Status */
  status: string;
  /**
   * Started At
   * @format date-time
   */
  started_at: string;
  /** Completed At */
  completed_at: string | null;
  /** Products Found */
  products_found: number | null;
  /** Products Inserted */
  products_inserted: number | null;
  /** Products Updated */
  products_updated: number | null;
  /** Products Skipped */
  products_skipped: number | null;
  /** Products Failed */
  products_failed: number | null;
  /** Price Changes */
  price_changes: number | null;
  /** Error Message */
  error_message: string | null;
  /** Duration S */
  duration_s: number | null;
}

/** UserRoleOut */
export interface UserRoleOut {
  /** User Id */
  user_id: string;
  /** Role */
  role: string;
  /**
   * Created At
   * @format date-time
   */
  created_at: string;
}

/** UserRoleUpdate */
export interface UserRoleUpdate {
  /** User Id */
  user_id: string;
  /** Role */
  role: string;
}

/** ValidationError */
export interface ValidationError {
  /** Location */
  loc: (string | number)[];
  /** Message */
  msg: string;
  /** Error Type */
  type: string;
}

export type CheckHealthData = HealthResponse;

/** Response List Arrangements */
export type ListArrangementsData = ArrangementSummary[];

export type CreateArrangementData = ArrangementOut;

export type CreateArrangementError = HTTPValidationError;

export interface GetArrangementParams {
  /** Arrangement Id */
  arrangementId: number;
}

export type GetArrangementData = ArrangementOut;

export type GetArrangementError = HTTPValidationError;

export interface UpdateArrangementParams {
  /** Arrangement Id */
  arrangementId: number;
}

export type UpdateArrangementData = ArrangementOut;

export type UpdateArrangementError = HTTPValidationError;

export interface DeleteArrangementParams {
  /** Arrangement Id */
  arrangementId: number;
}

export type DeleteArrangementData = any;

export type DeleteArrangementError = HTTPValidationError;

export interface AddContainerParams {
  /** Arrangement Id */
  arrangementId: number;
}

export type AddContainerData = ArrangementOut;

export type AddContainerError = HTTPValidationError;

export interface RemoveContainerParams {
  /** Container Id */
  containerId: number;
}

export type RemoveContainerData = any;

export type RemoveContainerError = HTTPValidationError;

export interface AddItemToContainerParams {
  /** Container Id */
  containerId: number;
}

export type AddItemToContainerData = any;

export type AddItemToContainerError = HTTPValidationError;

export interface RemoveItemParams {
  /** Item Id */
  itemId: number;
}

export type RemoveItemData = any;

export type RemoveItemError = HTTPValidationError;

export interface UpdateItemQuantityParams {
  /** Quantity */
  quantity: number;
  /** Item Id */
  itemId: number;
}

export type UpdateItemQuantityData = any;

export type UpdateItemQuantityError = HTTPValidationError;

export interface ImageProxyParams {
  /** Url */
  url?: string | null;
  /** Key */
  key?: string | null;
}

export type ImageProxyData = any;

export type ImageProxyError = HTTPValidationError;

export interface ListProductsParams {
  /** Supplier Id */
  supplier_id?: number | null;
  /** Category */
  category?: string | null;
  /** Favorites Only */
  favorites_only?: boolean | null;
  /** Search */
  search?: string | null;
}

/** Response List Products */
export type ListProductsData = ProductOut[];

export type ListProductsError = HTTPValidationError;

export type CreateProductData = ProductOut;

export type CreateProductError = HTTPValidationError;

export interface UpdateProductParams {
  /** Product Id */
  productId: number;
}

export type UpdateProductData = ProductOut;

export type UpdateProductError = HTTPValidationError;

export interface DeleteProductParams {
  /** Product Id */
  productId: number;
}

export type DeleteProductData = any;

export type DeleteProductError = HTTPValidationError;

export interface UploadProductPhotoParams {
  /** Product Id */
  productId: number;
}

export type UploadProductPhotoData = any;

export type UploadProductPhotoError = HTTPValidationError;

export type UploadProductPhotoNewData = any;

export type UploadProductPhotoNewError = HTTPValidationError;

export interface ToggleFavoriteParams {
  /** Product Id */
  productId: number;
}

export type ToggleFavoriteData = any;

export type ToggleFavoriteError = HTTPValidationError;

export interface SyncPrices2Params {
  /** Product Id */
  productId: number;
}

export type SyncPrices2Data = ProductOut;

export type SyncPrices2Error = HTTPValidationError;

export type GetProductStatsData = any;

/** Response List Suppliers */
export type ListSuppliersData = SupplierOut[];

export type CreateSupplierData = SupplierOut;

export type CreateSupplierError = HTTPValidationError;

export interface UpdateSupplierParams {
  /** Supplier Id */
  supplierId: number;
}

export type UpdateSupplierData = SupplierOut;

export type UpdateSupplierError = HTTPValidationError;

export interface DeleteSupplierParams {
  /** Supplier Id */
  supplierId: number;
}

export type DeleteSupplierData = any;

export type DeleteSupplierError = HTTPValidationError;

export interface GetSupplierParams {
  /** Supplier Id */
  supplierId: number;
}

export type GetSupplierData = SupplierOut;

export type GetSupplierError = HTTPValidationError;

export interface GetCatalogFiltersParams {
  /** Supplier Id */
  supplierId: number;
}

export type GetCatalogFiltersData = CatalogFilters;

export type GetCatalogFiltersError = HTTPValidationError;

export interface SaveCatalogFiltersParams {
  /** Supplier Id */
  supplierId: number;
}

export type SaveCatalogFiltersData = CatalogFilters;

export type SaveCatalogFiltersError = HTTPValidationError;

export interface DeleteCatalogFiltersParams {
  /** Supplier Id */
  supplierId: number;
}

export type DeleteCatalogFiltersData = any;

export type DeleteCatalogFiltersError = HTTPValidationError;

export interface DiscoverCatalogParams {
  /**
   * Force Refresh
   * @default false
   */
  force_refresh?: boolean;
  /** Supplier Id */
  supplierId: number;
}

export type DiscoverCatalogData = DiscoverCatalogResponse;

export type DiscoverCatalogError = HTTPValidationError;

export type GetMarkupSettingsData = AllMarkupSettings;

export type UpdateMarkupData = any;

export type UpdateMarkupError = HTTPValidationError;

export interface DeleteCategoryMarkupParams {
  /** Category */
  category: string;
}

export type DeleteCategoryMarkupData = any;

export type DeleteCategoryMarkupError = HTTPValidationError;

/** Response List User Roles */
export type ListUserRolesData = UserRoleOut[];

export type SetUserRoleData = any;

export type SetUserRoleError = HTTPValidationError;

export type GetMyRoleData = any;

export interface ListMockupsParams {
  /** Arrangement Id */
  arrangementId: number;
}

/** Response List Mockups */
export type ListMockupsData = MockupOut[];

export type ListMockupsError = HTTPValidationError;

export type GenerateMockupData = MockupOut;

export type GenerateMockupError = HTTPValidationError;

export interface DeleteMockupParams {
  /** Mockup Id */
  mockupId: number;
}

export type DeleteMockupData = any;

export type DeleteMockupError = HTTPValidationError;

export type GetCategoryIndexData = CategoryIndexResponse;

export interface RebuildSupplierCategoryIndexParams {
  /** Supplier Id */
  supplierId: number;
}

export type RebuildSupplierCategoryIndexData = RebuildIndexResponse;

export type RebuildSupplierCategoryIndexError = HTTPValidationError;

export type GetAdminDashboardData = AdminDashboardResponse;

export interface ToggleScraperParams {
  /** Enabled */
  enabled: boolean;
  /** Supplier Id */
  supplierId: number;
}

export type ToggleScraperData = any;

export type ToggleScraperError = HTTPValidationError;

export interface SyncPricesParams {
  /** Supplier Id */
  supplierId: number;
}

export type SyncPricesData = PriceSyncResponse;

export type SyncPricesError = HTTPValidationError;

export type SyncPricesBulkData = PriceSyncResponse;

export type SyncPricesBulkError = HTTPValidationError;

export interface GetPriceHistoryParams {
  /** Product Id */
  productId: number;
}

/** Response Get Price History */
export type GetPriceHistoryData = PriceHistoryEntry[];

export type GetPriceHistoryError = HTTPValidationError;

export type StartScrapeData = ScrapeJobOut;

export type StartScrapeError = HTTPValidationError;

export interface ListScrapeJobsParams {
  /** Supplier Id */
  supplierId: number;
}

/** Response List Scrape Jobs */
export type ListScrapeJobsData = ScrapeJobOut[];

export type ListScrapeJobsError = HTTPValidationError;

export interface GetScrapeJobParams {
  /** Job Id */
  jobId: number;
}

export type GetScrapeJobData = ScrapeJobOut;

export type GetScrapeJobError = HTTPValidationError;

export interface PreviewScrapedProductsParams {
  /**
   * Limit
   * @default 50
   */
  limit?: number;
  /** Job Id */
  jobId: number;
}

/** Response Preview Scraped Products */
export type PreviewScrapedProductsData = ScrapedProductOut[];

export type PreviewScrapedProductsError = HTTPValidationError;

export type ImportScrapedProductsData = any;

export type ImportScrapedProductsError = HTTPValidationError;

export type StartBackfillImagesData = BackfillStatusOut;

export type GetBackfillStatusData = BackfillStatusOut;
