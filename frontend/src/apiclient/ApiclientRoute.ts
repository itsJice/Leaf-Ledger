import {
  AddContainerData,
  AddItemToContainerData,
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
  CreateProductData,
  CreateSupplierData,
  DeleteArrangementData,
  DeleteCatalogFiltersData,
  DeleteCategoryMarkupData,
  DeleteMockupData,
  DeleteProductData,
  DeleteSupplierData,
  DiscoverCatalogData,
  GenerateMockupData,
  GetAdminDashboardData,
  GetArrangementData,
  GetBackfillStatusData,
  GetCatalogFiltersData,
  GetCategoryIndexData,
  GetMarkupSettingsData,
  GetMyRoleData,
  GetPriceHistoryData,
  GetProductStatsData,
  GetScrapeJobData,
  GetSupplierData,
  ImageProxyData,
  ImportScrapedProductsData,
  ImportScrapedRequest,
  ListArrangementsData,
  ListMockupsData,
  ListProductsData,
  ListScrapeJobsData,
  ListSuppliersData,
  ListUserRolesData,
  MarkupUpdate,
  MockupCreate,
  PreviewScrapedProductsData,
  ProductCreate,
  ProductPriceUpdate,
  ProductUpdate,
  RebuildSupplierCategoryIndexData,
  RemoveContainerData,
  RemoveItemData,
  SaveCatalogFiltersData,
  SetUserRoleData,
  StartBackfillImagesData,
  StartScrapeData,
  StartScrapeRequest,
  SupplierCreate,
  SupplierUpdate,
  SyncPrices2Data,
  SyncPricesBulkData,
  SyncPricesData,
  ToggleFavoriteData,
  ToggleScraperData,
  UpdateArrangementData,
  UpdateItemQuantityData,
  UpdateMarkupData,
  UpdateProductData,
  UpdateSupplierData,
  UploadProductPhotoData,
  UploadProductPhotoNewData,
  UserRoleUpdate,
} from "./data-contracts";

export namespace Apiclient {
  /**
   * @description Check health of application. Returns 200 when OK, 500 when not.
   * @name check_health
   * @summary Check Health
   * @request GET:/_healthz
   */
  export namespace check_health {
    export type RequestParams = {};
    export type RequestQuery = {};
    export type RequestBody = never;
    export type RequestHeaders = {};
    export type ResponseBody = CheckHealthData;
  }

  /**
   * No description
   * @tags arrangements, dbtn/module:arrangements
   * @name list_arrangements
   * @summary List Arrangements
   * @request GET:/routes/arrangements/list
   */
  export namespace list_arrangements {
    export type RequestParams = {};
    export type RequestQuery = {};
    export type RequestBody = never;
    export type RequestHeaders = {};
    export type ResponseBody = ListArrangementsData;
  }

  /**
   * No description
   * @tags arrangements, dbtn/module:arrangements
   * @name create_arrangement
   * @summary Create Arrangement
   * @request POST:/routes/arrangements/create
   */
  export namespace create_arrangement {
    export type RequestParams = {};
    export type RequestQuery = {};
    export type RequestBody = ArrangementCreate;
    export type RequestHeaders = {};
    export type ResponseBody = CreateArrangementData;
  }

  /**
   * No description
   * @tags arrangements, dbtn/module:arrangements
   * @name get_arrangement
   * @summary Get Arrangement
   * @request GET:/routes/arrangements/get/{arrangement_id}
   */
  export namespace get_arrangement {
    export type RequestParams = {
      /** Arrangement Id */
      arrangementId: number;
    };
    export type RequestQuery = {};
    export type RequestBody = never;
    export type RequestHeaders = {};
    export type ResponseBody = GetArrangementData;
  }

  /**
   * No description
   * @tags arrangements, dbtn/module:arrangements
   * @name update_arrangement
   * @summary Update Arrangement
   * @request PUT:/routes/arrangements/update/{arrangement_id}
   */
  export namespace update_arrangement {
    export type RequestParams = {
      /** Arrangement Id */
      arrangementId: number;
    };
    export type RequestQuery = {};
    export type RequestBody = ArrangementUpdate;
    export type RequestHeaders = {};
    export type ResponseBody = UpdateArrangementData;
  }

