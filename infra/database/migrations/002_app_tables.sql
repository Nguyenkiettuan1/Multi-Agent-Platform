-- 002: Business tables (app schema)

SET search_path TO app;

CREATE TABLE IF NOT EXISTS clients (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(255) NOT NULL,
    tax_code    VARCHAR(50),
    email       VARCHAR(255),
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS contracts (
    id          SERIAL PRIMARY KEY,
    code        VARCHAR(50) NOT NULL UNIQUE,
    client_id   INTEGER REFERENCES clients(id),
    title       VARCHAR(500) NOT NULL,
    status      VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'expired', 'draft')),
    value_vnd   BIGINT DEFAULT 0,
    signed_at   DATE,
    expires_at  DATE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_contracts_status ON contracts(status);
CREATE INDEX IF NOT EXISTS idx_contracts_client ON contracts(client_id);
CREATE INDEX IF NOT EXISTS idx_clients_name ON clients(name);
