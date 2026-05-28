import {
  AddContainerData,
  AddContainerError,
  AddContainerParams,
  AddItemToContainerData,
  AddItemToContainerError,
  AddItemToContainerParams,
  ArrangementCreate,
  ArrangementUpdate,
  BodyUploadProductPhoto,
  BodyUploadProductPhotoNew,
  BulkPriceSyncRequest,
  CatalogFiltersUpdate,
  CheckHealthData,
  ContainerIn,
  ContainerItemIn,
  CreateArrangementData,
  CreateArrangementError,
  CreateProductData,
  CreateProductError,
  CreateSupplierData,
  CreateSupplierError,
  DeleteArrangementData,
  DeleteArrangementError,
  DeleteArrangementParams,
  DeleteCatalogFiltersData,
  DeleteCatalogFiltersError,
  DeleteCatalogFiltersParams,
  DeleteCategoryMarkupData,
  DeleteCategoryMarkupError,
  DeleteCategoryMarkupParams,
  DeleteMockupData,
  DeleteMockupError,
  DeleteMockupParams,
  DeleteProductData,
  DeleteProductError,
  DeleteProductParams,
  DeleteSupplierData,
  DeleteSupplierError,
  DeleteSupplierParams,
  DiscoverCatalogData,
  DiscoverCatalogError,
  DiscoverCatalogParams,
  GenerateMockupData,
  GenerateMockupError,
  GetAdminDashboardData,
  GetArrangementData,
  GetArrangementError,
  GetArrangementParams,
  GetBackfillStatusData,
  GetCatalogFiltersData,
  GetCatalogFiltersError,
  GetCatalogFiltersParams,
  GetCategoryIndexData,
  GetMarkupSettingsData,
  GetMyRoleData,
  GetPriceHistoryData,
  GetPriceHistoryError,
  GetPriceHistoryParams,
  GetProductStatsData,
  GetScrapeJobData,
  GetScrapeJobError,
  GetScrapeJobParams,
  GetSupplierData,
  GetSupplierError,
  GetSupplierParams,
  ImageProxyData,
  ImageProxyError,
  ImageProxyParams,
  ImportScrapedProductsData,
  ImportScrapedProductsError,
  ImportScrapedRequest,
  ListArrangementsData,
  ListMockupsData,
  ListMockupsError,
  ListMockupsParams,
  ListProductsData,
  ListProductsError,
  ListProductsParams,
  ListScrapeJobsData,
  ListScrapeJobsError,
  ListScrapeJobsParams,
  ListSuppliersData,
  ListUserRolesData,
  MarkupUpdate,
  MockupCreate,
  PreviewScrapedProductsData,
  PreviewScrapedProductsError,
  PreviewScrapedProductsParams,
  ProductCreate,
  ProductPriceUpdate,
  ProductUpdate,
  RebuildSupplierCategoryIndexData,
  RebuildSupplierCategoryIndexError,
  RebuildSupplierCategoryIndexParams,
  RemoveContainerData,
  RemoveContainerError,
  RemoveContainerParams,
  RemoveItemData,
  RemoveItemError,
  RemoveItemParams,
  SaveCatalogFiltersData,
  SaveCatalogFiltersError,
  SaveCatalogFiltersParams,
  SetUserRoleData,
  SetUserRoleError,
  StartBackfillImagesData,
  StartScrapeData,
  StartScrapeError,
  StartScrapeRequest,
  SupplierCreate,
  SupplierUpdate,
  SyncPrices2Data,
  SyncPrices2Error,
  SyncPrices2Params,
  SyncPricesBulkData,
  SyncPricesBulkError,
  SyncPricesData,
  SyncPricesError,
  SyncPricesParams,
  ToggleFavoriteData,
  ToggleFavoriteError,
  ToggleFavoriteParams,
  ToggleScraperData,
  ToggleScraperError,
  ToggleScraperParams,
  UpdateArrangementData,
  UpdateArrangementError,
  UpdateArrangementParams,
  UpdateItemQuantityData,
  UpdateItemQuantityError,
  UpdateItemQuantityParams,
  UpdateMarkupData,
  UpdateMarkupError,
  UpdateProductData,
  UpdateProductError,
  UpdateProductParams,
  UpdateSupplierData,
  UpdateSupplierError,
  UpdateSupplierParams,
  UploadProductPhotoData,
  UploadProductPhotoError,
  UploadProductPhotoNewData,
  UploadProductPhotoNewError,
  UploadProductPhotoParams,
  UserRoleUpdate,
} from "./data-contracts";
import { ContentType, HttpClient, RequestParams } from "./http-client";

