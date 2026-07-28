-- 005: pgvector + knowledge base (RAG local = production pattern)

SET search_path TO app, public;

CREATE TABLE IF NOT EXISTS knowledge_documents (
    id          SERIAL PRIMARY KEY,
    doc_id      VARCHAR(100) NOT NULL UNIQUE,
    title       VARCHAR(500) NOT NULL DEFAULT '',
    content     TEXT NOT NULL,
    source      VARCHAR(100) DEFAULT 'internal',
    domain      VARCHAR(50) DEFAULT 'general',
    metadata    JSONB DEFAULT '{}',
    embedding   vector(1536),
    tsv         tsvector GENERATED ALWAYS AS (
        to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(content, ''))
    ) STORED,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_knowledge_tsv ON knowledge_documents USING gin(tsv);
CREATE INDEX IF NOT EXISTS idx_knowledge_domain ON knowledge_documents(domain);
CREATE INDEX IF NOT EXISTS idx_knowledge_source ON knowledge_documents(source);