  /**
   * No description
   * @tags arrangements, dbtn/module:arrangements
   * @name delete_arrangement
   * @summary Delete Arrangement
   * @request DELETE:/routes/arrangements/delete/{arrangement_id}
   */
  export namespace delete_arrangement {
    export type RequestParams = {
      /** Arrangement Id */
      arrangementId: number;
    };
    export type RequestQuery = {};
    export type RequestBody = never;
    export type RequestHeaders = {};
    export type ResponseBody = DeleteArrangementData;
  }

  /**
   * No description
   * @tags arrangements, dbtn/module:arrangements
   * @name add_container
   * @summary Add Container
   * @request POST:/routes/arrangements/container/add/{arrangement_id}
   */
  export namespace add_container {
    export type RequestParams = {
      /** Arrangement Id */
      arrangementId: number;
    };
    export type RequestQuery = {};
    export type RequestBody = ContainerIn;
    export type RequestHeaders = {};
    export type ResponseBody = AddContainerData;
  }

  /**
   * No description
   * @tags arrangements, dbtn/module:arrangements
   * @name remove_container
   * @summary Remove Container
   * @request DELETE:/routes/arrangements/container/remove/{container_id}
   */
  export namespace remove_container {
    export type RequestParams = {
      /** Container Id */
      containerId: number;
    };
    export type RequestQuery = {};
    export type RequestBody = never;
    export type RequestHeaders = {};
    export type ResponseBody = RemoveContainerData;
  }

  /**
   * No description
   * @tags arrangements, dbtn/module:arrangements
   * @name add_item_to_container
   * @summary Add Item To Container
   * @request POST:/routes/arrangements/item/add/{container_id}
   */
  export namespace add_item_to_container {
    export type RequestParams = {
      /** Container Id */
      containerId: number;
    };
    export type RequestQuery = {};
    export type RequestBody = ContainerItemIn;
    export type RequestHeaders = {};
    export type ResponseBody = AddItemToContainerData;
  }

  /**
   * No description
   * @tags arrangements, dbtn/module:arrangements
   * @name remove_item
   * @summary Remove Item
   * @request DELETE:/routes/arrangements/item/remove/{item_id}
   */
  export namespace remove_item {
    export type RequestParams = {
      /** Item Id */
      itemId: number;
    };
    export type RequestQuery = {};
    export type RequestBody = never;
    export type RequestHeaders = {};
    export type ResponseBody = RemoveItemData;
  }

  /**
   * No description
   * @tags arrangements, dbtn/module:arrangements
   * @name update_item_quantity
   * @summary Update Item Quantity
   * @request PUT:/routes/arrangements/item/quantity/{item_id}
   */
  export namespace update_item_quantity {
    export type RequestParams = {
      /** Item Id */
      itemId: number;
    };
    export type RequestQuery = {
      /** Quantity */
      quantity: number;
    };
    export type RequestBody = never;
    export type RequestHeaders = {};
    export type ResponseBody = UpdateItemQuantityData;
  }

  /**
   * @description Serve a product image — either from Databutton storage (key=) or by proxying an external URL (url=).
   * @tags products, dbtn/module:products
   * @name image_proxy
   * @summary Image Proxy
   * @request GET:/routes/products/image-proxy
   */
  export namespace image_proxy {
    export type RequestParams = {};
    export type RequestQuery = {
      /** Url */
      url?: string | null;
      /** Key */
      key?: string | null;
    };
    export type RequestBody = never;
    export type RequestHeaders = {};
    export type ResponseBody = ImageProxyData;
  }

  /**
   * No description
   * @tags products, dbtn/module:products
   * @name list_products
   * @summary List Products
   * @request GET:/routes/products/list
   */
  export namespace list_products {
    export type RequestParams = {};
    export type RequestQuery = {
      /** Supplier Id */
      supplier_id?: number | null;
      /** Category */
      category?: string | null;
      /** Favorites Only */
      favorites_only?: boolean | null;
      /** Search */
      search?: string | null;
    };
    export type RequestBody = never;
    export type RequestHeaders = {};
    export type ResponseBody = ListProductsData;
  }

