"""
RAG orchestration for the DocuChat backend.

Reuses the existing Python pipeline:

* ``documents``  — PDF loading (PyMuPDF) + metadata-rich chunking
* ``embeddings``  — OpenAI embeddings + hybrid (BM25 + dense) retrieval
* ``agent``       — free ReAct agent with document tools
* ``chat``        — conversational retrieval chain + prompts

Documents are processed at upload time (text extraction, chunking, embedding
indexing).  The in-memory FAISS index is cached for the lifetime of the process;
chunk *text* + metadata is also persisted in PostgreSQL so an index can be
rebuilt (and re-embedded) from the database if the process restarts.
"""

from __future__ import annotations

import logging
import shutil
import threading
import uuid
from pathlib import Path
from typing import Optional

from fastapi.encoders import jsonable_encoder
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from backend.agent.agent import AgentConfig, FreeAgent
from backend.agent.agents.anomaly_audit import AnomalyAuditAgent
from backend.agent.agents.base import BaseAgent, BaseAgentConfig
from backend.agent.agents.classifier import ClassifierAgent
from backend.agent.agents.comparison import ComparisonAgent
from backend.agent.agents.compliance import ComplianceAgent
from backend.agent.agents.contract import ContractAgent
from backend.agent.agents.coordinator import CoordinatorAgent
from backend.agent.agents.extraction import ExtractionAgent
from backend.agent.agents.factcheck import FactCheckAgent
from backend.agent.agents.financial_statement import FinancialStatementAgent
from backend.agent.agents.form_parser import FormParserAgent
from backend.agent.agents.google_ai import GoogleAIDocumentAgent
from backend.agent.agents.invoice import InvoiceAgent
from backend.agent.agents.receipt import ReceiptAgent
from backend.agent.agents.redaction import RedactionAgent
from backend.agent.agents.research import ResearchAgent
from backend.agent.agents.resume import ResumeAgent
from backend.agent.agents.summary import SummaryAgent
from backend.agent.agents.translation import TranslationAgent
from backend.agent.tools.document_tools import DocumentToolKit
from backend.agent.tools.enhanced import EnhancedDocumentKit
from backend.chat.chatWithVSDB import get_conversation_chain, get_llm
from backend.documents.limits import MAX_DOCUMENT_PAGES, validate_page_count, validate_upload_size
from backend.documents.loader import load_document
from backend.documents.processors import DocumentProcessor, ProcessingConfig
from backend.embeddings.smart_embedding import SmartEmbedding, SmartEmbeddingConfig
from backend.embeddings.vectoreStore import SmartVectorStore

from .config import settings
from .db import get_conn, query


class IndexBundle:
    """Cached, in-memory representation of a processed document."""

    def __init__(self, doc_id: str):
        self.doc_id = doc_id
        self.vector_store: Optional[SmartVectorStore] = None
        self.pdf_docs: list = []
        self.model_name: str = settings.DEFAULT_MODEL

    def ensure_loaded(self) -> None:
        if self.vector_store is not None:
            return
        # Rebuild the FAISS index from persisted chunks (re-embeds).
        rows = (
            query(
                "SELECT text, metadata FROM docuchat.chunks WHERE document_id = %s ORDER BY chunk_index",
                (self.doc_id,),
            )
            or []
        )
        chunks: list[Document] = [Document(page_content=r["text"], metadata=r["metadata"] or {}) for r in rows]
        if not chunks:
            return
        emb = SmartEmbedding(_emb_config())
        vs = SmartVectorStore(embedding=emb).build(chunks)
        self.vector_store = vs
        file_path = _pdf_path(self.doc_id)
        if file_path.exists():
            self.pdf_docs = [load_document(file_path)]


logger = logging.getLogger(__name__)

_registry: dict[str, IndexBundle] = {}
_lock = threading.RLock()


def _emb_config() -> SmartEmbeddingConfig:
    return SmartEmbeddingConfig(
        embedding_model=settings.EMBEDDING_MODEL,
        embedding_api_key=settings.OPENAI_API_KEY or None,
        use_reranker=False,
        use_hybrid=True,
        use_rrf=True,
    )


