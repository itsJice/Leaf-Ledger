-- Scheduling restrictions on the client (Comments #23).
--
-- Free text about when a client can and can't take an install ("no Fridays",
-- "gate closes at 3 PM", "call before arriving"). Shown on the client page's
-- 2026 Install panel and as a badge on the Install Schedule's stop card and
-- popup. Client-level, not per season: it rarely changes year to year.
--
-- Nobody runs this by hand: app/apis/clients ensure_schema() adds the column
-- on first use (RESTRICTIONS_DDL). This file is the record.
--
-- The season's contact log needs no DDL: it is a JSON list in
-- client_activity.detail ("contact_log"), validated by
-- app/libs/client_season.py and appended through
-- POST /api/clients/{id}/seasons/{season}/contacts.

ALTER TABLE clients ADD COLUMN IF NOT EXISTS schedule_restrictions text;
