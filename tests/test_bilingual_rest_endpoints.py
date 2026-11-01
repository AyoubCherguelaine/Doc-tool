"""
Tests for bilingual REST endpoints on FastAPI server:
- POST /api/documents/{doc_id}/redaction
- POST /api/documents/{doc_id}/classifier
- POST /api/documents/{doc_id}/financial-statement
- POST /api/documents/{doc_id}/translation
- POST /api/documents/{doc_id}/anomaly-audit
- Capabilities reporting of all bilingual services
- Chat payload mode validation for bilingual modes
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from backend import server
from backend.agent.agents.base import AgentResult
from backend.auth import get_current_user
from backend.billing import billing_service
from backend.documents.pdf_loader import PageText, PDFDocument

USER = {"id": str(uuid.uuid4()), "name": "BilingualTester"}


@pytest.fixture(autouse=True)
def shared_document_query(monkeypatch):
    monkeypatch.setattr("backend.services.engine.query", lambda *args, **kwargs: server.query(*args, **kwargs))


@pytest.fixture
def client():
    server.app.dependency_overrides[get_current_user] = lambda: USER
    with TestClient(server.app) as client:
        yield client
    server.app.dependency_overrides.clear()


def test_capabilities_includes_bilingual_modes(client):
    res = client.get("/api/capabilities/agents")
    assert res.status_code == 200
    data = res.json()
    modes = [m["value"] for m in data.get("modes", [])]
    for expected in ["redaction", "classifier", "financial_statement", "translation", "anomaly_audit"]:
        assert expected in modes, f"Mode {expected} missing from /api/capabilities/agents"


@pytest.mark.parametrize(
    "endpoint,service_name",
    [
        ("/api/documents/doc-1/redaction", "redaction"),
        ("/api/documents/doc-1/classifier", "classifier"),
        ("/api/documents/doc-1/financial-statement", "financial_statement"),
        ("/api/documents/doc-1/translation", "translation"),
        ("/api/documents/doc-1/anomaly-audit", "anomaly_audit"),
    ],
)
def test_bilingual_endpoints_success(client, monkeypatch, endpoint, service_name):
    # Mock DB query for document ownership
    monkeypatch.setattr(
        server,
        "query",
        lambda sql, params=(), **kw: {"id": "doc-1", "original_filename": "invoice_saudi.pdf", "page_count": 2},
    )

    # Mock RAG bundle
    mock_bundle = MagicMock()
    mock_bundle.vector_store = MagicMock()
    mock_bundle.doc_id = "doc-1"
    text = {
        "redaction": "Contact: test@example.test",
        "classifier": "Tax Invoice",
        "financial_statement": "Revenue: SAR 100\nNet income: SAR 0",
        "translation": "Invoice 1: SAR 100",
        "anomaly_audit": "Subtotal: SAR 100\nVAT 20%: SAR 20\nTotal: SAR 120",
    }[service_name]
    mock_bundle.pdf_docs = [PDFDocument(name="invoice_saudi.pdf", pages=[PageText(1, text, "invoice_saudi.pdf", 1)])]
    monkeypatch.setattr(server.rag, "get_bundle", lambda doc_id: mock_bundle)

    # Mock agent execution
    mock_agent = MagicMock()
    mock_agent.run.return_value = AgentResult(
        response=json.dumps(
            {
                "redaction": {"redacted_text": "Contact: [REDACTED_EMAIL]", "findings": []},
                "classifier": {
                    "document_type": "invoice",
                    "language": "en",
                    "department": "finance",
                    "urgency": "normal",
                },
                "financial_statement": {"currency": "SAR", "metrics": {"revenue": 100, "net_income": 0}},
                "translation": {"translated_text": "فاتورة ١: SAR ١٠٠", "terminology_notes": []},
                "anomaly_audit": {"subtotal": 100, "tax_total": 20, "total": 120},
            }[service_name],
            ensure_ascii=False,
        ),
        success=True,
        iterations=2,
        steps=[{"step": 1, "action": service_name}],
    )
    monkeypatch.setattr(server.rag, "_build_agent", lambda bundle, model, mode, **kwargs: mock_agent)

    # Ensure company has credits
    account = billing_service.get_or_create_company(USER["id"], USER["name"])
    initial_credits = account.remaining_credits
    cost = billing_service.get_service_cost(service_name, model="gpt-4o")

    res = client.post(endpoint, json={"model": "gpt-4o"})
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["success"] is True
    assert data["service"] == service_name
    assert isinstance(data["data"], dict)
    assert data["validation"]["schemaValidated"] is True
    assert data["creditsDeducted"] == cost
    assert data["creditsRemaining"] == initial_credits - cost


@pytest.mark.parametrize(
    "endpoint,service_name",
    [
        ("/api/documents/doc-1/redaction", "redaction"),
        ("/api/documents/doc-1/classifier", "classifier"),
        ("/api/documents/doc-1/financial-statement", "financial_statement"),
        ("/api/documents/doc-1/translation", "translation"),
        ("/api/documents/doc-1/anomaly-audit", "anomaly_audit"),
    ],
)
def test_bilingual_endpoints_refund_on_failure(client, monkeypatch, endpoint, service_name):
    monkeypatch.setattr(
        server,
        "query",
        lambda sql, params=(), **kw: {"id": "doc-1", "original_filename": "error_sample.pdf", "page_count": 1},
    )
    mock_bundle = MagicMock()
    mock_bundle.vector_store = MagicMock()
    mock_bundle.doc_id = "doc-1"
    text = {
        "redaction": "Contact: test@example.test",
        "classifier": "Tax Invoice",
        "financial_statement": "Revenue: SAR 100\nNet income: SAR 0",
        "translation": "Invoice 1: SAR 100",
        "anomaly_audit": "Subtotal: SAR 100\nVAT 20%: SAR 20\nTotal: SAR 120",
    }[service_name]
    mock_bundle.pdf_docs = [PDFDocument(name="invoice_saudi.pdf", pages=[PageText(1, text, "invoice_saudi.pdf", 1)])]
    monkeypatch.setattr(server.rag, "get_bundle", lambda doc_id: mock_bundle)

    # Simulate agent failure
    mock_agent = MagicMock()
    mock_agent.run.return_value = AgentResult(
        response="Failed due to OCR unreadability",
        success=False,
        error="Unreadable scan",
        iterations=1,
    )
    monkeypatch.setattr(server.rag, "_build_agent", lambda bundle, model, mode, **kwargs: mock_agent)

    account = billing_service.get_or_create_company(USER["id"], USER["name"])
    balance_before = account.remaining_credits
    cost = billing_service.get_service_cost(service_name)

    res = client.post(endpoint, json={})
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is False
    assert data["creditsRefunded"] == cost
    assert data["creditsDeducted"] == 0
    assert data["creditsRemaining"] == balance_before


def test_bilingual_endpoint_doc_not_found(client, monkeypatch):
    monkeypatch.setattr(server, "query", lambda *a, **kw: None)
    res = client.post("/api/documents/unknown-id/redaction", json={})
    assert res.status_code == 404
