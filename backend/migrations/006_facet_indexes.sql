-- 006_facet_indexes.sql
--
-- Goal: serve catalog facet counts (category_group, colour, finish, size, colour
-- families) from SQL, so the web service can drop the ~892 MB in-memory facet
-- index that was OOM-killing it.
--
-- Idempotent: safe to re-run. Written for PostgreSQL 17 (Supabase).
--
-- ---------------------------------------------------------------------------
-- WHY THIS FILE DOES NOT JUST ADD EXPRESSION INDEXES
-- ---------------------------------------------------------------------------
-- The facet values live in `products.raw_data` (jsonb). The obvious cheap fix
-- is an expression index such as
--     CREATE INDEX ... ON products ((raw_data->'normalized'->>'finish'))
-- and that is what was tried first. It does not work, and it is actively
-- harmful. Measured on this database:
--
--   * PostgreSQL cannot serve an Index-Only Scan from an expression index.
--     check_index_only() resolves the query's target list down to the base
--     column (`raw_data`) via pull_varattnos, and an expression index registers
--     its key as attnum 0 and therefore never satisfies that base column. This
--     was confirmed on an isolated 50k-row probe table: an index on
--     (j->'normalized'->>'color') produced a Seq Scan, while a plain text
--     column index on the same data produced an Index Only Scan.
--
--   * Because no Index-Only Scan is possible, the planner instead picked a
--     plain Index Scan (it is cheaper *on paper* than a Seq Scan because it
--     avoids the hash aggregate). That walks the 355 MB heap in index order —
--     random I/O on an instance with only 224 MB of shared_buffers. Result:
--     the grouped finish query measured 40.8 / 47.7 / 63.0 s WITH the index,
--     versus 5.3-16.1 s with a plain Seq Scan. The index made it ~4x slower.
--
-- The expression index is therefore DROPPED below rather than added to.
--
-- ---------------------------------------------------------------------------
-- WHY A NARROW SIDE TABLE, AND NOT STORED GENERATED COLUMNS
-- ---------------------------------------------------------------------------
-- Real columns *do* get Index-Only Scans, so `ADD COLUMN ... GENERATED ALWAYS
-- AS (raw_data->...) STORED` would work. It was rejected on cost:
--
--   * It rewrites the whole table under an ACCESS EXCLUSIVE lock. Measured: a
--     1/4-size copy of products (41,504 rows, 70 MB heap) took 11.2 s to add
--     the four STORED columns, so the full table is a ~45 s hard lock. That is
--     45 s of real, user-visible downtime on a table the app reads constantly,
--     and it buys nothing the side table does not already give us.
--   * It does not shrink the working set. Facet aggregation would still scan a
--     355 MB heap + 143 MB TOAST that cannot fit in 224 MB of shared_buffers,
--     so every facet query keeps competing for cache with normal catalog reads.
--
-- The root cause of the slowness is that `raw_data` averages ~1.3 KB/row, so
-- any aggregate over a JSONB path must read and JSONB-parse ~215 MB of data
-- for 166k rows. The fix is to stop reading raw_data at query time at all.
--
-- `product_facets` is a narrow projection: one row per active product holding
-- only the facet values plus `name` (denormalised so keyword-filtered facets
-- never touch `products` either). It is small enough to sit entirely in
-- shared_buffers, which is what makes the facet queries fast.
--
-- It is maintained by triggers on `products`, NOT by a scheduled refresh:
-- products are written from at least four independent code paths
-- (app/libs/scraper_base.py, app/apis/scraper, app/apis/suppliers,
-- scripts/load_findings.py), so a refresh call would have to be added to all
-- of them and would silently drift the day someone adds a fifth. Triggers live
-- in the database and cannot be bypassed.
-- ---------------------------------------------------------------------------

