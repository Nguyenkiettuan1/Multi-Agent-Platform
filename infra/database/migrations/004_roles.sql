-- 004: Read-only role for DB agent (sql-mcp)

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'agent_reader') THEN
        CREATE ROLE agent_reader WITH LOGIN PASSWORD 'agent_reader_local';
    END IF;
END
$$;

GRANT USAGE ON SCHEMA app TO agent_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA app TO agent_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA app GRANT SELECT ON TABLES TO agent_reader;

-- Platform schema: only application service accounts (not agent_reader)
REVOKE ALL ON SCHEMA platform FROM agent_reader;
