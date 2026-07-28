-- 009: Feedback promotion to RAG knowledge base

SET search_path TO platform;

ALTER TABLE feedback
    ADD COLUMN IF NOT EXISTS promoted_to_rag BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS promoted_doc_id VARCHAR(100);

CREATE INDEX IF NOT EXISTS idx_feedback_promoted ON feedback(promoted_to_rag);
