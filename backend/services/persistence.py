"""PostgreSQL records for request deduplication and company document rules.

No in-memory fallback: when a caller requests idempotency, an unavailable ledger
must stop execution before charging, rather than risk executing twice.
"""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager

from fastapi import HTTPException
from psycopg2.extras import RealDictCursor

from backend.config import settings
from backend.db import get_conn

DDL = """
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
"""


class OperationStore:
    def __init__(self):
        self._initialized = False

    @contextmanager
    def cursor(self):
        try:
            with get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    if not self._initialized:
                        cursor.execute("SELECT pg_advisory_xact_lock(hashtext('docuchat-service-schema'))")
                        cursor.execute(DDL)
                    yield cursor
            self._initialized = True
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                503, "Service operation storage is unavailable. No automatic retry will execute a pending operation."
            ) from exc

    def claim(self, company: str, key: str, fingerprint: str):
        with self.cursor() as cur:
            cur.execute(
                "UPDATE docuchat.service_operations SET response = NULL WHERE response_expires_at < now() AND response IS NOT NULL"
            )
            cur.execute(
                """INSERT INTO docuchat.service_operations (company_id, operation_key, fingerprint)
                        VALUES (%s, %s, %s) ON CONFLICT DO NOTHING RETURNING operation_key""",
                (company, key, fingerprint),
            )
            if cur.fetchone():
                return None
            cur.execute(
                "SELECT * FROM docuchat.service_operations WHERE company_id=%s AND operation_key=%s", (company, key)
            )
            row = cur.fetchone()
            if row["fingerprint"] != fingerprint:
                raise HTTPException(409, "Idempotency key was already used with different request parameters")
            if row["status"] == "processing":
                raise HTTPException(
                    409, "Operation is already in progress; retry the same key later", headers={"Retry-After": "3"}
                )
            if row["response"] is None:
                raise HTTPException(
                    410,
                    "The stored result expired. This key will not run or charge again; use a new key for a new run.",
                )
            return {"body": row["response"], "status_code": row["http_status"]}

    def complete(self, company: str, key: str, body: dict, status_code: int = 200):
        with self.cursor() as cur:
            cur.execute(
                """UPDATE docuchat.service_operations SET status='completed', response=%s::jsonb,
                        http_status=%s, completed_at=now(), response_expires_at=now() + %s * interval '1 minute'
                        WHERE company_id=%s AND operation_key=%s AND status='processing'""",
                (
                    json.dumps(body, ensure_ascii=False, default=str),
                    status_code,
                    settings.DOC_TTL_MINUTES,
                    company,
                    key,
                ),
            )
            if cur.rowcount != 1:
                raise HTTPException(
                    503, "Operation completion could not be recorded; the operation remains protected against replay"
                )

    def purge_expired_results(self):
        with self.cursor() as cur:
            cur.execute(
                "UPDATE docuchat.service_operations SET response = NULL WHERE response_expires_at < now() AND response IS NOT NULL"
            )

    def save_rules(self, company: str, rule_id: str, name: str, rules: list[dict]):
        with self.cursor() as cur:
            cur.execute(
                """INSERT INTO docuchat.document_rule_sets(id, company_id, name, rules) VALUES(%s,%s,%s,%s::jsonb)
                        ON CONFLICT(id) DO UPDATE SET name=EXCLUDED.name, rules=EXCLUDED.rules, updated_at=now()
                        WHERE docuchat.document_rule_sets.company_id=EXCLUDED.company_id RETURNING id, name, rules""",
                (rule_id, company, name, json.dumps(rules, ensure_ascii=False)),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "Rule set not found")
            return dict(row)

    def get_rules(self, company: str, rule_id: str):
        with self.cursor() as cur:
            cur.execute(
                "SELECT id, name, rules FROM docuchat.document_rule_sets WHERE company_id=%s AND id=%s",
                (company, rule_id),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "Rule set not found")
            return dict(row)

    def list_rules(self, company: str):
        with self.cursor() as cur:
            cur.execute(
                "SELECT id, name, rules FROM docuchat.document_rule_sets WHERE company_id=%s ORDER BY updated_at DESC LIMIT 100",
                (company,),
            )
            return [dict(row) for row in cur.fetchall()]

    def delete_rules(self, company: str, rule_id: str):
        with self.cursor() as cur:
            cur.execute(
                "DELETE FROM docuchat.document_rule_sets WHERE company_id=%s AND id=%s RETURNING id", (company, rule_id)
            )
            if not cur.fetchone():
                raise HTTPException(404, "Rule set not found")


operation_store = OperationStore()


def operation_identity(namespace: str, key: str, payload: dict) -> tuple[str, str]:
    if not key.strip() or len(key) > 200:
        raise HTTPException(422, "Idempotency-Key must contain 1–200 characters")
    operation_key = hashlib.sha256(f"{namespace}:{key}".encode()).hexdigest()
    fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str, allow_nan=False).encode()
    ).hexdigest()
    return operation_key, fingerprint
