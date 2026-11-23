-- migrate:up
CREATE EXTENSION IF NOT EXISTS vector VERSION '0.8.7';
DO $$ BEGIN
 IF (SELECT extversion FROM pg_extension WHERE extname='vector') <> '0.8.7' THEN
   RAISE EXCEPTION 'This migration requires pgvector 0.8.7';
 END IF;
END $$;
CREATE TABLE embedding_spaces (
    id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model text NOT NULL CHECK (btrim(model) <> ''),
    version text NOT NULL CHECK (btrim(version) <> ''),
    dimensions integer NOT NULL CHECK (dimensions BETWEEN 1 AND 16000),
    UNIQUE (model, version, dimensions), UNIQUE (id, dimensions)
);
COMMENT ON TABLE embedding_spaces IS 'Immutable identity for compatible embedding vectors.';
INSERT INTO embedding_spaces(model,version,dimensions) VALUES ('text-embedding-3-small','1',1536);
CREATE TABLE knowledge_state (
    singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
    revision bigint NOT NULL DEFAULT 0 CHECK(revision >= 0),
    active_space_id integer NOT NULL REFERENCES embedding_spaces ON DELETE RESTRICT
);
COMMENT ON TABLE knowledge_state IS 'Atomic published corpus revision and active vector space.';
CREATE INDEX knowledge_state_active_space ON knowledge_state(active_space_id);
INSERT INTO knowledge_state(active_space_id) SELECT id FROM embedding_spaces;

CREATE TABLE knowledge_documents (
    id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_key text NOT NULL UNIQUE CHECK (btrim(source_key) <> ''),
    title text NOT NULL CHECK(btrim(title) <> ''),
    source_kind text NOT NULL CHECK(source_kind IN ('official','internal')),
    publisher text NOT NULL CHECK(btrim(publisher) <> ''),
    original_url text,
    CHECK ((source_kind='official')=(original_url IS NOT NULL))
);
COMMENT ON TABLE knowledge_documents IS 'Immutable configured source identity and provenance.';
INSERT INTO knowledge_documents(source_key,title,source_kind,publisher)
VALUES ('internal-guide','Internal licensing guide','internal','Onboarding team');
CREATE TABLE requirement_knowledge_links (
    provider_type_id integer NOT NULL REFERENCES provider_types ON DELETE RESTRICT,
    requirement_definition_id integer NOT NULL REFERENCES requirement_definitions ON DELETE RESTRICT,
    topic text NOT NULL CHECK(btrim(topic)<>''),
    PRIMARY KEY (provider_type_id,requirement_definition_id,topic)
);
CREATE INDEX requirement_knowledge_definition ON requirement_knowledge_links(requirement_definition_id);
COMMENT ON TABLE requirement_knowledge_links IS 'Configured type and definition bindings for optional question context.';

CREATE FUNCTION configure_synthetic_knowledge_links() RETURNS void LANGUAGE sql AS $$
INSERT INTO requirement_knowledge_links(provider_type_id,requirement_definition_id,topic)
                SELECT DISTINCT t.id,d.id,b.topic FROM provider_types t
                JOIN checklist_templates c ON c.provider_type_id=t.id
                JOIN template_requirements m ON m.checklist_template_id=c.id
                JOIN requirement_definitions d ON m.requirement_definition_id=d.id
                JOIN (VALUES ('Hawaii dental license','dental'),('State NED license','ned')) b(name,topic)
                ON d.name=b.name WHERE t.name='Dentist' ON CONFLICT DO NOTHING;
$$;
SELECT configure_synthetic_knowledge_links();

