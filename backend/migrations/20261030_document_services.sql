-- Add to the existing application database. No user/grant or OCR changes.

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
    PRIMARY KEY (company_id, operation_key)
);
CREATE INDEX IF NOT EXISTS service_operations_response_expiry
    ON docuchat.service_operations (response_expires_at) WHERE response IS NOT NULL;
CREATE TABLE IF NOT EXISTS docuchat.document_rule_sets (
    id UUID PRIMARY KEY,
    company_id TEXT NOT NULL,
    name TEXT NOT NULL,
    rules JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS document_rule_sets_company ON docuchat.document_rule_sets(company_id);
