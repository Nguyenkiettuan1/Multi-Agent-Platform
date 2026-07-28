-- 008: One feedback row per chat trace (upsert by trace_id)

SET search_path TO platform;

-- Remove duplicate trace_ids if any (keep latest)
DELETE FROM feedback a
USING feedback b
WHERE a.trace_id = b.trace_id AND a.id < b.id;

CREATE UNIQUE INDEX IF NOT EXISTS idx_feedback_trace_unique ON feedback(trace_id);