def _ensure_dirs() -> None:
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    Path(settings.INDEX_DIR).mkdir(parents=True, exist_ok=True)


def _pdf_path(doc_id: str) -> Path:
    # original filename stored on the documents row
    row = query("SELECT filename FROM docuchat.documents WHERE id = %s", (doc_id,), one=True)
    if not row:
        return Path(settings.UPLOAD_DIR) / f"{doc_id}.pdf"
    return Path(settings.UPLOAD_DIR) / doc_id / row["filename"]


class UploadResult(tuple):
    """Backwards-compatible tuple (chunk_count, page_count) that also holds document_id."""

    chunk_count: int
    page_count: int
    document_id: str

    def __new__(cls, chunk_count: int, page_count: int, document_id: str):
        instance = super().__new__(cls, (chunk_count, page_count))
        instance.chunk_count = chunk_count
        instance.page_count = page_count
        instance.document_id = document_id
        return instance


def process_upload(
    user_id: str,
    file_path: Path,
    original_filename: str,
    file_size: int,
    mime: str,
    max_pages: int = MAX_DOCUMENT_PAGES,
) -> UploadResult:
    """Process an uploaded document: chunk, embed-index, persist chunks.

    Returns UploadResult(chunk_count, page_count, document_id).
    """
    validate_upload_size(file_path.stat().st_size)
    _ensure_dirs()
    doc_id = str(uuid.uuid4())

    # Parse and embed before publishing metadata. Failed processing leaves no partial document.
    original_filename = Path(original_filename.replace("\\", "/")).name
    if not original_filename or original_filename in {".", ".."}:
        raise ValueError("Invalid filename")
    doc_dir = Path(settings.UPLOAD_DIR) / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)
    dest = doc_dir / original_filename
    try:
        shutil.copyfile(file_path, dest)
        from backend.storage import storage_service

        try:
            pdf_doc = load_document(dest)
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("This file could not be read. Check that it is a valid, unencrypted document.") from exc
        page_count = pdf_doc.total_pages
        validate_page_count(page_count, max_pages)
        storage_service.upload(f"documents/{doc_id}/{original_filename}", file_path, content_type=mime)
        processor = DocumentProcessor(
            ProcessingConfig(
                use_semantic_split=True,
                chunk_size=4000,
                chunk_overlap=500,
                min_semantic_chunk=1500,
            )
        )
        chunks = processor.process_documents([pdf_doc])
        if not chunks:
            raise ValueError("No readable content found in this file.")
        emb = SmartEmbedding(_emb_config())
        vs = SmartVectorStore(embedding=emb).build(chunks)
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO docuchat.documents "
                    "(id, user_id, filename, original_filename, file_size, mime_type, page_count) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (doc_id, user_id, original_filename, original_filename, file_size, mime, page_count),
                )
                for idx, ch in enumerate(chunks):
                    meta = {
                        **ch.metadata,
                        "doc_name": original_filename,
                        "source": original_filename,
                        "chunk_index": idx,
                    }
                    cur.execute(
                        "INSERT INTO docuchat.chunks "
                        "(id, document_id, page_index, chunk_index, text, metadata) "
                        "VALUES (%s, %s, %s, %s, %s, %s)",
                        (str(uuid.uuid4()), doc_id, ch.metadata.get("start_page"), idx, ch.page_content, _jsonb(meta)),
                    )
    except Exception:
        shutil.rmtree(doc_dir, ignore_errors=True)
        raise

    with _lock:
        bundle = IndexBundle(doc_id)
        bundle.vector_store = vs
        bundle.pdf_docs = [pdf_doc]
        _registry[doc_id] = bundle

    return UploadResult(len(chunks), page_count, doc_id)


def get_bundle(doc_id: str) -> IndexBundle:
    """Return a cached bundle, rebuilding from the DB if necessary."""
    with _lock:
        bundle = _registry.get(doc_id)
        if bundle is not None:
            bundle.ensure_loaded()
            return bundle
        bundle = IndexBundle(doc_id)
        bundle.ensure_loaded()
        _registry[doc_id] = bundle
        return bundle


