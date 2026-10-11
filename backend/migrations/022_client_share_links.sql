-- Client share links: a client group's private, read-only install schedule
-- (app/apis/client_share), e.g. M Crowd's 25 Dallas locations.
--
--   token         256-bit random (secrets.token_urlsafe(32)); the URL secret
--   label         who it is for ("M Crowd"); names the subscribed calendar
--   name_prefix   board client names starting with this, any case ("M Crowd ")
--   client_ids    and/or these app client ids
--   strip_prefix  removed from the front of each shown location name
--   revoked       true = every URL for it 404s; final
--
-- The app creates this itself on first use (ensure_schema_once); this file
-- is the record.
CREATE SCHEMA IF NOT EXISTS ll_app;
CREATE TABLE IF NOT EXISTS ll_app.client_share_links (
    id           bigserial PRIMARY KEY,
    token        text NOT NULL UNIQUE,
    label        text NOT NULL,
    name_prefix  text NOT NULL DEFAULT '',
    client_ids   integer[] NOT NULL DEFAULT '{}',
    strip_prefix text NOT NULL DEFAULT '',
    revoked      boolean NOT NULL DEFAULT false,
    revoked_at   timestamptz,
    revoked_by   text,
    created_by   text,
    created_at   timestamptz NOT NULL DEFAULT now()
);