export class Apiclient<SecurityDataType = unknown> extends HttpClient<SecurityDataType> {
  /**
   * @description Check health of application. Returns 200 when OK, 500 when not.
   *
   * @name check_health
   * @summary Check Health
   * @request GET:/_healthz
   */
  check_health = (params: RequestParams = {}) =>
    this.request<CheckHealthData, any>({
      path: `/_healthz`,
      method: "GET",
      ...params,
    });

  /**
   * No description
   *
   * @tags arrangements, dbtn/module:arrangements
   * @name list_arrangements
   * @summary List Arrangements
   * @request GET:/routes/arrangements/list
   */
  list_arrangements = (params: RequestParams = {}) =>
    this.request<ListArrangementsData, any>({
      path: `/routes/arrangements/list`,
      method: "GET",
      ...params,
    });

  /**
   * No description
   *
   * @tags arrangements, dbtn/module:arrangements
   * @name create_arrangement
   * @summary Create Arrangement
   * @request POST:/routes/arrangements/create
   */
  create_arrangement = (data: ArrangementCreate, params: RequestParams = {}) =>
    this.request<CreateArrangementData, CreateArrangementError>({
      path: `/routes/arrangements/create`,
      method: "POST",
      body: data,
      type: ContentType.Json,
      ...params,
    });

  /**
   * No description
   *
   * @tags arrangements, dbtn/module:arrangements
   * @name get_arrangement
   * @summary Get Arrangement
   * @request GET:/routes/arrangements/get/{arrangement_id}
   */
  get_arrangement = ({ arrangementId, ...query }: GetArrangementParams, params: RequestParams = {}) =>
    this.request<GetArrangementData, GetArrangementError>({
      path: `/routes/arrangements/get/${arrangementId}`,
      method: "GET",
      ...params,
    });

  /**
   * No description
   *
   * @tags arrangements, dbtn/module:arrangements
   * @name update_arrangement
   * @summary Update Arrangement
   * @request PUT:/routes/arrangements/update/{arrangement_id}
   */
  update_arrangement = (
    { arrangementId, ...query }: UpdateArrangementParams,
    data: ArrangementUpdate,
    params: RequestParams = {},
  ) =>
    this.request<UpdateArrangementData, UpdateArrangementError>({
      path: `/routes/arrangements/update/${arrangementId}`,
      method: "PUT",
      body: data,
      type: ContentType.Json,
      ...params,
    });

  /**
   * No description
   *
   * @tags arrangements, dbtn/module:arrangements
   * @name delete_arrangement
   * @summary Delete Arrangement
   * @request DELETE:/routes/arrangements/delete/{arrangement_id}
   */
  delete_arrangement = ({ arrangementId, ...query }: DeleteArrangementParams, params: RequestParams = {}) =>
    this.request<DeleteArrangementData, DeleteArrangementError>({
      path: `/routes/arrangements/delete/${arrangementId}`,
      method: "DELETE",
      ...params,
    });

  /**
   * No description
   *
   * @tags arrangements, dbtn/module:arrangements
   * @name add_container
   * @summary Add Container
   * @request POST:/routes/arrangements/container/add/{arrangement_id}
   */
  add_container = ({ arrangementId, ...query }: AddContainerParams, data: ContainerIn, params: RequestParams = {}) =>
    this.request<AddContainerData, AddContainerError>({
      path: `/routes/arrangements/container/add/${arrangementId}`,
      method: "POST",
      body: data,
      type: ContentType.Json,
      ...params,
    });

