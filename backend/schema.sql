-- DocuChat backend database schema.
-- Run once against the PostgreSQL+pgvector database:
--   PGPASSWORD=docuchat123 psql -h 127.0.0.1 -p 5436 -U postgres -d docuchat -f backend/schema.sql

CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA IF NOT EXISTS docuchat;

-- Users (auth)
CREATE TABLE IF NOT EXISTS docuchat.users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email         TEXT UNIQUE NOT NULL,
    name          TEXT,
    password_hash TEXT NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT now()
);

-- Uploaded documents
CREATE TABLE IF NOT EXISTS docuchat.documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES docuchat.users(id) ON DELETE CASCADE,
    filename        TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    file_size       BIGINT NOT NULL,
    mime_type       TEXT NOT NULL,
    page_count      INT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- Chunk text + metadata (FAISS holds the embeddings on disk; this is for
-- listing, preview and index rebuild on server restart)
CREATE TABLE IF NOT EXISTS docuchat.chunks (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id   UUID NOT NULL REFERENCES docuchat.documents(id) ON DELETE CASCADE,
    page_index    INT,
    chunk_index   INT,
    text          TEXT NOT NULL,
    metadata      JSONB,
    created_at    TIMESTAMPTZ DEFAULT now()
);

-- Per-document chat sessions
CREATE TABLE IF NOT EXISTS docuchat.sessions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES docuchat.users(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES docuchat.documents(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);

-- Persisted chat messages
CREATE TABLE IF NOT EXISTS docuchat.messages (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES docuchat.sessions(id) ON DELETE CASCADE,
    role       TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content    TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_chunks_doc     ON docuchat.chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_msgs_session   ON docuchat.messages(session_id);
CREATE INDEX IF NOT EXISTS idx_sessions_doc   ON docuchat.sessions(document_id);
CREATE INDEX IF NOT EXISTS idx_sessions_user  ON docuchat.sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_docs_user      ON docuchat.documents(user_id);

-- Company Accounts (Free trial only, 300 initial credits, API key)
CREATE TABLE IF NOT EXISTS docuchat.company_accounts (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID NOT NULL UNIQUE REFERENCES docuchat.users(id) ON DELETE CASCADE,
    company_name   TEXT NOT NULL DEFAULT 'Enterprise Free Trial',
    plan_tier      TEXT NOT NULL DEFAULT 'free_trial',
    total_credits  INT NOT NULL DEFAULT 300,
    used_credits   INT NOT NULL DEFAULT 0,
    api_key        TEXT UNIQUE NOT NULL,
    api_key_prefix TEXT NOT NULL,
    is_active      BOOLEAN NOT NULL DEFAULT true,
    created_at     TIMESTAMPTZ DEFAULT now(),
    updated_at     TIMESTAMPTZ DEFAULT now()
);

-- Company API Usage & Audit Logs
CREATE TABLE IF NOT EXISTS docuchat.api_usage_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      UUID NOT NULL REFERENCES docuchat.company_accounts(id) ON DELETE CASCADE,
    service_name    TEXT NOT NULL,
    credits_cost    INT NOT NULL,
    document_id     TEXT,
    request_summary TEXT,
    status          TEXT NOT NULL DEFAULT 'success',
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_company_user   ON docuchat.company_accounts(user_id);
CREATE INDEX IF NOT EXISTS idx_company_apikey ON docuchat.company_accounts(api_key);
CREATE INDEX IF NOT EXISTS idx_usage_company  ON docuchat.api_usage_logs(company_id);

-- Validated services: durable request claims and company-specific rule sets.
-- Processing claims never expire automatically: recovery must establish whether
-- billing/execution occurred before releasing a claim after a process crash.
CREATE TABLE IF NOT EXISTS docuchat.service_operations (
    company_id TEXT NOT NULL,
    operation_key TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'processing',
    response JSONB,
    http_status INTEGER,
    response_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    PRIMARY KEY(company_id, operation_key)
);
CREATE INDEX IF NOT EXISTS service_operations_response_expiry
    ON docuchat.service_operations(response_expires_at) WHERE response IS NOT NULL;
CREATE TABLE IF NOT EXISTS docuchat.document_rule_sets (
    id UUID PRIMARY KEY,
    company_id TEXT NOT NULL,
    name TEXT NOT NULL,
    rules JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS document_rule_sets_company ON docuchat.document_rule_sets(company_id);