  /**
   * No description
   * @tags products, dbtn/module:products
   * @name create_product
   * @summary Create Product
   * @request POST:/routes/products/create
   */
  export namespace create_product {
    export type RequestParams = {};
    export type RequestQuery = {};
    export type RequestBody = ProductCreate;
    export type RequestHeaders = {};
    export type ResponseBody = CreateProductData;
  }

  /**
   * No description
   * @tags products, dbtn/module:products
   * @name update_product
   * @summary Update Product
   * @request PUT:/routes/products/update/{product_id}
   */
  export namespace update_product {
    export type RequestParams = {
      /** Product Id */
      productId: number;
    };
    export type RequestQuery = {};
    export type RequestBody = ProductUpdate;
    export type RequestHeaders = {};
    export type ResponseBody = UpdateProductData;
  }

  /**
   * No description
   * @tags products, dbtn/module:products
   * @name delete_product
   * @summary Delete Product
   * @request DELETE:/routes/products/delete/{product_id}
   */
  export namespace delete_product {
    export type RequestParams = {
      /** Product Id */
      productId: number;
    };
    export type RequestQuery = {};
    export type RequestBody = never;
    export type RequestHeaders = {};
    export type ResponseBody = DeleteProductData;
  }

  /**
   * No description
   * @tags products, dbtn/module:products
   * @name upload_product_photo
   * @summary Upload Product Photo
   * @request POST:/routes/products/upload-photo/{product_id}
   */
  export namespace upload_product_photo {
    export type RequestParams = {
      /** Product Id */
      productId: number;
    };
    export type RequestQuery = {};
    export type RequestBody = BodyUploadProductPhoto;
    export type RequestHeaders = {};
    export type ResponseBody = UploadProductPhotoData;
  }

  /**
   * @description Upload a photo before product is created (returns temp URL)
   * @tags products, dbtn/module:products
   * @name upload_product_photo_new
   * @summary Upload Product Photo New
   * @request POST:/routes/products/upload-photo-new
   */
  export namespace upload_product_photo_new {
    export type RequestParams = {};
    export type RequestQuery = {};
    export type RequestBody = BodyUploadProductPhotoNew;
    export type RequestHeaders = {};
    export type ResponseBody = UploadProductPhotoNewData;
  }

  /**
   * No description
   * @tags products, dbtn/module:products
   * @name toggle_favorite
   * @summary Toggle Favorite
   * @request POST:/routes/products/favorite/{product_id}
   */
  export namespace toggle_favorite {
    export type RequestParams = {
      /** Product Id */
      productId: number;
    };
    export type RequestQuery = {};
    export type RequestBody = never;
    export type RequestHeaders = {};
    export type ResponseBody = ToggleFavoriteData;
  }

  /**
   * @description Manually update a product's price and record the change in price history.
   * @tags products, dbtn/module:products
   * @name sync_prices2
   * @summary Sync Prices2
   * @request POST:/routes/products/sync-price/{product_id}
   */
  export namespace sync_prices2 {
    export type RequestParams = {
      /** Product Id */
      productId: number;
    };
    export type RequestQuery = {};
    export type RequestBody = ProductPriceUpdate;
    export type RequestHeaders = {};
    export type ResponseBody = SyncPrices2Data;
  }

  /**
   * No description
   * @tags products, dbtn/module:products
   * @name get_product_stats
   * @summary Get Product Stats
   * @request GET:/routes/products/stats
   */
  export namespace get_product_stats {
    export type RequestParams = {};
    export type RequestQuery = {};
    export type RequestBody = never;
    export type RequestHeaders = {};
    export type ResponseBody = GetProductStatsData;
  }

  /**
   * No description
   * @tags suppliers, dbtn/module:suppliers
   * @name list_suppliers
   * @summary List Suppliers
   * @request GET:/routes/suppliers/list
   */
  export namespace list_suppliers {
    export type RequestParams = {};
    export type RequestQuery = {};
    export type RequestBody = never;
    export type RequestHeaders = {};
    export type ResponseBody = ListSuppliersData;
  }

