-- 010: Accounts, login sessions and server-side chat history
--
-- Rerunnable: db_migrate.py replays every file on each run, so everything here is
-- IF NOT EXISTS and the feedback backfill only runs when the legacy user is absent
-- (i.e. the first time). Rollback: infra/database/rollback/010_auth_chat_history.down.sql
-- Note: db_migrate.py passes this file through sqlalchemy.text(), so never write a colon
-- directly followed by a word (bind-param syntax) in this file, comments included.

SET search_path TO platform;

CREATE TABLE IF NOT EXISTS users (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email                 VARCHAR(320) NOT NULL,
    display_name          VARCHAR(200) NOT NULL DEFAULT '',
    role                  VARCHAR(16) NOT NULL DEFAULT 'user',
    auth_provider         VARCHAR(32) NOT NULL DEFAULT 'local',
    password_hash         TEXT,
    is_active             BOOLEAN NOT NULL DEFAULT TRUE,
    must_change_password  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at         TIMESTAMPTZ,
    -- Named so a later SSO migration can DROP and re-add them by a stable name.
    CONSTRAINT ck_users_role CHECK (role IN ('user', 'admin')),
    CONSTRAINT ck_users_auth_provider CHECK (auth_provider IN ('local', 'system')),
    CONSTRAINT ck_users_local_has_password CHECK (auth_provider <> 'local' OR password_hash IS NOT NULL)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_users_email ON users (lower(email));

-- token_hash is the SHA-256 hex of the cookie token; the raw token is never stored.
CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash  CHAR(64) PRIMARY KEY,
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL,
    revoked_at  TIMESTAMPTZ,
    ip          VARCHAR(64),
    user_agent  VARCHAR(300)
);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions (user_id);

CREATE TABLE IF NOT EXISTS auth_login_attempts (
    id          BIGSERIAL PRIMARY KEY,
    email_norm  VARCHAR(320) NOT NULL,
    ip          VARCHAR(64) NOT NULL,
    succeeded   BOOLEAN NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_auth_attempts_email ON auth_login_attempts (email_norm, created_at);
CREATE INDEX IF NOT EXISTS idx_auth_attempts_ip ON auth_login_attempts (ip, created_at);

-- id is VARCHAR (not UUID) to stay byte-identical to the LangGraph thread_id / feedback.session_id.
-- owner_id is RESTRICT: users are deactivated, never deleted.
CREATE TABLE IF NOT EXISTS chat_sessions (
    id          VARCHAR(100) PRIMARY KEY,
    owner_id    UUID NOT NULL REFERENCES users(id),
    title       VARCHAR(200) NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_owner ON chat_sessions (owner_id, updated_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS chat_messages (
    id          BIGSERIAL PRIMARY KEY,
    session_id  VARCHAR(100) NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role        VARCHAR(16) NOT NULL,
    content     TEXT NOT NULL DEFAULT '',
    status      VARCHAR(16) NOT NULL DEFAULT 'completed',
    trace_id    VARCHAR(100),
    error       VARCHAR(200),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_chat_messages_role CHECK (role IN ('user', 'assistant')),
    CONSTRAINT ck_chat_messages_status CHECK (status IN ('completed', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages (session_id, id);

-- Makes the backfill and retried writes idempotent per (trace, role).
CREATE UNIQUE INDEX IF NOT EXISTS ux_chat_messages_trace_role
    ON chat_messages (trace_id, role) WHERE trace_id IS NOT NULL;

-- System users cannot log in (auth_provider = 'system', no password).
-- 'service' owns sessions created through X-API-Key.
INSERT INTO users (id, email, display_name, role, auth_provider, is_active)
VALUES ('00000000-0000-0000-0000-000000000002'::uuid, 'service@system.invalid', 'Service', 'admin', 'system', TRUE)
ON CONFLICT DO NOTHING;

-- feedback.created_at is nullable; NULL rows get the epoch (not now()) so the result is
-- deterministic and they sort as oldest rather than jumping to the newest turn.
-- Backfill feedback into chat history exactly once: only when 'legacy' does not exist yet.
-- Running it on every migrate would adopt feedback rows written after deploy into 'legacy'.
DO $$
DECLARE
    legacy_id CONSTANT uuid := '00000000-0000-0000-0000-000000000001'::uuid;
BEGIN
    IF EXISTS (SELECT 1 FROM users WHERE id = legacy_id) THEN
        RETURN;
    END IF;

    INSERT INTO users (id, email, display_name, role, auth_provider, is_active)
    VALUES (legacy_id, 'legacy@system.invalid', 'Legacy', 'user', 'system', FALSE)
    ON CONFLICT DO NOTHING;

    INSERT INTO chat_sessions (id, owner_id, title, created_at, updated_at)
    SELECT session_id,
           legacy_id,
           left(coalesce((array_agg(user_message ORDER BY coalesce(created_at, 'epoch'::timestamptz), id))[1], ''), 200),
           min(coalesce(created_at, 'epoch'::timestamptz)),
           max(coalesce(created_at, 'epoch'::timestamptz))
    FROM feedback
    WHERE session_id IS NOT NULL AND session_id <> ''
    GROUP BY session_id
    ON CONFLICT (id) DO NOTHING;

    INSERT INTO chat_messages (session_id, role, content, status, trace_id, created_at)
    SELECT f.session_id, m.role, coalesce(m.content, ''), 'completed', f.trace_id, coalesce(f.created_at, 'epoch'::timestamptz)
    FROM feedback f
    CROSS JOIN LATERAL (
        VALUES (1, 'user', f.user_message), (2, 'assistant', f.response)
    ) AS m(ord, role, content)
    WHERE f.session_id IS NOT NULL AND f.session_id <> ''
    ORDER BY coalesce(f.created_at, 'epoch'::timestamptz), f.id, m.ord
    ON CONFLICT (trace_id, role) WHERE trace_id IS NOT NULL DO NOTHING;
END
$$;