def get_page_text(doc_id: str, page: int) -> Optional[str]:
    """Reconstruct page text from DB chunks when the PDF file is missing."""
    rows = query(
        "SELECT text, metadata FROM docuchat.chunks WHERE document_id = %s ORDER BY chunk_index",
        (doc_id,),
    )
    if not rows:
        return None
    page_texts: list[str] = []
    for r in rows:
        meta = r["metadata"] or {}
        start_page = meta.get("start_page")
        end_page = meta.get("end_page")
        if start_page is not None and end_page is not None:
            if start_page <= page <= end_page:
                page_texts.append(r["text"])
        elif r.get("page_index") == page:
            page_texts.append(r["text"])
    if not page_texts:
        return None
    return "\n\n".join(page_texts)


def get_history(session_id: str) -> list:
    rows = query(
        "SELECT role, content FROM (SELECT role, content, created_at FROM docuchat.messages "
        "WHERE session_id = %s ORDER BY created_at DESC LIMIT 20) recent ORDER BY created_at ASC",
        (session_id,),
    )
    messages: list = []
    for r in rows or []:
        if r["role"] == "user":
            messages.append(HumanMessage(content=r["content"]))
        else:
            messages.append(AIMessage(content=r["content"]))
    return messages


def _jsonb(val) -> str:
    import json

    return json.dumps(val)


def stream_chat(
    doc_id: str,
    query: str,
    history: list,
    model_name: str = settings.DEFAULT_MODEL,
    mode: str = "conversational",
    response_style: str = "balanced",
    service_options=None,
):
    """Yield streamed text chunks for a user turn.

    Supported ``mode`` values:

    * ``"conversational"`` — retrieval + LLM (classic Q&A)
    * ``"agent"`` — free ReAct agent (general research)
    * ``"summary"`` — executive summary agent
    * ``"research"`` — research agent (evidence gathering + verification)
    * ``"extraction"`` — data extraction agent (tables, metrics)
    * ``"comparison"`` — multi-document comparison agent
    * ``"factcheck"`` — claim verification agent
    * ``"coordinator"`` — routes to the best specialist agent
    """
    bundle = get_bundle(doc_id)
    if bundle.vector_store is None:
        yield "[ERROR] Document index not available. Re-upload the document."
        return

    instruction = {
        "concise": "Keep the answer brief and focused, using bullets where useful.",
        "balanced": "Give a clear answer with the evidence needed to support it.",
        "detailed": "Provide a thorough analysis with headings and specific evidence.",
    }.get(response_style, "")
    query = query + "\n\nResponse preference: " + instruction

    agent_modes = {
        "agent",
        "summary",
        "research",
        "extraction",
        "comparison",
        "factcheck",
        "coordinator",
        "invoice",
        "contract",
        "google_ai",
        "receipt",
        "resume",
        "compliance",
        "form_parser",
        "redaction",
        "classifier",
        "financial_statement",
        "translation",
        "anomaly_audit",
    }
    if mode in agent_modes:
        yield from _stream_agent(bundle, query, history, model_name, mode, service_options=service_options)
    else:
        yield from _stream_conversational(bundle, query, history, model_name)


def _stream_conversational(bundle: IndexBundle, query: str, history: list, model_name: str):
    chain = get_conversation_chain(bundle.vector_store, model_name=model_name)
    docs = chain._retrieve(query)  # type: ignore[attr-defined]
    context = chain._format_docs(docs)  # type: ignore[attr-defined]

    messages: list = [
        SystemMessage(content=chain.system_prompt.format(context=context)),
    ]
    messages.extend(history[-20:])
    messages.append(HumanMessage(content=query))

    llm = chain.llm
    emitted = False
    try:
        for chunk in llm.stream(messages):
            content = chunk.content if hasattr(chunk, "content") else str(chunk)
            if content:
                emitted = True
                yield content
    except Exception:
        if emitted:
            raise
        # Fallback to a single non-streaming completion.
        try:
            resp = llm.invoke(messages)
            content = resp.content if hasattr(resp, "content") else str(resp)
            if content:
                yield content
        except Exception:
            raise