  /**
   * No description
   * @tags suppliers, dbtn/module:suppliers
   * @name create_supplier
   * @summary Create Supplier
   * @request POST:/routes/suppliers/create
   */
  export namespace create_supplier {
    export type RequestParams = {};
    export type RequestQuery = {};
    export type RequestBody = SupplierCreate;
    export type RequestHeaders = {};
    export type ResponseBody = CreateSupplierData;
  }

  /**
   * No description
   * @tags suppliers, dbtn/module:suppliers
   * @name update_supplier
   * @summary Update Supplier
   * @request PUT:/routes/suppliers/update/{supplier_id}
   */
  export namespace update_supplier {
    export type RequestParams = {
      /** Supplier Id */
      supplierId: number;
    };
    export type RequestQuery = {};
    export type RequestBody = SupplierUpdate;
    export type RequestHeaders = {};
    export type ResponseBody = UpdateSupplierData;
  }

  /**
   * No description
   * @tags suppliers, dbtn/module:suppliers
   * @name delete_supplier
   * @summary Delete Supplier
   * @request DELETE:/routes/suppliers/delete/{supplier_id}
   */
  export namespace delete_supplier {
    export type RequestParams = {
      /** Supplier Id */
      supplierId: number;
    };
    export type RequestQuery = {};
    export type RequestBody = never;
    export type RequestHeaders = {};
    export type ResponseBody = DeleteSupplierData;
  }

  /**
   * No description
   * @tags suppliers, dbtn/module:suppliers
   * @name get_supplier
   * @summary Get Supplier
   * @request GET:/routes/suppliers/get/{supplier_id}
   */
  export namespace get_supplier {
    export type RequestParams = {
      /** Supplier Id */
      supplierId: number;
    };
    export type RequestQuery = {};
    export type RequestBody = never;
    export type RequestHeaders = {};
    export type ResponseBody = GetSupplierData;
  }

  /**
   * @description Return saved catalog filter selections for this supplier. Returns empty lists if none have been saved yet (meaning scrape everything).
   * @tags suppliers, dbtn/module:suppliers
   * @name get_catalog_filters
   * @summary Get Catalog Filters
   * @request GET:/routes/suppliers/{supplier_id}/catalog-filters
   */
  export namespace get_catalog_filters {
    export type RequestParams = {
      /** Supplier Id */
      supplierId: number;
    };
    export type RequestQuery = {};
    export type RequestBody = never;
    export type RequestHeaders = {};
    export type ResponseBody = GetCatalogFiltersData;
  }

  /**
   * @description Save the user's catalog selections for this supplier. Empty lists = scrape everything (safe default).
   * @tags suppliers, dbtn/module:suppliers
   * @name save_catalog_filters
   * @summary Save Catalog Filters
   * @request PUT:/routes/suppliers/{supplier_id}/catalog-filters
   */
  export namespace save_catalog_filters {
    export type RequestParams = {
      /** Supplier Id */
      supplierId: number;
    };
    export type RequestQuery = {};
    export type RequestBody = CatalogFiltersUpdate;
    export type RequestHeaders = {};
    export type ResponseBody = SaveCatalogFiltersData;
  }

  /**
   * @description Clear all catalog filter selections for this supplier (resets to scrape-everything).
   * @tags suppliers, dbtn/module:suppliers
   * @name delete_catalog_filters
   * @summary Delete Catalog Filters
   * @request DELETE:/routes/suppliers/{supplier_id}/catalog-filters
   */
  export namespace delete_catalog_filters {
    export type RequestParams = {
      /** Supplier Id */
      supplierId: number;
    };
    export type RequestQuery = {};
    export type RequestBody = never;
    export type RequestHeaders = {};
    export type ResponseBody = DeleteCatalogFiltersData;
  }

