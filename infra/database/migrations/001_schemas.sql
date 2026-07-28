-- 001: Create schemas
CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA IF NOT EXISTS app;
CREATE SCHEMA IF NOT EXISTS platform;

COMMENT ON SCHEMA app IS 'Business data — contracts, clients (DB agent read-only)';
COMMENT ON SCHEMA platform IS 'Agent runtime — checkpoints, audit, task DAG';
