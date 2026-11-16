-- migrate:up
-- One transaction: old workers must be stopped; restore the final backup to roll back.
LOCK TABLE provider_types, requirement_templates, providers, requirements,
    updates, suggestions, review_decisions, checklist_edits IN ACCESS EXCLUSIVE MODE;

-- Reject information that the normalized model cannot faithfully represent.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM requirements GROUP BY provider_id,lower(btrim(name)) HAVING count(*) > 1) THEN
        RAISE EXCEPTION 'Preflight: duplicate normalized requirement names within a provider; resolve before retrying.';
    END IF;
    IF EXISTS (
        SELECT 1 FROM provider_types a JOIN provider_types b
          ON lower(btrim(a.name))=lower(btrim(b.name)) AND a.id<b.id
        WHERE ARRAY(SELECT DISTINCT lower(btrim(name)) FROM requirement_templates WHERE provider_type_id=a.id ORDER BY 1)
           <> ARRAY(SELECT DISTINCT lower(btrim(name)) FROM requirement_templates WHERE provider_type_id=b.id ORDER BY 1)
    ) THEN
        RAISE EXCEPTION 'Preflight: normalized provider types have conflicting catalogs.';
    END IF;
    IF EXISTS (
        SELECT 1 FROM updates u JOIN providers p ON p.id=u.provider_id
        JOIN provider_types t ON t.id=p.provider_type_id
        WHERE NOT (u.provider_snapshot ?& ARRAY['id','name','provider_type','proposed_start_date','requirements'])
           OR (u.provider_snapshot->>'id') IS DISTINCT FROM p.id::text
           OR (u.provider_snapshot->>'name') IS DISTINCT FROM p.name
           OR lower(btrim(u.provider_snapshot->>'provider_type')) IS DISTINCT FROM lower(btrim(t.name))
           OR (u.provider_snapshot->>'proposed_start_date')::date IS DISTINCT FROM p.proposed_start_date
           OR jsonb_typeof(u.provider_snapshot->'requirements') IS DISTINCT FROM 'array'
           OR EXISTS (SELECT 1 FROM jsonb_object_keys(u.provider_snapshot) k
                      WHERE k <> ALL(ARRAY['id','name','provider_type','proposed_start_date','requirements']))
    ) THEN
        RAISE EXCEPTION 'Preflight: invalid or changed captured provider profile.';
    END IF;
    IF EXISTS (
        SELECT 1 FROM updates u CROSS JOIN LATERAL jsonb_array_elements(u.ambiguities) w
        WHERE jsonb_typeof(w) <> 'string' OR btrim(w #>> '{}')=''
    ) THEN
        RAISE EXCEPTION 'Preflight: invalid or blank ambiguity message.';
    END IF;
    IF EXISTS (
        SELECT 1 FROM updates u CROSS JOIN LATERAL jsonb_array_elements(u.provider_snapshot->'requirements') s
        LEFT JOIN requirements r ON r.id=(s->>'id')::uuid AND r.provider_id=u.provider_id
        WHERE r.id IS NULL
           OR NOT (s ?& ARRAY['id','provider_id','name','status','deadline','scheduled_date','version'])
           OR (s->>'provider_id') IS DISTINCT FROM u.provider_id::text
           OR lower(btrim(s->>'name')) IS DISTINCT FROM lower(btrim(r.name))
           OR jsonb_typeof(s->'status') IS DISTINCT FROM 'string' OR btrim(s->>'status')=''
           OR jsonb_typeof(s->'version') IS DISTINCT FROM 'number'
           OR (s->>'version') !~ '^[0-9]+$'
           OR EXISTS (SELECT 1 FROM jsonb_object_keys(s) k WHERE k <> ALL(ARRAY[
               'id','provider_id','source_template_id','name','status','deadline','scheduled_date','version']))
    ) THEN
        RAISE EXCEPTION 'Preflight: invalid captured requirement or missing historical parent.';
    END IF;
    IF EXISTS (
        SELECT 1 FROM updates u
        WHERE (SELECT count(*) FROM requirements r WHERE r.provider_id=u.provider_id)
           <> (SELECT count(DISTINCT s->>'id') FROM jsonb_array_elements(u.provider_snapshot->'requirements') s)
           OR jsonb_array_length(u.provider_snapshot->'requirements')
           <> (SELECT count(DISTINCT s->>'id') FROM jsonb_array_elements(u.provider_snapshot->'requirements') s)
    ) THEN
        RAISE EXCEPTION 'Preflight: captured checklist membership cannot be represented faithfully.';
    END IF;
    IF EXISTS (SELECT 1 FROM checklist_edits e JOIN requirements r ON r.id=e.requirement_id
               WHERE lower(btrim(e.requirement_name)) <> lower(btrim(r.name))) THEN
        RAISE EXCEPTION 'Preflight: historical requirement label differs from its current definition.';
    END IF;
END;
$$;

CREATE SCHEMA onboarding_legacy_cutover;
ALTER TABLE provider_types SET SCHEMA onboarding_legacy_cutover;
ALTER TABLE requirement_templates SET SCHEMA onboarding_legacy_cutover;
ALTER TABLE providers SET SCHEMA onboarding_legacy_cutover;
ALTER TABLE requirements SET SCHEMA onboarding_legacy_cutover;
ALTER TABLE updates SET SCHEMA onboarding_legacy_cutover;
ALTER TABLE suggestions SET SCHEMA onboarding_legacy_cutover;
ALTER TABLE review_decisions SET SCHEMA onboarding_legacy_cutover;
ALTER TABLE checklist_edits SET SCHEMA onboarding_legacy_cutover;

-- One row stores one provider type.
CREATE TABLE provider_types (
    id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL CHECK (btrim(name)<>'')
);
COMMENT ON TABLE provider_types IS 'One row stores one provider type.';
CREATE UNIQUE INDEX provider_types_normalized_name ON provider_types(lower(btrim(name)));

-- One row stores one reusable requirement definition.
CREATE TABLE requirement_definitions (
    id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL CHECK (btrim(name)<>'')
);
COMMENT ON TABLE requirement_definitions IS 'One row stores one reusable requirement definition.';
CREATE UNIQUE INDEX requirement_definitions_normalized_name ON requirement_definitions(lower(btrim(name)));

-- One row stores one complete checklist version for a provider type.
CREATE TABLE checklist_templates (
    id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider_type_id integer NOT NULL REFERENCES provider_types(id) ON DELETE RESTRICT,
    template_version integer NOT NULL CHECK (template_version>0),
    UNIQUE(provider_type_id,template_version)
);
COMMENT ON TABLE checklist_templates IS 'One row stores one complete checklist version for a provider type.';

-- One row assigns one requirement definition to one checklist version.
CREATE TABLE template_requirements (
    checklist_template_id integer NOT NULL REFERENCES checklist_templates(id) ON DELETE CASCADE,
    requirement_definition_id integer NOT NULL REFERENCES requirement_definitions(id) ON DELETE RESTRICT,
    PRIMARY KEY(checklist_template_id,requirement_definition_id)
);
COMMENT ON TABLE template_requirements IS 'One row assigns one requirement definition to one checklist version.';
CREATE INDEX template_requirements_definition ON template_requirements(requirement_definition_id);

-- One row stores one fictional provider and their assigned checklist version.
CREATE TABLE providers (
    id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    creation_request_id uuid NOT NULL UNIQUE,
    name text NOT NULL CHECK (btrim(name)<>''),
    checklist_template_id integer NOT NULL REFERENCES checklist_templates(id) ON DELETE RESTRICT,
    proposed_start_date date,
    archived_at timestamptz,
    UNIQUE(id,checklist_template_id)
);
COMMENT ON TABLE providers IS 'One row stores one fictional provider and their assigned checklist version.';
CREATE INDEX providers_template ON providers(checklist_template_id);

-- One row stores one provider's progress on one assigned checklist requirement.
CREATE TABLE requirements (
    id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider_id integer NOT NULL,
    checklist_template_id integer NOT NULL,
    requirement_definition_id integer NOT NULL,
    status text NOT NULL CHECK (btrim(status)<>''),
    scheduled_date date,
    deadline date,
    version integer NOT NULL DEFAULT 0 CHECK (version>=0),
    FOREIGN KEY(provider_id,checklist_template_id) REFERENCES providers(id,checklist_template_id) ON DELETE CASCADE,
    FOREIGN KEY(checklist_template_id,requirement_definition_id) REFERENCES template_requirements(checklist_template_id,requirement_definition_id) ON DELETE RESTRICT,
    UNIQUE(provider_id,requirement_definition_id), UNIQUE(id,provider_id)
);
COMMENT ON TABLE requirements IS 'One row stores one provider''s progress on one assigned checklist requirement.';
CREATE INDEX requirements_membership ON requirements(checklist_template_id,requirement_definition_id);
CREATE INDEX requirements_definition ON requirements(requirement_definition_id);

-- One row stores one original provider update and its analysis state.
CREATE TABLE updates (
    id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id uuid NOT NULL UNIQUE,
    provider_id integer NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
    original_text text NOT NULL CHECK (btrim(original_text)<>''),
    processing_state text NOT NULL CHECK (processing_state IN ('processing','completed','failed')),
    message text NOT NULL,
    failure_category text CHECK (failure_category IN ('configuration','timeout','model')),
    created_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz,
    UNIQUE(id,provider_id),
    CHECK ((processing_state='failed')=(failure_category IS NOT NULL))
);
COMMENT ON TABLE updates IS 'One row stores one original provider update and its analysis state.';
CREATE INDEX updates_provider_created ON updates(provider_id,created_at,id);

-- One row stores one requirement's state when an update was submitted.
CREATE TABLE update_requirement_snapshots (
    update_id integer NOT NULL, requirement_id integer NOT NULL, provider_id integer NOT NULL,
    status text NOT NULL CHECK (btrim(status)<>''),
    scheduled_date date, deadline date,
    requirement_version integer NOT NULL CHECK (requirement_version>=0),
    PRIMARY KEY(update_id,requirement_id),
    FOREIGN KEY(update_id,provider_id) REFERENCES updates(id,provider_id) ON DELETE CASCADE,
    FOREIGN KEY(requirement_id,provider_id) REFERENCES requirements(id,provider_id) ON DELETE CASCADE
);
COMMENT ON TABLE update_requirement_snapshots IS 'One row stores one requirement''s state when an update was submitted.';
CREATE INDEX update_requirement_snapshots_requirement ON update_requirement_snapshots(requirement_id);
CREATE INDEX update_requirement_snapshots_provider ON update_requirement_snapshots(provider_id);

-- One row stores one warning or ambiguity associated with an update.
CREATE TABLE update_ambiguities (
    id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    update_id integer NOT NULL REFERENCES updates(id) ON DELETE CASCADE,
    message text NOT NULL CHECK (btrim(message)<>'')
);
COMMENT ON TABLE update_ambiguities IS 'One row stores one warning or ambiguity associated with an update.';
CREATE INDEX update_ambiguities_update ON update_ambiguities(update_id);

-- One row stores one proposed change to one provider requirement.
CREATE TABLE suggestions (
    id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    update_id integer NOT NULL, requirement_id integer NOT NULL, provider_id integer NOT NULL,
    requirement_version integer NOT NULL CHECK (requirement_version>=0),
    proposed_status text NOT NULL CHECK (btrim(proposed_status)<>''),
    proposed_date date, supporting_text text NOT NULL,
    date_text text, date_inferred boolean NOT NULL DEFAULT false,
    date_explanation text, date_requires_confirmation boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY(update_id,provider_id) REFERENCES updates(id,provider_id) ON DELETE CASCADE,
    FOREIGN KEY(requirement_id,provider_id) REFERENCES requirements(id,provider_id) ON DELETE CASCADE
);
COMMENT ON TABLE suggestions IS 'One row stores one proposed change to one provider requirement.';
CREATE INDEX suggestions_update ON suggestions(update_id);
CREATE INDEX suggestions_requirement ON suggestions(requirement_id);
CREATE INDEX suggestions_provider ON suggestions(provider_id);

-- One row stores the terminal Manager decision on one suggestion.
CREATE TABLE review_decisions (
    id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    suggestion_id integer NOT NULL UNIQUE REFERENCES suggestions(id) ON DELETE CASCADE,
    outcome text NOT NULL CHECK (outcome IN ('approved','corrected','rejected')),
    previous_status text NOT NULL CHECK (btrim(previous_status)<>''), previous_scheduled_date date,
    applied_status text CHECK (applied_status IS NULL OR btrim(applied_status)<>''), applied_scheduled_date date,
    reviewer_role text NOT NULL CHECK (reviewer_role='manager'), reviewed_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((outcome='rejected' AND applied_status IS NULL AND applied_scheduled_date IS NULL)
        OR (outcome<>'rejected' AND applied_status IS NOT NULL))
);
COMMENT ON TABLE review_decisions IS 'One row stores the terminal Manager decision on one suggestion.';

-- One row stores the before-and-after evidence for one direct Manager checklist save.
CREATE TABLE checklist_edits (
    id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    operation_id uuid NOT NULL UNIQUE,
    provider_id integer NOT NULL, requirement_id integer NOT NULL,
    expected_version integer NOT NULL CHECK (expected_version>=0),
    resulting_version integer NOT NULL CHECK (resulting_version=expected_version+1),
    previous_status text NOT NULL CHECK (btrim(previous_status)<>''),
    previous_scheduled_date date, previous_deadline date,
    applied_status text NOT NULL CHECK (btrim(applied_status)<>''),
    applied_scheduled_date date, applied_deadline date,
    reviewer_role text NOT NULL CHECK (reviewer_role='manager'),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    FOREIGN KEY(requirement_id,provider_id) REFERENCES requirements(id,provider_id) ON DELETE CASCADE,
    CHECK (ROW(previous_status,previous_scheduled_date,previous_deadline)
        IS DISTINCT FROM ROW(applied_status,applied_scheduled_date,applied_deadline))
);
COMMENT ON TABLE checklist_edits IS 'One row stores the before-and-after evidence for one direct Manager checklist save.';
CREATE INDEX checklist_edits_requirement ON checklist_edits(requirement_id);
CREATE INDEX checklist_edits_provider_created ON checklist_edits(provider_id,created_at,id);

-- All collections below are transaction-local transformation maps, never application storage.
INSERT INTO provider_types(name)
SELECT DISTINCT ON (lower(btrim(name))) btrim(name)
FROM onboarding_legacy_cutover.provider_types ORDER BY lower(btrim(name)),id;
CREATE TEMP TABLE type_map ON COMMIT DROP AS
SELECT o.id old_id,n.id new_id FROM onboarding_legacy_cutover.provider_types o
JOIN provider_types n ON lower(btrim(n.name))=lower(btrim(o.name));

INSERT INTO requirement_definitions(name)
SELECT DISTINCT ON (lower(btrim(name))) btrim(name) FROM (
    SELECT name,id,0 priority FROM onboarding_legacy_cutover.requirement_templates
    UNION ALL SELECT name,id,1 FROM onboarding_legacy_cutover.requirements
) names ORDER BY lower(btrim(name)),priority,id;
CREATE TEMP TABLE definition_map ON COMMIT DROP AS
SELECT r.id old_id,d.id definition_id FROM onboarding_legacy_cutover.requirements r
JOIN requirement_definitions d ON lower(btrim(d.name))=lower(btrim(r.name));
CREATE TEMP TABLE catalog_sets ON COMMIT DROP AS
SELECT DISTINCT tm.new_id type_id,ARRAY(
    SELECT DISTINCT d.id FROM onboarding_legacy_cutover.requirement_templates r
    JOIN requirement_definitions d ON lower(btrim(d.name))=lower(btrim(r.name))
    WHERE r.provider_type_id=tm.old_id ORDER BY d.id
) members FROM type_map tm;
CREATE TEMP TABLE provider_sets ON COMMIT DROP AS
SELECT p.id old_id,tm.new_id type_id,ARRAY(
    SELECT DISTINCT dm.definition_id FROM onboarding_legacy_cutover.requirements r
    JOIN definition_map dm ON dm.old_id=r.id WHERE r.provider_id=p.id ORDER BY dm.definition_id
) members FROM onboarding_legacy_cutover.providers p JOIN type_map tm ON tm.old_id=p.provider_type_id;
CREATE TEMP TABLE version_sets ON COMMIT DROP AS
SELECT type_id,members,row_number() OVER (PARTITION BY type_id ORDER BY is_catalog,members)::integer template_version
FROM (
    SELECT type_id,members,bool_or(is_catalog) is_catalog FROM (
        SELECT type_id,members,true is_catalog FROM catalog_sets
        UNION ALL SELECT type_id,members,false FROM provider_sets
    ) combined GROUP BY type_id,members
) distinct_sets;
INSERT INTO checklist_templates(provider_type_id,template_version)
SELECT type_id,template_version FROM version_sets ORDER BY type_id,template_version;
INSERT INTO template_requirements(checklist_template_id,requirement_definition_id)
SELECT t.id,m.definition_id FROM version_sets s
JOIN checklist_templates t ON t.provider_type_id=s.type_id AND t.template_version=s.template_version
CROSS JOIN LATERAL unnest(s.members) m(definition_id);
INSERT INTO providers(creation_request_id,name,checklist_template_id,proposed_start_date)
SELECT p.id,p.name,t.id,p.proposed_start_date FROM onboarding_legacy_cutover.providers p
JOIN provider_sets ps ON ps.old_id=p.id
JOIN version_sets vs ON vs.type_id=ps.type_id AND vs.members=ps.members
JOIN checklist_templates t ON t.provider_type_id=vs.type_id AND t.template_version=vs.template_version
ORDER BY p.id;
CREATE TEMP TABLE requirement_map ON COMMIT DROP AS
SELECT r.id old_id,nextval(pg_get_serial_sequence('requirements','id'))::integer new_id
FROM onboarding_legacy_cutover.requirements r ORDER BY r.id;
INSERT INTO requirements(id,provider_id,checklist_template_id,requirement_definition_id,status,scheduled_date,deadline,version)
OVERRIDING SYSTEM VALUE
SELECT rm.new_id,p.id,p.checklist_template_id,dm.definition_id,r.status,r.scheduled_date,r.deadline,r.version
FROM onboarding_legacy_cutover.requirements r JOIN requirement_map rm ON rm.old_id=r.id
JOIN definition_map dm ON dm.old_id=r.id JOIN providers p ON p.creation_request_id=r.provider_id;
INSERT INTO updates(request_id,provider_id,original_text,processing_state,message,failure_category,created_at,completed_at)
SELECT u.request_id,p.id,u.original_text,u.processing_state,u.message,u.failure_category,u.created_at,u.completed_at
FROM onboarding_legacy_cutover.updates u JOIN providers p ON p.creation_request_id=u.provider_id ORDER BY u.id;
CREATE TEMP TABLE update_map ON COMMIT DROP AS
SELECT o.id old_id,n.id new_id FROM onboarding_legacy_cutover.updates o JOIN updates n USING(request_id);
INSERT INTO update_requirement_snapshots(update_id,requirement_id,provider_id,status,scheduled_date,deadline,requirement_version)
SELECT um.new_id,rm.new_id,p.id,s->>'status',(s->>'scheduled_date')::date,(s->>'deadline')::date,(s->>'version')::integer
FROM onboarding_legacy_cutover.updates u JOIN update_map um ON um.old_id=u.id
JOIN providers p ON p.creation_request_id=u.provider_id
CROSS JOIN LATERAL jsonb_array_elements(u.provider_snapshot->'requirements') s
JOIN requirement_map rm ON rm.old_id=(s->>'id')::uuid;
INSERT INTO update_ambiguities(update_id,message)
SELECT um.new_id,w #>> '{}' FROM onboarding_legacy_cutover.updates u
JOIN update_map um ON um.old_id=u.id CROSS JOIN LATERAL jsonb_array_elements(u.ambiguities) w;
CREATE TEMP TABLE suggestion_map ON COMMIT DROP AS
SELECT s.id old_id,nextval(pg_get_serial_sequence('suggestions','id'))::integer new_id
FROM onboarding_legacy_cutover.suggestions s ORDER BY s.id;
INSERT INTO suggestions(id,update_id,requirement_id,provider_id,requirement_version,proposed_status,proposed_date,
    supporting_text,date_text,date_inferred,date_explanation,date_requires_confirmation,created_at)
OVERRIDING SYSTEM VALUE
SELECT sm.new_id,um.new_id,rm.new_id,p.id,s.requirement_version,s.proposed_status,s.proposed_date,
    s.supporting_text,s.date_text,s.date_inferred,s.date_explanation,s.date_requires_confirmation,s.created_at
FROM onboarding_legacy_cutover.suggestions s JOIN suggestion_map sm ON sm.old_id=s.id
JOIN update_map um ON um.old_id=s.update_id JOIN requirement_map rm ON rm.old_id=s.requirement_id
JOIN providers p ON p.creation_request_id=s.provider_id;
INSERT INTO review_decisions(suggestion_id,outcome,previous_status,previous_scheduled_date,applied_status,
    applied_scheduled_date,reviewer_role,reviewed_at)
SELECT sm.new_id,d.outcome,d.previous_status,d.previous_scheduled_date,d.applied_status,
    d.applied_scheduled_date,d.reviewer_role,d.reviewed_at
FROM onboarding_legacy_cutover.review_decisions d JOIN suggestion_map sm ON sm.old_id=d.suggestion_id ORDER BY d.id;
INSERT INTO checklist_edits(operation_id,provider_id,requirement_id,expected_version,resulting_version,
    previous_status,previous_scheduled_date,previous_deadline,applied_status,applied_scheduled_date,
    applied_deadline,reviewer_role,created_at)
SELECT e.id,p.id,rm.new_id,e.expected_version,e.resulting_version,e.previous_status,e.previous_scheduled_date,
    e.previous_deadline,e.applied_status,e.applied_scheduled_date,e.applied_deadline,e.reviewer_role,e.created_at
FROM onboarding_legacy_cutover.checklist_edits e JOIN providers p ON p.creation_request_id=e.provider_id
JOIN requirement_map rm ON rm.old_id=e.requirement_id ORDER BY e.id;

-- Verify no history or requirement row disappeared through a mapping join.
DO $$
DECLARE table_name text; old_count bigint; new_count bigint;
BEGIN
    FOREACH table_name IN ARRAY ARRAY['providers','requirements','updates','suggestions','review_decisions','checklist_edits'] LOOP
        EXECUTE format('SELECT count(*) FROM onboarding_legacy_cutover.%I',table_name) INTO old_count;
        EXECUTE format('SELECT count(*) FROM public.%I',table_name) INTO new_count;
        IF old_count<>new_count THEN RAISE EXCEPTION 'Conversion row-count mismatch for %',table_name; END IF;
    END LOOP;
END;
$$;

CREATE FUNCTION preserve_catalog_label() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.name IS DISTINCT FROM OLD.name THEN RAISE EXCEPTION 'Catalog labels are immutable; use a new definition/version.'; END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER preserve_type_label BEFORE UPDATE ON provider_types FOR EACH ROW EXECUTE FUNCTION preserve_catalog_label();
CREATE TRIGGER preserve_definition_label BEFORE UPDATE ON requirement_definitions FOR EACH ROW EXECUTE FUNCTION preserve_catalog_label();

CREATE FUNCTION preserve_template_identity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF ROW(NEW.id,NEW.provider_type_id,NEW.template_version) IS DISTINCT FROM ROW(OLD.id,OLD.provider_type_id,OLD.template_version) THEN
        RAISE EXCEPTION 'Checklist version identity is immutable.';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER preserve_template_identity BEFORE UPDATE ON checklist_templates FOR EACH ROW EXECUTE FUNCTION preserve_template_identity();
CREATE FUNCTION preserve_template_membership() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE old_template integer; new_template integer;
BEGIN
    IF TG_OP<>'INSERT' THEN old_template:=OLD.checklist_template_id; END IF;
    IF TG_OP<>'DELETE' THEN new_template:=NEW.checklist_template_id; END IF;
    PERFORM id FROM checklist_templates WHERE id IN (old_template,new_template) ORDER BY id FOR UPDATE;
    IF EXISTS (SELECT 1 FROM providers WHERE checklist_template_id IN (old_template,new_template)) THEN
        RAISE EXCEPTION 'An assigned checklist version is immutable.';
    END IF;
    IF TG_OP='DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER preserve_template_membership BEFORE INSERT OR UPDATE OR DELETE ON template_requirements
    FOR EACH ROW EXECUTE FUNCTION preserve_template_membership();
CREATE FUNCTION preserve_provider_profile() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP='UPDATE' AND ROW(NEW.id,NEW.creation_request_id,NEW.name,NEW.checklist_template_id,NEW.proposed_start_date)
        IS DISTINCT FROM ROW(OLD.id,OLD.creation_request_id,OLD.name,OLD.checklist_template_id,OLD.proposed_start_date) THEN
        RAISE EXCEPTION 'Provider profile and assigned checklist version are fixed.';
    END IF;
    IF TG_OP='INSERT' THEN PERFORM id FROM checklist_templates WHERE id=NEW.checklist_template_id FOR UPDATE; END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER preserve_provider_profile BEFORE INSERT OR UPDATE ON providers FOR EACH ROW EXECUTE FUNCTION preserve_provider_profile();
CREATE FUNCTION preserve_requirement_owner() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF ROW(NEW.id,NEW.provider_id,NEW.checklist_template_id,NEW.requirement_definition_id)
        IS DISTINCT FROM ROW(OLD.id,OLD.provider_id,OLD.checklist_template_id,OLD.requirement_definition_id) THEN
        RAISE EXCEPTION 'Requirement ownership and membership are fixed.';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER preserve_requirement_owner BEFORE UPDATE ON requirements FOR EACH ROW EXECUTE FUNCTION preserve_requirement_owner();
CREATE OR REPLACE FUNCTION preserve_checklist_edit() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP='DELETE' AND NOT EXISTS (SELECT 1 FROM public.providers WHERE id=OLD.provider_id) THEN RETURN OLD; END IF;
    RAISE EXCEPTION 'Checklist edit history is immutable.';
END;
$$;
CREATE TRIGGER preserve_checklist_edit BEFORE UPDATE OR DELETE ON checklist_edits FOR EACH ROW EXECUTE FUNCTION preserve_checklist_edit();

DROP TABLE type_map,definition_map,catalog_sets,provider_sets,version_sets,requirement_map,update_map,suggestion_map;
DROP TABLE onboarding_legacy_cutover.checklist_edits;
DROP TABLE onboarding_legacy_cutover.review_decisions;
DROP TABLE onboarding_legacy_cutover.suggestions;
DROP TABLE onboarding_legacy_cutover.updates;
DROP TABLE onboarding_legacy_cutover.requirements;
DROP TABLE onboarding_legacy_cutover.providers;
DROP TABLE onboarding_legacy_cutover.requirement_templates;
DROP TABLE onboarding_legacy_cutover.provider_types;
DROP SCHEMA onboarding_legacy_cutover;

-- migrate:down
DO $$
BEGIN
    RAISE EXCEPTION 'Restore the verified final pre-cutover backup and matching old application; lost UUID identities cannot be reconstructed by SQL rollback.';
END;
$$;