  /**
   * @description Return the live category tree for a supplier, grouped by section. Strategy (cache-first with 30-day TTL): - If the category index was built < 30 days ago AND force_refresh is False, return the cached index instantly (no browser session needed). - If the index is stale (> 30 days) OR force_refresh=True, log in live, crawl all sections, save a fresh index, and return results. Does NOT scrape products — this is a lightweight discovery pass only. Live crawl takes ~1-3 minutes. Cached response is instant.
   * @tags suppliers, dbtn/module:suppliers
   * @name discover_catalog
   * @summary Discover Catalog
   * @request POST:/routes/suppliers/{supplier_id}/discover-catalog
   */
  export namespace discover_catalog {
    export type RequestParams = {
      /** Supplier Id */
      supplierId: number;
    };
    export type RequestQuery = {
      /**
       * Force Refresh
       * @default false
       */
      force_refresh?: boolean;
    };
    export type RequestBody = never;
    export type RequestHeaders = {};
    export type ResponseBody = DiscoverCatalogData;
  }

  /**
   * No description
   * @tags settings, dbtn/module:settings
   * @name get_markup_settings
   * @summary Get Markup Settings
   * @request GET:/routes/settings/markup
   */
  export namespace get_markup_settings {
    export type RequestParams = {};
    export type RequestQuery = {};
    export type RequestBody = never;
    export type RequestHeaders = {};
    export type ResponseBody = GetMarkupSettingsData;
  }

  /**
   * No description
   * @tags settings, dbtn/module:settings
   * @name update_markup
   * @summary Update Markup
   * @request PUT:/routes/settings/markup
   */
  export namespace update_markup {
    export type RequestParams = {};
    export type RequestQuery = {};
    export type RequestBody = MarkupUpdate;
    export type RequestHeaders = {};
    export type ResponseBody = UpdateMarkupData;
  }

  /**
   * No description
   * @tags settings, dbtn/module:settings
   * @name delete_category_markup
   * @summary Delete Category Markup
   * @request DELETE:/routes/settings/markup/category/{category}
   */
  export namespace delete_category_markup {
    export type RequestParams = {
      /** Category */
      category: string;
    };
    export type RequestQuery = {};
    export type RequestBody = never;
    export type RequestHeaders = {};
    export type ResponseBody = DeleteCategoryMarkupData;
  }

  /**
   * No description
   * @tags settings, dbtn/module:settings
   * @name list_user_roles
   * @summary List User Roles
   * @request GET:/routes/settings/roles
   */
  export namespace list_user_roles {
    export type RequestParams = {};
    export type RequestQuery = {};
    export type RequestBody = never;
    export type RequestHeaders = {};
    export type ResponseBody = ListUserRolesData;
  }

  /**
   * No description
   * @tags settings, dbtn/module:settings
   * @name set_user_role
   * @summary Set User Role
   * @request POST:/routes/settings/roles
   */
  export namespace set_user_role {
    export type RequestParams = {};
    export type RequestQuery = {};
    export type RequestBody = UserRoleUpdate;
    export type RequestHeaders = {};
    export type ResponseBody = SetUserRoleData;
  }

  /**
   * No description
   * @tags settings, dbtn/module:settings
   * @name get_my_role
   * @summary Get My Role
   * @request GET:/routes/settings/my-role
   */
  export namespace get_my_role {
    export type RequestParams = {};
    export type RequestQuery = {};
    export type RequestBody = never;
    export type RequestHeaders = {};
    export type ResponseBody = GetMyRoleData;
  }

  /**
   * No description
   * @tags mockups, dbtn/module:mockups
   * @name list_mockups
   * @summary List Mockups
   * @request GET:/routes/mockups/list/{arrangement_id}
   */
  export namespace list_mockups {
    export type RequestParams = {
      /** Arrangement Id */
      arrangementId: number;
    };
    export type RequestQuery = {};
    export type RequestBody = never;
    export type RequestHeaders = {};
    export type ResponseBody = ListMockupsData;
  }

  /**
   * No description
   * @tags mockups, dbtn/module:mockups
   * @name generate_mockup
   * @summary Generate Mockup
   * @request POST:/routes/mockups/generate
   */
  export namespace generate_mockup {
    export type RequestParams = {};
    export type RequestQuery = {};
    export type RequestBody = MockupCreate;
    export type RequestHeaders = {};
    export type ResponseBody = GenerateMockupData;
  }

