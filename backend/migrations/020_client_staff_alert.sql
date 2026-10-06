-- Staff alert on a client: one short warning ("dog in the yard -- call
-- before opening the gate", "owner disputes last invoice") flagged with an
-- amber icon next to the client's name on the Clients tab, the install
-- schedule, the leads' Shifts page and printed crew sheets. Set from
-- PUT /api/clients/{id}/staff-alert (staff and up); signed and dated.
--
-- The app adds these columns itself on first use (app.apis.clients
-- ensure_schema) -- nobody has to run this file. Kept here so a rebuilt
-- database has the record.

ALTER TABLE clients
    ADD COLUMN IF NOT EXISTS staff_alert TEXT,
    ADD COLUMN IF NOT EXISTS staff_alert_by TEXT,
    ADD COLUMN IF NOT EXISTS staff_alert_at TIMESTAMPTZ;
