"""
Tests for Company Billing, API Keys, 300 Free Trial Credits, and LLM Usage Pricing.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from backend import server
from backend.documents.pdf_loader import PDFDocument, PageText
from backend.billing import (
    CompanyBillingService,
    InsufficientCreditsError,
    billing_service,
)


@pytest.fixture(autouse=True)
def shared_document_query(monkeypatch):
    # Existing endpoint tests patch server.query for ownership. The shared executor
    # performs the same ownership query in its own module.
    monkeypatch.setattr("backend.services.engine.query", lambda *args, **kwargs: server.query(*args, **kwargs))


@pytest.fixture
def fresh_billing():
    """Create an isolated CompanyBillingService instance for tests."""
    return CompanyBillingService()


def test_company_free_trial_initial_credits(fresh_billing):
    from backend.billing.service import INITIAL_TRIAL_CREDITS
    user_id = str(uuid.uuid4())
    account = fresh_billing.get_or_create_company(user_id, company_name="Acme Corp")
    assert account.total_credits == INITIAL_TRIAL_CREDITS
    assert account.used_credits == 0
    assert account.remaining_credits == INITIAL_TRIAL_CREDITS
    assert account.plan_tier == "free_trial"
    assert account.api_key.startswith("docu_live_")
    assert account.api_key_prefix.startswith("docu_live_")


def test_api_key_lookup(fresh_billing):
    user_id = str(uuid.uuid4())
    account = fresh_billing.get_or_create_company(user_id)
    key = account.api_key

    found = fresh_billing.get_company_by_api_key(key)
    assert found is not None
    assert found.id == account.id

    assert fresh_billing.get_company_by_api_key("invalid_key") is None


def test_credit_deduction_and_pricing(fresh_billing):
    user_id = str(uuid.uuid4())
    account = fresh_billing.get_or_create_company(user_id)

    # Check pricing based on LLM usage
    assert fresh_billing.get_service_cost("chat") == 1
    assert fresh_billing.get_service_cost("summary") == 10
    assert fresh_billing.get_service_cost("extraction") == 15
    assert fresh_billing.get_service_cost("receipt") == 20
    assert fresh_billing.get_service_cost("form_parser") == 20
    assert fresh_billing.get_service_cost("invoice") == 25
    assert fresh_billing.get_service_cost("resume") == 25
    assert fresh_billing.get_service_cost("compliance") == 30
    assert fresh_billing.get_service_cost("contract") == 35
    assert fresh_billing.get_service_cost("google_ai") == 40
    assert fresh_billing.get_service_cost("research") == 50

    # Deduct for invoice (25 credits)
    rem = fresh_billing.check_and_deduct_credits(account, "invoice", document_id="doc1")
    assert rem == 300 - 25
    assert account.remaining_credits == 275
    assert account.used_credits == 25

    # Deduct for contract (35 credits)
    rem2 = fresh_billing.check_and_deduct_credits(account, "contract", document_id="doc2")
    assert rem2 == 275 - 35
    assert account.remaining_credits == 240


def test_insufficient_credits_raises_error(fresh_billing):
    user_id = str(uuid.uuid4())
    account = fresh_billing.get_or_create_company(user_id)
    account.used_credits = 290  # 10 credits remaining

    # Contract requires 35 credits
    with pytest.raises(InsufficientCreditsError) as exc_info:
        fresh_billing.check_and_deduct_credits(account, "contract")
    assert "Required: 35" in str(exc_info.value)
    assert "Remaining: 10" in str(exc_info.value)


def test_regenerate_api_key(fresh_billing):
    user_id = str(uuid.uuid4())
    account = fresh_billing.get_or_create_company(user_id)
    old_key = account.api_key

    new_acc = fresh_billing.regenerate_api_key(user_id)
    assert new_acc.api_key != old_key
    assert fresh_billing.get_company_by_api_key(old_key) is None
    assert fresh_billing.get_company_by_api_key(new_acc.api_key) is not None


# ---------------------------------------------------------------------------
# API Endpoint Integration Tests
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    with TestClient(server.app) as c:
        yield c


def test_pricing_endpoint(client):
    res = client.get("/api/company/pricing")
    assert res.status_code == 200
    data = res.json()
    assert data["initialCredits"] == 300
    assert data["freeTrialAvailableOnly"] is True
    assert len(data["services"]) >= 10

    service_map = {s["id"]: s for s in data["services"]}
    assert service_map["invoice"]["credits"] == 25
    assert service_map["contract"]["credits"] == 35
    assert service_map["receipt"]["credits"] == 20
    assert service_map["compliance"]["credits"] == 30
    assert service_map["google_ai"]["credits"] == 40


def test_company_api_service_execution(client, monkeypatch):
    user_id = str(uuid.uuid4())
    account = billing_service.get_or_create_company(user_id)
    key = account.api_key

    # Mock DB query for document check
    doc_id = str(uuid.uuid4())
    monkeypatch.setattr(server, "query", lambda *a, **kw: {"id": doc_id, "original_filename": "invoice.pdf", "page_count": 2})

    # Mock RAG agent
    mock_bundle = MagicMock()
    mock_bundle.vector_store = MagicMock()
    mock_bundle.doc_id = doc_id
    mock_bundle.pdf_docs = [PDFDocument(name="source.pdf", pages=[PageText(1, "INV-100 Target Total: 500\nReceipt Total: 42.50", "source.pdf", 1)])]
    monkeypatch.setattr(server.rag, "get_bundle", lambda *a: mock_bundle)

    mock_agent = MagicMock()
    mock_agent.run.return_value = MagicMock(response='{"invoice_number": "INV-100", "total": 500}', success=True, iterations=2, steps=[])
    monkeypatch.setattr(server.rag, "_build_agent", lambda *a, **kw: mock_agent)

    # Call /api/v1/services/invoice with X-API-Key
    start_credits = account.remaining_credits
    res = client.post(
        "/api/v1/services/invoice",
        headers={"X-API-Key": key},
        json={"document_id": doc_id},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "success"
    assert body["service"] == "invoice"
    assert body["creditsDeducted"] == 25
    assert body["creditsRemaining"] == start_credits - 25
    assert res.headers["X-Credits-Cost"] == "25"
    assert res.headers["X-Credits-Remaining"] == str(start_credits - 25)


def test_company_api_insufficient_credits(client, monkeypatch):
    user_id = str(uuid.uuid4())
    account = billing_service.get_or_create_company(user_id)
    key = account.api_key
    account.used_credits = 300  # 0 remaining

    doc_id = str(uuid.uuid4())
    res = client.post(
        "/api/v1/services/invoice",
        headers={"X-API-Key": key},
        json={"document_id": doc_id},
    )

    assert res.status_code == 402
    assert "Insufficient credits" in res.json()["detail"]


def test_company_api_invalid_key(client):
    res = client.post(
        "/api/v1/services/invoice",
        headers={"X-API-Key": "docu_live_invalidkey123"},
        json={"document_id": "any"},
    )
    assert res.status_code == 401


def test_web_chat_deducts_company_credits(client, monkeypatch):
    user_id = str(uuid.uuid4())
    test_user = {"id": user_id, "name": "Web User"}
    from backend.auth import get_current_user
    server.app.dependency_overrides[get_current_user] = lambda: test_user

    account = billing_service.get_or_create_company(user_id, "Web User")
    assert account.remaining_credits == 300

    monkeypatch.setattr(server, "query", lambda *a, **kw: {"document_id": "doc123"})
    monkeypatch.setattr(server, "execute", lambda *a, **kw: None)
    monkeypatch.setattr(server.rag, "get_history", lambda *a: [])
    monkeypatch.setattr(server.rag, "stream_chat", lambda **kw: iter(["Test response"]))

    # Send chat message (conversational costs 1 credit)
    res = client.post(
        "/api/sessions/sess1/chat",
        json={"message": "What is in this doc?", "mode": "conversational"},
    )
    assert res.status_code == 200
    assert account.remaining_credits == 300 - 1

    # Exhaust remaining credits
    account.used_credits = 300
    res_exhausted = client.post(
        "/api/sessions/sess1/chat",
        json={"message": "Another question?", "mode": "conversational"},
    )
    assert res_exhausted.status_code == 402
    assert "credits depleted" in res_exhausted.json()["detail"].lower()

    server.app.dependency_overrides.clear()


def test_web_receipt_endpoint_deducts_company_credits(client, monkeypatch):
    user_id = str(uuid.uuid4())
    test_user = {"id": user_id, "name": "Receipt User"}
    from backend.auth import get_current_user
    server.app.dependency_overrides[get_current_user] = lambda: test_user

    account = billing_service.get_or_create_company(user_id, "Receipt User")
    assert account.remaining_credits == 300

    doc_id = str(uuid.uuid4())
    monkeypatch.setattr(server, "query", lambda *a, **kw: {"id": doc_id, "original_filename": "receipt.pdf", "page_count": 1})
    mock_bundle = MagicMock()
    mock_bundle.vector_store = MagicMock()
    mock_bundle.doc_id = doc_id
    mock_bundle.pdf_docs = [PDFDocument(name="source.pdf", pages=[PageText(1, "INV-100 Target Total: 500\nReceipt Total: 42.50", "source.pdf", 1)])]
    monkeypatch.setattr(server.rag, "get_bundle", lambda *a: mock_bundle)

    mock_agent = MagicMock()
    mock_agent.run.return_value = MagicMock(response='{"merchant": "Target", "total": 42.50}', success=True, iterations=1, steps=[])
    monkeypatch.setattr(server.rag, "_build_agent", lambda *a, **kw: mock_agent)

    res = client.post(f"/api/documents/{doc_id}/receipt", json={})
    assert res.status_code == 200
    body = res.json()
    assert body["creditsDeducted"] == 20
    assert body["creditsRemaining"] == 300 - 20
    assert account.remaining_credits == 280

    server.app.dependency_overrides.clear()