  /**
   * No description
   * @tags mockups, dbtn/module:mockups
   * @name delete_mockup
   * @summary Delete Mockup
   * @request DELETE:/routes/mockups/delete/{mockup_id}
   */
  export namespace delete_mockup {
    export type RequestParams = {
      /** Mockup Id */
      mockupId: number;
    };
    export type RequestQuery = {};
    export type RequestBody = never;
    export type RequestHeaders = {};
    export type ResponseBody = DeleteMockupData;
  }

  /**
   * @description Return the full category index for all suppliers that have a scraper.
   * @tags admin, dbtn/module:admin_dashboard
   * @name get_category_index
   * @summary Get Category Index
   * @request GET:/routes/admin/category-index
   */
  export namespace get_category_index {
    export type RequestParams = {};
    export type RequestQuery = {};
    export type RequestBody = never;
    export type RequestHeaders = {};
    export type ResponseBody = GetCategoryIndexData;
  }

  /**
   * @description Wipe the category index so the next scrape does a full re-discovery.
   * @tags admin, dbtn/module:admin_dashboard
   * @name rebuild_supplier_category_index
   * @summary Rebuild Supplier Category Index
   * @request POST:/routes/admin/category-index/{supplier_id}/rebuild
   */
  export namespace rebuild_supplier_category_index {
    export type RequestParams = {
      /** Supplier Id */
      supplierId: number;
    };
    export type RequestQuery = {};
    export type RequestBody = never;
    export type RequestHeaders = {};
    export type ResponseBody = RebuildSupplierCategoryIndexData;
  }

  /**
   * @description Return full admin dashboard: supplier health, sync history, and price changes.
   * @tags admin, dbtn/module:admin_dashboard
   * @name get_admin_dashboard
   * @summary Get Admin Dashboard
   * @request GET:/routes/admin/dashboard
   */
  export namespace get_admin_dashboard {
    export type RequestParams = {};
    export type RequestQuery = {};
    export type RequestBody = never;
    export type RequestHeaders = {};
    export type ResponseBody = GetAdminDashboardData;
  }

  /**
   * @description Enable or disable the automated scraper for a supplier.
   * @tags admin, dbtn/module:admin_dashboard
   * @name toggle_scraper
   * @summary Toggle Scraper
   * @request POST:/routes/admin/toggle-scraper/{supplier_id}
   */
  export namespace toggle_scraper {
    export type RequestParams = {
      /** Supplier Id */
      supplierId: number;
    };
    export type RequestQuery = {
      /** Enabled */
      enabled: boolean;
    };
    export type RequestBody = never;
    export type RequestHeaders = {};
    export type ResponseBody = ToggleScraperData;
  }

  /**
   * @description Trigger a price-only sync for a supplier. Updates existing product prices fast.
   * @tags scraper, dbtn/module:scraper
   * @name sync_prices
   * @summary Sync Prices
   * @request POST:/routes/scraper/sync-prices/{supplier_id}
   */
  export namespace sync_prices {
    export type RequestParams = {
      /** Supplier Id */
      supplierId: number;
    };
    export type RequestQuery = {};
    export type RequestBody = never;
    export type RequestHeaders = {};
    export type ResponseBody = SyncPricesData;
  }

  /**
   * @description Sync prices for multiple suppliers at once. Used for auto-sync on arrangement/invoice open.
   * @tags scraper, dbtn/module:scraper
   * @name sync_prices_bulk
   * @summary Sync Prices Bulk
   * @request POST:/routes/scraper/sync-prices-bulk
   */
  export namespace sync_prices_bulk {
    export type RequestParams = {};
    export type RequestQuery = {};
    export type RequestBody = BulkPriceSyncRequest;
    export type RequestHeaders = {};
    export type ResponseBody = SyncPricesBulkData;
  }

