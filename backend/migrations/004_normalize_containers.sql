-- Phase 0 — normalize the arrangement/container data model.
--
-- Why: built products ("designs") AND rooms were both crammed into
-- `arrangement_containers`, with their real fields JSON-encoded into the
-- `label` TEXT column behind two prefixes:
--
--   label = 'LL_ROOM:{"name":...,"notes":...}'                 -> actually a ROOM
--   label = 'LL_SCOPE:{"label":...,"room_id":...,"bucket_type":...,
--                      "requested_quantity":...,"scope_notes":...}'  -> a DESIGN
--
-- while the real `bucket_type` / `room_id` / `requested_quantity` /
-- `scope_notes` columns sat NULL on every single row. The encoded `room_id`
-- inside LL_SCOPE pointed at the *pseudo-container* id of the LL_ROOM row, not
-- at `project_rooms.id`, so nothing could be joined and nothing could be
-- indexed. `/api/designs` cannot be built on top of that.
--
-- After this migration:
--   * a row in `arrangement_containers` is ALWAYS a design (never a room);
--   * rooms live in `project_rooms`, and `arrangement_containers.room_id` is a
--     real FK into it;
--   * `label`, `bucket_type`, `build_type`, `requested_quantity`, `scope_notes`
--     are real columns, so the designs API reads columns, not JSON-in-a-string.
--
-- NOTE ON `scope_notes`: it may embed a `LL_BUILD_INTELLIGENCE:{...}` JSON blob
-- on its own line (see app/apis/recipe_intelligence). It is copied VERBATIM.
-- Never rewrite or re-wrap it.
--
-- The DDL below is idempotent. The row-level rewrite is done by the companion
-- script, which is also idempotent and dry-run by default:
--
--     backend/.venv/bin/python scripts/normalize_containers.py            # dry run
--     backend/.venv/bin/python scripts/normalize_containers.py --commit   # write
--
-- The script is the authoritative implementation: it does the LL_ROOM ->
-- project_rooms move and, critically, RE-POINTS every design's room reference
-- from the old pseudo-container id to the new project_rooms id BEFORE the
-- pseudo-container row is deleted. That re-pointing cannot be expressed safely
-- in plain SQL because the mapping only exists inside the encoded label.

-- ---------------------------------------------------------------------------
-- 1. Columns
-- ---------------------------------------------------------------------------

-- Rooms table (already created at runtime by ensure_project_schema, repeated
-- here so a fresh database can be built from migrations alone).
CREATE TABLE IF NOT EXISTS project_rooms (
    id             SERIAL PRIMARY KEY,
    arrangement_id INTEGER NOT NULL REFERENCES arrangements(id) ON DELETE CASCADE,
    name           TEXT NOT NULL,
    notes          TEXT,
    sort_order     INTEGER NOT NULL DEFAULT 0,
    created_at     TIMESTAMP DEFAULT NOW(),
    updated_at     TIMESTAMP DEFAULT NOW()
);

ALTER TABLE arrangement_containers
    ADD COLUMN IF NOT EXISTS bucket_type        TEXT,
    ADD COLUMN IF NOT EXISTS requested_quantity INTEGER NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS scope_notes        TEXT,
    ADD COLUMN IF NOT EXISTS room_id            INTEGER REFERENCES project_rooms(id) ON DELETE SET NULL,
    -- New in this migration:
    --   build_type      the design taxonomy ("Tree", "Wreath", "Christmas Tree",
    --                   ...). Seeded from bucket_type; bucket_type is kept as the
    --                   legacy alias so nothing that reads it breaks.
    --   status          lifecycle of the built product. 'draft' until a human
    --                   marks it otherwise.
    --   hero_image_url  stays NULL for now. The UI falls back to a type icon;
    --                   AI mockups fill this in later.
    ADD COLUMN IF NOT EXISTS build_type         TEXT,
    ADD COLUMN IF NOT EXISTS status             TEXT NOT NULL DEFAULT 'draft',
    ADD COLUMN IF NOT EXISTS hero_image_url     TEXT;

-- ---------------------------------------------------------------------------
-- 2. Indexes the designs API will lean on
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS arrangement_containers_arrangement_idx
    ON arrangement_containers (arrangement_id, sort_order);
CREATE INDEX IF NOT EXISTS arrangement_containers_room_idx
    ON arrangement_containers (room_id);
CREATE INDEX IF NOT EXISTS arrangement_containers_build_type_idx
    ON arrangement_containers (build_type);
CREATE INDEX IF NOT EXISTS project_rooms_arrangement_idx
    ON project_rooms (arrangement_id, sort_order);

-- ---------------------------------------------------------------------------
-- 3. Backfill that IS safe in plain SQL
-- ---------------------------------------------------------------------------

-- Any row that already had a real bucket_type gets a build_type to match.
UPDATE arrangement_containers
   SET build_type = bucket_type
 WHERE build_type IS NULL
   AND bucket_type IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 4. Row rewrite — run the script
-- ---------------------------------------------------------------------------
-- Decoding LL_SCOPE / LL_ROOM and re-pointing room references is done by
-- backend/scripts/normalize_containers.py (dry-run by default, --commit to
-- write). Run it after applying this file.
--
-- Post-conditions the script verifies:
--   * 0 rows in arrangement_containers with label LIKE 'LL_ROOM:%'
--   * 0 rows in arrangement_containers with label LIKE 'LL_SCOPE:%'
--   * every design that had an encoded room_id resolves to a live
--     project_rooms row in the SAME arrangement
--   * every design has a non-null bucket_type/build_type