  /**
   * No description
   *
   * @tags arrangements, dbtn/module:arrangements
   * @name remove_container
   * @summary Remove Container
   * @request DELETE:/routes/arrangements/container/remove/{container_id}
   */
  remove_container = ({ containerId, ...query }: RemoveContainerParams, params: RequestParams = {}) =>
    this.request<RemoveContainerData, RemoveContainerError>({
      path: `/routes/arrangements/container/remove/${containerId}`,
      method: "DELETE",
      ...params,
    });

  /**
   * No description
   *
   * @tags arrangements, dbtn/module:arrangements
   * @name add_item_to_container
   * @summary Add Item To Container
   * @request POST:/routes/arrangements/item/add/{container_id}
   */
  add_item_to_container = (
    { containerId, ...query }: AddItemToContainerParams,
    data: ContainerItemIn,
    params: RequestParams = {},
  ) =>
    this.request<AddItemToContainerData, AddItemToContainerError>({
      path: `/routes/arrangements/item/add/${containerId}`,
      method: "POST",
      body: data,
      type: ContentType.Json,
      ...params,
    });

  /**
   * No description
   *
   * @tags arrangements, dbtn/module:arrangements
   * @name remove_item
   * @summary Remove Item
   * @request DELETE:/routes/arrangements/item/remove/{item_id}
   */
  remove_item = ({ itemId, ...query }: RemoveItemParams, params: RequestParams = {}) =>
    this.request<RemoveItemData, RemoveItemError>({
      path: `/routes/arrangements/item/remove/${itemId}`,
      method: "DELETE",
      ...params,
    });

  /**
   * No description
   *
   * @tags arrangements, dbtn/module:arrangements
   * @name update_item_quantity
   * @summary Update Item Quantity
   * @request PUT:/routes/arrangements/item/quantity/{item_id}
   */
  update_item_quantity = ({ itemId, ...query }: UpdateItemQuantityParams, params: RequestParams = {}) =>
    this.request<UpdateItemQuantityData, UpdateItemQuantityError>({
      path: `/routes/arrangements/item/quantity/${itemId}`,
      method: "PUT",
      query: query,
      ...params,
    });

  /**
   * @description Serve a product image — either from Databutton storage (key=) or by proxying an external URL (url=).
   *
   * @tags products, dbtn/module:products
   * @name image_proxy
   * @summary Image Proxy
   * @request GET:/routes/products/image-proxy
   */
  image_proxy = (query: ImageProxyParams, params: RequestParams = {}) =>
    this.request<ImageProxyData, ImageProxyError>({
      path: `/routes/products/image-proxy`,
      method: "GET",
      query: query,
      ...params,
    });

  /**
   * No description
   *
   * @tags products, dbtn/module:products
   * @name list_products
   * @summary List Products
   * @request GET:/routes/products/list
   */
  list_products = (query: ListProductsParams, params: RequestParams = {}) =>
    this.request<ListProductsData, ListProductsError>({
      path: `/routes/products/list`,
      method: "GET",
      query: query,
      ...params,
    });

  /**
   * No description
   *
   * @tags products, dbtn/module:products
   * @name create_product
   * @summary Create Product
   * @request POST:/routes/products/create
   */
  create_product = (data: ProductCreate, params: RequestParams = {}) =>
    this.request<CreateProductData, CreateProductError>({
      path: `/routes/products/create`,
      method: "POST",
      body: data,
      type: ContentType.Json,
      ...params,
    });

  /**
   * No description
   *
   * @tags products, dbtn/module:products
   * @name update_product
   * @summary Update Product
   * @request PUT:/routes/products/update/{product_id}
   */
  update_product = ({ productId, ...query }: UpdateProductParams, data: ProductUpdate, params: RequestParams = {}) =>
    this.request<UpdateProductData, UpdateProductError>({
      path: `/routes/products/update/${productId}`,
      method: "PUT",
      body: data,
      type: ContentType.Json,
      ...params,
    });

