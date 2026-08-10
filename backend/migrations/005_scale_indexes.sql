-- Indexes for a catalog that outgrew its original size.
--
-- The product table went from ~95k to ~166k active rows (537 MB) when Michaels
-- and NewPro Containers were onboarded. Queries that were fine before started
-- taking 13-29s server-side, which made the Suppliers page and Catalog Search
-- look broken: the request outlived the browser.
--
-- Applied to Supabase on 2026-08-10. Kept here so any rebuilt database gets them.

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Per-supplier product counts, and any is_active-filtered scan.
CREATE INDEX IF NOT EXISTS idx_products_is_active
  ON products (is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_products_supplier_active
  ON products (supplier_id) WHERE is_active = TRUE;

-- The catalog's default ordering. Without this, ORDER BY name LIMIT 48 sorted
-- all 166k rows; with it the scan stops at the limit (13.3s -> 0.32s).
CREATE INDEX IF NOT EXISTS idx_products_active_name
  ON products (name) WHERE is_active = TRUE;

-- Keyword search uses ILIKE '%term%', which no btree can serve. Trigram GIN
-- indexes make it indexable (moss: 16.1s -> 1.7s).
CREATE INDEX IF NOT EXISTS idx_products_name_trgm
  ON products USING GIN (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_products_sku_trgm
  ON products USING GIN (supplier_sku gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_products_desc_trgm
  ON products USING GIN (description gin_trgm_ops);

-- Planner stats were stale after 75% row growth.
ANALYZE products;