  /**
   * @description Get price change history for a product.
   * @tags scraper, dbtn/module:scraper
   * @name get_price_history
   * @summary Get Price History
   * @request GET:/routes/scraper/price-history/{product_id}
   */
  export namespace get_price_history {
    export type RequestParams = {
      /** Product Id */
      productId: number;
    };
    export type RequestQuery = {};
    export type RequestBody = never;
    export type RequestHeaders = {};
    export type ResponseBody = GetPriceHistoryData;
  }

  /**
   * @description Kick off a catalog scrape for a supplier. Credentials must be saved on the supplier record first.
   * @tags scraper, dbtn/module:scraper
   * @name start_scrape
   * @summary Start Scrape
   * @request POST:/routes/scraper/start
   */
  export namespace start_scrape {
    export type RequestParams = {};
    export type RequestQuery = {};
    export type RequestBody = StartScrapeRequest;
    export type RequestHeaders = {};
    export type ResponseBody = StartScrapeData;
  }

  /**
   * @description List all scrape jobs for a supplier, newest first.
   * @tags scraper, dbtn/module:scraper
   * @name list_scrape_jobs
   * @summary List Scrape Jobs
   * @request GET:/routes/scraper/jobs/{supplier_id}
   */
  export namespace list_scrape_jobs {
    export type RequestParams = {
      /** Supplier Id */
      supplierId: number;
    };
    export type RequestQuery = {};
    export type RequestBody = never;
    export type RequestHeaders = {};
    export type ResponseBody = ListScrapeJobsData;
  }

  /**
   * @description Poll current status of a scrape job.
   * @tags scraper, dbtn/module:scraper
   * @name get_scrape_job
   * @summary Get Scrape Job
   * @request GET:/routes/scraper/job/{job_id}
   */
  export namespace get_scrape_job {
    export type RequestParams = {
      /** Job Id */
      jobId: number;
    };
    export type RequestQuery = {};
    export type RequestBody = never;
    export type RequestHeaders = {};
    export type ResponseBody = GetScrapeJobData;
  }

  /**
   * @description Return the first N scraped products for review before committing to the database.
   * @tags scraper, dbtn/module:scraper
   * @name preview_scraped_products
   * @summary Preview Scraped Products
   * @request GET:/routes/scraper/preview/{job_id}
   */
  export namespace preview_scraped_products {
    export type RequestParams = {
      /** Job Id */
      jobId: number;
    };
    export type RequestQuery = {
      /**
       * Limit
       * @default 50
       */
      limit?: number;
    };
    export type RequestBody = never;
    export type RequestHeaders = {};
    export type ResponseBody = PreviewScrapedProductsData;
  }

  /**
   * @description Kick off a background import of scraped products into the products table. Returns immediately — poll GET /scraper/job/{id} for phase='done' to know when it finishes.
   * @tags scraper, dbtn/module:scraper
   * @name import_scraped_products
   * @summary Import Scraped Products
   * @request POST:/routes/scraper/import
   */
  export namespace import_scraped_products {
    export type RequestParams = {};
    export type RequestQuery = {};
    export type RequestBody = ImportScrapedRequest;
    export type RequestHeaders = {};
    export type ResponseBody = ImportScrapedProductsData;
  }

  /**
   * @description Kick off a one-time background job that downloads all existing product images to Databutton storage so they never expire. Poll GET /scraper/backfill-images/status to track progress.
   * @tags scraper, dbtn/module:scraper
   * @name start_backfill_images
   * @summary Start Backfill Images
   * @request POST:/routes/scraper/backfill-images
   */
  export namespace start_backfill_images {
    export type RequestParams = {};
    export type RequestQuery = {};
    export type RequestBody = never;
    export type RequestHeaders = {};
    export type ResponseBody = StartBackfillImagesData;
  }

  /**
   * @description Poll the progress of the image backfill background job.
   * @tags scraper, dbtn/module:scraper
   * @name get_backfill_status
   * @summary Get Backfill Status
   * @request GET:/routes/scraper/backfill-images/status
   */
  export namespace get_backfill_status {
    export type RequestParams = {};
    export type RequestQuery = {};
    export type RequestBody = never;
    export type RequestHeaders = {};
    export type ResponseBody = GetBackfillStatusData;
  }
}