  /**
   * No description
   *
   * @tags products, dbtn/module:products
   * @name delete_product
   * @summary Delete Product
   * @request DELETE:/routes/products/delete/{product_id}
   */
  delete_product = ({ productId, ...query }: DeleteProductParams, params: RequestParams = {}) =>
    this.request<DeleteProductData, DeleteProductError>({
      path: `/routes/products/delete/${productId}`,
      method: "DELETE",
      ...params,
    });

  /**
   * No description
   *
   * @tags products, dbtn/module:products
   * @name upload_product_photo
   * @summary Upload Product Photo
   * @request POST:/routes/products/upload-photo/{product_id}
   */
  upload_product_photo = (
    { productId, ...query }: UploadProductPhotoParams,
    data: BodyUploadProductPhoto,
    params: RequestParams = {},
  ) =>
    this.request<UploadProductPhotoData, UploadProductPhotoError>({
      path: `/routes/products/upload-photo/${productId}`,
      method: "POST",
      body: data,
      type: ContentType.FormData,
      ...params,
    });

  /**
   * @description Upload a photo before product is created (returns temp URL)
   *
   * @tags products, dbtn/module:products
   * @name upload_product_photo_new
   * @summary Upload Product Photo New
   * @request POST:/routes/products/upload-photo-new
   */
  upload_product_photo_new = (data: BodyUploadProductPhotoNew, params: RequestParams = {}) =>
    this.request<UploadProductPhotoNewData, UploadProductPhotoNewError>({
      path: `/routes/products/upload-photo-new`,
      method: "POST",
      body: data,
      type: ContentType.FormData,
      ...params,
    });

  /**
   * No description
   *
   * @tags products, dbtn/module:products
   * @name toggle_favorite
   * @summary Toggle Favorite
   * @request POST:/routes/products/favorite/{product_id}
   */
  toggle_favorite = ({ productId, ...query }: ToggleFavoriteParams, params: RequestParams = {}) =>
    this.request<ToggleFavoriteData, ToggleFavoriteError>({
      path: `/routes/products/favorite/${productId}`,
      method: "POST",
      ...params,
    });

  /**
   * @description Manually update a product's price and record the change in price history.
   *
   * @tags products, dbtn/module:products
   * @name sync_prices2
   * @summary Sync Prices2
   * @request POST:/routes/products/sync-price/{product_id}
   */
  sync_prices2 = ({ productId, ...query }: SyncPrices2Params, data: ProductPriceUpdate, params: RequestParams = {}) =>
    this.request<SyncPrices2Data, SyncPrices2Error>({
      path: `/routes/products/sync-price/${productId}`,
      method: "POST",
      body: data,
      type: ContentType.Json,
      ...params,
    });

  /**
   * No description
   *
   * @tags products, dbtn/module:products
   * @name get_product_stats
   * @summary Get Product Stats
   * @request GET:/routes/products/stats
   */
  get_product_stats = (params: RequestParams = {}) =>
    this.request<GetProductStatsData, any>({
      path: `/routes/products/stats`,
      method: "GET",
      ...params,
    });

  /**
   * No description
   *
   * @tags suppliers, dbtn/module:suppliers
   * @name list_suppliers
   * @summary List Suppliers
   * @request GET:/routes/suppliers/list
   */
  list_suppliers = (params: RequestParams = {}) =>
    this.request<ListSuppliersData, any>({
      path: `/routes/suppliers/list`,
      method: "GET",
      ...params,
    });

  /**
   * No description
   *
   * @tags suppliers, dbtn/module:suppliers
   * @name create_supplier
   * @summary Create Supplier
   * @request POST:/routes/suppliers/create
   */
  create_supplier = (data: SupplierCreate, params: RequestParams = {}) =>
    this.request<CreateSupplierData, CreateSupplierError>({
      path: `/routes/suppliers/create`,
      method: "POST",
      body: data,
      type: ContentType.Json,
      ...params,
    });

