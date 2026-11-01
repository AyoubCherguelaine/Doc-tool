"""
Enhanced document tools for specialised agents.

Adds tools beyond the core DocumentToolKit:

* ``extract_table``  — pull a structured table from a specific page
* ``verify_fact``    — search for evidence to support/contradict a claim
* ``calculate``      — compute from numbers found in documents
* ``get_outline``    — retrieve the document structural outline / headings
* ``extract_invoice_data``     — LLM-based structured invoice extraction
* ``extract_contract_data``    — LLM-based structured contract extraction
* ``ocr_read_page``            — vision-based OCR of a specific page
* ``ocr_extract_invoice``      — vision-based invoice data extraction (JSON)
* ``ocr_extract_contract``     — vision-based contract analysis (JSON)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

from backend.documents.pdf_loader import PDFDocument


class EnhancedDocumentKit:
    """
    Extension of :class:`~backend.agent.tools.document_tools.DocumentToolKit`
    with structure-aware tools (tables, outlines, calculations, fact-checking).
    """

    def __init__(
        self,
        vector_store: Any = None,
        documents: Optional[list[PDFDocument]] = None,
        llm: Any = None,
    ):
        self.vector_store = vector_store
        self.documents: list[PDFDocument] = documents or []
        self._doc_map: dict[str, PDFDocument] = {d.name: d for d in self.documents}
        self.llm = llm

    # ------------------------------------------------------------------
    # Builders
    # ------------------------------------------------------------------

    @classmethod
    def from_kit(cls, kit) -> "EnhancedDocumentKit":
        """Wrap an existing DocumentToolKit to add enhanced capabilities."""
        return cls(
            vector_store=getattr(kit, "vector_store", None),
            documents=getattr(kit, "documents", []),
            llm=getattr(kit, "llm", None),
        )

    # ------------------------------------------------------------------
    # Tool registration (compatible with FreeAgent / BaseAgent)
    # ------------------------------------------------------------------

    def register_all(self, registry) -> None:
        """Register all enhanced tools into a :class:`ToolRegistry`."""
        from backend.agent.tools.registry import Tool

        # Core document tools
        if self.vector_store is not None:
            registry.register(
                Tool(
                    name="search_documents",
                    description="Search documents using hybrid RAG (BM25 + dense + RRF).",
                    parameters={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query."},
                            "top_k": {"type": "integer", "description": "Number of results (default 5).", "default": 5},
                        },
                        "required": ["query"],
                    },
                    func=self.search_documents,
                )
            )
            registry.register(
                Tool(
                    name="compare_documents",
                    description="Search across all documents and group results by source to compare treatments of a subject.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Comparison topic or query."},
                            "top_k_per_doc": {"type": "integer", "description": "Results per document (default 3).", "default": 3},
                        },
                        "required": ["query"],
                    },
                    func=self.compare_documents,
                )
            )

        registry.register(
            Tool(
                name="read_page",
                description="Read a specific page from a document.",
                parameters={
                    "type": "object",
                    "properties": {
                        "doc_name": {"type": "string", "description": "Document name."},
                        "page_num": {"type": "integer", "description": "1-indexed page number."},
                    },
                    "required": ["doc_name", "page_num"],
                },
                func=self._read_page_compat,
            )
        )
        registry.register(
            Tool(
                name="read_pages",
                description="Read a range of pages from a document.",
                parameters={
                    "type": "object",
                    "properties": {
                        "doc_name": {"type": "string", "description": "Document name."},
                        "start_page": {"type": "integer", "description": "Start page (1-indexed)."},
                        "end_page": {"type": "integer", "description": "End page (inclusive)."},
                    },
                    "required": ["doc_name", "start_page", "end_page"],
                },
                func=self.read_pages,
            )
        )
        registry.register(
            Tool(
                name="list_documents",
                description="List all loaded documents.",
                parameters={"type": "object", "properties": {}, "required": []},
                func=self._list_documents_compat,
            )
        )
        registry.register(
            Tool(
                name="summarize",
                description="Summarize text or passage concisely.",
                parameters={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "The text to summarize."},
                    },
                    "required": ["text"],
                },
                func=self.summarize,
            )
        )
        registry.register(
            Tool(
                name="get_metadata",
                description="Retrieve metadata about a document page or section.",
                parameters={
                    "type": "object",
                    "properties": {
                        "doc_name": {"type": "string", "description": "Document name."},
                        "page_num": {"type": "integer", "description": "Page number."},
                    },
                    "required": ["doc_name", "page_num"],
                },
                func=self.get_metadata,
            )
        )

        # Enhanced tools
        registry.register(
            Tool(
                name="calculate",
                description="Evaluate a mathematical expression.",
                parameters={
                    "type": "object",
                    "properties": {
                        "expression": {"type": "string", "description": "Math expression, e.g. '1250 + 3400'"},
                    },
                    "required": ["expression"],
                },
                func=self.calculate,
            )
        )

        registry.register(
            Tool(
                name="get_outline",
                description="Get the structural outline (headings) of a document.",
                parameters={
                    "type": "object",
                    "properties": {
                        "doc_name": {"type": "string", "description": "Document name."},
                        "max_depth": {"type": "integer", "description": "Max heading depth (default 3).", "default": 3},
                    },
                    "required": ["doc_name"],
                },
                func=self.get_outline,
            )
        )

        registry.register(
            Tool(
                name="verify_fact",
                description="Search for evidence supporting or contradicting a claim.",
                parameters={
                    "type": "object",
                    "properties": {
                        "claim": {"type": "string", "description": "Claim to verify."},
                        "top_k": {"type": "integer", "description": "Search results (default 10).", "default": 10},
                    },
                    "required": ["claim"],
                },
                func=self.verify_fact,
            )
        )

        registry.register(
            Tool(
                name="extract_table",
                description="Extract a structured table from a PDF page.",
                parameters={
                    "type": "object",
                    "properties": {
                        "doc_name": {"type": "string", "description": "Document name."},
                        "page_num": {"type": "integer", "description": "1-indexed page number."},
                        "table_index": {"type": "integer", "description": "Table index (0-based, default 0).", "default": 0},
                    },
                    "required": ["doc_name", "page_num"],
                },
                func=self.extract_table,
            )
        )

        if hasattr(self, "extract_invoice_data"):
            registry.register(
                Tool(
                    name="extract_invoice_data",
                    description="Extract structured invoice data as JSON from a text-based PDF.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "doc_name": {"type": "string", "description": "Document name."},
                        },
                        "required": ["doc_name"],
                    },
                    func=self.extract_invoice_data,
                )
            )

        if hasattr(self, "extract_contract_data"):
            registry.register(
                Tool(
                    name="extract_contract_data",
                    description="Extract structured contract data as JSON from a text-based PDF.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "doc_name": {"type": "string", "description": "Document name."},
                        },
                        "required": ["doc_name"],
                    },
                    func=self.extract_contract_data,
                )
            )

        if hasattr(self, "ocr_read_page"):
            registry.register(
                Tool(
                    name="ocr_read_page",
                    description="Vision-based OCR of a specific PDF page (for scanned PDFs).",
                    parameters={
                        "type": "object",
                        "properties": {
                            "doc_name": {"type": "string", "description": "Document name."},
                            "page_num": {"type": "integer", "description": "1-indexed page number."},
                        },
                        "required": ["doc_name", "page_num"],
                    },
                    func=self.ocr_read_page,
                )
            )

        if hasattr(self, "ocr_extract_invoice"):
            registry.register(
                Tool(
                    name="ocr_extract_invoice",
                    description="Vision-based invoice data extraction (JSON) from scanned PDFs.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "doc_name": {"type": "string", "description": "Document name."},
                            "page_num": {"type": "integer", "description": "Optional page number.", "default": None},
                        },
                        "required": ["doc_name"],
                    },
                    func=self.ocr_extract_invoice,
                )
            )

        if hasattr(self, "ocr_extract_contract"):
            registry.register(
                Tool(
                    name="ocr_extract_contract",
                    description="Vision-based contract analysis (JSON) from scanned PDFs.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "doc_name": {"type": "string", "description": "Document name."},
                            "page_num": {"type": "integer", "description": "Optional page number.", "default": None},
                        },
                        "required": ["doc_name"],
                    },
                    func=self.ocr_extract_contract,
                )
            )

        if hasattr(self, "ocr_extract_blocks"):
            registry.register(
                Tool(
                    name="ocr_extract_blocks",
                    description=(
                        "Extract semantic document blocks with structured content, verbatim ocr_text, "
                        "normalized coordinates, tables, visual descriptions, and cross-page continuation links."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "doc_name": {"type": "string", "description": "Document name or ID."},
                            "page_num": {"type": "integer", "description": "Optional page number. If omitted, extracts all pages.", "default": None},
                        },
                        "required": ["doc_name"],
                    },
                    func=self.ocr_extract_blocks,
                )
            )

        if hasattr(self, "ocr_page_blocks"):
            registry.register(
                Tool(
                    name="ocr_page_blocks",
                    description=(
                        "Extract bilingual semantic blocks with structured content and verbatim ocr_text "
                        "for a specific page. Includes normalized coordinates, tables, and visual descriptions."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "doc_name": {"type": "string", "description": "Document name or ID."},
                            "page_num": {"type": "integer", "description": "1-indexed page number to extract blocks from."},
                            "language": {"type": "string", "description": "Target language: 'auto', 'ar', 'en', or 'mixed'.", "default": "auto"},
                            "force_ocr": {"type": "boolean", "description": "Force vision OCR re-extraction.", "default": False},
                        },
                        "required": ["doc_name", "page_num"],
                    },
                    func=self.ocr_page_blocks,
                )
            )

        if hasattr(self, "google_ai_parse_document"):
            registry.register(
                Tool(
                    name="google_ai_parse_document",
                    description=(
                        "Deep document intelligence powered by Google AI: extracts layout structure, "
                        "key-value entities, form fields, and tables."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "doc_name": {"type": "string", "description": "Document name."},
                            "task": {
                                "type": "string",
                                "description": "Analysis task: 'comprehensive', 'entities', 'layout', or 'tables'.",
                                "default": "comprehensive",
                            },
                        },
                        "required": ["doc_name"],
                    },
                    func=self.google_ai_parse_document,
                )
            )

        if hasattr(self, "extract_receipt_data"):
            registry.register(
                Tool(
                    name="extract_receipt_data",
                    description=(
                        "Extract structured receipt and expense data (merchant, date, line items, "
                        "taxes, tip, payment method, category) as JSON."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "doc_name": {"type": "string", "description": "Document name."},
                        },
                        "required": ["doc_name"],
                    },
                    func=self.extract_receipt_data,
                )
            )

        if hasattr(self, "extract_resume_data"):
            registry.register(
                Tool(
                    name="extract_resume_data",
                    description=(
                        "Extract structured resume / CV data (candidate contact, summary, skills, "
                        "work history, education, certifications, seniority level) as JSON."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "doc_name": {"type": "string", "description": "Document name."},
                        },
                        "required": ["doc_name"],
                    },
                    func=self.extract_resume_data,
                )
            )

        if hasattr(self, "audit_document_compliance"):
            registry.register(
                Tool(
                    name="audit_document_compliance",
                    description=(
                        "Audit document for PII, GDPR/HIPAA compliance risks, sensitive data, "
                        "and produce risk scoring and redaction preview."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "doc_name": {"type": "string", "description": "Document name."},
                        },
                        "required": ["doc_name"],
                    },
                    func=self.audit_document_compliance,
                )
            )

        if hasattr(self, "extract_form_fields"):
            registry.register(
                Tool(
                    name="extract_form_fields",
                    description=(
                        "Extract key-value pairs, checkbox states, and signature information "
                        "from structured or semi-structured forms."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "doc_name": {"type": "string", "description": "Document name."},
                        },
                        "required": ["doc_name"],
                    },
                    func=self.extract_form_fields,
                )
            )

        registry.register(
            Tool(
                name="explain_document_services",
                description="List document services with their capabilities and current credit costs.",
                parameters={"type": "object", "properties": {}, "required": []},
                func=self.explain_services,
            )
        )
        registry.register(
            Tool(
                name="run_document_ai_service",
                description="Execute a specialized Document AI service on this document (invoice, contract, compliance, summary, financial_statement, receipt, resume, redaction, translation, form_parser).",
                parameters={
                    "type": "object",
                    "properties": {
                        "service": {
                            "type": "string",
                            "description": "Service name to run: 'invoice', 'contract', 'compliance', 'summary', 'extraction', 'financial_statement', 'receipt', 'resume', 'redaction', 'translation', 'form_parser', 'classifier', 'anomaly_audit'.",
                        },
                        "instruction": {
                            "type": "string",
                            "description": "Specific instruction or query for the service.",
                        },
                    },
                    "required": ["service"],
                },
                func=self.run_service_tool,
            )
        )

    # ------------------------------------------------------------------
    # Compatibility methods for FreeAgent
    # ------------------------------------------------------------------

    def search_documents(self, query: str, top_k: int = 5) -> str:
        """Search documents using the vector store."""
        if self.vector_store is None:
            return "ERROR: No vector store available."
        docs = self.vector_store.search(query, top_k=top_k)
        if not docs:
            return "No relevant documents found."
        parts = []
        for i, doc in enumerate(docs, 1):
            meta = doc.metadata
            source = meta.get("doc_name", "unknown")
            page = meta.get("start_page", "?")
            parts.append(f"[{source} p.{page}] {doc.page_content[:300].strip()}")
        return "\n\n".join(parts)

    def _read_page_compat(self, doc_name: str, page_num: int) -> str:
        """Read a specific page from a document (compatibility wrapper)."""
        doc = self._find_document(doc_name)
        if doc is None:
            return self._list_available_error()
        content = doc.get_page(page_num)
        if content is None:
            return f"ERROR: Page {page_num} not found in '{doc_name}'."
        return content.text

    def _list_documents_compat(self) -> str:
        """List available documents (compatibility wrapper)."""
        if not self._doc_map:
            return "No documents loaded."
        lines = []
        for name, doc in self._doc_map.items():
            lines.append(f"- {doc.name} ({getattr(doc, 'total_pages', '?')} pages)")
        return "\n".join(lines)

    def read_pages(self, doc_name: str, start_page: int, end_page: int) -> str:
        """Read a range of pages from a loaded document."""
        doc = self._find_document(doc_name)
        if doc is None:
            return self._list_available_error()

        if start_page > end_page:
            start_page, end_page = end_page, start_page

        pages = doc.get_pages(start_page, end_page)
        if not pages:
            return f"ERROR: Pages {start_page}-{end_page} are out of range. Document has {getattr(doc, 'total_pages', '?')} pages."

        parts = [f"=== {doc.name} — Page {p.page_number} of {p.total_pages} ===" for p in pages]
        texts = [p.text.strip() for p in pages]
        return "\n\n".join(f"{h}\n\n{t}" for h, t in zip(parts, texts))

    def explain_services(self) -> str:
        """Use the billing catalog so service names and prices cannot drift."""
        from backend.billing import SERVICE_PRICING

        lines = ["### Document services", "| Service | Credits | Description |", "| :--- | :--- | :--- |"]
        for service, details in SERVICE_PRICING.items():
            lines.append(f"| **{service}** | {details['credits']} | {details['description']} |")
        lines.append("Invoice matching and contract version comparison require a second document. Document checks accept company rules.")
        return "\n".join(lines)

    def run_service_tool(self, service: str, instruction: str = "") -> str:
        """Execute a specialized Document AI service on this document."""
        s = service.lower().replace("-", "_").strip()
        doc_name = self.documents[0].name if self.documents else None

        if s == "invoice" and hasattr(self, "extract_invoice_data") and doc_name:
            return str(self.extract_invoice_data(doc_name))
        if s == "contract" and hasattr(self, "extract_contract_data") and doc_name:
            return str(self.extract_contract_data(doc_name))
        if s == "receipt" and hasattr(self, "extract_receipt_data") and doc_name:
            return str(self.extract_receipt_data(doc_name))
        if s == "resume" and hasattr(self, "extract_resume_data") and doc_name:
            return str(self.extract_resume_data(doc_name))
        if s == "compliance" and hasattr(self, "audit_document_compliance") and doc_name:
            return str(self.audit_document_compliance(doc_name))
        if s == "form_parser" and hasattr(self, "extract_form_fields") and doc_name:
            return str(self.extract_form_fields(doc_name))
        if s == "redaction" and hasattr(self, "redact_sensitive_data") and doc_name:
            return str(self.redact_sensitive_data(doc_name))
        if s == "classifier" and hasattr(self, "classify_document") and doc_name:
            return str(self.classify_document(doc_name))
        if s in ("financial_statement", "finance") and hasattr(self, "analyze_financial_statement") and doc_name:
            return str(self.analyze_financial_statement(doc_name))
        if s == "translation" and hasattr(self, "translate_document") and doc_name:
            return str(self.translate_document(doc_name, target_language="en"))
        if s == "anomaly_audit" and hasattr(self, "audit_document_anomalies") and doc_name:
            return str(self.audit_document_anomalies(doc_name))

        # Fallback using LLM with document context
        doc_text = ""
        if self.documents and self.documents[0].pages:
            doc_text = "\n\n".join([f"--- Page {p.page_number} ---\n{p.text}" for p in self.documents[0].pages[:3]])
        elif self.vector_store:
            docs = self.vector_store.search(instruction or s, top_k=5)
            doc_text = "\n\n".join([d.page_content for d in docs])

        prompt = (
            f"You are the DOC Tool {s.upper()} specialist engine.\n"
            f"Analyze the following document context:\n\n{doc_text}\n\n"
            f"Execution Instruction: {instruction or 'Extract all structured fields, metrics, and insights.'}\n"
            f"Return a structured, professional markdown report with clear headings, tables, or key-value fields."
        )
        if self.llm:
            try:
                from langchain_core.messages import HumanMessage
                res = self.llm.invoke([HumanMessage(content=prompt)])
                return res.content if hasattr(res, "content") else str(res)
            except Exception as e:
                return f"Error executing {s}: {e}"
        return f"Executed {s} on {doc_name}."

    def summarize(self, text: str) -> str:
        """Summarize text using the configured LLM or extractive fallback."""
        if not text.strip():
            return "No text provided to summarize."

        max_chars = 8000
        if len(text) > max_chars:
            text = text[:max_chars] + "... [truncated]"

        if self.llm is not None:
            try:
                from langchain_core.messages import HumanMessage

                summary_prompt = "Summarize the following text in 3-5 bullet points:\n\n{text}\n\nSummary:"
                if hasattr(self.llm, "invoke"):
                    response = self.llm.invoke([HumanMessage(content=summary_prompt.format(text=text))])
                    return response.content if hasattr(response, "content") else str(response)
            except Exception:
                pass

        # Extractive fallback
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        top = sentences[:3]
        return "• " + "\n• ".join(top) if top else text[:200]

    def compare_documents(self, query: str, top_k_per_doc: int = 3) -> str:
        """Search across loaded documents and group results by source for comparative analysis."""
        if self.vector_store is None:
            return "ERROR: No vector store available."

        num_docs = max(len(self.documents), len(self._doc_map), 1)
        top_k = max(3, top_k_per_doc * num_docs)
        results = self.vector_store.search(query, top_k=top_k)

        grouped: dict[str, list] = {}
        for doc in results:
            name = doc.metadata.get("doc_name", "unknown")
            grouped.setdefault(name, []).append(doc)

        if not grouped:
            return f"No comparison results found for '{query}' across documents."

        lines = [f"=== Comparison for: '{query}' ==="]
        for name, docs in grouped.items():
            lines.append(f"\n--- {name} ({len(docs)} matches) ---")
            for i, doc in enumerate(docs, 1):
                meta = doc.metadata
                page_ref = meta.get("start_page", "?")
                lines.append(f"  {i}. [p. {page_ref}] {doc.page_content[:300].strip()}")

        if len(grouped) == 1:
            lines.append("\n(Note: 1 document matched. For multi-document comparisons, upload additional documents.)")

        return "\n".join(lines)

    def get_metadata(self, doc_name: str, page_num: int) -> str:
        """Return metadata about a specific page or section in a document."""
        doc = self._find_document(doc_name)
        if doc is None:
            return self._list_available_error()

        page = doc.get_page(page_num)
        if page is None:
            return f"ERROR: Page {page_num} not found (doc has {getattr(doc, 'total_pages', '?')} pages)."

        chunk_refs = []
        if self.vector_store is not None and getattr(self.vector_store, "embedding", None) is not None:
            try:
                chunks = self.vector_store.embedding.get_chunks_by_page(doc_name, page.page_number)
                chunk_refs = [
                    f"chunk {c.metadata.get('chunk_index', '?')}"
                    for c in chunks
                ]
            except Exception:
                pass

        refs_str = f" Referenced by: {', '.join(chunk_refs)}" if chunk_refs else ""
        return (
            f"Document: {doc.name} | Page {page.page_number} of {page.total_pages} | "
            f"Characters: {len(page.text)} | Source: {doc.file_path or 'memory'}.{refs_str}"
        )

    def add_documents(self, documents: list[PDFDocument]) -> None:
        self.documents.extend(documents)
        for d in documents:
            self._doc_map[d.name] = d

    # ------------------------------------------------------------------
    # Tool: extract_table
    # ------------------------------------------------------------------

    def extract_table(self, doc_name: str, page_num: int, table_index: int = 0) -> str:
        """Extract a structured table from a specific page of a document."""
        doc = self._find_document(doc_name)
        if doc is None:
            return self._list_available_error()

        file_path = getattr(doc, "file_path", None)
        if not file_path:
            return f"ERROR: No file path available for '{doc_name}'."

        from backend.documents.structure import extract_tables

        try:
            tables = extract_tables(file_path, pages=[page_num])
        except Exception as exc:
            return f"ERROR: Could not extract tables: {exc}"

        if not tables:
            return f"No tables found on page {page_num} of '{doc_name}'."

        if table_index >= len(tables):
            return (
                f"ERROR: Table index {table_index} out of range. "
                f"Found {len(tables)} table(s) on page {page_num}."
            )

        table = tables[table_index]
        return (
            f"=== Table {table_index + 1} from {doc.name} — Page {page_num} ===\n\n"
            + table.to_markdown()
        )

    # ------------------------------------------------------------------
    # Tool: verify_fact
    # ------------------------------------------------------------------

    def verify_fact(self, claim: str, top_k: int = 10) -> str:
        """Search the document for evidence supporting or contradicting a claim."""
        if self.vector_store is None:
            return "ERROR: No vector store available. Documents not loaded."

        docs = self.vector_store.search(claim, top_k=top_k)
        if not docs:
            return f"No evidence found in the documents for: '{claim}'"

        lines = [f"=== Fact-check: '{claim}' ===", ""]
        for i, doc in enumerate(docs, 1):
            meta = doc.metadata
            source = meta.get("doc_name", "unknown")
            page = meta.get("start_page", "?")
            snippet = doc.page_content[:400].strip()
            lines.append(f"Evidence {i}: [{source} p.{page}]")
            lines.append(f"  {snippet}")

        # Use LLM to classify support/contradiction if available
        if self.llm is not None:
            try:
                from langchain_core.messages import HumanMessage

                evidence_text = "\n\n".join(
                    f"[{d.metadata.get('doc_name', '?')} p.{d.metadata.get('start_page', '?')}]: "
                    f"{d.page_content[:300].strip()}"
                    for d in docs
                )
                prompt = (
                    f"Claim: {claim}\n\n"
                    f"Evidence:\n{evidence_text}\n\n"
                    f"Is the claim SUPPORTED, CONTRADICTED, or UNDETERMINED by the evidence? "
                    f"Give a verdict and cite the source. Reply in 3-5 sentences."
                )
                response = self.llm.invoke([HumanMessage(content=prompt)])
                verdict = response.content if hasattr(response, "content") else str(response)
                if not isinstance(verdict, str):
                    verdict = str(verdict)
                lines.append("")
                lines.append("=== Assessment ===")
                lines.append(verdict)
            except Exception:
                pass

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Tool: calculate
    # ------------------------------------------------------------------

    def calculate(self, expression: str) -> str:
        """Evaluate a mathematical expression containing numbers from the documents."""
        if not expression.strip():
            return "ERROR: Empty expression."

        # Extract all numeric tokens to give context
        re.findall(r"[-+]?\d+\.?\d*(?:[eE][-+]?\d+)?", expression)

        try:
            # Safely evaluate basic arithmetic
            allowed_names: dict[str, Any] = {}
            result = eval(  # noqa: S307 - restricted to math expressions
                expression,
                {"__builtins__": {}},
                allowed_names,
            )
            result_str = f"{result}"
            if "." in result_str:
                result_str = f"{float(result_str):.4g}"
            return f"Result: {result_str}"
        except Exception as exc:
            return f"ERROR: Could not evaluate '{expression}': {exc}"

    # ------------------------------------------------------------------
    # Tool: extract_invoice_data
    # ------------------------------------------------------------------

    def extract_invoice_data(self, doc_name: str) -> str:
        """Extract structured invoice data as JSON using the LLM or vision OCR."""
        doc = self._find_document(doc_name)
        if doc is None:
            return self._list_available_error()

        if hasattr(doc, "structured_data") and doc.structured_data:
            import json
            return json.dumps(doc.structured_data, indent=2, ensure_ascii=False)

        text = doc.full_text if hasattr(doc, "full_text") and doc.full_text else self._doc_text(doc)

        if not text or len(text.strip()) < 80:
            # Automatically use vision OCR if text is sparse or scanned
            try:
                ocr_res = self.ocr_extract_invoice(doc_name)
                if ocr_res and not ocr_res.startswith("ERROR:"):
                    return ocr_res
            except Exception:
                pass

        if not text:
            return f"ERROR: Could not extract text from '{doc_name}'."

        if self.llm is None:
            return (
                "ERROR: No LLM available for structured extraction. "
                "Falling back to plain text search."
            )

        prompt = (
            "Extract invoice data from the following text. Return ONLY valid JSON. "
            "If the document is not an invoice, return {'is_invoice': false, 'reason': '...'}. "
            "For invoices, include: vendor (name, address, email, phone), "
            "client (name, address, email), invoice_number, invoice_date (ISO), "
            "due_date (ISO), currency, line_items (list of {description, quantity, "
            "unit_price, amount, tax_rate}), subtotal, tax_total, total, payment_terms, "
            "po_number, notes.\n\n"
            f"=== DOCUMENT TEXT ===\n{text[:60000]}\n"
        )
        try:
            from langchain_core.messages import HumanMessage

            response = self.llm.invoke([HumanMessage(content=prompt)])
            content = response.content if hasattr(response, "content") else str(response)
            if not isinstance(content, str):
                content = str(content)
            return content.strip()
        except Exception as exc:
            return f"ERROR: Invoice extraction failed: {exc}"

    # ------------------------------------------------------------------
    # Tool: extract_contract_data
    # ------------------------------------------------------------------

    def extract_contract_data(self, doc_name: str) -> str:
        """Extract structured contract data as JSON using the LLM or vision OCR."""
        doc = self._find_document(doc_name)
        if doc is None:
            return self._list_available_error()

        if hasattr(doc, "structured_data") and doc.structured_data:
            import json
            return json.dumps(doc.structured_data, indent=2, ensure_ascii=False)

        text = doc.full_text if hasattr(doc, "full_text") and doc.full_text else self._doc_text(doc)

        if not text or len(text.strip()) < 80:
            # Automatically use vision OCR if text is sparse or scanned
            try:
                ocr_res = self.ocr_extract_contract(doc_name)
                if ocr_res and not ocr_res.startswith("ERROR:"):
                    return ocr_res
            except Exception:
                pass

        if not text:
            return f"ERROR: Could not extract text from '{doc_name}'."

        if self.llm is None:
            return (
                "ERROR: No LLM available for structured extraction. "
                "Falling back to plain text search."
            )

        prompt = (
            "Extract contract data from the following text. Return ONLY valid JSON. "
            "If the document is not a contract, return {'is_contract': false, 'reason': '...'}. "
            "For contracts, include: parties (list of {name, address, email, role}), "
            "effective_date (ISO), expiration_date (ISO), renewal_terms, governing_law, "
            "jurisdiction, key_clauses (list of {name, text, page}), payment_terms, "
            "obligations, risk_flags (list of {flag, severity, clause, recommendation}), "
            "termination_notice, dispute_resolution.\n\n"
            f"=== DOCUMENT TEXT ===\n{text[:60000]}\n"
        )
        try:
            from langchain_core.messages import HumanMessage

            response = self.llm.invoke([HumanMessage(content=prompt)])
            content = response.content if hasattr(response, "content") else str(response)
            if not isinstance(content, str):
                content = str(content)
            return content.strip()
        except Exception as exc:
            return f"ERROR: Contract extraction failed: {exc}"

    # ------------------------------------------------------------------
    # Helper: text fallback
    # ------------------------------------------------------------------

    def _doc_text(self, doc: PDFDocument) -> str:
        """Get full text from a PDFDocument, falling back to page iteration."""
        chunks = []
        for i in range(getattr(doc, "total_pages", 1)):
            try:
                content = doc.get_page(i + 1)
                if content and getattr(content, "text", None):
                    chunks.append(content.text)
            except Exception:
                pass
        return "\n".join(chunks)

    # ------------------------------------------------------------------
    # Tool: get_outline
    # ------------------------------------------------------------------

    def get_outline(self, doc_name: str, max_depth: int = 3) -> str:
        """Retrieve the structural outline (headings) of a document."""
        doc = self._find_document(doc_name)
        if doc is None:
            return self._list_available_error()

        file_path = getattr(doc, "file_path", None)
        headings = []
        if file_path:
            from backend.documents.structure import extract_outline

            try:
                headings = extract_outline(file_path)
            except Exception:
                headings = []

        if not headings:
            from backend.documents.structure import extract_text_outline

            headings = extract_text_outline(doc)

        if not headings:
            return f"No headings found in '{doc_name}'."

        # Filter by depth and format
        lines = [f"=== Document outline: {doc.name} ===", ""]
        for h in headings:
            if h.level <= max_depth:
                indent = "  " * (h.level - 1)
                lines.append(f"{indent}• {h.text} (page {h.page_number})")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Helpers (inherited-style from DocumentToolKit)
    # ------------------------------------------------------------------

    def _find_document(self, doc_name: str) -> Optional[PDFDocument]:
        if not self.documents:
            return None
        if (not self._doc_map or len(self._doc_map) != len(self.documents)):
            self._doc_map = {d.name: d for d in self.documents}

        # If only 1 document is in the bundle, resolve to it automatically
        if len(self.documents) == 1:
            return self.documents[0]

        clean_doc = str(doc_name or "").strip()
        if not clean_doc or clean_doc.lower() in ("document", "current", "file", "default"):
            return self.documents[0]

        if clean_doc in self._doc_map:
            return self._doc_map[clean_doc]

        lower = clean_doc.lower()
        base_target = Path(clean_doc).stem.lower()
        for name, doc in self._doc_map.items():
            base_name = Path(name).stem.lower()
            if lower in name.lower() or name.lower() in lower:
                return doc
            if base_target == base_name or base_target in base_name or base_name in base_target:
                return doc

        return self.documents[0]

    def _list_available_error(self) -> str:
        names = ", ".join(self._doc_map.keys()) if self._doc_map else "none"
        return f"ERROR: Document not found. Available documents: {names}"

    # ------------------------------------------------------------------
    # Tool: ocr_read_page (vision-based OCR for scanned PDFs)
    # ------------------------------------------------------------------

    def ocr_read_page(self, doc_name: str, page_num: int) -> str:
        """Use vision-based OCR to read a specific page (for scanned PDFs)."""
        doc = self._find_document(doc_name)
        if doc is None:
            return self._list_available_error()

        file_path = getattr(doc, "file_path", None) or getattr(doc, "path", None)
        if not file_path:
            return f"ERROR: No file path available for '{doc_name}'."

        try:
            from backend.agent.tools.ocr import OcrService

            service = OcrService(llm=self.llm)
            return service.ocr_read_page(Path(file_path), page_num)
        except Exception as exc:
            return f"ERROR: OCR failed: {exc}"

    # ------------------------------------------------------------------
    # Tool: ocr_extract_invoice (vision-based invoice extraction)
    # ------------------------------------------------------------------

    def ocr_extract_invoice(self, doc_name: str, page_num: Optional[int] = None) -> str:
        """Use vision-based OCR to extract structured invoice data as JSON."""
        doc = self._find_document(doc_name)
        if doc is None:
            return self._list_available_error()

        file_path = getattr(doc, "file_path", None) or getattr(doc, "path", None)
        if not file_path:
            return f"ERROR: No file path available for '{doc_name}'."

        try:
            from backend.agent.tools.ocr import OcrService

            service = OcrService(llm=self.llm)
            return service.ocr_extract_invoice(Path(file_path), page_num)
        except Exception as exc:
            return f"ERROR: Invoice OCR failed: {exc}"

    # ------------------------------------------------------------------
    # Tool: ocr_extract_contract (vision-based contract extraction)
    # ------------------------------------------------------------------

    def ocr_extract_contract(self, doc_name: str, page_num: Optional[int] = None) -> str:
        """Use vision-based OCR to extract structured contract data as JSON."""
        doc = self._find_document(doc_name)
        if doc is None:
            return self._list_available_error()

        file_path = getattr(doc, "file_path", None) or getattr(doc, "path", None)
        if not file_path:
            return f"ERROR: No file path available for '{doc_name}'."

        try:
            from backend.agent.tools.ocr import OcrService

            service = OcrService(llm=self.llm)
            return service.ocr_extract_contract(Path(file_path), page_num)
        except Exception as exc:
            return f"ERROR: Contract OCR failed: {exc}"

    # ------------------------------------------------------------------
    # Tool: ocr_extract_blocks (Layout Blocks: text, title, tables, images)
    # ------------------------------------------------------------------

    def ocr_extract_blocks(self, doc_name: str, page_num: Optional[int] = None) -> str:
        """Extract semantic blocks, full OCR transcription, and page continuation links."""
        doc = self._find_document(doc_name)
        if doc is None:
            return self._list_available_error()

        file_path = getattr(doc, "file_path", None) or getattr(doc, "path", None)
        if not file_path:
            return f"ERROR: No file path available for '{doc_name}'."

        try:
            import json

            from backend.agent.tools.ocr import OcrService

            service = OcrService(llm=self.llm)
            data = service.ocr_extract_blocks(Path(file_path), page_num)
            return json.dumps(data, ensure_ascii=False)
        except Exception as exc:
            return f"ERROR: Layout blocks extraction failed: {exc}"

    # ------------------------------------------------------------------
    # Tool: ocr_page_blocks (Bilingual Arabic & English Blocks by Page)
    # ------------------------------------------------------------------

    def ocr_page_blocks(
        self,
        doc_name: str,
        page_num: int,
        language: str = "auto",
        force_ocr: bool = False,
    ) -> str:
        """Extract bilingual Arabic and English layout blocks for a specific page."""
        doc = self._find_document(doc_name)
        if doc is None:
            return self._list_available_error()

        file_path = getattr(doc, "file_path", None) or getattr(doc, "path", None)
        if not file_path:
            return f"ERROR: No file path available for '{doc_name}'."

        try:
            import json

            from backend.agent.tools.ocr import OcrService

            service = OcrService(llm=self.llm)
            data = service.ocr_read_page_blocks(
                Path(file_path),
                page_number=page_num,
                language=language,
                force_ocr=force_ocr,
            )
            return json.dumps(data, ensure_ascii=False)
        except Exception as exc:
            return f"ERROR: Failed to extract blocks for page {page_num}: {exc}"

    # ------------------------------------------------------------------
    # Tool: google_ai_parse_document (Google AI Document Intelligence)
    # ------------------------------------------------------------------

    def google_ai_parse_document(self, doc_name: str, task: str = "comprehensive") -> str:
        """Analyze document structure, layout, entities, and tables using Google AI Document Intelligence."""
        doc = self._find_document(doc_name)
        if doc is None:
            return self._list_available_error()

        file_path = getattr(doc, "file_path", None) or getattr(doc, "path", None)
        text = doc.full_text if hasattr(doc, "full_text") and doc.full_text else self._doc_text(doc)

        try:
            from backend.agent.tools.google_document_ai import GoogleDocumentAIService

            service = GoogleDocumentAIService(llm=self.llm)
            if file_path and Path(file_path).exists():
                return service.analyze_pdf(Path(file_path), task=task)
            elif text:
                return service.analyze_document_text(text, doc_name=doc.name, task=task)
            else:
                return f"ERROR: No content available to analyze for '{doc_name}'."
        except Exception as exc:
            return f"ERROR: Google AI Document parsing failed: {exc}"

    # ------------------------------------------------------------------
    # Tool: extract_receipt_data
    # ------------------------------------------------------------------

    def extract_receipt_data(self, doc_name: str) -> str:
        """Extract structured receipt and expense data as JSON using the LLM."""
        doc = self._find_document(doc_name)
        if doc is None:
            return self._list_available_error()

        text = doc.full_text if hasattr(doc, "full_text") and doc.full_text else self._doc_text(doc)
        if not text:
            return f"ERROR: Could not extract text from '{doc_name}'."

        if self.llm is None:
            return "ERROR: No LLM available for structured receipt extraction."

        prompt = (
            "You are an expense and receipt intelligence engine. Extract all receipt details from the document text. "
            "Return ONLY valid JSON. If not a receipt, return {'is_receipt': false, 'reason': '...'}.\n"
            "Include:\n"
            "- merchant: {name, address, phone, tax_id}\n"
            "- transaction: {date, time, receipt_number, currency, payment_method, card_last4}\n"
            "- line_items: [{description, quantity, unit_price, total_price, category}]\n"
            "- financials: {subtotal, tax_amount, tax_rate, tip, total_amount}\n"
            "- expense_category: (e.g. Meals & Entertainment, Travel, Lodging, Office Supplies, Software, Utilities)\n"
            "- verification: {math_valid: boolean, notes: string}\n\n"
            f"=== DOCUMENT TEXT ===\n{text[:60000]}\n"
        )
        try:
            from langchain_core.messages import HumanMessage
            response = self.llm.invoke([HumanMessage(content=prompt)])
            content = response.content if hasattr(response, "content") else str(response)
            return content.strip() if isinstance(content, str) else str(content)
        except Exception as exc:
            return f"ERROR: Receipt extraction failed: {exc}"

    # ------------------------------------------------------------------
    # Tool: extract_resume_data
    # ------------------------------------------------------------------

    def extract_resume_data(self, doc_name: str) -> str:
        """Extract candidate profile and skills from resumes/CVs as JSON using the LLM."""
        doc = self._find_document(doc_name)
        if doc is None:
            return self._list_available_error()

        text = doc.full_text if hasattr(doc, "full_text") and doc.full_text else self._doc_text(doc)
        if not text:
            return f"ERROR: Could not extract text from '{doc_name}'."

        if self.llm is None:
            return "ERROR: No LLM available for resume extraction."

        prompt = (
            "You are an AI talent intelligence and resume parsing engine. Analyze the resume/CV text. "
            "Return ONLY valid JSON. If not a resume, return {'is_resume': false, 'reason': '...'}.\n"
            "Include:\n"
            "- candidate: {full_name, email, phone, location, linkedin, github, portfolio_url}\n"
            "- summary: professional summary string\n"
            "- skills: {technical: [string], soft: [string], languages: [string], tools_and_frameworks: [string]}\n"
            "- experience: [{company, role, start_date, end_date, is_current, responsibilities: [string], achievements: [string]}]\n"
            "- education: [{institution, degree, field_of_study, graduation_year, honors}]\n"
            "- certifications: [{name, issuer, year}]\n"
            "- profile_assessment: {total_years_experience: number, seniority_level: string, top_strengths: [string]}\n\n"
            f"=== DOCUMENT TEXT ===\n{text[:9000]}\n"
        )
        try:
            from langchain_core.messages import HumanMessage
            response = self.llm.invoke([HumanMessage(content=prompt)])
            content = response.content if hasattr(response, "content") else str(response)
            return content.strip() if isinstance(content, str) else str(content)
        except Exception as exc:
            return f"ERROR: Resume extraction failed: {exc}"

    # ------------------------------------------------------------------
    # Tool: audit_document_compliance
    # ------------------------------------------------------------------

    def audit_document_compliance(self, doc_name: str) -> str:
        """Audit document for PII, GDPR/HIPAA risks, and secret leaks as JSON."""
        doc = self._find_document(doc_name)
        if doc is None:
            return self._list_available_error()

        text = doc.full_text if hasattr(doc, "full_text") and doc.full_text else self._doc_text(doc)
        if not text:
            return f"ERROR: Could not extract text from '{doc_name}'."

        if self.llm is None:
            return "ERROR: No LLM available for compliance audit."

        prompt = (
            "You are an enterprise Data Privacy and Compliance Auditor. Analyze the document for sensitive data, "
            "Personally Identifiable Information (PII), confidential secrets, and regulatory compliance (GDPR, HIPAA).\n"
            "Return ONLY valid JSON containing:\n"
            "- compliance_status: 'Compliant' | 'Needs Review' | 'Critical Risk'\n"
            "- risk_score: number between 0 (safe) and 100 (critical breach risk)\n"
            "- pii_detected: [{type: 'SSN'|'CreditCard'|'Email'|'Phone'|'DOB'|'Address'|'Other', snippet: string, page_or_location: string, severity: 'High'|'Medium'|'Low'}]\n"
            "- secrets_or_credentials: [{type: string, snippet: string, severity: 'High'|'Critical'}]\n"
            "- regulatory_flags: {gdpr_concerns: [string], hipaa_concerns: [string]}\n"
            "- remediation_recommendations: [string]\n"
            "- redaction_summary: string explaining what sections must be masked\n\n"
            f"=== DOCUMENT TEXT ===\n{text[:9000]}\n"
        )
        try:
            from langchain_core.messages import HumanMessage
            response = self.llm.invoke([HumanMessage(content=prompt)])
            content = response.content if hasattr(response, "content") else str(response)
            return content.strip() if isinstance(content, str) else str(content)
        except Exception as exc:
            return f"ERROR: Compliance audit failed: {exc}"

    # ------------------------------------------------------------------
    # Tool: extract_form_fields
    # ------------------------------------------------------------------

    def extract_form_fields(self, doc_name: str) -> str:
        """Extract key-value pairs, checkboxes, and signatures from structured forms as JSON."""
        doc = self._find_document(doc_name)
        if doc is None:
            return self._list_available_error()

        text = doc.full_text if hasattr(doc, "full_text") and doc.full_text else self._doc_text(doc)
        if not text:
            return f"ERROR: Could not extract text from '{doc_name}'."

        if self.llm is None:
            return "ERROR: No LLM available for form field parsing."

        prompt = (
            "You are an Intelligent Form Parser engine. Extract all key-value fields, options, checkboxes, "
            "and signature states from this form document. Return ONLY valid JSON.\n"
            "Include:\n"
            "- form_metadata: {form_title, form_id_or_number, revision_date}\n"
            "- field_groups: [{group_title: string, fields: [{label: string, value: string, field_type: 'text'|'date'|'number'|'selection'}]}]\n"
            "- checkboxes_and_radios: [{label: string, is_selected: boolean}]\n"
            "- signatures: [{signer_name: string, signature_present: boolean, date_signed: string}]\n"
            "- missing_or_incomplete_fields: [string]\n\n"
            f"=== DOCUMENT TEXT ===\n{text[:9000]}\n"
        )
        try:
            from langchain_core.messages import HumanMessage
            response = self.llm.invoke([HumanMessage(content=prompt)])
            content = response.content if hasattr(response, "content") else str(response)
            return content.strip() if isinstance(content, str) else str(content)
        except Exception as exc:
            return f"ERROR: Form field extraction failed: {exc}"
