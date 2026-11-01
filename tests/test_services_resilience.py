"""
Tests for Services Resilience, Error Handling, Downtime Escapes, and Credit Refunds.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from langchain_core.documents import Document

from backend import server
from backend.agent.agents.base import AgentResult, BaseAgent, BaseAgentConfig
from backend.agent.agents.comparison import ComparisonAgent
from backend.agent.tools.enhanced import EnhancedDocumentKit
from backend.agent.tools.registry import ToolRegistry
from backend.auth import get_current_user
from backend.billing import (
    INITIAL_TRIAL_CREDITS,
    SERVICE_PRICING,
    CompanyBillingService,
    billing_service,
)
from backend.documents.pdf_loader import PageText, PDFDocument

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def shared_document_query(monkeypatch):
    # Existing endpoint tests patch server.query for ownership. The shared executor
    # performs the same ownership query in its own module.
    monkeypatch.setattr("backend.services.engine.query", lambda *args, **kwargs: server.query(*args, **kwargs))


@pytest.fixture
def mock_user():
    return {"id": str(uuid.uuid4()), "name": "ResilienceTester"}


@pytest.fixture
def client(mock_user):
    server.app.dependency_overrides[get_current_user] = lambda: mock_user
    with TestClient(server.app) as c:
        yield c
    server.app.dependency_overrides.clear()


def make_mock_pdf(name: str = "doc1.pdf", num_pages: int = 3) -> PDFDocument:
    pages = [
        PageText(i, f"Content for {name} on page {i}. Detailed clause and policy notes.", name, num_pages)
        for i in range(1, num_pages + 1)
    ]
    doc = PDFDocument(name=name, pages=pages)
    doc.full_text = "\n".join(p.text for p in pages)
    return doc


# ---------------------------------------------------------------------------
# EnhancedDocumentKit Tests (Parity and Resilience)
# ---------------------------------------------------------------------------


def test_enhanced_kit_registers_all_comparison_and_helper_tools():
    mock_vs = MagicMock()
    doc1 = make_mock_pdf("contract_a.pdf")
    doc2 = make_mock_pdf("contract_b.pdf")
    kit = EnhancedDocumentKit(vector_store=mock_vs, documents=[doc1, doc2])

    reg = ToolRegistry()
    kit.register_all(reg)

    names = set(reg.tool_names)
    assert "compare_documents" in names
    assert "read_pages" in names
    assert "summarize" in names
    assert "get_metadata" in names
    assert "search_documents" in names
    assert "read_page" in names
    assert "list_documents" in names


def test_enhanced_kit_compare_documents_multi_doc():
    mock_vs = MagicMock()
    mock_vs.search.return_value = [
        Document(page_content="Liability is capped at $1M", metadata={"doc_name": "contract_a.pdf", "start_page": 2}),
        Document(page_content="Liability is capped at $5M", metadata={"doc_name": "contract_b.pdf", "start_page": 4}),
    ]
    doc1 = make_mock_pdf("contract_a.pdf")
    doc2 = make_mock_pdf("contract_b.pdf")
    kit = EnhancedDocumentKit(vector_store=mock_vs, documents=[doc1, doc2])

    result = kit.compare_documents("liability cap")
    assert "contract_a.pdf" in result
    assert "contract_b.pdf" in result
    assert "$1M" in result
    assert "$5M" in result


def test_enhanced_kit_compare_documents_single_doc_graceful():
    mock_vs = MagicMock()
    mock_vs.search.return_value = [
        Document(page_content="Initial term is 1 year", metadata={"doc_name": "solo.pdf", "start_page": 1}),
        Document(page_content="Renewal term is 2 years", metadata={"doc_name": "solo.pdf", "start_page": 3}),
    ]
    doc = make_mock_pdf("solo.pdf")
    kit = EnhancedDocumentKit(vector_store=mock_vs, documents=[doc])

    result = kit.compare_documents("term length")
    assert "solo.pdf" in result
    assert "1 document matched" in result


def test_enhanced_kit_read_pages_and_summarize():
    doc = make_mock_pdf("guide.pdf", num_pages=4)
    kit = EnhancedDocumentKit(documents=[doc])

    pages_text = kit.read_pages("guide.pdf", 1, 2)
    assert "Page 1 of 4" in pages_text
    assert "Page 2 of 4" in pages_text

    summary = kit.summarize("Antigravity delivers advanced agents. Antigravity automates document tasks.")
    assert "•" in summary


# ---------------------------------------------------------------------------
# ComparisonAgent Tests
# ---------------------------------------------------------------------------


def test_comparison_agent_registers_compare_tool():
    mock_llm = MagicMock()
    kit = EnhancedDocumentKit()
    agent = ComparisonAgent(mock_llm, kit)
    assert "compare_documents" in agent.registry.tool_names


def test_comparison_agent_post_process_adds_markdown_header():
    mock_llm = MagicMock()
    kit = EnhancedDocumentKit()
    agent = ComparisonAgent(mock_llm, kit)
    raw = "The two documents diverge on governing law: California vs Delaware."
    out = agent._post_process(raw, [])
    assert out.startswith("## Comparison\n\n")
    assert "California vs Delaware" in out


# ---------------------------------------------------------------------------
# BaseAgent Fault Tolerance & Error Escaping
# ---------------------------------------------------------------------------


def test_base_agent_catches_unhandled_llm_exception():
    mock_llm = MagicMock()
    mock_llm.invoke.side_effect = ConnectionError("OpenAI API connection refused: provider down")

    kit = EnhancedDocumentKit()
    agent = BaseAgent(mock_llm, kit, config=BaseAgentConfig(max_iterations=3))

    # Should not raise an exception; must return AgentResult with error
    result = agent.run("What are the key terms?")
    assert result.success is False
    assert "LLM service" in (result.error or "")
    assert result.response != ""


def test_base_agent_retries_transient_llm_error():
    mock_llm = MagicMock()
    success_msg = MagicMock()
    success_msg.content = "THOUGHT: direct answer\nACTION: FINAL\nRESPONSE: Recovered answer."

    # Fails once with transient timeout, then succeeds
    mock_llm.invoke.side_effect = [TimeoutError("Gateway timeout"), success_msg]

    kit = EnhancedDocumentKit()
    agent = BaseAgent(mock_llm, kit, config=BaseAgentConfig(max_iterations=3))

    result = agent.run("test transient retry")
    assert result.success is True
    assert result.response == "Recovered answer."
    assert mock_llm.invoke.call_count == 2


def test_base_agent_catches_tool_execution_exception():
    mock_llm = MagicMock()
    resp1 = MagicMock()
    resp1.content = 'THOUGHT: use crashing tool\nACTION: crash_tool\nPARAMS: {}'
    resp2 = MagicMock()
    resp2.content = 'THOUGHT: done\nACTION: FINAL\nRESPONSE: Survived tool crash.'
    mock_llm.invoke.side_effect = [resp1, resp2]

    kit = EnhancedDocumentKit()
    agent = BaseAgent(mock_llm, kit, config=BaseAgentConfig(max_iterations=3, stop_after_no_action=False))

    from backend.agent.tools.registry import Tool

    def buggy_func():
        raise ZeroDivisionError("division by zero in tool")

    agent.registry.register(Tool(name="crash_tool", description="crashes", parameters={"type": "object", "properties": {}}, func=buggy_func))

    result = agent.run("execute crash tool")
    assert result.success is True
    assert result.response == "Survived tool crash."


# ---------------------------------------------------------------------------
# Billing & Credit Refund Resilience
# ---------------------------------------------------------------------------


def test_service_pricing_includes_comparison_and_factcheck():
    assert "comparison" in SERVICE_PRICING
    assert "factcheck" in SERVICE_PRICING
    assert billing_service.get_service_cost("comparison") == 30
    assert billing_service.get_service_cost("factcheck") == 20


def test_billing_refund_credits_restores_balance():
    billing = CompanyBillingService()
    account = billing.get_or_create_company("usr-123", "Acme")
    assert account.remaining_credits == INITIAL_TRIAL_CREDITS

    # Deduct 30 credits for comparison
    rem = billing.check_and_deduct_credits(account, "comparison", document_id="doc-1")
    assert rem == INITIAL_TRIAL_CREDITS - 30
    assert account.used_credits == 30

    # Service fails -> refund credits
    restored = billing.refund_credits(account, "comparison", credits_to_refund=30, document_id="doc-1", reason="LLM timed out")
    assert restored == INITIAL_TRIAL_CREDITS
    assert account.used_credits == 0

    # Check logs
    logs = billing.get_usage_logs(account.id)
    assert len(logs) == 2
    assert logs[0]["status"] == "refunded"
    assert logs[0]["creditsCost"] == -30


def test_billing_get_service_status_telemetry():
    status = billing_service.get_service_status()
    assert len(status) >= 14
    assert status["comparison"]["status"] == "operational"
    assert status["chat"]["status"] == "operational"
    assert status["coordinator"]["status"] == "operational"


# ---------------------------------------------------------------------------
# Server Endpoints Resilience & Health Checks
# ---------------------------------------------------------------------------


def test_health_check_returns_operational_services(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in {"ok", "degraded"}
    assert "services" in data
    assert "comparison" in data["services"]
    assert "factcheck" in data["services"]


def test_services_status_endpoint(client):
    res = client.get("/api/services/status")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["totalServices"] >= 14
    assert "comparison" in data["services"]


def test_company_service_refunds_credits_on_agent_failure(client, monkeypatch):
    account = billing_service.get_or_create_company("test-user-id")
    initial_credits = account.remaining_credits
    cost = billing_service.get_service_cost("comparison")

    # Mock DB query for document
    monkeypatch.setattr(server, "query", lambda *a, **kw: {"id": "doc-uuid", "original_filename": "test.pdf", "page_count": 1})

    # Mock rag bundle
    mock_bundle = MagicMock()
    mock_bundle.vector_store = MagicMock()
    monkeypatch.setattr(server.rag, "get_bundle", lambda doc_id: mock_bundle)

    # Mock agent that returns failure
    mock_agent = MagicMock()
    mock_agent.run.return_value = AgentResult(
        response="Failed to compare due to model rate limit.",
        success=False,
        error="429 RateLimitError",
        iterations=1,
    )
    monkeypatch.setattr(server.rag, "_build_agent", lambda bundle, model, mode, **kwargs: mock_agent)

    # Call /api/v1/services/comparison with company API key
    headers = {"X-API-Key": account.api_key}
    res = client.post(
        "/api/v1/services/comparison",
        headers=headers,
        json={"document_id": "doc-uuid", "query": "compare liabilities"},
    )

    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "failed"
    assert data["success"] is False
    assert data["creditsDeducted"] == 0
    assert data["creditsRefunded"] == cost
    assert data["creditsRemaining"] == initial_credits
    assert account.remaining_credits == initial_credits


def test_company_service_refunds_credits_on_unexpected_exception(client, monkeypatch):
    account = billing_service.get_or_create_company("test-user-id-2")
    initial_credits = account.remaining_credits

    monkeypatch.setattr(server, "query", lambda *a, **kw: {"id": "doc-uuid", "original_filename": "test.pdf", "page_count": 1})
    mock_bundle = MagicMock()
    mock_bundle.vector_store = MagicMock()
    monkeypatch.setattr(server.rag, "get_bundle", lambda doc_id: mock_bundle)

    # Mock agent that raises an unexpected exception
    mock_agent = MagicMock()
    mock_agent.run.side_effect = RuntimeError("Synthetic worker failure for refund test")
    monkeypatch.setattr(server.rag, "_build_agent", lambda bundle, model, mode, **kwargs: mock_agent)

    headers = {"X-API-Key": account.api_key}
    res = client.post(
        "/api/v1/services/invoice",
        headers=headers,
        json={"document_id": "doc-uuid", "query": "extract invoice"},
    )

    # All service adapters use the same failed-result envelope and refund policy.
    assert res.status_code == 200
    assert res.json()["success"] is False
    assert res.json()["creditsDeducted"] == 0
    assert res.json()["creditsRefunded"] > 0
    assert account.remaining_credits == initial_credits
