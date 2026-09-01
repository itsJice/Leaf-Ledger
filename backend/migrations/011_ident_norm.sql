-- Punctuation-blind vendor style numbers.
--
-- Style numbers are searchable today only if you type the separators exactly as
-- the vendor stored them. The catalog holds B1670-BU, ROT.20.TA, X1923/75 and
-- N592522DCV; ~33k of 166k active products carry a separator (17.7k dots,
-- 13.8k hyphens, plus slashes and spaces). Typing B1670BU, ROT20TA or
-- N592522-DCV returns nothing, and it fails in both directions -- adding a
-- separator the catalog lacks breaks just as surely as omitting one it has.
--
-- ident_norm holds the same identifiers with every non-alphanumeric character
-- removed, so the query can strip the user's spelling the same way and compare
-- like for like. This is normalisation, not fuzzy matching: b1670bu and
-- B1670-BU are the same product, whereas N592522DCV and N592522DA are
-- different colours of one. Only the first kind is safe to merge silently.

-- ---------------------------------------------------------------------------
-- 1. The column
-- ---------------------------------------------------------------------------
ALTER TABLE product_facets
  ADD COLUMN IF NOT EXISTS ident_norm text;

-- ---------------------------------------------------------------------------
-- 2. How it is built
-- ---------------------------------------------------------------------------
-- Every identifier a buyer might quote, not just supplier_sku: upc appears on
-- 35% of products and master_sku / base_sku / item_code on the rest of the
-- long tail. Tokens stay space-separated so one identifier cannot bleed into
-- the next and invent a match that spans two of them.
CREATE OR REPLACE FUNCTION public.product_facets_ident(p products)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT NULLIF(
    regexp_replace(
      lower(concat_ws(' ',
        p.supplier_sku,
        p.raw_data->>'sku',
        p.raw_data->>'upc',
        p.raw_data->>'master_sku',
        p.raw_data->>'base_sku',
        p.raw_data->>'item_code'
      )),
      '[^a-z0-9 ]', '', 'g'
    ), '');
$$;

-- ---------------------------------------------------------------------------
-- 3. Teach the sync trigger about it
-- ---------------------------------------------------------------------------
-- Same body as migrations/007, with ident_norm threaded through the INSERT,
-- the DO UPDATE and the IS DISTINCT FROM guard. That guard is what stops a
-- re-scrape that rewrites raw_data identically from leaving a dead tuple
-- behind on every row, so ident_norm has to be inside it too.
CREATE OR REPLACE FUNCTION public.product_facets_sync()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    IF TG_OP = 'DELETE' THEN
        DELETE FROM product_facets WHERE product_id = OLD.id;
        RETURN OLD;
    END IF;

    IF NEW.is_active IS NOT TRUE THEN
        DELETE FROM product_facets WHERE product_id = NEW.id;
        RETURN NEW;
    END IF;

    INSERT INTO product_facets AS pf (
        product_id, name, supplier_id, category_group,
        norm_color, norm_finish, norm_size_in, color_families,
        search_blob, product_type, availability, ident_norm
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
        NEW.availability,
        public.product_facets_ident(NEW)
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
        availability   = EXCLUDED.availability,
        ident_norm     = EXCLUDED.ident_norm
    WHERE (pf.name, pf.supplier_id, pf.category_group, pf.norm_color,
           pf.norm_finish, pf.norm_size_in, pf.color_families,
           pf.search_blob, pf.product_type, pf.availability, pf.ident_norm)
      IS DISTINCT FROM
          (EXCLUDED.name, EXCLUDED.supplier_id, EXCLUDED.category_group,
           EXCLUDED.norm_color, EXCLUDED.norm_finish, EXCLUDED.norm_size_in,
           EXCLUDED.color_families, EXCLUDED.search_blob,
           EXCLUDED.product_type, EXCLUDED.availability, EXCLUDED.ident_norm);

    RETURN NEW;
END;
$function$;

-- ---------------------------------------------------------------------------
-- 4. Index
-- ---------------------------------------------------------------------------
-- Trigram, matching ix_pf_search_blob_trgm: the query is a LIKE '%...%', which
-- no btree can serve. CONCURRENTLY so the live app keeps reading; must run
-- outside a transaction block.
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_pf_ident_norm_trgm
  ON product_facets USING GIN (ident_norm gin_trgm_ops);

-- ---------------------------------------------------------------------------
-- 5. Backfill
-- ---------------------------------------------------------------------------
-- Batched by scripts/backfill_ident_norm.py, not here -- a single UPDATE over
-- 166k rows holds one transaction open long enough to bloat the table.
