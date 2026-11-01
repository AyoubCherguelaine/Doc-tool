"""Real PostgreSQL concurrency/isolation tests against an explicitly isolated test cluster."""

import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import psycopg2
import pytest
from fastapi import HTTPException

from backend.services import persistence
from backend.services.persistence import OperationStore, operation_identity


@pytest.fixture
def pg_store(monkeypatch):
    dsn = os.getenv("DOCTOOL_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Set DOCTOOL_TEST_POSTGRES_DSN to an isolated PostgreSQL test database")
    if "/tmp/doctool-pg." not in dsn:
        pytest.fail("Persistence tests require the isolated /tmp/doctool-pg.* Unix socket cluster")

    @contextmanager
    def connect():
        conn = psycopg2.connect(dsn)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE SCHEMA IF NOT EXISTS docuchat")
            cur.execute(persistence.DDL)
            cur.execute("TRUNCATE docuchat.service_operations, docuchat.document_rule_sets")
    monkeypatch.setattr(persistence, "get_conn", connect)
    store = OperationStore()
    store._initialized = True
    return store, connect


def test_durable_concurrent_claim_replay_conflict_expiry(pg_store):
    store, connect = pg_store
    key, fingerprint = operation_identity("pipeline", "same-key", {"service": "invoice"})

    def claim(_):
        try:
            return store.claim("company", key, fingerprint)
        except HTTPException as exc:
            return exc.status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        claims = list(pool.map(claim, range(8)))
    assert claims.count(None) == 1
    assert claims.count(409) == 7
    store.complete("company", key, {"data": {"total": 120}, "creditsDeducted": 25})
    restarted_store = OperationStore()
    assert restarted_store.claim("company", key, fingerprint)["body"]["data"]["total"] == 120
    with pytest.raises(HTTPException) as mismatch:
        restarted_store.claim("company", key, "different")
    assert mismatch.value.status_code == 409
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE docuchat.service_operations SET response_expires_at=now()-interval '1 second'")
    restarted_store.purge_expired_results()
    with pytest.raises(HTTPException) as expired:
        restarted_store.claim("company", key, fingerprint)
    assert expired.value.status_code == 410
    # Same external key in a different company has an independent operation.
    assert store.claim("another-company", key, fingerprint) is None


def test_stale_pending_operation_cannot_charge_again(pg_store):
    store, connect = pg_store
    assert store.claim("company", "pending", "fp") is None
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE docuchat.service_operations SET created_at=now()-interval '10 days'")
    with pytest.raises(HTTPException) as pending:
        OperationStore().claim("company", "pending", "fp")
    assert pending.value.status_code == 409


def test_company_rule_set_crud_and_isolation(pg_store):
    store, _ = pg_store
    rule_id = "00000000-0000-0000-0000-000000000001"
    rule = {"field": "total", "operator": "lte", "value": 1000}
    store.save_rules("a", rule_id, "Approval threshold", [rule])
    assert store.get_rules("a", rule_id)["rules"] == [rule]
    assert store.list_rules("b") == []
    for operation in [
        lambda: store.get_rules("b", rule_id),
        lambda: store.delete_rules("b", rule_id),
        lambda: store.save_rules("b", rule_id, "stolen", []),
    ]:
        with pytest.raises(HTTPException) as forbidden:
            operation()
        assert forbidden.value.status_code == 404
    store.save_rules("a", rule_id, "Updated", [{**rule, "value": 500}])
    assert store.get_rules("a", rule_id)["rules"][0]["value"] == 500
    store.delete_rules("a", rule_id)
    assert store.list_rules("a") == []


def test_idempotency_fails_closed_when_database_unavailable(monkeypatch):
    @contextmanager
    def broken():
        raise OSError("database offline")
        yield  # pragma: no cover

    monkeypatch.setattr(persistence, "get_conn", broken)
    with pytest.raises(HTTPException) as failure:
        OperationStore().claim("company", "key", "fingerprint")
    assert failure.value.status_code == 503
