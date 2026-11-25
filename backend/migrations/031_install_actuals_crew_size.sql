-- Crew size on Install Times (2026-11-25): estimates assume a full crew, and
-- short crews run long. For the rest of the 2026 season each stop visit also
-- records ladders or lifts used and whether the crew was short, next to the
-- existing people_count (prefilled from the crew-day's staffing). Job makeup
-- comes from the client card. Data collection only: no model reads these yet.
--
-- Both nullable: NULL means "not entered". short_crew false means the office
-- said the crew was full. Corrections keep history like the times do (a new
-- row with supersedes_id). The latest view is re-created so SELECT a.*
-- picks up the new columns (Postgres expands * when a view is created).
--
-- The app applies this itself on first use
-- (app.apis.install_actuals.ensure_schema, key "install_actuals_crew_size",
-- after checking information_schema, with lock_timeout 5s); this file is the
-- record. Nobody runs it by hand.
ALTER TABLE ll_app.install_actuals
    ADD COLUMN IF NOT EXISTS ladders integer CHECK (ladders IS NULL OR ladders BETWEEN 0 AND 20),
    ADD COLUMN IF NOT EXISTS short_crew boolean;

CREATE OR REPLACE VIEW ll_app.install_actuals_latest AS
    SELECT a.*
      FROM ll_app.install_actuals a
     WHERE NOT EXISTS (SELECT 1 FROM ll_app.install_actuals b WHERE b.supersedes_id = a.id);