  /**
   * No description
   *
   * @tags suppliers, dbtn/module:suppliers
   * @name update_supplier
   * @summary Update Supplier
   * @request PUT:/routes/suppliers/update/{supplier_id}
   */
  update_supplier = (
    { supplierId, ...query }: UpdateSupplierParams,
    data: SupplierUpdate,
    params: RequestParams = {},
  ) =>
    this.request<UpdateSupplierData, UpdateSupplierError>({
      path: `/routes/suppliers/update/${supplierId}`,
      method: "PUT",
      body: data,
      type: ContentType.Json,
      ...params,
    });

  /**
   * No description
   *
   * @tags suppliers, dbtn/module:suppliers
   * @name delete_supplier
   * @summary Delete Supplier
   * @request DELETE:/routes/suppliers/delete/{supplier_id}
   */
  delete_supplier = ({ supplierId, ...query }: DeleteSupplierParams, params: RequestParams = {}) =>
    this.request<DeleteSupplierData, DeleteSupplierError>({
      path: `/routes/suppliers/delete/${supplierId}`,
      method: "DELETE",
      ...params,
    });

  /**
   * No description
   *
   * @tags suppliers, dbtn/module:suppliers
   * @name get_supplier
   * @summary Get Supplier
   * @request GET:/routes/suppliers/get/{supplier_id}
   */
  get_supplier = ({ supplierId, ...query }: GetSupplierParams, params: RequestParams = {}) =>
    this.request<GetSupplierData, GetSupplierError>({
      path: `/routes/suppliers/get/${supplierId}`,
      method: "GET",
      ...params,
    });

  /**
   * @description Return saved catalog filter selections for this supplier. Returns empty lists if none have been saved yet (meaning scrape everything).
   *
   * @tags suppliers, dbtn/module:suppliers
   * @name get_catalog_filters
   * @summary Get Catalog Filters
   * @request GET:/routes/suppliers/{supplier_id}/catalog-filters
   */
  get_catalog_filters = ({ supplierId, ...query }: GetCatalogFiltersParams, params: RequestParams = {}) =>
    this.request<GetCatalogFiltersData, GetCatalogFiltersError>({
      path: `/routes/suppliers/${supplierId}/catalog-filters`,
      method: "GET",
      ...params,
    });

  /**
   * @description Save the user's catalog selections for this supplier. Empty lists = scrape everything (safe default).
   *
   * @tags suppliers, dbtn/module:suppliers
   * @name save_catalog_filters
   * @summary Save Catalog Filters
   * @request PUT:/routes/suppliers/{supplier_id}/catalog-filters
   */
  save_catalog_filters = (
    { supplierId, ...query }: SaveCatalogFiltersParams,
    data: CatalogFiltersUpdate,
    params: RequestParams = {},
  ) =>
    this.request<SaveCatalogFiltersData, SaveCatalogFiltersError>({
      path: `/routes/suppliers/${supplierId}/catalog-filters`,
      method: "PUT",
      body: data,
      type: ContentType.Json,
      ...params,
    });

  /**
   * @description Clear all catalog filter selections for this supplier (resets to scrape-everything).
   *
   * @tags suppliers, dbtn/module:suppliers
   * @name delete_catalog_filters
   * @summary Delete Catalog Filters
   * @request DELETE:/routes/suppliers/{supplier_id}/catalog-filters
   */
  delete_catalog_filters = ({ supplierId, ...query }: DeleteCatalogFiltersParams, params: RequestParams = {}) =>
    this.request<DeleteCatalogFiltersData, DeleteCatalogFiltersError>({
      path: `/routes/suppliers/${supplierId}/catalog-filters`,
      method: "DELETE",
      ...params,
    });

  /**
   * @description Return the live category tree for a supplier, grouped by section. Strategy (cache-first with 30-day TTL): - If the category index was built < 30 days ago AND force_refresh is False, return the cached index instantly (no browser session needed). - If the index is stale (> 30 days) OR force_refresh=True, log in live, crawl all sections, save a fresh index, and return results. Does NOT scrape products — this is a lightweight discovery pass only. Live crawl takes ~1-3 minutes. Cached response is instant.
   *
   * @tags suppliers, dbtn/module:suppliers
   * @name discover_catalog
   * @summary Discover Catalog
   * @request POST:/routes/suppliers/{supplier_id}/discover-catalog
   */
  discover_catalog = ({ supplierId, ...query }: DiscoverCatalogParams, params: RequestParams = {}) =>
    this.request<DiscoverCatalogData, DiscoverCatalogError>({
      path: `/routes/suppliers/${supplierId}/discover-catalog`,
      method: "POST",
      query: query,
      ...params,
    });