def _build_toolkit(
    bundle: IndexBundle,
    model_name: str,
    enhanced: bool = False,
    temperature: Optional[float] = None,
):
    """Build a DocumentToolKit (or EnhancedDocumentKit) for agent use."""
    llm = get_llm(model_name=model_name, temperature=temperature)
    kit_cls = EnhancedDocumentKit if enhanced else DocumentToolKit
    return kit_cls(
        vector_store=bundle.vector_store,
        documents=bundle.pdf_docs,
        llm=llm,
    )


def create_text_bundle(text: str, name: str = "sample_document.txt") -> IndexBundle:
    """Create a lightweight in-memory IndexBundle from raw text for playground and quick runs."""
    import uuid

    from langchain_core.documents import Document as LCDocument

    from backend.documents.pdf_loader import PageText, PDFDocument

    doc_id = "mem-" + str(uuid.uuid4())[:8]
    bundle = IndexBundle(doc_id)
    pdf_doc = PDFDocument(
        name=name,
        pages=[PageText(page_number=1, text=text, doc_name=name, total_pages=1)],
        file_path="",
    )
    bundle.pdf_docs = [pdf_doc]

    chunks = [LCDocument(page_content=text, metadata={"page": 1, "source": name, "chunk_index": 0})]
    try:
        emb = SmartEmbedding(_emb_config())
        bundle.vector_store = SmartVectorStore(embedding=emb).build(chunks)
    except Exception as exc:
        logger.warning("Could not build SmartVectorStore for text bundle, falling back: %s", exc)
        from langchain_community.embeddings import FakeEmbeddings
        from langchain_community.vectorstores import FAISS

        bundle.vector_store = FAISS.from_documents(chunks, FakeEmbeddings(size=1536))

    with _lock:
        _registry[doc_id] = bundle
    return bundle


