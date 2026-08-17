-- Close the last two parity gaps between the SQL search path and the in-memory
-- index, so the index (≈892 MB, OOM-killing the web service) can be retired.
--
-- 1. Sort order. The index sorts on Python str.lower(), i.e. raw codepoints.
--    This database is en_US.UTF-8, whose collation ignores leading punctuation,
--    so the two paths returned different PAGES for the same query and offset
--    pagination broke across a path flip. Sorting by lower(name) COLLATE "C"
--    reproduces Python's ordering; without an index behind it that sort costs
--    6.66s vs 0.12s.
--
-- 2. Keyword recall. The index searches a flattened blob of every searchable
--    value in raw_data; SQL only searched name/description/sku, returning ~69%
--    fewer rows for "green wreath". 61 of the 62 remaining parity defects were
--    downstream of this one gap - every wrong facet count is a symptom.
--
-- Also adds product_type and availability to the facet table. They were the
-- only reason the unfiltered facet baseline cost ~59s: `style` is NULL on 82%
-- of rows, so product_type fell through to raw_data and detoasted the catalog.
--
-- Applied 2026-08-17. All backfill work happens server-side (no egress).

-- ---------------------------------------------------------------------------
-- 1. Ordering index on products
-- ---------------------------------------------------------------------------
-- CONCURRENTLY: no ACCESS EXCLUSIVE lock, so the live app keeps reading.
-- Must run outside a transaction block.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_products_lower_name_c
  ON products (lower(name) COLLATE "C") WHERE is_active;

-- ---------------------------------------------------------------------------
-- 2. Extra facet columns
-- ---------------------------------------------------------------------------
ALTER TABLE product_facets
  ADD COLUMN IF NOT EXISTS search_blob  text,
  ADD COLUMN IF NOT EXISTS product_type text,
  ADD COLUMN IF NOT EXISTS availability text;

-- ---------------------------------------------------------------------------
-- 3. Teach the sync trigger about them
-- ---------------------------------------------------------------------------
-- search_blob mirrors _searchable_values() in app/apis/products/__init__.py:
-- every scalar value in raw_data, minus URLs and anything >= 200 chars (long
-- prose and image links add weight without adding search terms), plus the
-- columns the index also folds in: name, sku, description and supplier name.
CREATE OR REPLACE FUNCTION public.product_facets_blob(p products)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT lower(concat_ws(' ',
    p.name, p.supplier_sku, p.description,
    (SELECT s.name FROM suppliers s WHERE s.id = p.supplier_id),
    (SELECT string_agg(v.value, ' ')
       FROM jsonb_each_text(
              CASE WHEN jsonb_typeof(p.raw_data) = 'object'
                   THEN p.raw_data ELSE '{}'::jsonb END) AS v(key, value)
      WHERE v.value <> ''
        AND length(v.value) < 200
        AND v.value NOT LIKE 'http%')
  ));
$$;

CREATE OR REPLACE FUNCTION public.product_facets_sync()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    IF TG_OP = 'DELETE' THEN
        DELETE FROM product_facets WHERE product_id = OLD.id;
        RETURN OLD;
    END IF;

    -- Only active products are faceted; a deactivated product drops out.
    IF NEW.is_active IS NOT TRUE THEN
        DELETE FROM product_facets WHERE product_id = NEW.id;
        RETURN NEW;
    END IF;

    INSERT INTO product_facets AS pf (
        product_id, name, supplier_id, category_group,
        norm_color, norm_finish, norm_size_in, color_families,
        search_blob, product_type, availability
    )
    VALUES (
        NEW.id,
        NEW.name,
        NEW.supplier_id,
        NEW.raw_data->>'category_group',
        NEW.raw_data->'normalized'->>'color',
        NEW.raw_data->'normalized'->>'finish',
        NEW.raw_data->'normalized'->>'size_in',
        CASE WHEN jsonb_typeof(NEW.raw_data->'color_families') = 'array'
             THEN ARRAY(SELECT jsonb_array_elements_text(NEW.raw_data->'color_families'))
        END,
        public.product_facets_blob(NEW),
        COALESCE(NULLIF(NEW.style, ''), NEW.raw_data->>'product_type'),
        NEW.availability
    )
    ON CONFLICT (product_id) DO UPDATE SET
        name           = EXCLUDED.name,
        supplier_id    = EXCLUDED.supplier_id,
        category_group = EXCLUDED.category_group,
        norm_color     = EXCLUDED.norm_color,
        norm_finish    = EXCLUDED.norm_finish,
        norm_size_in   = EXCLUDED.norm_size_in,
        color_families = EXCLUDED.color_families,
        search_blob    = EXCLUDED.search_blob,
        product_type   = EXCLUDED.product_type,
        availability   = EXCLUDED.availability
    -- Skip the write when nothing a facet cares about actually changed. A
    -- re-scrape usually rewrites raw_data byte-for-byte identically; without
    -- this guard every such write would leave a dead tuple here and bloat the
    -- table and its indexes.
    WHERE (pf.name, pf.supplier_id, pf.category_group, pf.norm_color,
           pf.norm_finish, pf.norm_size_in, pf.color_families,
           pf.search_blob, pf.product_type, pf.availability)
      IS DISTINCT FROM
          (EXCLUDED.name, EXCLUDED.supplier_id, EXCLUDED.category_group,
           EXCLUDED.norm_color, EXCLUDED.norm_finish, EXCLUDED.norm_size_in,
           EXCLUDED.color_families, EXCLUDED.search_blob,
           EXCLUDED.product_type, EXCLUDED.availability);

    RETURN NEW;
END;
$function$;

-- ---------------------------------------------------------------------------
-- 4. Backfill (run in batches by the migration script, not here)
-- ---------------------------------------------------------------------------
-- UPDATE product_facets f SET search_blob = ..., product_type = ..., availability = ...
--   FROM products p WHERE p.id = f.product_id;

-- ---------------------------------------------------------------------------
-- 5. Indexes for the new columns
-- ---------------------------------------------------------------------------
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_pf_search_blob_trgm
  ON product_facets USING GIN (search_blob gin_trgm_ops);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_pf_product_type
  ON product_facets (product_type);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_pf_availability
  ON product_facets (availability);
