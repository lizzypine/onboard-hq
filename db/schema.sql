--
-- PostgreSQL database dump
--

\restrict dbmate

-- Dumped from database version 18.6 (Homebrew)
-- Dumped by pg_dump version 18.6 (Homebrew)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: preserve_catalog_label(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.preserve_catalog_label() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF NEW.name IS DISTINCT FROM OLD.name THEN RAISE EXCEPTION 'Catalog labels are immutable; use a new definition/version.'; END IF;
    RETURN NEW;
END;
$$;


--
-- Name: preserve_checklist_edit(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.preserve_checklist_edit() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF TG_OP='DELETE' AND NOT EXISTS (SELECT 1 FROM public.providers WHERE id=OLD.provider_id) THEN RETURN OLD; END IF;
    RAISE EXCEPTION 'Checklist edit history is immutable.';
END;
$$;


--
-- Name: preserve_provider_profile(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.preserve_provider_profile() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF TG_OP='UPDATE' AND ROW(NEW.id,NEW.creation_request_id,NEW.name,NEW.checklist_template_id,NEW.proposed_start_date)
        IS DISTINCT FROM ROW(OLD.id,OLD.creation_request_id,OLD.name,OLD.checklist_template_id,OLD.proposed_start_date) THEN
        RAISE EXCEPTION 'Provider profile and assigned checklist version are fixed.';
    END IF;
    IF TG_OP='INSERT' THEN PERFORM id FROM checklist_templates WHERE id=NEW.checklist_template_id FOR UPDATE; END IF;
    RETURN NEW;
END;
$$;


--
-- Name: preserve_requirement_owner(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.preserve_requirement_owner() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
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


--
-- Name: preserve_template_identity(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.preserve_template_identity() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF ROW(NEW.id,NEW.provider_type_id,NEW.template_version) IS DISTINCT FROM ROW(OLD.id,OLD.provider_type_id,OLD.template_version) THEN
        RAISE EXCEPTION 'Checklist version identity is immutable.';
    END IF;
    RETURN NEW;
END;
$$;


--
-- Name: preserve_template_membership(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.preserve_template_membership() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
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


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: checklist_edits; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.checklist_edits (
    id integer NOT NULL,
    operation_id uuid NOT NULL,
    provider_id integer NOT NULL,
    requirement_id integer NOT NULL,
    expected_version integer NOT NULL,
    resulting_version integer NOT NULL,
    previous_status text NOT NULL,
    previous_scheduled_date date,
    previous_deadline date,
    applied_status text NOT NULL,
    applied_scheduled_date date,
    applied_deadline date,
    reviewer_role text NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT checklist_edits_applied_status_check CHECK ((btrim(applied_status) <> ''::text)),
    CONSTRAINT checklist_edits_check CHECK ((resulting_version = (expected_version + 1))),
    CONSTRAINT checklist_edits_check1 CHECK ((((previous_status IS DISTINCT FROM applied_status) OR (previous_scheduled_date IS DISTINCT FROM applied_scheduled_date)) OR (previous_deadline IS DISTINCT FROM applied_deadline))),
    CONSTRAINT checklist_edits_expected_version_check CHECK ((expected_version >= 0)),
    CONSTRAINT checklist_edits_previous_status_check CHECK ((btrim(previous_status) <> ''::text)),
    CONSTRAINT checklist_edits_reviewer_role_check CHECK ((reviewer_role = 'manager'::text))
);


--
-- Name: TABLE checklist_edits; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.checklist_edits IS 'One row stores the before-and-after evidence for one direct Manager checklist save.';


--
-- Name: checklist_edits_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.checklist_edits ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.checklist_edits_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: checklist_templates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.checklist_templates (
    id integer NOT NULL,
    provider_type_id integer NOT NULL,
    template_version integer NOT NULL,
    CONSTRAINT checklist_templates_template_version_check CHECK ((template_version > 0))
);


--
-- Name: TABLE checklist_templates; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.checklist_templates IS 'One row stores one complete checklist version for a provider type.';


--
-- Name: checklist_templates_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.checklist_templates ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.checklist_templates_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: provider_types; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.provider_types (
    id integer NOT NULL,
    name text NOT NULL,
    CONSTRAINT provider_types_name_check CHECK ((btrim(name) <> ''::text))
);


--
-- Name: TABLE provider_types; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.provider_types IS 'One row stores one provider type.';


--
-- Name: provider_types_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.provider_types ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.provider_types_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: providers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.providers (
    id integer NOT NULL,
    creation_request_id uuid NOT NULL,
    name text NOT NULL,
    checklist_template_id integer NOT NULL,
    proposed_start_date date,
    archived_at timestamp with time zone,
    CONSTRAINT providers_name_check CHECK ((btrim(name) <> ''::text))
);


--
-- Name: TABLE providers; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.providers IS 'One row stores one fictional provider and their assigned checklist version.';


--
-- Name: providers_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.providers ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.providers_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: requirement_definitions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.requirement_definitions (
    id integer NOT NULL,
    name text NOT NULL,
    CONSTRAINT requirement_definitions_name_check CHECK ((btrim(name) <> ''::text))
);


--
-- Name: TABLE requirement_definitions; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.requirement_definitions IS 'One row stores one reusable requirement definition.';


--
-- Name: requirement_definitions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.requirement_definitions ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.requirement_definitions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: requirements; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.requirements (
    id integer NOT NULL,
    provider_id integer NOT NULL,
    checklist_template_id integer,
    requirement_definition_id integer NOT NULL,
    status text NOT NULL,
    scheduled_date date,
    deadline date,
    version integer DEFAULT 0 NOT NULL,
    initial_status text,
    initial_scheduled_date date,
    initial_deadline date,
    CONSTRAINT requirements_initial_values CHECK ((((checklist_template_id IS NOT NULL) AND (initial_status IS NULL) AND (initial_scheduled_date IS NULL) AND (initial_deadline IS NULL)) OR ((checklist_template_id IS NULL) AND (initial_status IS NOT NULL) AND (btrim(initial_status) <> ''::text)))),
    CONSTRAINT requirements_status_check CHECK ((btrim(status) <> ''::text)),
    CONSTRAINT requirements_version_check CHECK ((version >= 0))
);


--
-- Name: TABLE requirements; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.requirements IS 'One row stores one provider''s progress on a standard or provider-only requirement.';


--
-- Name: requirements_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.requirements ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.requirements_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: review_decisions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.review_decisions (
    id integer NOT NULL,
    suggestion_id integer NOT NULL,
    outcome text NOT NULL,
    previous_status text NOT NULL,
    previous_scheduled_date date,
    applied_status text,
    applied_scheduled_date date,
    reviewer_role text NOT NULL,
    reviewed_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT review_decisions_applied_status_check CHECK (((applied_status IS NULL) OR (btrim(applied_status) <> ''::text))),
    CONSTRAINT review_decisions_check CHECK ((((outcome = 'rejected'::text) AND (applied_status IS NULL) AND (applied_scheduled_date IS NULL)) OR ((outcome <> 'rejected'::text) AND (applied_status IS NOT NULL)))),
    CONSTRAINT review_decisions_outcome_check CHECK ((outcome = ANY (ARRAY['approved'::text, 'corrected'::text, 'rejected'::text]))),
    CONSTRAINT review_decisions_previous_status_check CHECK ((btrim(previous_status) <> ''::text)),
    CONSTRAINT review_decisions_reviewer_role_check CHECK ((reviewer_role = 'manager'::text))
);


--
-- Name: TABLE review_decisions; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.review_decisions IS 'One row stores the terminal Manager decision on one suggestion.';


--
-- Name: review_decisions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.review_decisions ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.review_decisions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: schema_migrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.schema_migrations (
    version character varying NOT NULL
);


--
-- Name: suggestions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.suggestions (
    id integer NOT NULL,
    update_id integer NOT NULL,
    requirement_id integer NOT NULL,
    provider_id integer NOT NULL,
    requirement_version integer NOT NULL,
    proposed_status text NOT NULL,
    proposed_date date,
    supporting_text text NOT NULL,
    date_text text,
    date_inferred boolean DEFAULT false NOT NULL,
    date_explanation text,
    date_requires_confirmation boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT suggestions_proposed_status_check CHECK ((btrim(proposed_status) <> ''::text)),
    CONSTRAINT suggestions_requirement_version_check CHECK ((requirement_version >= 0))
);


--
-- Name: TABLE suggestions; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.suggestions IS 'One row stores one proposed change to one provider requirement.';


--
-- Name: suggestions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.suggestions ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.suggestions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: template_requirements; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.template_requirements (
    checklist_template_id integer NOT NULL,
    requirement_definition_id integer NOT NULL
);


--
-- Name: TABLE template_requirements; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.template_requirements IS 'One row assigns one requirement definition to one checklist version.';


--
-- Name: update_ambiguities; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.update_ambiguities (
    id integer NOT NULL,
    update_id integer NOT NULL,
    message text NOT NULL,
    CONSTRAINT update_ambiguities_message_check CHECK ((btrim(message) <> ''::text))
);


--
-- Name: TABLE update_ambiguities; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.update_ambiguities IS 'One row stores one warning or ambiguity associated with an update.';


--
-- Name: update_ambiguities_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.update_ambiguities ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.update_ambiguities_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: update_requirement_snapshots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.update_requirement_snapshots (
    update_id integer NOT NULL,
    requirement_id integer NOT NULL,
    provider_id integer NOT NULL,
    status text NOT NULL,
    scheduled_date date,
    deadline date,
    requirement_version integer NOT NULL,
    CONSTRAINT update_requirement_snapshots_requirement_version_check CHECK ((requirement_version >= 0)),
    CONSTRAINT update_requirement_snapshots_status_check CHECK ((btrim(status) <> ''::text))
);


--
-- Name: TABLE update_requirement_snapshots; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.update_requirement_snapshots IS 'One row stores one requirement''s state when an update was submitted.';


--
-- Name: updates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.updates (
    id integer NOT NULL,
    request_id uuid NOT NULL,
    provider_id integer NOT NULL,
    original_text text NOT NULL,
    processing_state text NOT NULL,
    message text NOT NULL,
    failure_category text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    completed_at timestamp with time zone,
    CONSTRAINT updates_check CHECK (((processing_state = 'failed'::text) = (failure_category IS NOT NULL))),
    CONSTRAINT updates_failure_category_check CHECK ((failure_category = ANY (ARRAY['configuration'::text, 'timeout'::text, 'model'::text]))),
    CONSTRAINT updates_original_text_check CHECK ((btrim(original_text) <> ''::text)),
    CONSTRAINT updates_processing_state_check CHECK ((processing_state = ANY (ARRAY['processing'::text, 'completed'::text, 'failed'::text])))
);


--
-- Name: TABLE updates; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.updates IS 'One row stores one original provider update and its analysis state.';


--
-- Name: updates_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.updates ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.updates_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: checklist_edits checklist_edits_operation_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.checklist_edits
    ADD CONSTRAINT checklist_edits_operation_id_key UNIQUE (operation_id);


--
-- Name: checklist_edits checklist_edits_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.checklist_edits
    ADD CONSTRAINT checklist_edits_pkey PRIMARY KEY (id);


--
-- Name: checklist_templates checklist_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.checklist_templates
    ADD CONSTRAINT checklist_templates_pkey PRIMARY KEY (id);


--
-- Name: checklist_templates checklist_templates_provider_type_id_template_version_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.checklist_templates
    ADD CONSTRAINT checklist_templates_provider_type_id_template_version_key UNIQUE (provider_type_id, template_version);


--
-- Name: provider_types provider_types_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_types
    ADD CONSTRAINT provider_types_pkey PRIMARY KEY (id);


--
-- Name: providers providers_creation_request_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.providers
    ADD CONSTRAINT providers_creation_request_id_key UNIQUE (creation_request_id);


--
-- Name: providers providers_id_checklist_template_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.providers
    ADD CONSTRAINT providers_id_checklist_template_id_key UNIQUE (id, checklist_template_id);


--
-- Name: providers providers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.providers
    ADD CONSTRAINT providers_pkey PRIMARY KEY (id);


--
-- Name: requirement_definitions requirement_definitions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.requirement_definitions
    ADD CONSTRAINT requirement_definitions_pkey PRIMARY KEY (id);


--
-- Name: requirements requirements_id_provider_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.requirements
    ADD CONSTRAINT requirements_id_provider_id_key UNIQUE (id, provider_id);


--
-- Name: requirements requirements_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.requirements
    ADD CONSTRAINT requirements_pkey PRIMARY KEY (id);


--
-- Name: requirements requirements_provider_id_requirement_definition_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.requirements
    ADD CONSTRAINT requirements_provider_id_requirement_definition_id_key UNIQUE (provider_id, requirement_definition_id);


--
-- Name: review_decisions review_decisions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.review_decisions
    ADD CONSTRAINT review_decisions_pkey PRIMARY KEY (id);


--
-- Name: review_decisions review_decisions_suggestion_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.review_decisions
    ADD CONSTRAINT review_decisions_suggestion_id_key UNIQUE (suggestion_id);


--
-- Name: schema_migrations schema_migrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.schema_migrations
    ADD CONSTRAINT schema_migrations_pkey PRIMARY KEY (version);


--
-- Name: suggestions suggestions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.suggestions
    ADD CONSTRAINT suggestions_pkey PRIMARY KEY (id);


--
-- Name: template_requirements template_requirements_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.template_requirements
    ADD CONSTRAINT template_requirements_pkey PRIMARY KEY (checklist_template_id, requirement_definition_id);


--
-- Name: update_ambiguities update_ambiguities_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.update_ambiguities
    ADD CONSTRAINT update_ambiguities_pkey PRIMARY KEY (id);


--
-- Name: update_requirement_snapshots update_requirement_snapshots_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.update_requirement_snapshots
    ADD CONSTRAINT update_requirement_snapshots_pkey PRIMARY KEY (update_id, requirement_id);


--
-- Name: updates updates_id_provider_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.updates
    ADD CONSTRAINT updates_id_provider_id_key UNIQUE (id, provider_id);


--
-- Name: updates updates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.updates
    ADD CONSTRAINT updates_pkey PRIMARY KEY (id);


--
-- Name: updates updates_request_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.updates
    ADD CONSTRAINT updates_request_id_key UNIQUE (request_id);


--
-- Name: checklist_edits_provider_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX checklist_edits_provider_created ON public.checklist_edits USING btree (provider_id, created_at, id);


--
-- Name: checklist_edits_requirement; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX checklist_edits_requirement ON public.checklist_edits USING btree (requirement_id);


--
-- Name: provider_types_normalized_name; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX provider_types_normalized_name ON public.provider_types USING btree (lower(btrim(name)));


--
-- Name: providers_template; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX providers_template ON public.providers USING btree (checklist_template_id);


--
-- Name: requirement_definitions_normalized_name; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX requirement_definitions_normalized_name ON public.requirement_definitions USING btree (lower(btrim(name)));


--
-- Name: requirements_definition; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX requirements_definition ON public.requirements USING btree (requirement_definition_id);


--
-- Name: requirements_membership; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX requirements_membership ON public.requirements USING btree (checklist_template_id, requirement_definition_id);


--
-- Name: suggestions_provider; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX suggestions_provider ON public.suggestions USING btree (provider_id);


--
-- Name: suggestions_requirement; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX suggestions_requirement ON public.suggestions USING btree (requirement_id);


--
-- Name: suggestions_update; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX suggestions_update ON public.suggestions USING btree (update_id);


--
-- Name: template_requirements_definition; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX template_requirements_definition ON public.template_requirements USING btree (requirement_definition_id);


--
-- Name: update_ambiguities_update; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX update_ambiguities_update ON public.update_ambiguities USING btree (update_id);


--
-- Name: update_requirement_snapshots_provider; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX update_requirement_snapshots_provider ON public.update_requirement_snapshots USING btree (provider_id);


--
-- Name: update_requirement_snapshots_requirement; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX update_requirement_snapshots_requirement ON public.update_requirement_snapshots USING btree (requirement_id);


--
-- Name: updates_provider_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX updates_provider_created ON public.updates USING btree (provider_id, created_at, id);


--
-- Name: checklist_edits preserve_checklist_edit; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER preserve_checklist_edit BEFORE DELETE OR UPDATE ON public.checklist_edits FOR EACH ROW EXECUTE FUNCTION public.preserve_checklist_edit();


--
-- Name: requirement_definitions preserve_definition_label; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER preserve_definition_label BEFORE UPDATE ON public.requirement_definitions FOR EACH ROW EXECUTE FUNCTION public.preserve_catalog_label();


--
-- Name: providers preserve_provider_profile; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER preserve_provider_profile BEFORE INSERT OR UPDATE ON public.providers FOR EACH ROW EXECUTE FUNCTION public.preserve_provider_profile();


--
-- Name: requirements preserve_requirement_owner; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER preserve_requirement_owner BEFORE UPDATE ON public.requirements FOR EACH ROW EXECUTE FUNCTION public.preserve_requirement_owner();


--
-- Name: checklist_templates preserve_template_identity; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER preserve_template_identity BEFORE UPDATE ON public.checklist_templates FOR EACH ROW EXECUTE FUNCTION public.preserve_template_identity();


--
-- Name: template_requirements preserve_template_membership; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER preserve_template_membership BEFORE INSERT OR DELETE OR UPDATE ON public.template_requirements FOR EACH ROW EXECUTE FUNCTION public.preserve_template_membership();


--
-- Name: provider_types preserve_type_label; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER preserve_type_label BEFORE UPDATE ON public.provider_types FOR EACH ROW EXECUTE FUNCTION public.preserve_catalog_label();


--
-- Name: checklist_edits checklist_edits_requirement_id_provider_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.checklist_edits
    ADD CONSTRAINT checklist_edits_requirement_id_provider_id_fkey FOREIGN KEY (requirement_id, provider_id) REFERENCES public.requirements(id, provider_id) ON DELETE CASCADE;


--
-- Name: checklist_templates checklist_templates_provider_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.checklist_templates
    ADD CONSTRAINT checklist_templates_provider_type_id_fkey FOREIGN KEY (provider_type_id) REFERENCES public.provider_types(id) ON DELETE RESTRICT;


--
-- Name: providers providers_checklist_template_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.providers
    ADD CONSTRAINT providers_checklist_template_id_fkey FOREIGN KEY (checklist_template_id) REFERENCES public.checklist_templates(id) ON DELETE RESTRICT;


--
-- Name: requirements requirements_checklist_template_id_requirement_definition__fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.requirements
    ADD CONSTRAINT requirements_checklist_template_id_requirement_definition__fkey FOREIGN KEY (checklist_template_id, requirement_definition_id) REFERENCES public.template_requirements(checklist_template_id, requirement_definition_id) ON DELETE RESTRICT;


--
-- Name: requirements requirements_definition_owner; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.requirements
    ADD CONSTRAINT requirements_definition_owner FOREIGN KEY (requirement_definition_id) REFERENCES public.requirement_definitions(id) ON DELETE RESTRICT;


--
-- Name: requirements requirements_provider_id_checklist_template_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.requirements
    ADD CONSTRAINT requirements_provider_id_checklist_template_id_fkey FOREIGN KEY (provider_id, checklist_template_id) REFERENCES public.providers(id, checklist_template_id) ON DELETE CASCADE;


--
-- Name: requirements requirements_provider_owner; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.requirements
    ADD CONSTRAINT requirements_provider_owner FOREIGN KEY (provider_id) REFERENCES public.providers(id) ON DELETE CASCADE;


--
-- Name: review_decisions review_decisions_suggestion_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.review_decisions
    ADD CONSTRAINT review_decisions_suggestion_id_fkey FOREIGN KEY (suggestion_id) REFERENCES public.suggestions(id) ON DELETE CASCADE;


--
-- Name: suggestions suggestions_requirement_id_provider_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.suggestions
    ADD CONSTRAINT suggestions_requirement_id_provider_id_fkey FOREIGN KEY (requirement_id, provider_id) REFERENCES public.requirements(id, provider_id) ON DELETE CASCADE;


--
-- Name: suggestions suggestions_update_id_provider_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.suggestions
    ADD CONSTRAINT suggestions_update_id_provider_id_fkey FOREIGN KEY (update_id, provider_id) REFERENCES public.updates(id, provider_id) ON DELETE CASCADE;


--
-- Name: template_requirements template_requirements_checklist_template_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.template_requirements
    ADD CONSTRAINT template_requirements_checklist_template_id_fkey FOREIGN KEY (checklist_template_id) REFERENCES public.checklist_templates(id) ON DELETE CASCADE;


--
-- Name: template_requirements template_requirements_requirement_definition_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.template_requirements
    ADD CONSTRAINT template_requirements_requirement_definition_id_fkey FOREIGN KEY (requirement_definition_id) REFERENCES public.requirement_definitions(id) ON DELETE RESTRICT;


--
-- Name: update_ambiguities update_ambiguities_update_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.update_ambiguities
    ADD CONSTRAINT update_ambiguities_update_id_fkey FOREIGN KEY (update_id) REFERENCES public.updates(id) ON DELETE CASCADE;


--
-- Name: update_requirement_snapshots update_requirement_snapshots_requirement_id_provider_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.update_requirement_snapshots
    ADD CONSTRAINT update_requirement_snapshots_requirement_id_provider_id_fkey FOREIGN KEY (requirement_id, provider_id) REFERENCES public.requirements(id, provider_id) ON DELETE CASCADE;


--
-- Name: update_requirement_snapshots update_requirement_snapshots_update_id_provider_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.update_requirement_snapshots
    ADD CONSTRAINT update_requirement_snapshots_update_id_provider_id_fkey FOREIGN KEY (update_id, provider_id) REFERENCES public.updates(id, provider_id) ON DELETE CASCADE;


--
-- Name: updates updates_provider_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.updates
    ADD CONSTRAINT updates_provider_id_fkey FOREIGN KEY (provider_id) REFERENCES public.providers(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict dbmate


--
-- Dbmate schema migrations
--

INSERT INTO public.schema_migrations (version) VALUES
    ('20261111000100'),
    ('20261112000100'),
    ('20261114000100'),
    ('20261115000100'),
    ('20261122000100');
