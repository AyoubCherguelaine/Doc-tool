"""
DOCTool Enterprise Python SDK Client.

Provides synchronous and asynchronous methods to ingest documents,
execute specialized AI agents, and query hybrid vector stores in B2B pipelines.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

import httpx


class DOCToolError(Exception):
    """Base exception for DOCTool SDK errors."""

    def __init__(self, message: str, status_code: Optional[int] = None, details: Optional[Any] = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details


# Backwards compatibility alias
DocuChatError = DOCToolError


class DOCToolClient:
    """
    Enterprise client for DOCTool SaaS API.

    Example:
    >>> client = DOCToolClient(api_key="docu_live_...")
    >>> doc = client.upload_document("invoices/invoice_1024.pdf")
    >>> print("Uploaded doc ID:", doc["documentId"])
    >>> data = client.extract_invoice(doc["documentId"])
    >>> print("Invoice Total:", data.get("data", {}).get("total"))
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "http://127.0.0.1:8000",
        timeout: float = 60.0,
    ):
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.headers = {
            "X-API-Key": self.api_key,
            "User-Agent": "DOCTool-Enterprise-SDK/1.0",
        }

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.request(
                    method=method,
                    url=url,
                    headers={**self.headers, **({"Idempotency-Key": idempotency_key} if idempotency_key else {})},
                    params=params,
                    json=json_data,
                    files=files,
                )
                if resp.is_error:
                    try:
                        err_json = resp.json()
                        detail = err_json.get("detail", resp.text)
                    except Exception:
                        detail = resp.text
                    raise DOCToolError(
                        f"DOCTool API Error [{resp.status_code}]: {detail}",
                        status_code=resp.status_code,
                        details=detail,
                    )
                return resp.json() if resp.status_code != 204 else {}
        except httpx.RequestError as exc:
            raise DOCToolError(f"Network transport error connecting to {url}: {exc}") from exc

    def upload_document(
        self,
        file: Union[str, Path, bytes, io.BytesIO],
        filename: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Upload and index a document (PDF, DOCX, XLSX, TXT, MD, CSV) for pipeline processing.
        """
        if isinstance(file, (str, Path)):
            path = Path(file)
            fname = filename or path.name
            with open(path, "rb") as f:
                content = f.read()
        elif isinstance(file, io.BytesIO):
            fname = filename or "uploaded_document.pdf"
            content = file.getvalue()
        elif isinstance(file, bytes):
            fname = filename or "uploaded_document.pdf"
            content = file
        else:
            raise ValueError("File must be a path string, Path, bytes, or BytesIO object.")

        files = {"file": (fname, content, "application/octet-stream")}
        return self._request("POST", "/api/v1/documents/upload", files=files)

    def upload_text(self, text: str, filename: str = "document.txt") -> Dict[str, Any]:
        """Upload raw text or markdown content directly into the pipeline."""
        payload = {"content": text, "filename": filename}
        return self._request("POST", "/api/v1/documents/upload", json_data=payload)

    def list_documents(self, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        """List documents indexed under this company account."""
        return self._request("GET", "/api/v1/documents", params={"limit": limit, "offset": offset})

    def get_document(self, document_id: str) -> Dict[str, Any]:
        """Get document status, page count, and metadata."""
        return self._request("GET", f"/api/v1/documents/{document_id}")

    def search(self, document_id: str, query: str, top_k: int = 5) -> Dict[str, Any]:
        """Search document chunks using hybrid vector + BM25 keyword retrieval."""
        return self._request(
            "GET",
            f"/api/v1/documents/{document_id}/search",
            params={"query": query, "top_k": top_k},
        )

    def run_pipeline(
        self,
        document_id: str,
        service: str,
        query: Optional[str] = None,
        output_format: Literal["json", "markdown", "auto"] = "auto",
        model: Optional[str] = None,
        guardian: bool = True,
        webhook_url: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
        schema_override: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
        text_content: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute an AI service on a document in the pipeline.

        Services: invoice, contract, compliance, summary, form_parser,
                  receipt, resume, research, comparison, factcheck, chat.
        """
        payload = {
            "document_id": document_id,
            "service": service,
            "query": query,
            "output_format": output_format,
            "model": model,
            "guardian": guardian,
            "webhook_url": webhook_url,
            "options": options or {},
            "schema_override": schema_override,
            "text_content": text_content,
        }
        return self._request("POST", "/api/v1/pipeline/run", json_data=payload, idempotency_key=idempotency_key)

    def extract_invoice(self, document_id: str, query: Optional[str] = None) -> Dict[str, Any]:
        """Extract structured line items, vendor details, and totals from an invoice."""
        return self.run_pipeline(document_id, service="invoice", query=query, output_format="json")

    def analyze_contract(self, document_id: str, query: Optional[str] = None) -> Dict[str, Any]:
        """Analyze clauses, legal risks, liabilities, and termination conditions."""
        return self.run_pipeline(document_id, service="contract", query=query, output_format="json")

    def audit_compliance(self, document_id: str, query: Optional[str] = None) -> Dict[str, Any]:
        """Scan document for PII, GDPR/HIPAA risk scoring, and security flags."""
        return self.run_pipeline(document_id, service="compliance", query=query, output_format="json")

    def parse_form(self, document_id: str, query: Optional[str] = None) -> Dict[str, Any]:
        """Extract key-value pairs, checkboxes, and tables from forms."""
        return self.run_pipeline(document_id, service="form_parser", query=query, output_format="json")

    def summarize(self, document_id: str, query: Optional[str] = None) -> Dict[str, Any]:
        """Generate structured executive summary with citations."""
        return self.run_pipeline(document_id, service="summary", query=query, output_format="markdown")

    def redact_document(self, document_id: str, query: Optional[str] = None) -> Dict[str, Any]:
        """Redact and sanitize sensitive PII in English & Arabic documents."""
        return self.run_pipeline(document_id, service="redaction", query=query, output_format="json")

    def classify_document(self, document_id: str) -> Dict[str, Any]:
        """Classify document category, language, and routing department in EN & AR."""
        return self.run_pipeline(document_id, service="classifier", query="Classify document", output_format="json")

    def analyze_financial_statement(self, document_id: str, query: Optional[str] = None) -> Dict[str, Any]:
        """Analyze balance sheets and P&L statements, extracting financial ratios."""
        return self.run_pipeline(document_id, service="financial_statement", query=query, output_format="json")

    def translate_document(
        self,
        document_id: str,
        target_language: str = "Arabic",
        *,
        source_language: str = "auto",
        glossary: Optional[Dict[str, str]] = None,
        preserve_names: Optional[List[str]] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Translate with explicit language, terminology and preservation checks."""
        languages = {"arabic": "ar", "english": "en", "ar": "ar", "en": "en", "auto": "auto"}
        target = languages.get(target_language.lower())
        source = languages.get(source_language.lower())
        if target not in {"ar", "en"} or source is None:
            raise ValueError("Supported languages are Arabic/ar and English/en; source may be auto")
        return self.run_pipeline(
            document_id,
            "translation",
            output_format="json",
            idempotency_key=idempotency_key,
            options={
                "translation": {
                    "target_language": target,
                    "source_language": source,
                    "glossary": glossary or {},
                    "preserve_names": preserve_names or [],
                }
            },
        )

    def match_invoice(
        self,
        invoice_document_id: str,
        purchase_order_document_id: str,
        *,
        financial_options: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.run_pipeline(
            invoice_document_id,
            "invoice_matching",
            output_format="json",
            idempotency_key=idempotency_key,
            options={"reference_document_id": purchase_order_document_id, "financial": financial_options or {}},
        )

    def compare_contract_versions(
        self, before_document_id: str, after_document_id: str, *, idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        return self.run_pipeline(
            before_document_id,
            "contract_comparison",
            output_format="json",
            idempotency_key=idempotency_key,
            options={"reference_document_id": after_document_id},
        )

    def check_document(
        self,
        document_id: str,
        *,
        rules: Optional[List[Dict[str, Any]]] = None,
        rule_set_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.run_pipeline(
            document_id,
            "document_checks",
            output_format="json",
            idempotency_key=idempotency_key,
            options={"rules": rules or [], "rule_set_id": rule_set_id},
        )

    def create_rule_set(self, name: str, rules: List[Dict[str, Any]]) -> Dict[str, Any]:
        return self._request("POST", "/api/v1/rule-sets", json_data={"name": name, "rules": rules})

    def list_rule_sets(self) -> Dict[str, Any]:
        return self._request("GET", "/api/v1/rule-sets")

    def get_rule_set(self, rule_set_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/api/v1/rule-sets/{rule_set_id}")

    def update_rule_set(self, rule_set_id: str, name: str, rules: List[Dict[str, Any]]) -> Dict[str, Any]:
        return self._request("PUT", f"/api/v1/rule-sets/{rule_set_id}", json_data={"name": name, "rules": rules})

    def delete_rule_set(self, rule_set_id: str) -> None:
        self._request("DELETE", f"/api/v1/rule-sets/{rule_set_id}")

    def audit_anomalies(self, document_id: str, query: Optional[str] = None) -> Dict[str, Any]:
        """Perform forensic arithmetic, tax, and date consistency audit."""
        return self.run_pipeline(document_id, service="anomaly_audit", query=query, output_format="json")

    def batch_run(
        self, tasks: List[Dict[str, Any]], webhook_url: Optional[str] = None, idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """Run batch processing across multiple documents and services."""
        payload = {"tasks": tasks, "webhook_url": webhook_url}
        return self._request("POST", "/api/v1/pipeline/batch", json_data=payload, idempotency_key=idempotency_key)

    def submit_async_job(
        self,
        document_id: str,
        service: str,
        query: Optional[str] = None,
        output_format: Literal["json", "markdown", "auto"] = "auto",
        webhook_url: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
        schema_override: Optional[Dict[str, Any]] = None,
        model: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Submit a background asynchronous job (Redis queue) and return job ID immediately."""
        payload = {
            "document_id": document_id,
            "service": service,
            "query": query,
            "output_format": output_format,
            "webhook_url": webhook_url,
            "options": options or {},
            "schema_override": schema_override,
            "model": model,
        }
        return self._request("POST", "/api/v1/pipeline/jobs", json_data=payload, idempotency_key=idempotency_key)

    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Poll the status, progress (0-100), and result of a background job."""
        return self._request("GET", f"/api/v1/pipeline/jobs/{job_id}")

    def list_jobs(self, limit: int = 50) -> Dict[str, Any]:
        """List recent pipeline jobs."""
        return self._request("GET", "/api/v1/pipeline/jobs", params={"limit": limit})

    def get_document_url(self, document_id: str, expires_seconds: int = 3600) -> str:
        """Get a secure expiring download/view URL for a document."""
        res = self._request(
            "GET",
            f"/api/v1/storage/documents/{document_id}/presigned-url",
            params={"expires_seconds": expires_seconds},
        )
        return res.get("url", "")

    def get_account(self) -> Dict[str, Any]:
        """Get account details and remaining credits."""
        return self._request("GET", "/api/v1/company/account")

    def get_pricing(self) -> Dict[str, Any]:
        """Get service catalog and credit pricing."""
        return self._request("GET", "/api/v1/company/pricing")

    def get_guardian_setting(self) -> Dict[str, Any]:
        """Get the current Guardian mode setting."""
        return self._request("GET", "/api/v1/settings/guardian")

    def set_guardian_setting(self, enabled: bool) -> Dict[str, Any]:
        """Update Guardian mode setting."""
        return self._request("POST", "/api/v1/settings/guardian", json_data={"enabled": enabled})


# Backwards compatibility alias
DocuChatClient = DOCToolClient
