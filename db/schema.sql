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

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: provider_types; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.provider_types (
    id uuid NOT NULL,
    name text NOT NULL,
    CONSTRAINT provider_types_name_check CHECK ((btrim(name) <> ''::text))
);


--
-- Name: providers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.providers (
    id uuid NOT NULL,
    provider_type_id uuid NOT NULL,
    name text NOT NULL,
    proposed_start_date date,
    CONSTRAINT providers_name_check CHECK ((btrim(name) <> ''::text))
);


--
-- Name: requirement_templates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.requirement_templates (
    id uuid NOT NULL,
    provider_type_id uuid NOT NULL,
    name text NOT NULL,
    CONSTRAINT requirement_templates_name_check CHECK ((btrim(name) <> ''::text))
);


--
-- Name: requirements; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.requirements (
    id uuid NOT NULL,
    provider_id uuid NOT NULL,
    provider_type_id uuid NOT NULL,
    source_template_id uuid,
    name text NOT NULL,
    status text NOT NULL,
    deadline date,
    scheduled_date date,
    version integer DEFAULT 0 NOT NULL,
    CONSTRAINT requirements_name_check CHECK ((btrim(name) <> ''::text)),
    CONSTRAINT requirements_status_check CHECK ((btrim(status) <> ''::text)),
    CONSTRAINT requirements_version_check CHECK ((version >= 0))
);


--
-- Name: review_decisions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.review_decisions (
    id uuid NOT NULL,
    suggestion_id uuid NOT NULL,
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
-- Name: schema_migrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.schema_migrations (
    version character varying NOT NULL
);


--
-- Name: suggestions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.suggestions (
    id uuid NOT NULL,
    update_id uuid NOT NULL,
    requirement_id uuid NOT NULL,
    provider_id uuid NOT NULL,
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
-- Name: updates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.updates (
    id uuid NOT NULL,
    request_id uuid NOT NULL,
    provider_id uuid NOT NULL,
    original_text text NOT NULL,
    provider_snapshot jsonb NOT NULL,
    processing_state text NOT NULL,
    message text NOT NULL,
    ambiguities jsonb DEFAULT '[]'::jsonb NOT NULL,
    failure_category text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    completed_at timestamp with time zone,
    CONSTRAINT updates_ambiguities_check CHECK ((jsonb_typeof(ambiguities) = 'array'::text)),
    CONSTRAINT updates_check CHECK (((processing_state = 'failed'::text) = (failure_category IS NOT NULL))),
    CONSTRAINT updates_failure_category_check CHECK ((failure_category = ANY (ARRAY['configuration'::text, 'timeout'::text, 'model'::text]))),
    CONSTRAINT updates_original_text_check CHECK ((btrim(original_text) <> ''::text)),
    CONSTRAINT updates_processing_state_check CHECK ((processing_state = ANY (ARRAY['processing'::text, 'completed'::text, 'failed'::text]))),
    CONSTRAINT updates_provider_snapshot_check CHECK ((jsonb_typeof(provider_snapshot) = 'object'::text))
);


--
-- Name: provider_types provider_types_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_types
    ADD CONSTRAINT provider_types_name_key UNIQUE (name);


--
-- Name: provider_types provider_types_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_types
    ADD CONSTRAINT provider_types_pkey PRIMARY KEY (id);


--
-- Name: providers providers_id_provider_type_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.providers
    ADD CONSTRAINT providers_id_provider_type_id_key UNIQUE (id, provider_type_id);


--
-- Name: providers providers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.providers
    ADD CONSTRAINT providers_pkey PRIMARY KEY (id);


--
-- Name: requirement_templates requirement_templates_id_provider_type_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.requirement_templates
    ADD CONSTRAINT requirement_templates_id_provider_type_id_key UNIQUE (id, provider_type_id);


--
-- Name: requirement_templates requirement_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.requirement_templates
    ADD CONSTRAINT requirement_templates_pkey PRIMARY KEY (id);


--
-- Name: requirement_templates requirement_templates_provider_type_id_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.requirement_templates
    ADD CONSTRAINT requirement_templates_provider_type_id_name_key UNIQUE (provider_type_id, name);


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
-- Name: requirements requirements_provider_id_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.requirements
    ADD CONSTRAINT requirements_provider_id_name_key UNIQUE (provider_id, name);


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
-- Name: suggestions_requirement; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX suggestions_requirement ON public.suggestions USING btree (requirement_id);


--
-- Name: suggestions_update; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX suggestions_update ON public.suggestions USING btree (update_id);


--
-- Name: updates_provider_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX updates_provider_created ON public.updates USING btree (provider_id, created_at, id);


--
-- Name: providers providers_provider_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.providers
    ADD CONSTRAINT providers_provider_type_id_fkey FOREIGN KEY (provider_type_id) REFERENCES public.provider_types(id);


--
-- Name: requirement_templates requirement_templates_provider_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.requirement_templates
    ADD CONSTRAINT requirement_templates_provider_type_id_fkey FOREIGN KEY (provider_type_id) REFERENCES public.provider_types(id);


--
-- Name: requirements requirements_provider_id_provider_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.requirements
    ADD CONSTRAINT requirements_provider_id_provider_type_id_fkey FOREIGN KEY (provider_id, provider_type_id) REFERENCES public.providers(id, provider_type_id);


--
-- Name: requirements requirements_source_template_id_provider_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.requirements
    ADD CONSTRAINT requirements_source_template_id_provider_type_id_fkey FOREIGN KEY (source_template_id, provider_type_id) REFERENCES public.requirement_templates(id, provider_type_id);


--
-- Name: review_decisions review_decisions_suggestion_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.review_decisions
    ADD CONSTRAINT review_decisions_suggestion_id_fkey FOREIGN KEY (suggestion_id) REFERENCES public.suggestions(id);


--
-- Name: suggestions suggestions_requirement_id_provider_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.suggestions
    ADD CONSTRAINT suggestions_requirement_id_provider_id_fkey FOREIGN KEY (requirement_id, provider_id) REFERENCES public.requirements(id, provider_id);


--
-- Name: suggestions suggestions_update_id_provider_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.suggestions
    ADD CONSTRAINT suggestions_update_id_provider_id_fkey FOREIGN KEY (update_id, provider_id) REFERENCES public.updates(id, provider_id);


--
-- Name: updates updates_provider_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.updates
    ADD CONSTRAINT updates_provider_id_fkey FOREIGN KEY (provider_id) REFERENCES public.providers(id);


--
-- PostgreSQL database dump complete
--

\unrestrict dbmate


--
-- Dbmate schema migrations
--

INSERT INTO public.schema_migrations (version) VALUES
    ('20261111000100');