CREATE TABLE knowledge_versions (
    id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id integer NOT NULL REFERENCES knowledge_documents ON DELETE RESTRICT,
    status text NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','published','superseded','withdrawn')),
    draft_revision integer NOT NULL DEFAULT 1 CHECK(draft_revision > 0),
    stated_revision text,
    original bytea NOT NULL CHECK(octet_length(original) BETWEEN 1 AND 16777216),
    checksum text GENERATED ALWAYS AS (encode(sha256(original),'hex')) STORED,
    media_type text NOT NULL CHECK(media_type IN ('text/plain','text/html','application/pdf')),
    text text NOT NULL CHECK(btrim(text) <> ''),
    retrieved_at timestamptz NOT NULL,
    reviewed_at timestamptz,
    effective_from date,
    effective_to date,
    CHECK(effective_from <= effective_to),
    CHECK((status='draft')=(reviewed_at IS NULL))
);
COMMENT ON TABLE knowledge_versions IS 'Draft or retained source bytes, effective dates and immutable published evidence.';
CREATE INDEX knowledge_versions_document ON knowledge_versions(document_id);
CREATE UNIQUE INDEX one_published_version ON knowledge_versions(document_id) WHERE status='published';
CREATE TABLE knowledge_scopes (
    version_id integer NOT NULL REFERENCES knowledge_versions ON DELETE RESTRICT,
    provider_type_id integer NOT NULL REFERENCES provider_types ON DELETE RESTRICT,
    jurisdiction text NOT NULL CHECK(btrim(jurisdiction) <> ''),
    topic text NOT NULL CHECK(btrim(topic) <> ''),
    PRIMARY KEY(version_id,provider_type_id,jurisdiction,topic)
);
CREATE INDEX knowledge_scope_type ON knowledge_scopes(provider_type_id);
COMMENT ON TABLE knowledge_scopes IS 'Reviewed version applicability by configured provider type, jurisdiction and topic.';
CREATE TABLE knowledge_review_issues (
    version_id integer NOT NULL REFERENCES knowledge_versions ON DELETE RESTRICT,
    issue text NOT NULL CHECK(btrim(issue) <> ''),
    PRIMARY KEY(version_id,issue)
);
COMMENT ON TABLE knowledge_review_issues IS 'Unresolved review issues that block publication.';
CREATE TABLE knowledge_chunks (
    id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    version_id integer NOT NULL REFERENCES knowledge_versions ON DELETE RESTRICT,
    section text NOT NULL CHECK(btrim(section) <> ''),
    page integer CHECK(page > 0),
    char_start integer NOT NULL CHECK(char_start >= 0),
    char_end integer NOT NULL,
    text text NOT NULL CHECK(btrim(text) <> ''),
    terms tsvector GENERATED ALWAYS AS (to_tsvector('english'::regconfig,text)) STORED,
    CHECK (char_end-char_start=char_length(text)),
    UNIQUE (version_id,char_start)
);
COMMENT ON TABLE knowledge_chunks IS 'Immutable published passages with offsets into the retained extraction.';
CREATE INDEX knowledge_chunk_terms ON knowledge_chunks USING gin(terms);
CREATE TABLE knowledge_embeddings (
    chunk_id integer NOT NULL REFERENCES knowledge_chunks ON DELETE RESTRICT,
    space_id integer NOT NULL,
    dimensions integer NOT NULL,
    embedding vector NOT NULL CHECK(vector_dims(embedding)=dimensions AND vector_norm(embedding)>0),
    FOREIGN KEY(space_id,dimensions) REFERENCES embedding_spaces(id,dimensions) ON DELETE RESTRICT,
    PRIMARY KEY(chunk_id,space_id)
);
COMMENT ON TABLE knowledge_embeddings IS 'A complete vector for a specific passage and compatible model space.';
CREATE INDEX knowledge_embeddings_space ON knowledge_embeddings(space_id);
CREATE INDEX knowledge_embeddings_dimensions ON knowledge_embeddings(dimensions);
CREATE TABLE knowledge_publications (
    id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    operation_id uuid NOT NULL UNIQUE,
    request_hash text NOT NULL CHECK(length(request_hash)=64),
    action text NOT NULL CHECK(action IN ('create','edit','publish','withdraw')),
    version_id integer NOT NULL REFERENCES knowledge_versions ON DELETE RESTRICT,
    draft_revision integer NOT NULL CHECK(draft_revision>0),
    corpus_revision bigint NOT NULL CHECK(corpus_revision>=0),
    superseded_version_id integer REFERENCES knowledge_versions ON DELETE RESTRICT,
    decided_at timestamptz NOT NULL DEFAULT now(),
    role text NOT NULL DEFAULT 'manager' CHECK(role='manager')
);
COMMENT ON TABLE knowledge_publications IS 'Immutable simulated Manager operation receipts including supersession history.';
CREATE INDEX knowledge_publications_version ON knowledge_publications(version_id);
CREATE INDEX knowledge_publications_superseded ON knowledge_publications(superseded_version_id);

CREATE FUNCTION knowledge_reject_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Retained knowledge evidence is immutable'; END $$;
CREATE TRIGGER immutable_documents BEFORE UPDATE OR DELETE ON knowledge_documents FOR EACH ROW EXECUTE FUNCTION knowledge_reject_change();
CREATE TRIGGER immutable_spaces BEFORE UPDATE OR DELETE ON embedding_spaces FOR EACH ROW EXECUTE FUNCTION knowledge_reject_change();
CREATE TRIGGER immutable_operations BEFORE UPDATE OR DELETE ON knowledge_publications FOR EACH ROW EXECUTE FUNCTION knowledge_reject_change();
CREATE TRIGGER immutable_embeddings BEFORE UPDATE OR DELETE ON knowledge_embeddings FOR EACH ROW EXECUTE FUNCTION knowledge_reject_change();

CREATE FUNCTION knowledge_freeze_version() RETURNS trigger LANGUAGE plpgsql AS $$
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
CREATE TRIGGER freeze_version BEFORE INSERT OR UPDATE OR DELETE ON knowledge_versions FOR EACH ROW EXECUTE FUNCTION knowledge_freeze_version();

CREATE FUNCTION knowledge_draft_children() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP <> 'INSERT' AND (SELECT status FROM knowledge_versions WHERE id=OLD.version_id FOR UPDATE) <> 'draft' THEN
    RAISE EXCEPTION 'Published evidence is immutable'; END IF;
 IF TG_OP <> 'DELETE' AND (SELECT status FROM knowledge_versions WHERE id=NEW.version_id FOR UPDATE) <> 'draft' THEN
    RAISE EXCEPTION 'Published evidence is immutable'; END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER draft_scopes BEFORE INSERT OR UPDATE OR DELETE ON knowledge_scopes FOR EACH ROW EXECUTE FUNCTION knowledge_draft_children();
CREATE TRIGGER draft_issues BEFORE INSERT OR UPDATE OR DELETE ON knowledge_review_issues FOR EACH ROW EXECUTE FUNCTION knowledge_draft_children();
CREATE TRIGGER draft_chunks BEFORE INSERT OR UPDATE OR DELETE ON knowledge_chunks FOR EACH ROW EXECUTE FUNCTION knowledge_draft_children();

-- migrate:down
DO $$ BEGIN
 IF EXISTS (SELECT FROM knowledge_versions) THEN RAISE EXCEPTION 'Retained source history requires a backup before rollback'; END IF;
END $$;
DROP FUNCTION configure_synthetic_knowledge_links();
DROP TABLE requirement_knowledge_links, knowledge_publications, knowledge_embeddings, knowledge_chunks, knowledge_review_issues, knowledge_scopes, knowledge_versions, knowledge_documents, knowledge_state, embedding_spaces;
DROP FUNCTION knowledge_freeze_version(), knowledge_draft_children(), knowledge_reject_change();
