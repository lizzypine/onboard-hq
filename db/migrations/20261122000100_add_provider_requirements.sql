-- migrate:up

-- One row stores one provider's progress on a standard or provider-only requirement.
ALTER TABLE requirements
    ALTER COLUMN checklist_template_id DROP NOT NULL,
    ADD COLUMN initial_status text,
    ADD COLUMN initial_scheduled_date date,
    ADD COLUMN initial_deadline date,
    ADD CONSTRAINT requirements_provider_owner
        FOREIGN KEY (provider_id) REFERENCES providers(id) ON DELETE CASCADE,
    ADD CONSTRAINT requirements_definition_owner
        FOREIGN KEY (requirement_definition_id) REFERENCES requirement_definitions(id) ON DELETE RESTRICT,
    ADD CONSTRAINT requirements_initial_values CHECK (
        (checklist_template_id IS NOT NULL AND initial_status IS NULL
            AND initial_scheduled_date IS NULL AND initial_deadline IS NULL)
        OR (checklist_template_id IS NULL AND initial_status IS NOT NULL
            AND btrim(initial_status) <> '')
    );

-- The existing provider/definition unique index and definition index cover the new foreign keys.
COMMENT ON TABLE requirements IS 'One row stores one provider''s progress on a standard or provider-only requirement.';

CREATE OR REPLACE FUNCTION preserve_requirement_owner() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF ROW(NEW.id,NEW.provider_id,NEW.checklist_template_id,NEW.requirement_definition_id,
           NEW.initial_status,NEW.initial_scheduled_date,NEW.initial_deadline)
        IS DISTINCT FROM ROW(OLD.id,OLD.provider_id,OLD.checklist_template_id,OLD.requirement_definition_id,
                             OLD.initial_status,OLD.initial_scheduled_date,OLD.initial_deadline) THEN
        RAISE EXCEPTION 'Requirement ownership, origin, and initial values are fixed.';
    END IF;
    RETURN NEW;
END;
$$;

-- migrate:down
