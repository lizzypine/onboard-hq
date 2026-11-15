-- migrate:up
-- Shared catalog rows are restricted; provider-owned records cascade.
ALTER TABLE requirement_templates
    DROP CONSTRAINT requirement_templates_provider_type_id_fkey,
    ADD CONSTRAINT requirement_templates_provider_type_id_fkey
        FOREIGN KEY (provider_type_id) REFERENCES provider_types(id)
        ON DELETE RESTRICT;

ALTER TABLE providers
    DROP CONSTRAINT providers_provider_type_id_fkey,
    ADD CONSTRAINT providers_provider_type_id_fkey
        FOREIGN KEY (provider_type_id) REFERENCES provider_types(id)
        ON DELETE RESTRICT;

ALTER TABLE requirements
    DROP CONSTRAINT requirements_provider_id_provider_type_id_fkey,
    ADD CONSTRAINT requirements_provider_id_provider_type_id_fkey
        FOREIGN KEY (provider_id, provider_type_id) REFERENCES providers(id, provider_type_id)
        ON DELETE CASCADE;

ALTER TABLE requirements
    DROP CONSTRAINT requirements_source_template_id_provider_type_id_fkey,
    ADD CONSTRAINT requirements_source_template_id_provider_type_id_fkey
        FOREIGN KEY (source_template_id, provider_type_id) REFERENCES requirement_templates(id, provider_type_id)
        ON DELETE RESTRICT;

ALTER TABLE updates
    DROP CONSTRAINT updates_provider_id_fkey,
    ADD CONSTRAINT updates_provider_id_fkey
        FOREIGN KEY (provider_id) REFERENCES providers(id)
        ON DELETE CASCADE;

ALTER TABLE suggestions
    DROP CONSTRAINT suggestions_update_id_provider_id_fkey,
    ADD CONSTRAINT suggestions_update_id_provider_id_fkey
        FOREIGN KEY (update_id, provider_id) REFERENCES updates(id, provider_id)
        ON DELETE CASCADE;

ALTER TABLE suggestions
    DROP CONSTRAINT suggestions_requirement_id_provider_id_fkey,
    ADD CONSTRAINT suggestions_requirement_id_provider_id_fkey
        FOREIGN KEY (requirement_id, provider_id) REFERENCES requirements(id, provider_id)
        ON DELETE CASCADE;

ALTER TABLE review_decisions
    DROP CONSTRAINT review_decisions_suggestion_id_fkey,
    ADD CONSTRAINT review_decisions_suggestion_id_fkey
        FOREIGN KEY (suggestion_id) REFERENCES suggestions(id)
        ON DELETE CASCADE;

ALTER TABLE checklist_edits
    DROP CONSTRAINT checklist_edits_requirement_id_provider_id_fkey,
    ADD CONSTRAINT checklist_edits_requirement_id_provider_id_fkey
        FOREIGN KEY (requirement_id, provider_id) REFERENCES requirements(id, provider_id)
        ON DELETE CASCADE;

CREATE OR REPLACE FUNCTION preserve_checklist_edit() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    -- A missing provider identifies its cascading deletion in this transaction.
    IF TG_OP = 'DELETE' AND NOT EXISTS (
        SELECT 1 FROM providers WHERE id = OLD.provider_id
    ) THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'Checklist edit history is immutable.';
END;
$$;

-- migrate:down
-- Restore the original blocking policy and unconditional history protection.
ALTER TABLE requirement_templates
    DROP CONSTRAINT requirement_templates_provider_type_id_fkey,
    ADD CONSTRAINT requirement_templates_provider_type_id_fkey
        FOREIGN KEY (provider_type_id) REFERENCES provider_types(id)
        ON DELETE NO ACTION;

ALTER TABLE providers
    DROP CONSTRAINT providers_provider_type_id_fkey,
    ADD CONSTRAINT providers_provider_type_id_fkey
        FOREIGN KEY (provider_type_id) REFERENCES provider_types(id)
        ON DELETE NO ACTION;

ALTER TABLE requirements
    DROP CONSTRAINT requirements_provider_id_provider_type_id_fkey,
    ADD CONSTRAINT requirements_provider_id_provider_type_id_fkey
        FOREIGN KEY (provider_id, provider_type_id) REFERENCES providers(id, provider_type_id)
        ON DELETE NO ACTION;

ALTER TABLE requirements
    DROP CONSTRAINT requirements_source_template_id_provider_type_id_fkey,
    ADD CONSTRAINT requirements_source_template_id_provider_type_id_fkey
        FOREIGN KEY (source_template_id, provider_type_id) REFERENCES requirement_templates(id, provider_type_id)
        ON DELETE NO ACTION;

ALTER TABLE updates
    DROP CONSTRAINT updates_provider_id_fkey,
    ADD CONSTRAINT updates_provider_id_fkey
        FOREIGN KEY (provider_id) REFERENCES providers(id)
        ON DELETE NO ACTION;

ALTER TABLE suggestions
    DROP CONSTRAINT suggestions_update_id_provider_id_fkey,
    ADD CONSTRAINT suggestions_update_id_provider_id_fkey
        FOREIGN KEY (update_id, provider_id) REFERENCES updates(id, provider_id)
        ON DELETE NO ACTION;

ALTER TABLE suggestions
    DROP CONSTRAINT suggestions_requirement_id_provider_id_fkey,
    ADD CONSTRAINT suggestions_requirement_id_provider_id_fkey
        FOREIGN KEY (requirement_id, provider_id) REFERENCES requirements(id, provider_id)
        ON DELETE NO ACTION;

ALTER TABLE review_decisions
    DROP CONSTRAINT review_decisions_suggestion_id_fkey,
    ADD CONSTRAINT review_decisions_suggestion_id_fkey
        FOREIGN KEY (suggestion_id) REFERENCES suggestions(id)
        ON DELETE NO ACTION;

ALTER TABLE checklist_edits
    DROP CONSTRAINT checklist_edits_requirement_id_provider_id_fkey,
    ADD CONSTRAINT checklist_edits_requirement_id_provider_id_fkey
        FOREIGN KEY (requirement_id, provider_id) REFERENCES requirements(id, provider_id)
        ON DELETE NO ACTION;

CREATE OR REPLACE FUNCTION preserve_checklist_edit() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Checklist edit history is immutable.';
END;
$$;