-- ---------------------------------------------------------------------------
-- MEASURED RESULT (Supabase Pro, 224 MB shared_buffers, 166,029 active rows)
--
-- Grouped facet count, server-side, median of 5 runs:
--
--   facet                 before (scan raw_data)   after (product_facets)
--   category_group                       7,114 ms                 27.5 ms
--   normalized color                    13,809 ms                 26.7 ms
--   normalized finish                   20,153 ms                 25.4 ms
--   normalized size_in                  12,781 ms                 27.8 ms
--   color_families (all)                 8,933 ms                121.2 ms
--   color_families @> ARRAY['Red']              -                  1.3 ms
--   all five in one query               ~62,800 ms                229.7 ms
--
--   ...and with `name ILIKE '%moss%'` also applied, every individual facet is
--   ~4 ms and all five together are 20 ms.
--
-- Build cost: ~4.5 min on first run, ~75 s on a re-run, none of it blocking
-- readers (see operational notes). Storage: 44 MB (18 MB heap + 25 MB indexes)
-- against a 632 MB products table -- of which 16 MB is the name trigram index
-- that makes the keyword-filtered facets self-contained.
--
-- ---------------------------------------------------------------------------
-- OPERATIONAL NOTES FOR RE-RUNNING THIS
--
--   * Run it with `SET statement_timeout = 0`. The initial population takes
--     ~108 s and Supabase's default statement timeout will kill it.
--   * CREATE/DROP TRIGGER needs a lock on `products` that conflicts with
--     writers. On the first run the DROP TRIGGER waited 147 s behind existing
--     long-running catalog queries before it could proceed. It blocks writes,
--     not reads, and only for as long as it waits -- but if the app is busy,
--     set a `lock_timeout` and retry rather than letting it queue and stack up
--     behind you.
--   * Run the statements individually, NOT as one batch. As a single
--     transaction the trigger's lock on `products` would be held for the whole
--     ~4 min run, blocking every scraper write for that entire window.
-- ---------------------------------------------------------------------------

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ---------------------------------------------------------------------------
-- 1. Remove the counter-productive expression index (see above).
--    Cost: 0.05 s. This index made the finish facet ~4x SLOWER.
-- ---------------------------------------------------------------------------
DROP INDEX IF EXISTS idx_products_norm_finish;

-- ---------------------------------------------------------------------------
-- 2. The narrow facet projection.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS product_facets (
    product_id     integer PRIMARY KEY
                   REFERENCES products (id) ON DELETE CASCADE,
    name           text,
    supplier_id    integer,
    category_group text,
    norm_color     text,
    norm_finish    text,
    norm_size_in   text,
    color_families text[]
);

COMMENT ON TABLE product_facets IS
  'Narrow projection of active products.raw_data facet values. Maintained by '
  'trigger from products; never write to it directly. Exists so facet counts '
  'do not have to scan/detoast the 500 MB products table.';

-- ---------------------------------------------------------------------------
-- 3. Keep it in sync with products.
--    The extraction logic lives in one function used by both the trigger and
--    the initial/rebuild population, so they can never disagree.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION product_facets_sync() RETURNS trigger
LANGUAGE plpgsql AS $$
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
        norm_color, norm_finish, norm_size_in, color_families
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
        END
    )
    ON CONFLICT (product_id) DO UPDATE SET
        name           = EXCLUDED.name,
        supplier_id    = EXCLUDED.supplier_id,
        category_group = EXCLUDED.category_group,
        norm_color     = EXCLUDED.norm_color,
        norm_finish    = EXCLUDED.norm_finish,
        norm_size_in   = EXCLUDED.norm_size_in,
        color_families = EXCLUDED.color_families
    -- Skip the write when nothing a facet cares about actually changed. A
    -- re-scrape usually rewrites raw_data byte-for-byte identically; without
    -- this guard every such write would leave a dead tuple here and bloat the
    -- table and its indexes.
    WHERE (pf.name, pf.supplier_id, pf.category_group, pf.norm_color,
           pf.norm_finish, pf.norm_size_in, pf.color_families)
      IS DISTINCT FROM
          (EXCLUDED.name, EXCLUDED.supplier_id, EXCLUDED.category_group,
           EXCLUDED.norm_color, EXCLUDED.norm_finish, EXCLUDED.norm_size_in,
           EXCLUDED.color_families);

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_product_facets_sync ON products;

-- Fires only when something a facet depends on actually changed, so the common
-- price-scrape UPDATE (current_price, last_scraped_at) costs nothing.
CREATE TRIGGER trg_product_facets_sync
AFTER INSERT OR DELETE OR UPDATE OF raw_data, name, supplier_id, is_active
ON products
FOR EACH ROW EXECUTE FUNCTION product_facets_sync();

-- ---------------------------------------------------------------------------
-- 4. Initial population (idempotent; also usable as a rebuild).
--    Cost: ~108 s. This is a plain read of products, so it does not block the
--    app; it is slow only because it is the one time we must detoast and parse
--    all 166k raw_data documents.
-- ---------------------------------------------------------------------------
INSERT INTO product_facets AS pf (
    product_id, name, supplier_id, category_group,
    norm_color, norm_finish, norm_size_in, color_families
)
SELECT p.id,
       p.name,
       p.supplier_id,
       p.raw_data->>'category_group',
       p.raw_data->'normalized'->>'color',
       p.raw_data->'normalized'->>'finish',
       p.raw_data->'normalized'->>'size_in',
       CASE WHEN jsonb_typeof(p.raw_data->'color_families') = 'array'
            THEN ARRAY(SELECT jsonb_array_elements_text(p.raw_data->'color_families'))
       END
