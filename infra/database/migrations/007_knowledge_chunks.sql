-- 007: Multi-chunk document support

SET search_path TO app, public;

ALTER TABLE knowledge_documents
    ADD COLUMN IF NOT EXISTS parent_doc_id VARCHAR(100),
    ADD COLUMN IF NOT EXISTS chunk_index INTEGER;

CREATE INDEX IF NOT EXISTS idx_knowledge_parent ON knowledge_documents(parent_doc_id);
