-- migrate:up
CREATE TABLE qa_runs (
    id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id uuid NOT NULL UNIQUE,
    provider_id integer NOT NULL REFERENCES providers ON DELETE CASCADE,
    provider_type_id integer NOT NULL REFERENCES provider_types ON DELETE RESTRICT,
    provider_name text NOT NULL CHECK (btrim(provider_name) <> ''),
    provider_type text NOT NULL CHECK (btrim(provider_type) <> ''),
    requirement_id integer,
    requirement_name text,
    topic_hint text,
    jurisdiction text NOT NULL CHECK (btrim(jurisdiction) <> ''),
    question text NOT NULL CHECK (btrim(question) <> '' AND char_length(question) <= 2000),
    as_of date NOT NULL,
    corpus_revision bigint NOT NULL CHECK (corpus_revision >= 0),
    embedding_space_id integer NOT NULL REFERENCES embedding_spaces ON DELETE RESTRICT,
    generation_model text CHECK (btrim(generation_model) <> ''),
    state text NOT NULL DEFAULT 'processing' CHECK (state IN ('processing','completed','failed')),
    outcome text CHECK (outcome IN ('supported','more_information_needed','conflicting_guidance','cannot_answer','service_unavailable')),
    explanation text CHECK (btrim(explanation) <> ''),
    missing_facts text CHECK (btrim(missing_facts) <> ''),
    conflict_explanation text CHECK (btrim(conflict_explanation) <> ''),
    failure_message text CHECK (btrim(failure_message) <> ''),
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    became_outdated boolean NOT NULL DEFAULT false,
    FOREIGN KEY (requirement_id,provider_id) REFERENCES requirements(id,provider_id) ON DELETE CASCADE,
    CHECK ((requirement_id IS NULL) = (requirement_name IS NULL)),
    CHECK (topic_hint IS NULL OR requirement_id IS NOT NULL),
    CHECK (
      (state='processing' AND completed_at IS NULL AND outcome IS NULL AND NOT became_outdated)
      OR (state='completed' AND completed_at IS NOT NULL AND outcome IS NOT NULL AND outcome<>'service_unavailable')
      OR (state='failed' AND completed_at IS NOT NULL AND outcome IS NOT DISTINCT FROM 'service_unavailable')
    ),
    CHECK ((state='failed') = (failure_message IS NOT NULL)),
    CHECK ((outcome IS NOT DISTINCT FROM 'more_information_needed') = (missing_facts IS NOT NULL)),
    CHECK ((outcome IS NOT DISTINCT FROM 'conflicting_guidance') = (conflict_explanation IS NOT NULL)),
    CHECK (explanation IS NULL OR (state='completed' AND outcome='cannot_answer'))
);
COMMENT ON TABLE qa_runs IS 'Captured read-only licensing questions with UUID receipts and immutable terminal outcomes.';
CREATE INDEX qa_runs_provider_created ON qa_runs(provider_id,created_at DESC,id DESC);
CREATE INDEX qa_runs_provider_type ON qa_runs(provider_type_id);
CREATE INDEX qa_runs_requirement ON qa_runs(requirement_id,provider_id);
CREATE INDEX qa_runs_space ON qa_runs(embedding_space_id);

CREATE TABLE qa_run_topics (
    run_id integer NOT NULL REFERENCES qa_runs ON DELETE CASCADE,
    topic text NOT NULL CHECK (btrim(topic) <> '' AND topic = lower(btrim(topic))),
    PRIMARY KEY (run_id,topic)
);
COMMENT ON TABLE qa_run_topics IS 'One applicable topic resolved at capture and retained for later eligibility checks.';

CREATE TABLE qa_corpus_versions (
    run_id integer NOT NULL REFERENCES qa_runs ON DELETE CASCADE,
    version_id integer NOT NULL REFERENCES knowledge_versions ON DELETE RESTRICT,
    PRIMARY KEY (run_id,version_id)
);
COMMENT ON TABLE qa_corpus_versions IS 'Eligible approved source version membership captured before outbound work.';
CREATE INDEX qa_corpus_versions_version ON qa_corpus_versions(version_id);

