-- 003: Platform tables (agent runtime)

SET search_path TO platform;

CREATE TABLE IF NOT EXISTS sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         VARCHAR(255) NOT NULL,
    slo_tier        VARCHAR(20) DEFAULT 'standard',
    topology_mode   VARCHAR(20),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS task_dag (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID REFERENCES sessions(id),
    task_id         VARCHAR(100) NOT NULL,
    agent           VARCHAR(100) NOT NULL,
    description     TEXT NOT NULL,
    status          VARCHAR(20) DEFAULT 'pending',
    depends_on      TEXT[],
    result_summary  TEXT,
    tokens_used     INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS audit_log (
    id              BIGSERIAL PRIMARY KEY,
    trace_id        VARCHAR(100) NOT NULL,
    session_id      UUID,
    user_id         VARCHAR(255),
    agent_name      VARCHAR(100),
    action          VARCHAR(50) NOT NULL,
    payload         JSONB,
    sql_executed    TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audit_trace ON audit_log(trace_id);
CREATE INDEX idx_audit_user ON audit_log(user_id);
CREATE INDEX idx_audit_created ON audit_log(created_at);
CREATE INDEX idx_task_dag_session ON task_dag(session_id);

-- LangGraph PostgresSaver tạo bảng checkpoints tự động qua checkpointer.setup()
