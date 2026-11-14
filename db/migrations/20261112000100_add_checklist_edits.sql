-- migrate:up
CREATE TABLE checklist_edits (
    id uuid PRIMARY KEY,
    provider_id uuid NOT NULL,
    requirement_id uuid NOT NULL,
    requirement_name text NOT NULL CHECK (btrim(requirement_name) <> ''),
    expected_version integer NOT NULL CHECK (expected_version >= 0),
    resulting_version integer NOT NULL CHECK (resulting_version = expected_version + 1),
    previous_status text NOT NULL CHECK (btrim(previous_status) <> ''),
    previous_scheduled_date date,
    previous_deadline date,
    applied_status text NOT NULL CHECK (btrim(applied_status) <> ''),
    applied_scheduled_date date,
    applied_deadline date,
    reviewer_role text NOT NULL CHECK (reviewer_role = 'manager'),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    FOREIGN KEY (requirement_id, provider_id) REFERENCES requirements(id, provider_id),
    CHECK (ROW(previous_status,previous_scheduled_date,previous_deadline)
        IS DISTINCT FROM ROW(applied_status,applied_scheduled_date,applied_deadline))
);
CREATE INDEX checklist_edits_provider_created ON checklist_edits(provider_id,created_at,id);
CREATE FUNCTION preserve_checklist_edit() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Checklist edit history is immutable.';
END;
$$;
CREATE TRIGGER preserve_checklist_edit BEFORE UPDATE OR DELETE ON checklist_edits
    FOR EACH ROW EXECUTE FUNCTION preserve_checklist_edit();

-- migrate:down
DROP TABLE checklist_edits;
DROP FUNCTION preserve_checklist_edit();
