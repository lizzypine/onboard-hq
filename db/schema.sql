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
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: EXTENSION vector; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';


--
-- Name: configure_synthetic_knowledge_links(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.configure_synthetic_knowledge_links() RETURNS void
    LANGUAGE sql
    AS $$
INSERT INTO requirement_knowledge_links(provider_type_id,requirement_definition_id,topic)
                SELECT DISTINCT t.id,d.id,b.topic FROM provider_types t
                JOIN checklist_templates c ON c.provider_type_id=t.id
                JOIN template_requirements m ON m.checklist_template_id=c.id
                JOIN requirement_definitions d ON m.requirement_definition_id=d.id
                JOIN (VALUES ('Hawaii dental license','dental'),('State NED license','ned')) b(name,topic)
                ON d.name=b.name WHERE t.name='Dentist' ON CONFLICT DO NOTHING;
$$;


--
-- Name: knowledge_draft_children(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.knowledge_draft_children() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
 IF TG_OP <> 'INSERT' AND (SELECT status FROM knowledge_versions WHERE id=OLD.version_id FOR UPDATE) <> 'draft' THEN
    RAISE EXCEPTION 'Published evidence is immutable'; END IF;
 IF TG_OP <> 'DELETE' AND (SELECT status FROM knowledge_versions WHERE id=NEW.version_id FOR UPDATE) <> 'draft' THEN
    RAISE EXCEPTION 'Published evidence is immutable'; END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 RETURN NEW;
END $$;


--
-- Name: knowledge_freeze_version(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.knowledge_freeze_version() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
 IF TG_OP='INSERT' THEN
   IF NEW.status='draft' THEN RETURN NEW; END IF;
   RAISE EXCEPTION 'A new source version must begin as a draft';
 END IF;
 IF OLD.status='draft' AND TG_OP='UPDATE' THEN
   IF NEW.status='draft' THEN RETURN NEW; END IF;
   IF NEW.status='published' AND EXISTS(SELECT FROM knowledge_scopes WHERE version_id=NEW.id)
      AND NOT EXISTS(SELECT FROM knowledge_review_issues WHERE version_id=NEW.id)
      AND EXISTS(SELECT FROM knowledge_chunks WHERE version_id=NEW.id)
      AND NOT EXISTS(SELECT FROM knowledge_chunks c WHERE c.version_id=NEW.id AND
         (substring(NEW.text FROM c.char_start+1 FOR c.char_end-c.char_start)<>c.text
          OR NOT EXISTS(SELECT FROM knowledge_embeddings e JOIN knowledge_state s ON s.active_space_id=e.space_id
             WHERE e.chunk_id=c.id))) THEN RETURN NEW; END IF;
   RAISE EXCEPTION 'Publication requires reviewed scopes, correct locators and complete active-space vectors';
 END IF;
 IF TG_OP='UPDATE' AND OLD.status='published' AND NEW.status IN ('withdrawn','superseded')
    AND (to_jsonb(OLD)-'status'-'checksum')=(to_jsonb(NEW)-'status'-'checksum') THEN RETURN NEW; END IF;
 RAISE EXCEPTION 'Retained knowledge version is immutable';
END $$;


--
-- Name: knowledge_reject_change(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.knowledge_reject_change() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN RAISE EXCEPTION 'Retained knowledge evidence is immutable'; END $$;


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
-- Name: embedding_spaces; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.embedding_spaces (
    id integer NOT NULL,
    model text NOT NULL,
    version text NOT NULL,
    dimensions integer NOT NULL,
    CONSTRAINT embedding_spaces_dimensions_check CHECK (((dimensions >= 1) AND (dimensions <= 16000))),
    CONSTRAINT embedding_spaces_model_check CHECK ((btrim(model) <> ''::text)),
    CONSTRAINT embedding_spaces_version_check CHECK ((btrim(version) <> ''::text))
);


--
-- Name: TABLE embedding_spaces; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.embedding_spaces IS 'Immutable identity for compatible embedding vectors.';


--
-- Name: embedding_spaces_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.embedding_spaces ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.embedding_spaces_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: knowledge_chunks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.knowledge_chunks (
    id integer NOT NULL,
    version_id integer NOT NULL,
    section text NOT NULL,
    page integer,
    char_start integer NOT NULL,
    char_end integer NOT NULL,
    text text NOT NULL,
    terms tsvector GENERATED ALWAYS AS (to_tsvector('english'::regconfig, text)) STORED,
    CONSTRAINT knowledge_chunks_char_start_check CHECK ((char_start >= 0)),
    CONSTRAINT knowledge_chunks_check CHECK (((char_end - char_start) = char_length(text))),
    CONSTRAINT knowledge_chunks_page_check CHECK ((page > 0)),
    CONSTRAINT knowledge_chunks_section_check CHECK ((btrim(section) <> ''::text)),
    CONSTRAINT knowledge_chunks_text_check CHECK ((btrim(text) <> ''::text))
);


--
-- Name: TABLE knowledge_chunks; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.knowledge_chunks IS 'Immutable published passages with offsets into the retained extraction.';


--
-- Name: knowledge_chunks_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.knowledge_chunks ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.knowledge_chunks_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: knowledge_documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.knowledge_documents (
    id integer NOT NULL,
    source_key text NOT NULL,
    title text NOT NULL,
    source_kind text NOT NULL,
    publisher text NOT NULL,
    original_url text,
    CONSTRAINT knowledge_documents_check CHECK (((source_kind = 'official'::text) = (original_url IS NOT NULL))),
    CONSTRAINT knowledge_documents_publisher_check CHECK ((btrim(publisher) <> ''::text)),
    CONSTRAINT knowledge_documents_source_key_check CHECK ((btrim(source_key) <> ''::text)),
    CONSTRAINT knowledge_documents_source_kind_check CHECK ((source_kind = ANY (ARRAY['official'::text, 'internal'::text]))),
    CONSTRAINT knowledge_documents_title_check CHECK ((btrim(title) <> ''::text))
);


--
-- Name: TABLE knowledge_documents; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.knowledge_documents IS 'Immutable configured source identity and provenance.';


--
-- Name: knowledge_documents_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.knowledge_documents ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.knowledge_documents_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: knowledge_embeddings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.knowledge_embeddings (
    chunk_id integer NOT NULL,
    space_id integer NOT NULL,
    dimensions integer NOT NULL,
    embedding public.vector NOT NULL,
    CONSTRAINT knowledge_embeddings_check CHECK (((public.vector_dims(embedding) = dimensions) AND (public.vector_norm(embedding) > (0)::double precision)))
);


--
-- Name: TABLE knowledge_embeddings; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.knowledge_embeddings IS 'A complete vector for a specific passage and compatible model space.';


--
-- Name: knowledge_publications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.knowledge_publications (
    id integer NOT NULL,
    operation_id uuid NOT NULL,
    request_hash text NOT NULL,
    action text NOT NULL,
    version_id integer NOT NULL,
    draft_revision integer NOT NULL,
    corpus_revision bigint NOT NULL,
    superseded_version_id integer,
    decided_at timestamp with time zone DEFAULT now() NOT NULL,
    role text DEFAULT 'manager'::text NOT NULL,
    CONSTRAINT knowledge_publications_action_check CHECK ((action = ANY (ARRAY['create'::text, 'edit'::text, 'publish'::text, 'withdraw'::text]))),
    CONSTRAINT knowledge_publications_corpus_revision_check CHECK ((corpus_revision >= 0)),
    CONSTRAINT knowledge_publications_draft_revision_check CHECK ((draft_revision > 0)),
    CONSTRAINT knowledge_publications_request_hash_check CHECK ((length(request_hash) = 64)),
    CONSTRAINT knowledge_publications_role_check CHECK ((role = 'manager'::text))
);


--
-- Name: TABLE knowledge_publications; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.knowledge_publications IS 'Immutable simulated Manager operation receipts including supersession history.';


--
-- Name: knowledge_publications_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.knowledge_publications ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.knowledge_publications_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: knowledge_review_issues; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.knowledge_review_issues (
    version_id integer NOT NULL,
    issue text NOT NULL,
    CONSTRAINT knowledge_review_issues_issue_check CHECK ((btrim(issue) <> ''::text))
);


--
-- Name: TABLE knowledge_review_issues; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.knowledge_review_issues IS 'Unresolved review issues that block publication.';


--
-- Name: knowledge_scopes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.knowledge_scopes (
    version_id integer NOT NULL,
    provider_type_id integer NOT NULL,
    jurisdiction text NOT NULL,
    topic text NOT NULL,
    CONSTRAINT knowledge_scopes_jurisdiction_check CHECK ((btrim(jurisdiction) <> ''::text)),
    CONSTRAINT knowledge_scopes_topic_check CHECK ((btrim(topic) <> ''::text))
);


--
-- Name: TABLE knowledge_scopes; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.knowledge_scopes IS 'Reviewed version applicability by configured provider type, jurisdiction and topic.';


--
-- Name: knowledge_state; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.knowledge_state (
    singleton boolean DEFAULT true NOT NULL,
    revision bigint DEFAULT 0 NOT NULL,
    active_space_id integer NOT NULL,
    CONSTRAINT knowledge_state_revision_check CHECK ((revision >= 0)),
    CONSTRAINT knowledge_state_singleton_check CHECK (singleton)
);


--
-- Name: TABLE knowledge_state; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.knowledge_state IS 'Atomic published corpus revision and active vector space.';


--
-- Name: knowledge_versions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.knowledge_versions (
    id integer NOT NULL,
    document_id integer NOT NULL,
    status text DEFAULT 'draft'::text NOT NULL,
    draft_revision integer DEFAULT 1 NOT NULL,
    stated_revision text,
    original bytea NOT NULL,
    checksum text GENERATED ALWAYS AS (encode(sha256(original), 'hex'::text)) STORED,
    media_type text NOT NULL,
    text text NOT NULL,
    retrieved_at timestamp with time zone NOT NULL,
    reviewed_at timestamp with time zone,
    effective_from date,
    effective_to date,
    CONSTRAINT knowledge_versions_check CHECK ((effective_from <= effective_to)),
    CONSTRAINT knowledge_versions_check1 CHECK (((status = 'draft'::text) = (reviewed_at IS NULL))),
    CONSTRAINT knowledge_versions_draft_revision_check CHECK ((draft_revision > 0)),
    CONSTRAINT knowledge_versions_media_type_check CHECK ((media_type = ANY (ARRAY['text/plain'::text, 'text/html'::text, 'application/pdf'::text]))),
    CONSTRAINT knowledge_versions_original_check CHECK (((octet_length(original) >= 1) AND (octet_length(original) <= 16777216))),
    CONSTRAINT knowledge_versions_status_check CHECK ((status = ANY (ARRAY['draft'::text, 'published'::text, 'superseded'::text, 'withdrawn'::text]))),
    CONSTRAINT knowledge_versions_text_check CHECK ((btrim(text) <> ''::text))
);


--
-- Name: TABLE knowledge_versions; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.knowledge_versions IS 'Draft or retained source bytes, effective dates and immutable published evidence.';


--
-- Name: knowledge_versions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.knowledge_versions ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.knowledge_versions_id_seq
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
-- Name: requirement_knowledge_links; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.requirement_knowledge_links (
    provider_type_id integer NOT NULL,
    requirement_definition_id integer NOT NULL,
    topic text NOT NULL,
    CONSTRAINT requirement_knowledge_links_topic_check CHECK ((btrim(topic) <> ''::text))
);


--
-- Name: TABLE requirement_knowledge_links; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.requirement_knowledge_links IS 'Configured type and definition bindings for optional question context.';


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
-- Name: embedding_spaces embedding_spaces_id_dimensions_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.embedding_spaces
    ADD CONSTRAINT embedding_spaces_id_dimensions_key UNIQUE (id, dimensions);


--
-- Name: embedding_spaces embedding_spaces_model_version_dimensions_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.embedding_spaces
    ADD CONSTRAINT embedding_spaces_model_version_dimensions_key UNIQUE (model, version, dimensions);


--
-- Name: embedding_spaces embedding_spaces_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.embedding_spaces
    ADD CONSTRAINT embedding_spaces_pkey PRIMARY KEY (id);


--
-- Name: knowledge_chunks knowledge_chunks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_chunks
    ADD CONSTRAINT knowledge_chunks_pkey PRIMARY KEY (id);


--
-- Name: knowledge_chunks knowledge_chunks_version_id_char_start_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_chunks
    ADD CONSTRAINT knowledge_chunks_version_id_char_start_key UNIQUE (version_id, char_start);


--
-- Name: knowledge_documents knowledge_documents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_documents
    ADD CONSTRAINT knowledge_documents_pkey PRIMARY KEY (id);


--
-- Name: knowledge_documents knowledge_documents_source_key_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_documents
    ADD CONSTRAINT knowledge_documents_source_key_key UNIQUE (source_key);


--
-- Name: knowledge_embeddings knowledge_embeddings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_embeddings
    ADD CONSTRAINT knowledge_embeddings_pkey PRIMARY KEY (chunk_id, space_id);


--
-- Name: knowledge_publications knowledge_publications_operation_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_publications
    ADD CONSTRAINT knowledge_publications_operation_id_key UNIQUE (operation_id);


--
-- Name: knowledge_publications knowledge_publications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_publications
    ADD CONSTRAINT knowledge_publications_pkey PRIMARY KEY (id);


--
-- Name: knowledge_review_issues knowledge_review_issues_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_review_issues
    ADD CONSTRAINT knowledge_review_issues_pkey PRIMARY KEY (version_id, issue);


--
-- Name: knowledge_scopes knowledge_scopes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_scopes
    ADD CONSTRAINT knowledge_scopes_pkey PRIMARY KEY (version_id, provider_type_id, jurisdiction, topic);


--
-- Name: knowledge_state knowledge_state_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_state
    ADD CONSTRAINT knowledge_state_pkey PRIMARY KEY (singleton);


--
-- Name: knowledge_versions knowledge_versions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_versions
    ADD CONSTRAINT knowledge_versions_pkey PRIMARY KEY (id);


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
-- Name: requirement_knowledge_links requirement_knowledge_links_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.requirement_knowledge_links
    ADD CONSTRAINT requirement_knowledge_links_pkey PRIMARY KEY (provider_type_id, requirement_definition_id, topic);


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
-- Name: knowledge_chunk_terms; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX knowledge_chunk_terms ON public.knowledge_chunks USING gin (terms);


--
-- Name: knowledge_embeddings_dimensions; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX knowledge_embeddings_dimensions ON public.knowledge_embeddings USING btree (dimensions);


--
-- Name: knowledge_embeddings_space; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX knowledge_embeddings_space ON public.knowledge_embeddings USING btree (space_id);


--
-- Name: knowledge_publications_superseded; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX knowledge_publications_superseded ON public.knowledge_publications USING btree (superseded_version_id);


--
-- Name: knowledge_publications_version; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX knowledge_publications_version ON public.knowledge_publications USING btree (version_id);


--
-- Name: knowledge_scope_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX knowledge_scope_type ON public.knowledge_scopes USING btree (provider_type_id);


--
-- Name: knowledge_state_active_space; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX knowledge_state_active_space ON public.knowledge_state USING btree (active_space_id);


--
-- Name: knowledge_versions_document; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX knowledge_versions_document ON public.knowledge_versions USING btree (document_id);


--
-- Name: one_published_version; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX one_published_version ON public.knowledge_versions USING btree (document_id) WHERE (status = 'published'::text);


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
-- Name: requirement_knowledge_definition; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX requirement_knowledge_definition ON public.requirement_knowledge_links USING btree (requirement_definition_id);


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
-- Name: knowledge_chunks draft_chunks; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER draft_chunks BEFORE INSERT OR DELETE OR UPDATE ON public.knowledge_chunks FOR EACH ROW EXECUTE FUNCTION public.knowledge_draft_children();


--
-- Name: knowledge_review_issues draft_issues; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER draft_issues BEFORE INSERT OR DELETE OR UPDATE ON public.knowledge_review_issues FOR EACH ROW EXECUTE FUNCTION public.knowledge_draft_children();


--
-- Name: knowledge_scopes draft_scopes; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER draft_scopes BEFORE INSERT OR DELETE OR UPDATE ON public.knowledge_scopes FOR EACH ROW EXECUTE FUNCTION public.knowledge_draft_children();


--
-- Name: knowledge_versions freeze_version; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER freeze_version BEFORE INSERT OR DELETE OR UPDATE ON public.knowledge_versions FOR EACH ROW EXECUTE FUNCTION public.knowledge_freeze_version();


--
-- Name: knowledge_documents immutable_documents; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER immutable_documents BEFORE DELETE OR UPDATE ON public.knowledge_documents FOR EACH ROW EXECUTE FUNCTION public.knowledge_reject_change();


--
-- Name: knowledge_embeddings immutable_embeddings; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER immutable_embeddings BEFORE DELETE OR UPDATE ON public.knowledge_embeddings FOR EACH ROW EXECUTE FUNCTION public.knowledge_reject_change();


--
-- Name: knowledge_publications immutable_operations; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER immutable_operations BEFORE DELETE OR UPDATE ON public.knowledge_publications FOR EACH ROW EXECUTE FUNCTION public.knowledge_reject_change();


--
-- Name: embedding_spaces immutable_spaces; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER immutable_spaces BEFORE DELETE OR UPDATE ON public.embedding_spaces FOR EACH ROW EXECUTE FUNCTION public.knowledge_reject_change();


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
-- Name: knowledge_chunks knowledge_chunks_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_chunks
    ADD CONSTRAINT knowledge_chunks_version_id_fkey FOREIGN KEY (version_id) REFERENCES public.knowledge_versions(id) ON DELETE RESTRICT;


--
-- Name: knowledge_embeddings knowledge_embeddings_chunk_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_embeddings
    ADD CONSTRAINT knowledge_embeddings_chunk_id_fkey FOREIGN KEY (chunk_id) REFERENCES public.knowledge_chunks(id) ON DELETE RESTRICT;


--
-- Name: knowledge_embeddings knowledge_embeddings_space_id_dimensions_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_embeddings
    ADD CONSTRAINT knowledge_embeddings_space_id_dimensions_fkey FOREIGN KEY (space_id, dimensions) REFERENCES public.embedding_spaces(id, dimensions) ON DELETE RESTRICT;


--
-- Name: knowledge_publications knowledge_publications_superseded_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_publications
    ADD CONSTRAINT knowledge_publications_superseded_version_id_fkey FOREIGN KEY (superseded_version_id) REFERENCES public.knowledge_versions(id) ON DELETE RESTRICT;


--
-- Name: knowledge_publications knowledge_publications_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_publications
    ADD CONSTRAINT knowledge_publications_version_id_fkey FOREIGN KEY (version_id) REFERENCES public.knowledge_versions(id) ON DELETE RESTRICT;


--
-- Name: knowledge_review_issues knowledge_review_issues_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_review_issues
    ADD CONSTRAINT knowledge_review_issues_version_id_fkey FOREIGN KEY (version_id) REFERENCES public.knowledge_versions(id) ON DELETE RESTRICT;


--
-- Name: knowledge_scopes knowledge_scopes_provider_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_scopes
    ADD CONSTRAINT knowledge_scopes_provider_type_id_fkey FOREIGN KEY (provider_type_id) REFERENCES public.provider_types(id) ON DELETE RESTRICT;


--
-- Name: knowledge_scopes knowledge_scopes_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_scopes
    ADD CONSTRAINT knowledge_scopes_version_id_fkey FOREIGN KEY (version_id) REFERENCES public.knowledge_versions(id) ON DELETE RESTRICT;


--
-- Name: knowledge_state knowledge_state_active_space_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_state
    ADD CONSTRAINT knowledge_state_active_space_id_fkey FOREIGN KEY (active_space_id) REFERENCES public.embedding_spaces(id) ON DELETE RESTRICT;


--
-- Name: knowledge_versions knowledge_versions_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_versions
    ADD CONSTRAINT knowledge_versions_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.knowledge_documents(id) ON DELETE RESTRICT;


--
-- Name: providers providers_checklist_template_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.providers
    ADD CONSTRAINT providers_checklist_template_id_fkey FOREIGN KEY (checklist_template_id) REFERENCES public.checklist_templates(id) ON DELETE RESTRICT;


--
-- Name: requirement_knowledge_links requirement_knowledge_links_provider_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.requirement_knowledge_links
    ADD CONSTRAINT requirement_knowledge_links_provider_type_id_fkey FOREIGN KEY (provider_type_id) REFERENCES public.provider_types(id) ON DELETE RESTRICT;


--
-- Name: requirement_knowledge_links requirement_knowledge_links_requirement_definition_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.requirement_knowledge_links
    ADD CONSTRAINT requirement_knowledge_links_requirement_definition_id_fkey FOREIGN KEY (requirement_definition_id) REFERENCES public.requirement_definitions(id) ON DELETE RESTRICT;


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
    ('20261122000100'),
    ('20261122000200');