  /**
   * No description
   *
   * @tags settings, dbtn/module:settings
   * @name get_markup_settings
   * @summary Get Markup Settings
   * @request GET:/routes/settings/markup
   */
  get_markup_settings = (params: RequestParams = {}) =>
    this.request<GetMarkupSettingsData, any>({
      path: `/routes/settings/markup`,
      method: "GET",
      ...params,
    });

  /**
   * No description
   *
   * @tags settings, dbtn/module:settings
   * @name update_markup
   * @summary Update Markup
   * @request PUT:/routes/settings/markup
   */
  update_markup = (data: MarkupUpdate, params: RequestParams = {}) =>
    this.request<UpdateMarkupData, UpdateMarkupError>({
      path: `/routes/settings/markup`,
      method: "PUT",
      body: data,
      type: ContentType.Json,
      ...params,
    });

  /**
   * No description
   *
   * @tags settings, dbtn/module:settings
   * @name delete_category_markup
   * @summary Delete Category Markup
   * @request DELETE:/routes/settings/markup/category/{category}
   */
  delete_category_markup = ({ category, ...query }: DeleteCategoryMarkupParams, params: RequestParams = {}) =>
    this.request<DeleteCategoryMarkupData, DeleteCategoryMarkupError>({
      path: `/routes/settings/markup/category/${category}`,
      method: "DELETE",
      ...params,
    });

  /**
   * No description
   *
   * @tags settings, dbtn/module:settings
   * @name list_user_roles
   * @summary List User Roles
   * @request GET:/routes/settings/roles
   */
  list_user_roles = (params: RequestParams = {}) =>
    this.request<ListUserRolesData, any>({
      path: `/routes/settings/roles`,
      method: "GET",
      ...params,
    });

  /**
   * No description
   *
   * @tags settings, dbtn/module:settings
   * @name set_user_role
   * @summary Set User Role
   * @request POST:/routes/settings/roles
   */
  set_user_role = (data: UserRoleUpdate, params: RequestParams = {}) =>
    this.request<SetUserRoleData, SetUserRoleError>({
      path: `/routes/settings/roles`,
      method: "POST",
      body: data,
      type: ContentType.Json,
      ...params,
    });

  /**
   * No description
   *
   * @tags settings, dbtn/module:settings
   * @name get_my_role
   * @summary Get My Role
   * @request GET:/routes/settings/my-role
   */
  get_my_role = (params: RequestParams = {}) =>
    this.request<GetMyRoleData, any>({
      path: `/routes/settings/my-role`,
      method: "GET",
      ...params,
    });

  /**
   * No description
   *
   * @tags mockups, dbtn/module:mockups
   * @name list_mockups
   * @summary List Mockups
   * @request GET:/routes/mockups/list/{arrangement_id}
   */
  list_mockups = ({ arrangementId, ...query }: ListMockupsParams, params: RequestParams = {}) =>
    this.request<ListMockupsData, ListMockupsError>({
      path: `/routes/mockups/list/${arrangementId}`,
      method: "GET",
      ...params,
    });

  /**
   * No description
   *
   * @tags mockups, dbtn/module:mockups
   * @name generate_mockup
   * @summary Generate Mockup
   * @request POST:/routes/mockups/generate
   */
  generate_mockup = (data: MockupCreate, params: RequestParams = {}) =>
    this.request<GenerateMockupData, GenerateMockupError>({
      path: `/routes/mockups/generate`,
      method: "POST",
      body: data,
      type: ContentType.Json,
      ...params,
    });

