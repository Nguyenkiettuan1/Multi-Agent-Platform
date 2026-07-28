-- 006: Feedback loop — self-improvement dataset

SET search_path TO platform;

CREATE TABLE IF NOT EXISTS feedback (
    id              BIGSERIAL PRIMARY KEY,
    trace_id        VARCHAR(100) NOT NULL,
    session_id      VARCHAR(100),
    user_message    TEXT,
    response        TEXT,
    rating          SMALLINT CHECK (rating BETWEEN 1 AND 5),
    comment         TEXT,
    eval_score      REAL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_feedback_trace ON feedback(trace_id);
CREATE INDEX IF NOT EXISTS idx_feedback_rating ON feedback(rating);
CREATE INDEX IF NOT EXISTS idx_feedback_created ON feedback(created_at);
