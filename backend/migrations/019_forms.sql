-- Forms: the Product Purchase Request Form (and any later form) built in,
-- replacing the team's Google Form and its responses Sheet.
--
-- forms / form_sections / form_questions hold the form itself (data, not
-- code), form_responses + form_answers the submissions. The API
-- (backend/app/apis/forms) creates these on first use with the identical DDL
-- and seeds the Product Request form from app/libs/forms.py; this file is the
-- record, so a rebuilt database gets the same tables.
--
-- product_request_items.form_response_id links each submission to the item
-- it was filed as on an open request, which the Jobs page's "Load a request"
-- picker reads.

CREATE SCHEMA IF NOT EXISTS ll_app;

CREATE TABLE IF NOT EXISTS ll_app.forms (
    id            serial PRIMARY KEY,
    slug          text NOT NULL UNIQUE,
    title         text NOT NULL,
    description   text,
    is_accepting  boolean NOT NULL DEFAULT true,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ll_app.form_sections (
    id           serial PRIMARY KEY,
    form_id      integer NOT NULL REFERENCES ll_app.forms(id) ON DELETE CASCADE,
    position     integer NOT NULL,
    title        text NOT NULL,
    description  text
);

CREATE TABLE IF NOT EXISTS ll_app.form_questions (
    id               serial PRIMARY KEY,
    form_id          integer NOT NULL REFERENCES ll_app.forms(id) ON DELETE CASCADE,
    section_id       integer NOT NULL REFERENCES ll_app.form_sections(id) ON DELETE CASCADE,
    position         integer NOT NULL,
    key              text NOT NULL,
    label            text NOT NULL,
    helper_text      text,
    type             text NOT NULL CHECK (type IN ('short_text','long_text','dropdown','radio','checkboxes','date')),
    required         boolean NOT NULL DEFAULT false,
    options          jsonb,
    export_position  integer,
    UNIQUE (form_id, key)
);

CREATE TABLE IF NOT EXISTS ll_app.form_responses (
    id            serial PRIMARY KEY,
    form_id       integer NOT NULL REFERENCES ll_app.forms(id) ON DELETE CASCADE,
    submitted_at  timestamptz NOT NULL DEFAULT now(),
    status        text NOT NULL DEFAULT 'New' CHECK (status IN ('New','Ordered','Received','Cancelled')),
    buyer_notes   text,
    submitted_by  text,
    source        text NOT NULL DEFAULT 'app',
    updated_at    timestamptz NOT NULL DEFAULT now(),
    updated_by    text
);
CREATE INDEX IF NOT EXISTS form_responses_form_idx ON ll_app.form_responses (form_id, submitted_at);

CREATE TABLE IF NOT EXISTS ll_app.form_answers (
    response_id  integer NOT NULL REFERENCES ll_app.form_responses(id) ON DELETE CASCADE,
    question_id  integer NOT NULL REFERENCES ll_app.form_questions(id) ON DELETE CASCADE,
    value        jsonb,
    PRIMARY KEY (response_id, question_id)
);

ALTER TABLE ll_app.product_request_items ADD COLUMN IF NOT EXISTS form_response_id integer;
