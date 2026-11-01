"""
Model Context Protocol (MCP) Server for DocuChat.

Exposes DocuChat's document intelligence, RAG search, specialized agents,
and enterprise billing to Claude Code, Claude Desktop, Cursor, and GPT chats.
Supports both stdio transport (CLI/desktop) and SSE transport (HTTP/FastAPI).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from fastapi.encoders import jsonable_encoder
from mcp.server import MCPServer

logger = logging.getLogger("docuchat.mcp")

# Initialize MCP Server instance
mcp_server = MCPServer(
    name="DOCTool",
    instructions=(
        "DOCTool Enterprise Document Intelligence MCP Server. "
        "Provides tools to upload, search, query, and extract structured data "
        "from enterprise documents (invoices, contracts, compliance/PII scans, forms, summaries)."
    ),
)


# ---------------------------------------------------------------------------
# Configuration & Backend Dispatcher
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = os.getenv("DOCUCHAT_BASE_URL", "http://127.0.0.1:8000")
DEFAULT_API_KEY = os.getenv("DOCUCHAT_API_KEY", "")


def _get_api_key() -> str:
    """Retrieve active API key from env or fallback company account."""
    key = os.getenv("DOCUCHAT_API_KEY", "").strip()
    if key:
        return key
    # Fallback to local default company account if available in-memory/db
    try:
        from backend.billing import billing_service

        acc = billing_service.get_or_create_company("00000000-0000-0000-0000-000000000001", "MCP Client")
        return acc.api_key
    except Exception:
        return "docu_live_default_trial_key"


def _is_http_server_reachable(base_url: str) -> bool:
    """Check if the DocuChat HTTP server is currently responding."""
    try:
        with httpx.Client(timeout=1.0) as client:
            resp = client.get(f"{base_url.rstrip('/')}/api/health")
            return resp.status_code == 200
    except Exception:
        return False


def _execute_service_inprocess(
    document_id: str,
    service_name: str,
    query: Optional[str] = None,
    options: Optional[Dict[str, Any]] = None,
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    """MCP shares service validation, ownership checks, billing and optional durable replay."""
    from fastapi import HTTPException

    from backend.billing import billing_service
    from backend.services.engine import execute_service
    from backend.services.idempotency import begin, finish, finish_error
    from backend.services.models import ServiceRequest

    account = billing_service.get_company_by_api_key(_get_api_key())
    if not account:
        return {"success": False, "error": "MCP company account not found"}
    operation_key = None
    try:
        request = ServiceRequest(
            document_id=document_id, service=service_name, query=query or None, options=options or {}
        )
        operation_key, replay = begin(account, "mcp", idempotency_key, request.model_dump(mode="json"))
        if replay:
            return replay["body"]
        body = execute_service(request, account)
        body.update(
            response=json.dumps(
                jsonable_encoder(
                    {"data": body.get("data"), "fieldEvidence": body.get("fieldEvidence"), "checks": body.get("checks")}
                ),
                ensure_ascii=False,
            )
            if body.get("data") is not None
            else body.get("raw", ""),
            credits_deducted=body.get("creditsDeducted", 0),
            credits_remaining=body.get("creditsRemaining"),
        )
        finish(account, operation_key, body)
        return body
    except HTTPException as exc:
        finish_error(account, operation_key, exc)
        return {"success": False, "error": str(exc.detail)}
    except ValueError as exc:
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------


@mcp_server.tool(
    name="docuchat_list_documents",
    description="List all documents indexed in DocuChat with their document IDs, page counts, and filenames.",
)
def docuchat_list_documents(limit: int = 20) -> str:
    """List available indexed documents."""
    base_url = os.getenv("DOCUCHAT_BASE_URL", DEFAULT_BASE_URL)
    api_key = _get_api_key()

    if _is_http_server_reachable(base_url):
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(
                    f"{base_url.rstrip('/')}/api/v1/documents",
                    headers={"X-API-Key": api_key},
                    params={"limit": limit},
                )
                if resp.status_code == 200:
                    return json.dumps(resp.json(), indent=2)
        except Exception:
            pass

    # In-process listing fallback
    try:
        from backend.db import query

        rows = (
            query(
                "SELECT id, original_filename, file_size, page_count, created_at FROM docuchat.documents ORDER BY created_at DESC LIMIT %s",
                (limit,),
            )
            or []
        )
        docs = [
            {
                "id": str(r["id"]),
                "filename": r["original_filename"],
                "fileSize": r["file_size"],
                "pageCount": r["page_count"],
                "createdAt": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]
        return json.dumps({"documents": docs, "count": len(docs)}, indent=2)
    except Exception:
        from backend import rag

        cached = [{"id": doc_id, "ready": b.vector_store is not None} for doc_id, b in rag._registry.items()]
        return json.dumps({"documents": cached, "count": len(cached)}, indent=2)


@mcp_server.tool(
    name="docuchat_upload_document",
    description="Upload and index a document (PDF, DOCX, XLSX, TXT, MD) into DocuChat. Accepts a local file path or raw text content.",
)
def docuchat_upload_document(
    file_path: str = "",
    content: str = "",
    filename: str = "document.txt",
) -> str:
    """Ingest a document into DocuChat and return its document ID for subsequent queries."""
    base_url = os.getenv("DOCUCHAT_BASE_URL", DEFAULT_BASE_URL)
    api_key = _get_api_key()

    # Case 1: Upload via HTTP server
    if _is_http_server_reachable(base_url):
        try:
            with httpx.Client(timeout=30.0) as client:
                if file_path and Path(file_path).exists():
                    p = Path(file_path)
                    with open(p, "rb") as f:
                        files = {"file": (p.name, f.read(), "application/octet-stream")}
                        resp = client.post(
                            f"{base_url.rstrip('/')}/api/v1/documents/upload",
                            headers={"X-API-Key": api_key},
                            files=files,
                        )
                else:
                    resp = client.post(
                        f"{base_url.rstrip('/')}/api/v1/documents/upload",
                        headers={"X-API-Key": api_key},
                        json={"content": content, "filename": filename},
                    )
                if resp.status_code == 200:
                    return json.dumps(resp.json(), indent=2)
                return f"Upload failed [{resp.status_code}]: {resp.text}"
        except Exception as exc:
            logger.warning("HTTP upload failed, trying in-process: %s", exc)

    # Case 2: In-process fallback
    try:
        from backend import rag
        from backend.billing import billing_service

        account = billing_service.get_company_by_api_key(api_key)
        user_id = str(account.user_id) if account else "00000000-0000-0000-0000-000000000001"

        if file_path and Path(file_path).exists():
            p = Path(file_path)
            fname = p.name
            raw_bytes = p.read_bytes()
        else:
            fname = filename or "document.txt"
            raw_bytes = content.encode("utf-8")

        suffix = Path(fname).suffix or ".txt"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(raw_bytes)
            tmp_path = tmp.name

        try:
            upload_res = rag.process_upload(
                user_id=user_id,
                file_path=Path(tmp_path),
                original_filename=fname,
                file_size=len(raw_bytes),
                mime="application/octet-stream",
            )
            doc_id = getattr(upload_res, "document_id", str(uuid.uuid4()))
            return json.dumps(
                {
                    "status": "success",
                    "documentId": doc_id,
                    "filename": fname,
                    "pageCount": upload_res[1],
                    "chunkCount": upload_res[0],
                },
                indent=2,
            )
        finally:
            Path(tmp_path).unlink(missing_ok=True)
    except Exception as exc:
        return json.dumps({"error": f"Failed to upload document: {exc}"})


@mcp_server.tool(
    name="docuchat_search_chunks",
    description="Search document text chunks using hybrid vector embeddings + BM25 keyword search. Returns exact snippets with page citations.",
)
def docuchat_search_chunks(
    query: str,
    document_id: str = "",
    top_k: int = 5,
) -> str:
    """Retrieve relevant chunks from a document."""
    base_url = os.getenv("DOCUCHAT_BASE_URL", DEFAULT_BASE_URL)
    api_key = _get_api_key()

    if document_id and _is_http_server_reachable(base_url):
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(
                    f"{base_url.rstrip('/')}/api/v1/documents/{document_id}/search",
                    headers={"X-API-Key": api_key},
                    params={"query": query, "top_k": top_k},
                )
                if resp.status_code == 200:
                    return json.dumps(resp.json(), indent=2)
        except Exception:
            pass

    # In-process search
    try:
        from backend import rag

        if not document_id:
            # Pick first available doc
            if not rag._registry:
                return json.dumps({"error": "No documents available. Provide a valid document_id."})
            document_id = next(iter(rag._registry.keys()))

        bundle = rag.get_bundle(document_id)
        if not bundle.vector_store:
            return json.dumps({"error": f"Vector store for document '{document_id}' is empty or not loaded."})

        docs = bundle.vector_store.search(query, top_k=top_k)
        results = [
            {
                "page": d.metadata.get("start_page") or d.metadata.get("page") or 1,
                "chunkIndex": d.metadata.get("chunk_index"),
                "source": d.metadata.get("source"),
                "content": d.page_content,
            }
            for d in docs
        ]
        return json.dumps({"documentId": document_id, "query": query, "results": results}, indent=2)
    except Exception as exc:
        return json.dumps({"error": f"Search failed: {exc}"})


@mcp_server.tool(
    name="docuchat_query_document",
    description="Ask any question about a document and receive a grounded answer with page citations using RAG.",
)
def docuchat_query_document(document_id: str, question: str) -> str:
    """Query a document using conversational RAG."""
    base_url = os.getenv("DOCUCHAT_BASE_URL", DEFAULT_BASE_URL)
    api_key = _get_api_key()

    if _is_http_server_reachable(base_url):
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    f"{base_url.rstrip('/')}/api/v1/pipeline/run",
                    headers={"X-API-Key": api_key},
                    json={"document_id": document_id, "service": "chat", "query": question},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("raw") or json.dumps(data, indent=2)
        except Exception:
            pass

    res = _execute_service_inprocess(document_id, "chat", question)
    return res.get("response") or res.get("error", "No response generated.")


@mcp_server.tool(
    name="docuchat_extract_invoice",
    description="Extract financial invoice data (vendor, invoice number, line items, taxes, total, payment terms) into structured JSON.",
)
def docuchat_extract_invoice(document_id: str, query: str = "") -> str:
    """Extract structured data from an invoice."""
    res = _execute_service_inprocess(document_id, "invoice", query)
    return res.get("response") or res.get("error", "Failed to extract invoice.")


@mcp_server.tool(
    name="docuchat_analyze_contract",
    description="Analyze legal contracts: parties, liabilities, warranties, indemnification, termination clauses, and risk assessment.",
)
def docuchat_analyze_contract(document_id: str, query: str = "") -> str:
    """Perform in-depth legal analysis of a contract."""
    res = _execute_service_inprocess(document_id, "contract", query)
    return res.get("response") or res.get("error", "Failed to analyze contract.")


@mcp_server.tool(
    name="docuchat_audit_compliance",
    description="Audit document for PII (names, emails, SSN/IDs, financial accounts), GDPR/HIPAA risk scoring, and security flags.",
)
def docuchat_audit_compliance(document_id: str, query: str = "") -> str:
    """Scan document for compliance risks and PII."""
    res = _execute_service_inprocess(document_id, "compliance", query)
    return res.get("response") or res.get("error", "Failed to audit compliance.")


@mcp_server.tool(
    name="docuchat_parse_form",
    description="Parse form fields, checkboxes [X], signature blocks, and tables from structured documents.",
)
def docuchat_parse_form(document_id: str, query: str = "") -> str:
    """Extract key-value fields and checkboxes from forms."""
    res = _execute_service_inprocess(document_id, "form_parser", query)
    return res.get("response") or res.get("error", "Failed to parse form.")


@mcp_server.tool(
    name="docuchat_summarize_document",
    description="Generate a multi-section executive summary of a document with key findings and actionable takeaways.",
)
def docuchat_summarize_document(document_id: str, query: str = "") -> str:
    """Summarize document contents."""
    res = _execute_service_inprocess(document_id, "summary", query)
    return res.get("response") or res.get("error", "Failed to summarize document.")


@mcp_server.tool(
    name="docuchat_compare_documents",
    description="Compare two documents and highlight agreements, discrepancies, contradictions, and distinct clauses.",
)
def docuchat_compare_documents(
    document_id_a: str,
    document_id_b: str,
    query: str = "",
) -> str:
    """Compare two documents side-by-side."""
    prompt = f"Compare document {document_id_a} and document {document_id_b}. Focus on: {query or 'key terms, discrepancies, and revisions'}."
    res = _execute_service_inprocess(
        document_id_a, "contract_comparison", prompt, options={"reference_document_id": document_id_b}
    )
    return res.get("response") or res.get("error", "Failed to compare documents.")


@mcp_server.tool(
    name="docuchat_redact_document",
    description="Sanitize and redact sensitive PII (National IDs, Iqama, IBANs, Credit Cards, Phones, Emails) in English and Arabic.",
)
def docuchat_redact_document(document_id: str, query: str = "") -> str:
    """Anonymize sensitive entities in English and Arabic documents."""
    res = _execute_service_inprocess(document_id, "redaction", query)
    return res.get("response") or res.get("error", "Failed to redact document.")


@mcp_server.tool(
    name="docuchat_classify_document",
    description="Classify document category (Invoice, Contract, Financial Statement, Resume, CR, Letter), language, urgency, and routing department in EN & AR.",
)
def docuchat_classify_document(document_id: str) -> str:
    """Classify document and determine target department and priority."""
    res = _execute_service_inprocess(
        document_id, "classifier", "Classify this document category, language, and routing department."
    )
    return res.get("response") or res.get("error", "Failed to classify document.")


@mcp_server.tool(
    name="docuchat_analyze_financial_statement",
    description="Analyze balance sheets, P&L statements, and cash flows to extract key metrics (revenue, EBIT, net income, equity) and ratios in EN & AR.",
)
def docuchat_analyze_financial_statement(document_id: str, query: str = "") -> str:
    """Extract financial metrics and compute profitability/solvency ratios."""
    res = _execute_service_inprocess(document_id, "financial_statement", query)
    return res.get("response") or res.get("error", "Failed to analyze financial statement.")


@mcp_server.tool(
    name="docuchat_translate_document",
    description="Certified bidirectional enterprise and legal translation between English and Arabic (EN <-> AR) preserving clauses and table layouts.",
)
def docuchat_translate_document(document_id: str, target_language: str = "Arabic") -> str:
    """Translate document content accurately preserving legal and financial terminology."""
    prompt = f"Translate this document into {target_language}. Maintain all clause numbering, tables, formatting, and legal terminology."
    target = {"arabic": "ar", "english": "en", "ar": "ar", "en": "en"}.get(target_language.lower())
    if target is None:
        return "Target language must be Arabic/ar or English/en"
    res = _execute_service_inprocess(
        document_id, "translation", prompt, options={"translation": {"target_language": target}}
    )
    return res.get("response") or res.get("error", "Failed to translate document.")


@mcp_server.tool(
    name="docuchat_audit_anomalies",
    description="Audit document for mathematical discrepancies, configured tax calculation errors, date inversions, and contractual contradictions.",
)
def docuchat_audit_anomalies(document_id: str, query: str = "") -> str:
    """Perform forensic arithmetic, tax, and date consistency audit."""
    res = _execute_service_inprocess(document_id, "anomaly_audit", query)
    return res.get("response") or res.get("error", "Failed to audit anomalies.")


@mcp_server.tool(
    name="docuchat_get_company_credits",
    description="Check remaining company credits, plan tier, and pricing catalog.",
)
def docuchat_get_company_credits() -> str:
    """Return company account balance and pricing."""
    try:
        from backend.billing import SERVICE_PRICING, billing_service

        acc = billing_service.get_company_by_api_key(_get_api_key())
        if not acc:
            acc = billing_service.get_or_create_company("00000000-0000-0000-0000-000000000001", "MCP Client")

        info = {
            "companyName": acc.company_name,
            "planTier": acc.plan_tier,
            "totalCredits": acc.total_credits,
            "usedCredits": acc.used_credits,
            "remainingCredits": acc.remaining_credits,
            "pricing": {k: v["credits"] for k, v in SERVICE_PRICING.items()},
        }
        return json.dumps(info, indent=2)
    except Exception as exc:
        return json.dumps({"error": f"Failed to retrieve account info: {exc}"})


# ---------------------------------------------------------------------------
# MCP Resources
# ---------------------------------------------------------------------------


@mcp_server.resource(
    uri="docuchat://documents",
    name="Document Catalog",
    mime_type="application/json",
)
def resource_list_documents() -> str:
    """List of all indexed documents in the workspace."""
    return docuchat_list_documents(limit=50)


@mcp_server.resource(
    uri="docuchat://pricing",
    name="B2B Pricing & Services Catalog",
    mime_type="application/json",
)
def resource_get_pricing() -> str:
    """Service catalog and credit consumption per AI service."""
    from backend.billing import INITIAL_TRIAL_CREDITS, SERVICE_PRICING

    return json.dumps(
        {
            "plan": "Enterprise Free Trial",
            "initialCredits": INITIAL_TRIAL_CREDITS,
            "services": SERVICE_PRICING,
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# MCP Prompts
# ---------------------------------------------------------------------------


@mcp_server.prompt(
    name="analyze_financial_document",
    description="Prompt to extract and verify financial metrics and line items from a document.",
)
def prompt_analyze_invoice(document_id: str) -> str:
    return (
        f"Please analyze document '{document_id}' as a financial document. "
        "Extract the vendor, invoice/receipt number, date, itemized line items, "
        "subtotal, tax breakdown, and total. Verify that the math adds up."
    )


@mcp_server.prompt(
    name="review_legal_contract",
    description="Prompt to review contract clauses, governing law, and legal risk liabilities.",
)
def prompt_review_contract(document_id: str) -> str:
    return (
        f"Perform a thorough legal review of contract '{document_id}'. "
        "Identify the parties, effective date, core obligations, liability caps, "
        "indemnification clauses, termination provisions, and assign a risk rating."
    )


@mcp_server.prompt(
    name="audit_document_compliance",
    description="Prompt to perform PII scan, GDPR/HIPAA compliance audit, and redaction check.",
)
def prompt_audit_compliance(document_id: str) -> str:
    return (
        f"Audit document '{document_id}' for compliance risks. "
        "Scan for Personally Identifiable Information (PII), confidential credentials, "
        "calculate a GDPR/HIPAA risk score, and list recommended redactions."
    )


@mcp_server.prompt(
    name="executive_document_summary",
    description="Prompt to generate an executive summary with key findings.",
)
def prompt_executive_summary(document_id: str) -> str:
    return (
        f"Generate a clear executive summary for document '{document_id}'. "
        "Include: 1) Executive Overview, 2) Key Findings & Metrics, 3) Actionable Takeaways. "
        "Cite specific page numbers for every key fact."
    )


# ---------------------------------------------------------------------------
# CLI Entrypoint (stdio or standalone SSE)
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="DOCTool Model Context Protocol (MCP) Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="MCP transport protocol (stdio for Claude Code/Desktop, sse for HTTP)",
    )
    parser.add_argument("--port", type=int, default=8001, help="Port for SSE transport")
    parser.add_argument("--host", default="127.0.0.1", help="Host for SSE transport")
    parser.add_argument("--api-key", default=None, help="DOCTool Company API Key (docu_live_...)")
    parser.add_argument("--base-url", default=None, help="Base URL of DOCTool server")

    args = parser.parse_args()

    if args.api_key:
        os.environ["DOCUCHAT_API_KEY"] = args.api_key
    if args.base_url:
        os.environ["DOCUCHAT_BASE_URL"] = args.base_url

    if args.transport == "stdio":
        # Run stdio transport (Claude Code CLI and Claude Desktop)
        mcp_server.run(transport="stdio")
    else:
        # Run standalone SSE transport
        mcp_server.run(transport="sse", host=args.host, port=args.port)


if __name__ == "__main__":
    main()


@mcp_server.tool(
    name="docuchat_run_validated_service",
    description="Run a document service with validated output, source evidence and configurable options. Supports invoice_matching, contract_comparison, document_checks, translation and existing services.",
)
def docuchat_run_validated_service(
    document_id: str,
    service: str,
    options: Optional[Dict[str, Any]] = None,
    query: str = "",
    idempotency_key: Optional[str] = None,
) -> str:
    return json.dumps(
        jsonable_encoder(_execute_service_inprocess(document_id, service, query, options, idempotency_key)),
        ensure_ascii=False,
    )