def _build_agent(
    bundle: IndexBundle,
    model_name: str,
    mode: str,
    system_prompt: Optional[str] = None,
    temperature: Optional[float] = None,
) -> BaseAgent:
    """Factory: build the appropriate agent for the requested mode."""
    use_enhanced = mode in {
        "extraction",
        "factcheck",
        "coordinator",
        "invoice",
        "contract",
        "google_ai",
        "receipt",
        "resume",
        "compliance",
        "form_parser",
        "redaction",
        "classifier",
        "financial_statement",
        "translation",
        "anomaly_audit",
    }
    toolkit = _build_toolkit(bundle, model_name, enhanced=use_enhanced, temperature=temperature)

    def _cfg(max_iter: int = 10):
        return BaseAgentConfig(
            max_iterations=max_iter,
            verbose=False,
            system_prompt=system_prompt or "",
            temperature=temperature,
        )

    if mode == "summary":
        agent: BaseAgent = SummaryAgent(
            llm=toolkit.llm,
            tool_kit=toolkit,
            config=_cfg(8),
        )
    elif mode == "research":
        agent = ResearchAgent(
            llm=toolkit.llm,
            tool_kit=toolkit,
            config=_cfg(10),
        )
    elif mode == "extraction":
        agent = ExtractionAgent(
            llm=toolkit.llm,
            tool_kit=toolkit,
            config=_cfg(8),
        )
    elif mode == "comparison":
        agent = ComparisonAgent(
            llm=toolkit.llm,
            tool_kit=toolkit,
            config=_cfg(8),
        )
    elif mode == "factcheck":
        agent = FactCheckAgent(
            llm=toolkit.llm,
            tool_kit=toolkit,
            config=_cfg(6),
        )
    elif mode == "invoice":
        agent = InvoiceAgent(
            llm=toolkit.llm,
            tool_kit=toolkit,
            config=_cfg(10),
        )
    elif mode == "contract":
        agent = ContractAgent(
            llm=toolkit.llm,
            tool_kit=toolkit,
            config=_cfg(12),
        )
    elif mode == "google_ai":
        agent = GoogleAIDocumentAgent(
            llm=toolkit.llm,
            tool_kit=toolkit,
            config=_cfg(10),
        )
    elif mode == "receipt":
        agent = ReceiptAgent(
            llm=toolkit.llm,
            tool_kit=toolkit,
            config=_cfg(10),
        )
    elif mode == "resume":
        agent = ResumeAgent(
            llm=toolkit.llm,
            tool_kit=toolkit,
            config=_cfg(10),
        )
    elif mode == "compliance":
        agent = ComplianceAgent(
            llm=toolkit.llm,
            tool_kit=toolkit,
            config=_cfg(10),
        )
    elif mode == "form_parser":
        agent = FormParserAgent(
            llm=toolkit.llm,
            tool_kit=toolkit,
            config=_cfg(10),
        )
    elif mode == "redaction":
        agent = RedactionAgent(
            llm=toolkit.llm,
            tool_kit=toolkit,
            config=_cfg(10),
        )
    elif mode == "classifier":
        agent = ClassifierAgent(
            llm=toolkit.llm,
            tool_kit=toolkit,
            config=_cfg(8),
        )
    elif mode == "financial_statement":
        agent = FinancialStatementAgent(
            llm=toolkit.llm,
            tool_kit=toolkit,
            config=_cfg(10),
        )
    elif mode == "translation":
        agent = TranslationAgent(
            llm=toolkit.llm,
            tool_kit=toolkit,
            config=_cfg(10),
        )
    elif mode == "anomaly_audit":
        agent = AnomalyAuditAgent(
            llm=toolkit.llm,
            tool_kit=toolkit,
            config=_cfg(10),
        )
    elif mode == "coordinator":
        coordinator = CoordinatorAgent(
            llm=toolkit.llm,
            tool_kit=toolkit,
            config=BaseAgentConfig(max_iterations=8, verbose=False),
        )
        # Register sub-agents
        for sub_name, sub_cls in [
            ("summary", SummaryAgent),
            ("research", ResearchAgent),
            ("extraction", ExtractionAgent),
            ("comparison", ComparisonAgent),
            ("factcheck", FactCheckAgent),
            ("invoice", InvoiceAgent),
            ("contract", ContractAgent),
            ("google_ai", GoogleAIDocumentAgent),
            ("receipt", ReceiptAgent),
            ("resume", ResumeAgent),
            ("compliance", ComplianceAgent),
            ("form_parser", FormParserAgent),
            ("redaction", RedactionAgent),
            ("classifier", ClassifierAgent),
            ("financial_statement", FinancialStatementAgent),
            ("translation", TranslationAgent),
            ("anomaly_audit", AnomalyAuditAgent),
            ("chat", FreeAgent),
        ]:
            sub = sub_cls(
                llm=get_llm(model_name=model_name),
                tool_kit=toolkit,
                config=BaseAgentConfig(max_iterations=8, verbose=False),
            )
            coordinator.register_sub_agent(sub_name, sub)
        agent = coordinator
    else:
        # Default: FreeAgent (general-purpose ReAct)
        agent = FreeAgent(
            llm=toolkit.llm,
            tool_kit=toolkit,
            config=AgentConfig(max_iterations=8, verbose=False),
        )

    return agent


def _stream_agent(
    bundle: IndexBundle,
    query: str,
    history: list,
    model_name: str,
    mode: str = "agent",
    service_options=None,
):

    recent = "\n".join(f"{m.type}: {m.content}" for m in history[-10:])
    full_query = "Conversation context (for reference only):\n" + recent + "\n\nCurrent request:\n" + query
    from backend.services.contracts import FIELDS

    if mode in FIELDS:
        from backend.services.engine import run_validated
        from backend.services.models import ServiceOptions, ServiceRequest

        validated = run_validated(
            ServiceRequest(
                service=mode,
                document_id=bundle.doc_id,
                query=full_query,
                model=model_name,
                options=service_options or ServiceOptions(),
            ),
            bundle,
        )
        import json

        text = json.dumps(
            jsonable_encoder(
                {"data": validated["data"], "fieldEvidence": validated["fieldEvidence"], "checks": validated["checks"]}
            ),
            ensure_ascii=False,
            indent=2,
        )
    else:
        agent = _build_agent(bundle, model_name, mode)
        result = agent.run(full_query)
        if not result.success:
            raise RuntimeError("Service execution failed")
        text = result.response or ""
    for i in range(0, len(text), 60):
        yield text[i : i + 60]