  /**
   * No description
   *
   * @tags mockups, dbtn/module:mockups
   * @name delete_mockup
   * @summary Delete Mockup
   * @request DELETE:/routes/mockups/delete/{mockup_id}
   */
  delete_mockup = ({ mockupId, ...query }: DeleteMockupParams, params: RequestParams = {}) =>
    this.request<DeleteMockupData, DeleteMockupError>({
      path: `/routes/mockups/delete/${mockupId}`,
      method: "DELETE",
      ...params,
    });

  /**
   * @description Return the full category index for all suppliers that have a scraper.
   *
   * @tags admin, dbtn/module:admin_dashboard
   * @name get_category_index
   * @summary Get Category Index
   * @request GET:/routes/admin/category-index
   */
  get_category_index = (params: RequestParams = {}) =>
    this.request<GetCategoryIndexData, any>({
      path: `/routes/admin/category-index`,
      method: "GET",
      ...params,
    });

  /**
   * @description Wipe the category index so the next scrape does a full re-discovery.
   *
   * @tags admin, dbtn/module:admin_dashboard
   * @name rebuild_supplier_category_index
   * @summary Rebuild Supplier Category Index
   * @request POST:/routes/admin/category-index/{supplier_id}/rebuild
   */
  rebuild_supplier_category_index = (
    { supplierId, ...query }: RebuildSupplierCategoryIndexParams,
    params: RequestParams = {},
  ) =>
    this.request<RebuildSupplierCategoryIndexData, RebuildSupplierCategoryIndexError>({
      path: `/routes/admin/category-index/${supplierId}/rebuild`,
      method: "POST",
      ...params,
    });

  /**
   * @description Return full admin dashboard: supplier health, sync history, and price changes.
   *
   * @tags admin, dbtn/module:admin_dashboard
   * @name get_admin_dashboard
   * @summary Get Admin Dashboard
   * @request GET:/routes/admin/dashboard
   */
  get_admin_dashboard = (params: RequestParams = {}) =>
    this.request<GetAdminDashboardData, any>({
      path: `/routes/admin/dashboard`,
      method: "GET",
      ...params,
    });

  /**
   * @description Enable or disable the automated scraper for a supplier.
   *
   * @tags admin, dbtn/module:admin_dashboard
   * @name toggle_scraper
   * @summary Toggle Scraper
   * @request POST:/routes/admin/toggle-scraper/{supplier_id}
   */
  toggle_scraper = ({ supplierId, ...query }: ToggleScraperParams, params: RequestParams = {}) =>
    this.request<ToggleScraperData, ToggleScraperError>({
      path: `/routes/admin/toggle-scraper/${supplierId}`,
      method: "POST",
      query: query,
      ...params,
    });

  /**
   * @description Trigger a price-only sync for a supplier. Updates existing product prices fast.
   *
   * @tags scraper, dbtn/module:scraper
   * @name sync_prices
   * @summary Sync Prices
   * @request POST:/routes/scraper/sync-prices/{supplier_id}
   */
  sync_prices = ({ supplierId, ...query }: SyncPricesParams, params: RequestParams = {}) =>
    this.request<SyncPricesData, SyncPricesError>({
      path: `/routes/scraper/sync-prices/${supplierId}`,
      method: "POST",
      ...params,
    });

  /**
   * @description Sync prices for multiple suppliers at once. Used for auto-sync on arrangement/invoice open.
   *
   * @tags scraper, dbtn/module:scraper
   * @name sync_prices_bulk
   * @summary Sync Prices Bulk
   * @request POST:/routes/scraper/sync-prices-bulk
   */
  sync_prices_bulk = (data: BulkPriceSyncRequest, params: RequestParams = {}) =>
    this.request<SyncPricesBulkData, SyncPricesBulkError>({
      path: `/routes/scraper/sync-prices-bulk`,
      method: "POST",
      body: data,
      type: ContentType.Json,
      ...params,
    });

  /**
   * @description Get price change history for a product.
   *
   * @tags scraper, dbtn/module:scraper
   * @name get_price_history
   * @summary Get Price History
   * @request GET:/routes/scraper/price-history/{product_id}
   */
  get_price_history = ({ productId, ...query }: GetPriceHistoryParams, params: RequestParams = {}) =>
    this.request<GetPriceHistoryData, GetPriceHistoryError>({
      path: `/routes/scraper/price-history/${productId}`,
      method: "GET",
      ...params,
    });