ALTER TABLE knowledge_chunks ADD UNIQUE (id,version_id);
CREATE TABLE qa_retrieved_chunks (
    run_id integer NOT NULL,
    chunk_id integer NOT NULL,
    version_id integer NOT NULL,
    keyword_rank integer CHECK (keyword_rank BETWEEN 1 AND 20),
    vector_rank integer CHECK (vector_rank BETWEEN 1 AND 20),
    fused_rank integer CHECK (fused_rank BETWEEN 1 AND 40),
    context_order integer CHECK (context_order BETWEEN 1 AND 12),
    PRIMARY KEY (run_id,chunk_id),
    FOREIGN KEY (run_id,version_id) REFERENCES qa_corpus_versions ON DELETE CASCADE,
    FOREIGN KEY (chunk_id,version_id) REFERENCES knowledge_chunks(id,version_id) ON DELETE RESTRICT,
    UNIQUE (run_id,keyword_rank),
    UNIQUE (run_id,vector_rank),
    UNIQUE (run_id,fused_rank),
    UNIQUE (run_id,context_order),
    UNIQUE (run_id,chunk_id,context_order),
    CHECK ((fused_rank IS NOT NULL) = (keyword_rank IS NOT NULL OR vector_rank IS NOT NULL)),
    CHECK (fused_rank IS NOT NULL OR context_order IS NOT NULL)
);
COMMENT ON TABLE qa_retrieved_chunks IS 'One fused candidate or adjacent context passage, with path ranks and optional generation context order.';
CREATE INDEX qa_retrieved_version ON qa_retrieved_chunks(version_id,run_id);
CREATE INDEX qa_retrieved_chunk ON qa_retrieved_chunks(chunk_id,version_id);

CREATE TABLE qa_claims (
    run_id integer NOT NULL REFERENCES qa_runs ON DELETE CASCADE,
    position integer NOT NULL CHECK (position BETWEEN 1 AND 12),
    text text NOT NULL CHECK (btrim(text) <> ''),
    PRIMARY KEY (run_id,position)
);
COMMENT ON TABLE qa_claims IS 'An ordered answer claim with separately retained supporting citations.';

CREATE TABLE qa_citations (
    run_id integer NOT NULL,
    claim_position integer NOT NULL,
    position integer NOT NULL CHECK (position BETWEEN 1 AND 8),
    chunk_id integer NOT NULL,
    context_order integer NOT NULL,
    quote text NOT NULL CHECK (btrim(quote) <> ''),
    quote_start integer NOT NULL CHECK (quote_start >= 0),
    quote_end integer NOT NULL,
    PRIMARY KEY (run_id,claim_position,position),
    FOREIGN KEY (run_id,claim_position) REFERENCES qa_claims ON DELETE CASCADE,
    FOREIGN KEY (run_id,chunk_id,context_order) REFERENCES qa_retrieved_chunks(run_id,chunk_id,context_order) ON DELETE CASCADE,
    UNIQUE (run_id,claim_position,chunk_id,quote_start,quote_end),
    CHECK (quote_end - quote_start = char_length(quote))
);
COMMENT ON TABLE qa_citations IS 'A claim’s exact end-exclusive, passage-relative quote from supplied generation context.';
CREATE INDEX qa_citations_chunk ON qa_citations(chunk_id,run_id,context_order);
CREATE INDEX qa_citations_claim ON qa_citations(claim_position);
CREATE INDEX qa_citations_context_order ON qa_citations(context_order);

