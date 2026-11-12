-- migrate:up
CREATE TABLE provider_types (
    id uuid PRIMARY KEY,
    name text NOT NULL UNIQUE CHECK (btrim(name) <> '')
);
CREATE TABLE requirement_templates (
    id uuid PRIMARY KEY,
    provider_type_id uuid NOT NULL REFERENCES provider_types(id),
    name text NOT NULL CHECK (btrim(name) <> ''),
    UNIQUE (provider_type_id, name), UNIQUE (id, provider_type_id)
);
CREATE TABLE providers (
    id uuid PRIMARY KEY,
    provider_type_id uuid NOT NULL REFERENCES provider_types(id),
    name text NOT NULL CHECK (btrim(name) <> ''),
    proposed_start_date date,
    UNIQUE (id, provider_type_id)
);
CREATE TABLE requirements (
    id uuid PRIMARY KEY,
    provider_id uuid NOT NULL,
    provider_type_id uuid NOT NULL,
    source_template_id uuid,
    name text NOT NULL CHECK (btrim(name) <> ''),
    status text NOT NULL CHECK (btrim(status) <> ''),
    deadline date, scheduled_date date,
    version integer NOT NULL DEFAULT 0 CHECK (version >= 0),
    FOREIGN KEY (provider_id, provider_type_id) REFERENCES providers(id, provider_type_id),
    FOREIGN KEY (source_template_id, provider_type_id) REFERENCES requirement_templates(id, provider_type_id),
    UNIQUE (provider_id, name), UNIQUE (id, provider_id)
);
CREATE TABLE updates (
    id uuid PRIMARY KEY, request_id uuid NOT NULL UNIQUE,
    provider_id uuid NOT NULL REFERENCES providers(id),
    original_text text NOT NULL CHECK (btrim(original_text) <> ''),
    provider_snapshot jsonb NOT NULL CHECK (jsonb_typeof(provider_snapshot) = 'object'),
    processing_state text NOT NULL CHECK (processing_state IN ('processing', 'completed', 'failed')),
    message text NOT NULL,
    ambiguities jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(ambiguities) = 'array'),
    failure_category text CHECK (failure_category IN ('configuration', 'timeout', 'model')),
    created_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz,
    UNIQUE (id, provider_id),
    CHECK ((processing_state = 'failed') = (failure_category IS NOT NULL))
);
CREATE INDEX updates_provider_created ON updates(provider_id, created_at, id);
CREATE TABLE suggestions (
    id uuid PRIMARY KEY, update_id uuid NOT NULL, requirement_id uuid NOT NULL, provider_id uuid NOT NULL,
    requirement_version integer NOT NULL CHECK (requirement_version >= 0),
    proposed_status text NOT NULL CHECK (btrim(proposed_status) <> ''),
    proposed_date date, supporting_text text NOT NULL,
    date_text text, date_inferred boolean NOT NULL DEFAULT false,
    date_explanation text, date_requires_confirmation boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (update_id, provider_id) REFERENCES updates(id, provider_id),
    FOREIGN KEY (requirement_id, provider_id) REFERENCES requirements(id, provider_id)
);
CREATE INDEX suggestions_update ON suggestions(update_id);
CREATE INDEX suggestions_requirement ON suggestions(requirement_id);
CREATE TABLE review_decisions (
    id uuid PRIMARY KEY,
    suggestion_id uuid NOT NULL UNIQUE REFERENCES suggestions(id),
    outcome text NOT NULL CHECK (outcome IN ('approved', 'corrected', 'rejected')),
    previous_status text NOT NULL CHECK (btrim(previous_status) <> ''), previous_scheduled_date date,
    applied_status text CHECK (applied_status IS NULL OR btrim(applied_status) <> ''), applied_scheduled_date date,
    reviewer_role text NOT NULL CHECK (reviewer_role = 'manager'),
    reviewed_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((outcome = 'rejected' AND applied_status IS NULL AND applied_scheduled_date IS NULL)
       OR (outcome <> 'rejected' AND applied_status IS NOT NULL))
);

-- migrate:down
DROP TABLE review_decisions;
DROP TABLE suggestions;
DROP TABLE updates;
DROP TABLE requirements;
DROP TABLE providers;
DROP TABLE requirement_templates;
DROP TABLE provider_types;