  /**
   * @description Kick off a catalog scrape for a supplier. Credentials must be saved on the supplier record first.
   *
   * @tags scraper, dbtn/module:scraper
   * @name start_scrape
   * @summary Start Scrape
   * @request POST:/routes/scraper/start
   */
  start_scrape = (data: StartScrapeRequest, params: RequestParams = {}) =>
    this.request<StartScrapeData, StartScrapeError>({
      path: `/routes/scraper/start`,
      method: "POST",
      body: data,
      type: ContentType.Json,
      ...params,
    });

  /**
   * @description List all scrape jobs for a supplier, newest first.
   *
   * @tags scraper, dbtn/module:scraper
   * @name list_scrape_jobs
   * @summary List Scrape Jobs
   * @request GET:/routes/scraper/jobs/{supplier_id}
   */
  list_scrape_jobs = ({ supplierId, ...query }: ListScrapeJobsParams, params: RequestParams = {}) =>
    this.request<ListScrapeJobsData, ListScrapeJobsError>({
      path: `/routes/scraper/jobs/${supplierId}`,
      method: "GET",
      ...params,
    });

  /**
   * @description Poll current status of a scrape job.
   *
   * @tags scraper, dbtn/module:scraper
   * @name get_scrape_job
   * @summary Get Scrape Job
   * @request GET:/routes/scraper/job/{job_id}
   */
  get_scrape_job = ({ jobId, ...query }: GetScrapeJobParams, params: RequestParams = {}) =>
    this.request<GetScrapeJobData, GetScrapeJobError>({
      path: `/routes/scraper/job/${jobId}`,
      method: "GET",
      ...params,
    });

  /**
   * @description Return the first N scraped products for review before committing to the database.
   *
   * @tags scraper, dbtn/module:scraper
   * @name preview_scraped_products
   * @summary Preview Scraped Products
   * @request GET:/routes/scraper/preview/{job_id}
   */
  preview_scraped_products = ({ jobId, ...query }: PreviewScrapedProductsParams, params: RequestParams = {}) =>
    this.request<PreviewScrapedProductsData, PreviewScrapedProductsError>({
      path: `/routes/scraper/preview/${jobId}`,
      method: "GET",
      query: query,
      ...params,
    });

  /**
   * @description Kick off a background import of scraped products into the products table. Returns immediately — poll GET /scraper/job/{id} for phase='done' to know when it finishes.
   *
   * @tags scraper, dbtn/module:scraper
   * @name import_scraped_products
   * @summary Import Scraped Products
   * @request POST:/routes/scraper/import
   */
  import_scraped_products = (data: ImportScrapedRequest, params: RequestParams = {}) =>
    this.request<ImportScrapedProductsData, ImportScrapedProductsError>({
      path: `/routes/scraper/import`,
      method: "POST",
      body: data,
      type: ContentType.Json,
      ...params,
    });

  /**
   * @description Kick off a one-time background job that downloads all existing product images to Databutton storage so they never expire. Poll GET /scraper/backfill-images/status to track progress.
   *
   * @tags scraper, dbtn/module:scraper
   * @name start_backfill_images
   * @summary Start Backfill Images
   * @request POST:/routes/scraper/backfill-images
   */
  start_backfill_images = (params: RequestParams = {}) =>
    this.request<StartBackfillImagesData, any>({
      path: `/routes/scraper/backfill-images`,
      method: "POST",
      ...params,
    });

  /**
   * @description Poll the progress of the image backfill background job.
   *
   * @tags scraper, dbtn/module:scraper
   * @name get_backfill_status
   * @summary Get Backfill Status
   * @request GET:/routes/scraper/backfill-images/status
   */
  get_backfill_status = (params: RequestParams = {}) =>
    this.request<GetBackfillStatusData, any>({
      path: `/routes/scraper/backfill-images/status`,
      method: "GET",
      ...params,
    });
}