CREATE FUNCTION qa_run_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP='INSERT' AND NEW.state='processing' THEN RETURN NEW; END IF;
    IF TG_OP='DELETE' AND NOT EXISTS (SELECT FROM providers WHERE id=OLD.provider_id) THEN
        RETURN OLD;
    END IF;
    IF TG_OP<>'UPDATE' OR OLD.state<>'processing' THEN
        RAISE EXCEPTION 'A retained answer can only leave processing once';
    END IF;
    IF NEW.state='processing' OR
        (to_jsonb(NEW) - ARRAY['state','outcome','completed_at','generation_model','explanation','missing_facts','conflict_explanation','failure_message','became_outdated'])
        IS DISTINCT FROM
        (to_jsonb(OLD) - ARRAY['state','outcome','completed_at','generation_model','explanation','missing_facts','conflict_explanation','failure_message','became_outdated']) THEN
        RAISE EXCEPTION 'Captured question identity is immutable';
    END IF;
    IF (NEW.outcome='supported' AND NOT EXISTS (SELECT FROM qa_claims WHERE run_id=NEW.id))
        OR (NEW.outcome IN ('cannot_answer','service_unavailable') AND EXISTS (SELECT FROM qa_claims WHERE run_id=NEW.id))
        OR EXISTS (
            SELECT FROM qa_claims c WHERE c.run_id=NEW.id AND NOT EXISTS (
                SELECT FROM qa_citations e WHERE e.run_id=c.run_id AND e.claim_position=c.position
            )
        ) THEN
        RAISE EXCEPTION 'Terminal claims require validated citation evidence';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER qa_run_guard BEFORE INSERT OR UPDATE OR DELETE ON qa_runs FOR EACH ROW EXECUTE FUNCTION qa_run_guard();

CREATE FUNCTION qa_evidence_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP='DELETE' AND NOT EXISTS (SELECT FROM qa_runs WHERE id=OLD.run_id) THEN
        RETURN OLD;
    END IF;
    IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'Retained question evidence is immutable'; END IF;
    IF (SELECT state FROM qa_runs WHERE id=NEW.run_id FOR UPDATE) <> 'processing' THEN
        RAISE EXCEPTION 'A terminal answer cannot acquire more evidence';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER qa_topic_guard BEFORE INSERT OR UPDATE OR DELETE ON qa_run_topics FOR EACH ROW EXECUTE FUNCTION qa_evidence_guard();
CREATE TRIGGER qa_corpus_guard BEFORE INSERT OR UPDATE OR DELETE ON qa_corpus_versions FOR EACH ROW EXECUTE FUNCTION qa_evidence_guard();
CREATE TRIGGER qa_retrieval_guard BEFORE INSERT OR UPDATE OR DELETE ON qa_retrieved_chunks FOR EACH ROW EXECUTE FUNCTION qa_evidence_guard();
CREATE TRIGGER qa_claim_guard BEFORE INSERT OR UPDATE OR DELETE ON qa_claims FOR EACH ROW EXECUTE FUNCTION qa_evidence_guard();
CREATE TRIGGER qa_citation_guard BEFORE INSERT OR UPDATE OR DELETE ON qa_citations FOR EACH ROW EXECUTE FUNCTION qa_evidence_guard();

CREATE FUNCTION qa_check_quote() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (SELECT substring(text FROM NEW.quote_start+1 FOR NEW.quote_end-NEW.quote_start)
        FROM knowledge_chunks WHERE id=NEW.chunk_id) IS DISTINCT FROM NEW.quote THEN
        RAISE EXCEPTION 'Citation quote must match its retained passage span';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER qa_check_quote BEFORE INSERT ON qa_citations FOR EACH ROW EXECUTE FUNCTION qa_check_quote();

-- migrate:down
DO $$ BEGIN
 IF EXISTS (SELECT FROM qa_runs) THEN RAISE EXCEPTION 'Retained answer history requires a backup before rollback'; END IF;
END $$;
DROP TABLE qa_citations, qa_claims, qa_retrieved_chunks, qa_corpus_versions, qa_run_topics, qa_runs;
ALTER TABLE knowledge_chunks DROP CONSTRAINT knowledge_chunks_id_version_id_key;
DROP FUNCTION qa_run_guard(), qa_evidence_guard(), qa_check_quote();