FROM products p
WHERE p.is_active
ON CONFLICT (product_id) DO UPDATE SET
    name           = EXCLUDED.name,
    supplier_id    = EXCLUDED.supplier_id,
    category_group = EXCLUDED.category_group,
    norm_color     = EXCLUDED.norm_color,
    norm_finish    = EXCLUDED.norm_finish,
    norm_size_in   = EXCLUDED.norm_size_in,
    color_families = EXCLUDED.color_families
-- Same change guard as the trigger: makes re-running this migration a no-op
-- write-wise instead of rewriting all 166k rows (which bloated the table from
-- 18 MB to 38 MB the first time it was re-run).
WHERE (pf.name, pf.supplier_id, pf.category_group, pf.norm_color,
       pf.norm_finish, pf.norm_size_in, pf.color_families)
  IS DISTINCT FROM
      (EXCLUDED.name, EXCLUDED.supplier_id, EXCLUDED.category_group,
       EXCLUDED.norm_color, EXCLUDED.norm_finish, EXCLUDED.norm_size_in,
       EXCLUDED.color_families);

-- ---------------------------------------------------------------------------
-- 5. Indexes.
--    The single-column btrees are small (~1.1 MB each) and let the grouped
--    counts run as Index Only Scans with zero heap fetches. Build cost was
--    0.2-5 s each; total index footprint 25 MB.
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS ix_pf_category_group ON product_facets (category_group);
CREATE INDEX IF NOT EXISTS ix_pf_norm_color     ON product_facets (norm_color);
CREATE INDEX IF NOT EXISTS ix_pf_norm_finish    ON product_facets (norm_finish);
CREATE INDEX IF NOT EXISTS ix_pf_norm_size_in   ON product_facets (norm_size_in);
CREATE INDEX IF NOT EXISTS ix_pf_supplier_id    ON product_facets (supplier_id);

-- color_families is multi-valued (an item can be Red AND Green AND Multi-color).
-- GIN supports the containment filter the app needs: color_families @> ARRAY['Red'].
CREATE INDEX IF NOT EXISTS ix_pf_color_families ON product_facets USING GIN (color_families);

-- Keyword-filtered facets (name ILIKE '%moss%') resolve entirely inside this
-- table, so they need their own trigram index; the one on products is not
-- reachable from here.
CREATE INDEX IF NOT EXISTS ix_pf_name_trgm ON product_facets USING GIN (name gin_trgm_ops);

VACUUM (ANALYZE) product_facets;

-- ---------------------------------------------------------------------------
-- 6. products itself was last vacuumed weeks before this migration and only
--    36,890 of its 45,395 pages (81%) were marked all-visible, which degrades
--    every index scan against it. Cheap to fix, and non-blocking. Cost: ~40 s,
--    after which relallvisible = relpages.
-- ---------------------------------------------------------------------------
VACUUM (ANALYZE) products;

-- ---------------------------------------------------------------------------
-- 7. Reference queries — this is the API the app should now use instead of the
--    in-memory facet index. All are single-digit-to-low-hundreds of ms.
--
--   -- one round trip for every facet at once (230 ms unfiltered, 20 ms filtered)
--   SELECT 'category_group' AS facet, category_group AS value, COUNT(*)
--     FROM product_facets GROUP BY 1,2
--   UNION ALL SELECT 'color',  norm_color,   COUNT(*) FROM product_facets GROUP BY 1,2
--   UNION ALL SELECT 'finish', norm_finish,  COUNT(*) FROM product_facets GROUP BY 1,2
--   UNION ALL SELECT 'size_in',norm_size_in, COUNT(*) FROM product_facets GROUP BY 1,2
--   UNION ALL SELECT 'color_family', f, COUNT(*)
--     FROM product_facets, LATERAL unnest(color_families) f GROUP BY 1,2;
--
--   -- multi-valued colour family filter ("show me everything Red"), 1.3 ms
--   SELECT COUNT(*) FROM product_facets WHERE color_families @> ARRAY['Red'];
--
--   -- add any keyword filter to any of the above; it gets FASTER, not slower
--   ... WHERE name ILIKE '%moss%'
--
-- NOTE for whoever wires this up: product_facets contains ACTIVE products only,
-- so do not add `WHERE is_active` — that column is not here and the filter is
-- already applied. Join back to products on product_id when you need price,
-- photo_url, etc.
-- ---------------------------------------------------------------------------
