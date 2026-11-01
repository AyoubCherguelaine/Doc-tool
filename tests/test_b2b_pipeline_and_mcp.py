"""
Comprehensive Tests for B2B SaaS Pipeline Endpoints, Python SDK, and Model Context Protocol (MCP) Server.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from langchain_core.documents import Document

from backend import rag, server
from backend.documents.pdf_loader import PDFDocument, PageText
from backend.billing import INITIAL_TRIAL_CREDITS, billing_service
from backend.mcp.server import mcp_server
from backend.sdk.client import DocuChatClient, DocuChatError


@pytest.fixture
def client():
    return TestClient(server.app)


@pytest.fixture
def b2b_account():
    """Create a test company account with full credits."""
    user_id = str(uuid.uuid4())
    account = billing_service.get_or_create_company(user_id, company_name="Enterprise Pipeline Corp")
    return account


# ===========================================================================
# 1. B2B SaaS Pipeline API Tests (backend/v1/routes.py)
# ===========================================================================


def test_b2b_pricing_catalog(client):
    """Test retrieving B2B service pricing catalog."""
    resp = client.get("/api/v1/company/pricing")
    assert resp.status_code == 200
    data = resp.json()
    assert data["initialTrialCredits"] == INITIAL_TRIAL_CREDITS
    assert len(data["services"]) >= 10
    service_ids = [s["id"] for s in data["services"]]
    assert "invoice" in service_ids
    assert "contract" in service_ids


def test_b2b_list_models(client):
    """Test retrieving available models from models.json."""
    resp = client.get("/api/v1/models")
    assert resp.status_code == 200
    data = resp.json()
    assert data["object"] == "list"
    assert data["default_model"] in [m["id"] for m in data["data"]]
    assert len(data["data"]) >= 11
    ids = [m["id"] for m in data["data"]]
    assert "gpt-6-luna" in ids
    assert "gpt-4o-mini" in ids


def test_b2b_account_unauthorized(client):
    """Ensure accessing B2B endpoints without API key is rejected."""
    resp = client.get("/api/v1/company/account")
    assert resp.status_code == 401


def test_b2b_account_authorized(client, b2b_account):
    """Test authenticated company account access with X-API-Key."""
    resp = client.get(
        "/api/v1/company/account",
        headers={"X-API-Key": b2b_account.api_key},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["companyName"] == "Enterprise Pipeline Corp"
    assert data["remainingCredits"] == INITIAL_TRIAL_CREDITS
    assert data["planTier"] == "free_trial"


def test_b2b_raw_document_upload(client, b2b_account):
    """Test uploading raw document text directly into pipeline."""
    payload = {
        "content": "Invoice #INV-2026-991\nVendor: Global Tech\nTotal: $4,500.00\nPayment due in 30 days.",
        "filename": "pipeline_invoice.txt",
    }
    with patch("backend.rag.process_upload") as mock_upload:
        mock_upload.return_value = rag.UploadResult(5, 1, "test-doc-uuid-99")

        resp = client.post(
            "/api/v1/documents/upload",
            headers={"X-API-Key": b2b_account.api_key},
            json=payload,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["documentId"] == "test-doc-uuid-99"
        assert data["chunkCount"] == 5
        assert data["pageCount"] == 1


def test_b2b_multipart_document_upload(client, b2b_account):
    """Test uploading a file via multipart form-data."""
    file_bytes = b"Sample contract terms and liability clauses."
    files = {"file": ("contract.txt", file_bytes, "text/plain")}

    with patch("backend.rag.process_upload") as mock_upload:
        mock_upload.return_value = rag.UploadResult(8, 2, "test-doc-uuid-101")

        resp = client.post(
            "/api/v1/documents/upload",
            headers={"X-API-Key": b2b_account.api_key},
            files=files,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["documentId"] == "test-doc-uuid-101"


def test_b2b_documents_listing(client, b2b_account):
    """Test listing documents for company account."""
    with patch("backend.v1.routes.query") as mock_query:
        mock_query.return_value = [
            {
                "id": "doc-1",
                "original_filename": "invoice_1.pdf",
                "file_size": 2048,
                "mime_type": "application/pdf",
                "page_count": 3,
                "created_at": None,
            }
        ]
        resp = client.get(
            "/api/v1/documents",
            headers={"X-API-Key": b2b_account.api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["documents"][0]["filename"] == "invoice_1.pdf"


def test_b2b_search_chunks(client, b2b_account):
    """Test hybrid search chunks endpoint."""
    mock_bundle = MagicMock()
    mock_bundle.vector_store = MagicMock()
    mock_bundle.vector_store.search.return_value = [
        Document(
            page_content="Liability shall not exceed $1,000,000.",
            metadata={"start_page": 4, "chunk_index": 12, "source": "contract.pdf"},
        )
    ]

    with patch("backend.rag.get_bundle", return_value=mock_bundle):
        resp = client.get(
            "/api/v1/documents/doc-123/search",
            headers={"X-API-Key": b2b_account.api_key},
            params={"query": "liability limits", "top_k": 3},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["results"][0]["page"] == 4
        assert "Liability" in data["results"][0]["content"]


def test_b2b_pipeline_run_success_with_credits(client, b2b_account, monkeypatch):
    """Test running a Document AI agent via pipeline endpoint with credit deduction."""
    monkeypatch.setattr("backend.services.engine.query", lambda *args, **kwargs: {"id": "owned-document"})
    mock_bundle = MagicMock()
    mock_bundle.vector_store = MagicMock()
    mock_bundle.doc_id = "owned-document"
    mock_bundle.pdf_docs = [PDFDocument(name="invoice.pdf", pages=[PageText(1, "Vendor: Acme Inc\nTotal: 1250.00", "invoice.pdf", 1)])]

    mock_agent = MagicMock()
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.response = '{"vendor": "Acme Inc", "total": 1250.00}'
    mock_agent.run.return_value = mock_result

    with patch("backend.rag.get_bundle", return_value=mock_bundle), patch(
        "backend.rag._build_agent", return_value=mock_agent
    ):
        initial_balance = b2b_account.remaining_credits
        payload = {
            "document_id": "doc-invoice-44",
            "service": "invoice",
            "query": "Extract invoice line items",
            "output_format": "json",
        }
        resp = client.post(
            "/api/v1/pipeline/run",
            headers={"X-API-Key": b2b_account.api_key},
            json=payload,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["service"] == "invoice"
        assert data["creditsDeducted"] == 25
        assert data["creditsRemaining"] == initial_balance - 25
        assert data["data"]["vendor"] == "Acme Inc"
        assert data["data"]["total"] == 1250.00


def test_b2b_pipeline_run_failure_refunds_credits(client, b2b_account, monkeypatch):
    """Ensure failed pipeline executions automatically refund deducted credits."""
    monkeypatch.setattr("backend.services.engine.query", lambda *args, **kwargs: {"id": "owned-document"})
    mock_bundle = MagicMock()
    mock_bundle.vector_store = MagicMock()
    mock_bundle.doc_id = "owned-document"
    mock_bundle.pdf_docs = [PDFDocument(name="invoice.pdf", pages=[PageText(1, "Vendor: Acme Inc\nTotal: 1250.00", "invoice.pdf", 1)])]

    mock_agent = MagicMock()
    mock_result = MagicMock()
    mock_result.success = False
    mock_result.error = "LLM rate limit reached"
    mock_result.response = ""
    mock_agent.run.return_value = mock_result

    initial_balance = b2b_account.remaining_credits

    with patch("backend.rag.get_bundle", return_value=mock_bundle), patch(
        "backend.rag._build_agent", return_value=mock_agent
    ):
        payload = {
            "document_id": "doc-contract-99",
            "service": "contract",
        }
        resp = client.post(
            "/api/v1/pipeline/run",
            headers={"X-API-Key": b2b_account.api_key},
            json=payload,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "failed"
        assert data["creditsDeducted"] == 0
        assert data["creditsRefunded"] == 35
        # Verify credits were restored
        assert b2b_account.remaining_credits == initial_balance


def test_chatgpt_actions_openapi(client):
    """Test OpenAPI schema generated specifically for ChatGPT Custom GPT Actions."""
    resp = client.get("/api/v1/gpt/openapi.json")
    assert resp.status_code == 200
    data = resp.json()
    assert data["openapi"] == "3.1.0"
    assert "paths" in data
    assert "/documents" in data["paths"]
    assert "/pipeline/run" in data["paths"]
    assert "ApiKeyAuth" in data["components"]["securitySchemes"]


def test_openai_tools_spec(client):
    """Test OpenAI Function Calling schema list for GPT chat bots."""
    resp = client.get("/api/v1/openai/tools")
    assert resp.status_code == 200
    data = resp.json()
    assert "tools" in data
    tool_names = [t["function"]["name"] for t in data["tools"]]
    assert "docuchat_list_documents" in tool_names
    assert "docuchat_extract_invoice" in tool_names
    assert "docuchat_analyze_contract" in tool_names


# ===========================================================================
# 2. Enterprise Python SDK Tests (backend/sdk/client.py)
# ===========================================================================


def test_python_sdk_initialization():
    """Test SDK client initialization and header configuration."""
    sdk = DocuChatClient(api_key="docu_live_test_123", base_url="http://localhost:8000")
    assert sdk.headers["X-API-Key"] == "docu_live_test_123"
    assert sdk.base_url == "http://localhost:8000"


def test_python_sdk_upload_text_mocked():
    """Test client.upload_text calling API."""
    sdk = DocuChatClient(api_key="docu_live_test_123")
    mock_resp = {"status": "success", "documentId": "doc-sdk-1", "chunkCount": 3}

    with patch.object(sdk, "_request", return_value=mock_resp) as mock_req:
        res = sdk.upload_text("Simple document text", filename="memo.txt")
        assert res["documentId"] == "doc-sdk-1"
        mock_req.assert_called_once_with(
            "POST",
            "/api/v1/documents/upload",
            json_data={"content": "Simple document text", "filename": "memo.txt"},
        )


def test_python_sdk_extract_invoice_mocked():
    """Test specialized SDK helper method extract_invoice."""
    sdk = DocuChatClient(api_key="docu_live_test_123")
    mock_resp = {
        "status": "success",
        "data": {"vendor": "Stripe", "total": 99.00},
    }

    with patch.object(sdk, "run_pipeline", return_value=mock_resp) as mock_run:
        res = sdk.extract_invoice("doc-inv-1")
        assert res["data"]["vendor"] == "Stripe"
        mock_run.assert_called_once_with(
            "doc-inv-1", service="invoice", query=None, output_format="json"
        )


def test_python_sdk_error_handling():
    """Test DocuChatError when API responds with error status."""
    sdk = DocuChatClient(api_key="invalid_key")
    with patch("httpx.Client.request") as mock_req:
        mock_resp = MagicMock()
        mock_resp.is_error = True
        mock_resp.status_code = 401
        mock_resp.json.return_value = {"detail": "Invalid or inactive company API key."}
        mock_req.return_value = mock_resp

        with pytest.raises(DocuChatError) as exc_info:
            sdk.get_account()
        assert exc_info.value.status_code == 401
        assert "Invalid or inactive" in str(exc_info.value)


# ===========================================================================
# 3. Model Context Protocol (MCP) Server Tests (backend/mcp/server.py)
# ===========================================================================


@pytest.mark.asyncio
async def test_mcp_server_tools_registered():
    """Verify MCP tools are registered with valid schemas."""
    tools = await mcp_server.list_tools()
    tool_names = [t.name for t in tools]

    expected = [
        "docuchat_list_documents",
        "docuchat_upload_document",
        "docuchat_search_chunks",
        "docuchat_query_document",
        "docuchat_extract_invoice",
        "docuchat_analyze_contract",
        "docuchat_audit_compliance",
        "docuchat_parse_form",
        "docuchat_summarize_document",
        "docuchat_compare_documents",
        "docuchat_get_company_credits",
    ]
    for exp in expected:
        assert exp in tool_names, f"Expected MCP tool '{exp}' not found."


@pytest.mark.asyncio
async def test_mcp_server_resources_registered():
    """Verify MCP resources are available."""
    resources = await mcp_server.list_resources()
    uris = [r.uri for r in resources]
    assert "docuchat://documents" in uris
    assert "docuchat://pricing" in uris

    content = await mcp_server.read_resource("docuchat://pricing")
    assert len(content) > 0
    parsed = json.loads(content[0].content)
    assert parsed["initialCredits"] == INITIAL_TRIAL_CREDITS


@pytest.mark.asyncio
async def test_mcp_server_prompts_registered():
    """Verify MCP prompt templates are registered."""
    prompts = await mcp_server.list_prompts()
    prompt_names = [p.name for p in prompts]
    assert "analyze_financial_document" in prompt_names
    assert "review_legal_contract" in prompt_names
    assert "audit_document_compliance" in prompt_names
    assert "executive_document_summary" in prompt_names

    p_result = await mcp_server.get_prompt("review_legal_contract", {"document_id": "contract-123"})
    assert "contract-123" in p_result.messages[0].content.text


@pytest.mark.asyncio
async def test_mcp_call_credits_tool():
    """Test calling docuchat_get_company_credits tool."""
    res = await mcp_server.call_tool("docuchat_get_company_credits", {})
    assert not res.is_error
    text_content = res.content[0].text
    data = json.loads(text_content)
    assert "remainingCredits" in data
    assert "pricing" in data
    assert data["pricing"]["invoice"] == 25


def test_upload_document_enforces_max_pages(client):
    """Verify uploading a document with max_pages rejects documents exceeding page limit."""
    from backend.auth import get_current_user
    server.app.dependency_overrides[get_current_user] = lambda: {"id": "test-user-1", "name": "Test"}
    try:
        files = {"file": ("large_doc.txt", b"Page 1\nPage 2\nPage 3\nPage 4\n", "text/plain")}
        with patch("backend.rag.process_upload") as mock_upload:
            mock_upload.return_value = rag.UploadResult(10, 5, "doc-large-uuid")

            resp = client.post(
                "/api/documents/upload",
                files=files,
                data={"max_pages": 3},
            )
            assert resp.status_code == 422
            assert "exceeds the maximum limit of 3 pages" in resp.json()["detail"]
    finally:
        server.app.dependency_overrides.pop(get_current_user, None)
