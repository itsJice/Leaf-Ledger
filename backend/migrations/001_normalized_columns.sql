-- Phase 3 foundation: promote raw_data.normalized -> indexed columns for fast,
-- versatile catalog search. Run ONCE as the DB owner (Neon SQL console or the
-- neondb_owner role). The app role is DML-only, so it can't run this itself.
--
-- Fully ADDITIVE: only adds columns/indexes/extensions; touches no existing data.
-- After running, re-run backfill_norm_to_db.py with --columns to populate them
-- (it already computes the values; a flag switches the write target to columns).

-- 1) fuzzy search + trigram indexes
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 2) normalized attribute columns (mirror raw_data.normalized)
ALTER TABLE products
  ADD COLUMN IF NOT EXISTS norm_class      text,
  ADD COLUMN IF NOT EXISTS norm_size_in    numeric,
  ADD COLUMN IF NOT EXISTS norm_color      text,
  ADD COLUMN IF NOT EXISTS norm_finish     text,
  ADD COLUMN IF NOT EXISTS norm_pack_qty   integer,
  ADD COLUMN IF NOT EXISTS canonical_key   text,
  ADD COLUMN IF NOT EXISTS norm_confidence numeric,
  ADD COLUMN IF NOT EXISTS needs_review    boolean;

-- 3) one-time copy from the JSONB already backfilled by backfill_norm_to_db.py
UPDATE products SET
  norm_class      = raw_data->'normalized'->>'class',
  norm_size_in    = NULLIF(raw_data->'normalized'->>'size_in','')::numeric,
  norm_color      = raw_data->'normalized'->>'color',
  norm_finish     = raw_data->'normalized'->>'finish',
  norm_pack_qty   = NULLIF(raw_data->'normalized'->>'pack_qty','')::int,
  canonical_key   = raw_data->'normalized'->>'canonical_key',
  norm_confidence = NULLIF(raw_data->'normalized'->>'confidence','')::numeric,
  needs_review    = (raw_data->'normalized'->>'needs_review')::boolean
WHERE raw_data ? 'normalized';

-- 4) indexes for the search facets
CREATE INDEX IF NOT EXISTS idx_products_norm_class    ON products(norm_class);
CREATE INDEX IF NOT EXISTS idx_products_norm_color    ON products(norm_color);
CREATE INDEX IF NOT EXISTS idx_products_norm_finish   ON products(norm_finish);
CREATE INDEX IF NOT EXISTS idx_products_norm_size     ON products(norm_size_in);
CREATE INDEX IF NOT EXISTS idx_products_canonical_key ON products(canonical_key);
-- fuzzy keyword search on name
CREATE INDEX IF NOT EXISTS idx_products_name_trgm     ON products USING gin (name gin_trgm_ops);

-- 5) let the app role read/write the new columns (adjust role name if different)
-- GRANT SELECT, UPDATE ON products TO app;
