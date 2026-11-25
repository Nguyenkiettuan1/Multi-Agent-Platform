-- Rollback for 010_auth_chat_history.sql. NOT run by db_migrate.py (lives outside migrations/).
--
-- WARNING: DATA LOSS. Drops every account, login session, ownership link and failed chat turn.
-- Successful turns remain in platform.feedback. Back up first (PowerShell):
--   docker exec multiagent-postgres pg_dump -U multiagent -d multiagent -t platform.users -t platform.auth_sessions -t platform.auth_login_attempts -t platform.chat_sessions -t platform.chat_messages > D:\AI-project\_backup\ma-010-<date>.sql
-- Run:
--   Get-Content infra\database\rollback\010_auth_chat_history.down.sql | docker exec -i multiagent-postgres psql -U multiagent -d multiagent -v ON_ERROR_STOP=1
-- Re-applying 010 afterwards re-runs the backfill (the legacy user is gone).

SET search_path TO platform;

DROP TABLE IF EXISTS chat_messages;
DROP TABLE IF EXISTS chat_sessions;
DROP TABLE IF EXISTS auth_login_attempts;
DROP TABLE IF EXISTS auth_sessions;
DROP TABLE IF EXISTS users;
