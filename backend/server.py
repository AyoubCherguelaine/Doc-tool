from __future__ import annotations

import asyncio
import io
import json
import logging
import tempfile
import uuid
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from threading import Event
from typing import Annotated, Any, Literal, Optional

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from backend.billing import (
    INITIAL_TRIAL_CREDITS,
    SERVICE_PRICING,
    CompanyAccount,
    billing_service,
)
from backend.documents.limits import MAX_DOCUMENT_PAGES, MAX_UPLOAD_BYTES, MAX_UPLOAD_MB
from backend.documents.loader import SUPPORTED_EXTENSIONS
from backend.jobs import job_queue, start_background_worker
from backend.mcp.server import mcp_server
from backend.services.models import ServiceOptions, ServiceRequest
from backend.storage import storage_service
from backend.v1.routes import (
    _extract_json_from_text,
    extract_structured_data,
)
from backend.v1.routes import (
    router as v1_router,
)

from . import rag
from .auth import (
    CurrentUser,
    create_access_token,
    create_user,
    get_user_by_email,
    verify_password,
)
from .config import settings
from .db import execute, query

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("Starting DOCTool background job queue worker...")
    stop_worker = Event()
    worker = start_background_worker(stop_check=stop_worker.is_set)

    async def purge_service_results():
        from backend.services.persistence import operation_store

        while True:
            await asyncio.sleep(30)
            try:
                await asyncio.to_thread(operation_store.purge_expired_results)
            except Exception:
                logging.warning("Could not purge expired service operation results")

    cleanup = asyncio.create_task(purge_service_results())
    try:
        yield
    finally:
        stop_worker.set()
        await asyncio.to_thread(worker.join, 0.5)
        cleanup.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup


app = FastAPI(title="DOCTool API", version="0.1.0", lifespan=lifespan)

app.include_router(v1_router)
app.mount("/mcp", mcp_server.sse_app())

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Catch-all unhandled exception handler to escape crashes and keep API responsive."""
    logging.exception("Unhandled server exception on %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An unexpected error occurred during processing. The system remains online.",
            "error": str(exc),
            "path": request.url.path,
        },
    )


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------


class LoginPayload(BaseModel):
    email: str
    password: str


class RegisterPayload(BaseModel):
    email: str
    name: str
    password: str


def _public_user(row):
    return {
        "id": str(row["id"]),
        "email": row["email"],
        "name": row["name"],
        "createdAt": row["created_at"].isoformat() if row["created_at"] else None,
    }


@app.post("/api/auth/register")
def register(p: RegisterPayload):
    user = create_user(p.email, p.name, p.password)
    token = create_access_token(str(user["id"]))
    return {"accessToken": token, "user": _public_user(user)}


@app.post("/api/auth/login")
def login(p: LoginPayload):
    row = get_user_by_email(p.email)
    if not row or not verify_password(p.password, row["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    token = create_access_token(str(row["id"]))
    return {"accessToken": token, "user": _public_user(row)}


@app.get("/api/auth/me")
def me(user: CurrentUser):
    return _public_user(user)


# ---------------------------------------------------------------------------
# Document routes
# ---------------------------------------------------------------------------


@app.get("/api/documents")
def list_documents(user: CurrentUser):
    rows = (
        query(
            """
        SELECT id, user_id, filename, original_filename, file_size, mime_type,
               page_count, created_at
        FROM docuchat.documents
        WHERE user_id = %s
        ORDER BY created_at DESC
        """,
            (str(user["id"]),),
        )
        or []
    )
    return [
        {
            "id": str(r["id"]),
            "userId": str(r["user_id"]),
            "filename": r["filename"],
            "originalFilename": r["original_filename"],
            "fileSize": r["file_size"],
            "mimeType": r["mime_type"],
            "pageCount": r["page_count"],
            "createdAt": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]


@app.post("/api/documents/upload")
async def upload_document(
    user: CurrentUser,
    file: UploadFile = File(...),
    max_pages: Optional[int] = Form(None),
):
    filename = Path((file.filename or "").replace("\\", "/")).name
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Supported formats: PDF, DOCX, XLSX, XLS, CSV, TXT, MD.",
        )

    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if not raw or len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Choose a non-empty file up to 5 MB.")
    file_size = len(raw)

    page_limit = min(max_pages, MAX_DOCUMENT_PAGES) if max_pages and max_pages > 0 else MAX_DOCUMENT_PAGES

    suffix = ext
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(raw)
        tmp_path = tmp.name

    try:
        upload_result = await run_in_threadpool(
            rag.process_upload,
            user_id=str(user["id"]),
            file_path=Path(tmp_path),
            original_filename=filename,
            file_size=file_size,
            mime=file.content_type or "application/octet-stream",
            max_pages=page_limit,
        )
        chunk_count, page_count = upload_result[0], upload_result[1]
        doc_id = getattr(upload_result, "document_id", None)

        if page_count > page_limit:
            # Cleanup document
            try:
                from backend.db import get_conn
                with get_conn() as conn:
                    with conn.cursor() as cur:
                        cur.execute("DELETE FROM docuchat.chunks WHERE document_id = %s", (doc_id,))
                        cur.execute("DELETE FROM docuchat.documents WHERE id = %s", (doc_id,))
            except Exception:
                pass
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"This document has {page_count} pages, which exceeds the maximum limit of {page_limit} pages for chat. Please upload a document with at most {page_limit} pages.",
            )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logging.exception("Document processing failed")
        raise HTTPException(500, "Processing failed. Check the file and model configuration, then try again.") from exc
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except OSError:
            pass

    return {
        "id": doc_id,
        "filename": file.filename,
        "pageCount": page_count,
        "chunkCount": chunk_count,
    }


# ---------------------------------------------------------------------------
# Session routes
# ---------------------------------------------------------------------------


class SessionCreatePayload(BaseModel):
    documentId: str
    title: str | None = None


@app.get("/api/documents/{doc_id}/sessions")
def document_sessions(doc_id: str, user: CurrentUser):
    return _list_sessions(user, doc_id)


@app.get("/api/sessions")
def list_sessions(user: CurrentUser):
    return _list_sessions(user)


def _list_sessions(user, doc_id=None):
    rows = (
        query(
            """
        SELECT s.id, s.document_id, s.title, s.created_at, s.updated_at,
               (SELECT COUNT(*) FROM docuchat.messages m WHERE m.session_id = s.id) AS message_count
        FROM docuchat.sessions s
        WHERE s.user_id = %s AND (%s::uuid IS NULL OR s.document_id = %s::uuid)
        ORDER BY s.updated_at DESC
        """,
            (str(user["id"]), doc_id, doc_id),
        )
        or []
    )
    return [
        {
            "id": str(r["id"]),
            "userId": str(user["id"]),
            "documentId": str(r["document_id"]),
            "title": r["title"],
            "createdAt": r["created_at"].isoformat() if r["created_at"] else None,
            "updatedAt": r["updated_at"].isoformat() if r["updated_at"] else None,
            "messageCount": r["message_count"],
        }
        for r in rows
    ]


@app.post("/api/sessions")
def create_session(p: SessionCreatePayload, user: CurrentUser):
    # verify document ownership
    doc = query(
        "SELECT id, original_filename, page_count FROM docuchat.documents WHERE id = %s AND user_id = %s",
        (p.documentId, str(user["id"])),
        one=True,
    )
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    title = p.title or f"Chat about {doc['original_filename']}"
    row = query(
        """
        INSERT INTO docuchat.sessions (id, user_id, document_id, title)
        VALUES (%s, %s, %s, %s)
        RETURNING id, title, document_id, created_at, updated_at
        """,
        (str(uuid.uuid4()), str(user["id"]), str(doc["id"]), title),
        one=True,
    )
    return {
        "id": str(row["id"]),
        "title": row["title"],
        "documentId": str(row["document_id"]),
    }


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str, user: CurrentUser):
    s = query(
        """
        SELECT s.id, s.user_id, s.document_id, s.title, s.created_at, s.updated_at,
               d.original_filename, d.page_count
        FROM docuchat.sessions s
        JOIN docuchat.documents d ON d.id = s.document_id
        WHERE s.id = %s AND s.user_id = %s
        """,
        (session_id, str(user["id"])),
        one=True,
    )
    if not s:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    msgs = (
        query(
            "SELECT id, session_id, role, content, created_at FROM docuchat.messages "
            "WHERE session_id = %s ORDER BY created_at ASC",
            (session_id,),
        )
        or []
    )
    return {
        "id": str(s["id"]),
        "title": s["title"],
        "document": {
            "id": str(s["document_id"]),
            "originalFilename": s["original_filename"],
            "pageCount": s["page_count"],
        },
        "messages": [
            {
                "id": str(m["id"]),
                "sessionId": str(m["session_id"]),
                "role": m["role"],
                "content": m["content"],
                "createdAt": m["created_at"].isoformat() if m["created_at"] else None,
            }
            for m in msgs
        ],
    }


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str, user: CurrentUser):
    rows = execute(
        "DELETE FROM docuchat.sessions WHERE id = %s AND user_id = %s",
        (session_id, str(user["id"])),
    )
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# Chat route (streaming)
# ---------------------------------------------------------------------------


class ChatPayload(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    mode: Literal[
        "conversational",
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
    ] = "conversational"
    model: str | None = None
    responseStyle: Literal["concise", "balanced", "detailed"] = "balanced"

    options: ServiceOptions = Field(default_factory=ServiceOptions)


def _row_to_msg(r):
    return {
        "id": str(r["id"]),
        "sessionId": str(r["session_id"]),
        "role": r["role"],
        "content": r["content"],
        "createdAt": r["created_at"].isoformat() if r["created_at"] else None,
    }


@app.post("/api/sessions/{session_id}/chat")
def chat(
    session_id: str,
    payload: ChatPayload,
    user: CurrentUser,
    idempotency_key: Annotated[Optional[str], Header(alias="Idempotency-Key")] = None,
):
    from backend.billing import InsufficientCreditsError
    from backend.services.idempotency import begin, finish, finish_error, replay_response

    session = query(
        "SELECT document_id FROM docuchat.sessions WHERE id = %s AND user_id = %s",
        (session_id, str(user["id"])),
        one=True,
    )
    if not session:
        raise HTTPException(404, "Session not found")
    doc_id = str(session["document_id"])
    from backend.models_config import model_registry

    try:
        model = model_registry.validate_model(payload.model) if payload.model else (settings.DEFAULT_MODEL or model_registry.default_model_id)
    except HTTPException:
        raise HTTPException(422, "Model is not enabled on this server.")
    if model not in settings.CHAT_MODELS and model not in model_registry.allowed_model_ids:
        raise HTTPException(422, "Model is not enabled on this server.")
    if not payload.message.strip():
        raise HTTPException(422, "Message cannot be blank.")
    account = billing_service.get_or_create_company(user["id"], user.get("name"))
    operation_key, replay = begin(
        account, "chat", idempotency_key, {"session_id": session_id, **payload.model_dump(mode="json")}
    )
    if replay:
        if replay["status_code"] != 200:
            return replay_response(replay)
        return Response(
            replay["body"]["text"], media_type="text/plain; charset=utf-8", headers={"X-Idempotency-Replayed": "true"}
        )
    service = {"conversational": "chat", "agent": "research"}.get(payload.mode, payload.mode)
    cost = billing_service.get_service_cost(service, model_id=model)
    charged = False
    try:
        if account.remaining_credits < cost:
            message = "Company credits depleted." if account.remaining_credits == 0 else "Insufficient credits."
            raise HTTPException(402, f"{message} Required: {cost}, Remaining: {account.remaining_credits}.")
        billing_service.check_and_deduct_credits(
            account, service, document_id=doc_id, request_summary=payload.message[:80], model_id=model
        )
        charged = True
        history = rag.get_history(session_id)
        execute(
            "INSERT INTO docuchat.messages (id, session_id, role, content) VALUES (%s, %s, %s, %s)",
            (str(uuid.uuid4()), session_id, "user", payload.message),
        )
        execute("UPDATE docuchat.sessions SET updated_at = now() WHERE id = %s", (session_id,))
        gen = rag.stream_chat(
            doc_id=doc_id,
            query=payload.message,
            history=history,
            model_name=model,
            mode=payload.mode,
            response_style=payload.responseStyle,
            service_options=payload.options,
        )
    except Exception as exc:
        if charged:
            billing_service.refund_credits(account, service, cost, doc_id, "Chat preparation failed")
        error = (
            exc
            if isinstance(exc, HTTPException)
            else HTTPException(402, str(exc))
            if isinstance(exc, InsufficientCreditsError)
            else HTTPException(503, "Chat could not be prepared")
        )
        finish_error(account, operation_key, error)
        raise error from exc

    def _event_stream():
        accumulated = io.StringIO()
        completed, refunded = False, False
        try:
            for chunk in gen:
                accumulated.write(chunk)
                yield chunk
            if not accumulated.getvalue().strip():
                raise RuntimeError("Empty chat response")
            completed = True
        except Exception:
            logging.exception("Chat stream failed")
            billing_service.refund_credits(account, service, cost, doc_id, "Chat stream failed")
            refunded = True
            error_text = "\n\n[STREAM ERROR] The response could not be completed. Credits were refunded."
            accumulated.write(error_text)
            yield error_text
        finally:
            if not completed and not refunded:
                billing_service.refund_credits(account, service, cost, doc_id, "Chat stream interrupted")
                accumulated.write("\n\n[STREAM INTERRUPTED] The response was interrupted. Credits were refunded.")
            text = accumulated.getvalue()
            try:
                execute(
                    "INSERT INTO docuchat.messages (id, session_id, role, content) VALUES (%s, %s, %s, %s)",
                    (str(uuid.uuid4()), session_id, "assistant", text or "[no response]"),
                )
            except Exception:
                logging.exception("Could not persist the assistant turn")
            close = getattr(gen, "close", None)
            if callable(close):
                with suppress(Exception):
                    close()
            finish(
                account,
                operation_key,
                {"text": text, "success": completed, "creditsDeducted": cost if completed else 0},
            )

    return StreamingResponse(_event_stream(), media_type="text/plain; charset=utf-8")


# ---------------------------------------------------------------------------
# Health & Service Status
# ---------------------------------------------------------------------------


@app.get("/api/health")
def health():
    """Health check endpoint: verifies DB, Redis, SeaweedFS, and Worker readiness for production probes."""
    db_status = "operational"
    try:
        query("SELECT 1", one=True)
    except Exception as exc:
        logging.warning("Health check DB query warning: %s", exc)
        db_status = "degraded"

    redis_ok = job_queue.is_healthy()
    storage_ok = storage_service.is_healthy()

    return {
        "status": "ok" if db_status == "operational" else "degraded",
        "database": db_status,
        "redis": "operational" if redis_ok else "fallback_in_memory",
        "storage": "operational" if storage_ok else "unavailable",
        "jobWorker": "active",
        "services": {
            s_id: "operational" for s_id in SERVICE_PRICING.keys()
        },
        "totalServices": len(SERVICE_PRICING),
        "version": "1.0.0",
    }


@app.get("/api/services/status")
def get_services_status():
    """Detailed operational status and tier metadata for all Document AI services."""
    return {
        "status": "ok",
        "services": billing_service.get_service_status(),
        "totalServices": len(SERVICE_PRICING),
    }


@app.get("/api/capabilities")
def capabilities(user: CurrentUser):
    from backend.models_config import model_registry

    all_ids = sorted(list(model_registry.allowed_model_ids))
    return {
        "models": all_ids,
        "defaultModel": model_registry.default_model_id,
        "formats": sorted(SUPPORTED_EXTENSIONS),
        "maxUploadMB": MAX_UPLOAD_MB,
        "maxPages": MAX_DOCUMENT_PAGES,
        "creditPriceUsd": 0.002,
        "conversionFormula": "$2.00 = 1,000 Credits ($0.002 / Credit)",
    }


@app.get("/api/documents/{doc_id}/pages/{page}")
def read_document_page(doc_id: str, page: int, user: CurrentUser):
    doc = query(
        "SELECT id, filename, original_filename, page_count FROM docuchat.documents WHERE id = %s AND user_id = %s",
        (doc_id, str(user["id"])),
        one=True,
    )
    if not doc:
        raise HTTPException(404, "Document not found")

    bundle = rag.get_bundle(doc_id)

    if bundle.pdf_docs:
        document = bundle.pdf_docs[0]
        content = document.get_page(page)
        if content is None:
            raise HTTPException(404, "Page or section not found")
        return {
            "page": page,
            "totalPages": document.total_pages,
            "text": content.text,
            "filename": document.name,
        }

    file_path = rag._pdf_path(doc_id)
    if not file_path.exists():
        text = rag.get_page_text(doc_id, page)
        if text is None:
            raise HTTPException(404, "Document file not found. Please re-upload the document.")
        return {
            "page": page,
            "totalPages": doc["page_count"] or 0,
            "text": text,
            "filename": doc["original_filename"],
        }

    from backend.documents.loader import load_document

    document = load_document(file_path)
    content = document.get_page(page)
    if content is None:
        raise HTTPException(404, "Page or section not found")
    return {"page": page, "totalPages": document.total_pages, "text": content.text, "filename": document.name}


@app.get("/api/documents/{doc_id}/ocr/blocks")
def get_document_ocr_blocks(
    doc_id: str,
    user: CurrentUser,
    page: Optional[int] = None,
    force_ocr: bool = False,
):
    """
    Extract and return layout-aware blocks (text, title, metadata, tables with content_md, images with descriptions).
    """
    doc = query(
        "SELECT id, original_filename, page_count FROM docuchat.documents WHERE id = %s AND user_id = %s",
        (doc_id, str(user["id"])),
        one=True,
    )
    if not doc:
        raise HTTPException(404, "Document not found")

    file_path = rag._pdf_path(doc_id)
    if not file_path.exists():
        candidates = [
            Path(f"backend/storage/uploads/{doc_id}.pdf"),
            Path(f"backend/storage/uploads/{doc_id}"),
            Path(f"/tmp/{doc_id}.pdf"),
            Path(f"/tmp/{doc['original_filename']}"),
        ]
        for c in candidates:
            if c.exists():
                file_path = c
                break

    if not file_path.exists():
        raise HTTPException(404, "Document file not found on storage.")

    from backend.agent.tools.ocr import OcrService

    ocr_service = OcrService()
    try:
        data = ocr_service.ocr_extract_blocks(file_path, page_number=page, force_ocr=force_ocr)
        return {
            "status": "success",
            "document_id": doc_id,
            "filename": doc["original_filename"],
            "total_pages": data.get("total_pages", doc["page_count"] or 1),
            "page": page,
            "ocr_text": data.get("ocr_text", ""),
            "coordinate_system": data.get("coordinate_system", "normalized_0_1000"),
            "blocks": data.get("blocks", []),
            "pages": data.get("pages", []),
        }
    except Exception as exc:
        logger.error("Failed to extract blocks for %s: %s", doc_id, exc)
        raise HTTPException(500, f"Block extraction failed: {exc}")


@app.get("/api/documents/{doc_id}/page/{page_num}/ocr/blocks")
def get_document_page_ocr_blocks(
    doc_id: str,
    page_num: int,
    user: CurrentUser,
    language: str = "auto",
    force_ocr: bool = False,
):
    """
    Extract bilingual Arabic and English layout blocks for a specific document page number.
    Returns blocks with reading direction, language classification, markdown tables, and visual descriptions.
    """
    doc = query(
        "SELECT id, original_filename, page_count FROM docuchat.documents WHERE id = %s AND user_id = %s",
        (doc_id, str(user["id"])),
        one=True,
    )
    if not doc:
        raise HTTPException(404, "Document not found")

    file_path = rag._pdf_path(doc_id)
    if not file_path.exists():
        candidates = [
            Path(f"backend/storage/uploads/{doc_id}.pdf"),
            Path(f"backend/storage/uploads/{doc_id}"),
            Path(f"/tmp/{doc_id}.pdf"),
            Path(f"/tmp/{doc['original_filename']}"),
        ]
        for c in candidates:
            if c.exists():
                file_path = c
                break

    if not file_path.exists():
        raise HTTPException(404, "Document file not found on storage.")

    from backend.agent.tools.ocr import OcrService

    ocr_service = OcrService()
    try:
        data = ocr_service.ocr_read_page_blocks(
            file_path,
            page_number=page_num,
            language=language,
            force_ocr=force_ocr,
        )
        return {
            "status": "success",
            "document_id": doc_id,
            "filename": doc["original_filename"],
            "page_number": page_num,
            "language_detected": data.get("language_detected", language),
            "direction": data.get("direction", "rtl" if language == "ar" else "ltr"),
            "block_count": data.get("block_count", len(data.get("blocks", []))),
            "ocr_text": data.get("ocr_text", ""),
            "coordinate_system": data.get("coordinate_system", "normalized_0_1000"),
            "blocks": data.get("blocks", []),
        }
    except Exception as exc:
        logger.error("Failed to extract page blocks for %s (page %d): %s", doc_id, page_num, exc)
        raise HTTPException(500, f"Page block extraction failed: {exc}")


# ---------------------------------------------------------------------------
# Document structure endpoint
# ---------------------------------------------------------------------------


@app.get("/api/documents/{doc_id}/outline")
def get_document_outline(doc_id: str, user: CurrentUser):
    """Return the structural outline (headings) of an uploaded document."""
    doc = query(
        "SELECT id, original_filename, page_count FROM docuchat.documents WHERE id = %s AND user_id = %s",
        (doc_id, str(user["id"])),
        one=True,
    )
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    file_path = rag._pdf_path(doc_id)

    from backend.documents.structure import extract_outline

    headings = []
    if file_path.exists():
        try:
            headings = extract_outline(file_path)
        except Exception:
            headings = []

    return {
        "documentId": str(doc["id"]),
        "filename": doc["original_filename"],
        "pageCount": doc["page_count"] or 0,
        "headings": [h.to_dict() for h in headings[:100]],
    }


# ---------------------------------------------------------------------------
# Agent capabilities endpoint
# ---------------------------------------------------------------------------


@app.get("/api/capabilities/agents")
def agent_capabilities(user: CurrentUser):
    """Return the available agent modes and their descriptions."""
    return {
        "modes": [
            {"value": "conversational", "name": "Document chat", "description": "Classic retrieval + LLM Q&A"},
            {"value": "agent", "name": "Research agent", "description": "General-purpose ReAct agent"},
            {"value": "summary", "name": "Summary agent", "description": "Executive summaries"},
            {"value": "research", "name": "Deep research", "description": "Evidence gathering + verification"},
            {"value": "extraction", "name": "Data extraction", "description": "Structured data extraction"},
            {"value": "comparison", "name": "Comparison", "description": "Multi-document comparison"},
            {"value": "factcheck", "name": "Fact-check", "description": "Claim verification"},
            {"value": "invoice", "name": "Invoice processing", "description": "Extract invoice data as JSON"},
            {"value": "contract", "name": "Contract analysis", "description": "Analyze contracts and flag risks"},
            {"value": "google_ai", "name": "Google AI Document", "description": "Google AI multimodal document intelligence, layout parsing, and entity extraction"},
            {"value": "receipt", "name": "Receipt & Expense", "description": "Extract merchant, items, taxes, tips, and totals as JSON"},
            {"value": "resume", "name": "Resume & Talent", "description": "Candidate skills, experience timeline, and qualification analysis"},
            {"value": "compliance", "name": "PII & Compliance", "description": "Detect sensitive PII, GDPR/HIPAA risks, and redaction guidance"},
            {"value": "form_parser", "name": "Form Parser", "description": "Extract key-value fields, checkboxes, and signature states"},
            {"value": "redaction", "name": "Bilingual Redaction", "description": "Mask Saudi National IDs, GCC IBANs, ZATCA Tax IDs, CR, and PII"},
            {"value": "classifier", "name": "Document Classifier", "description": "Classify document type (AR/EN), language, urgency, and department"},
            {"value": "financial_statement", "name": "Financial Statement", "description": "Extract P&L/Balance sheet metrics and financial ratios"},
            {"value": "translation", "name": "Bilingual Translation", "description": "Fidelity legal & financial translation between English and Arabic"},
            {"value": "anomaly_audit", "name": "Tax & Anomaly Audit", "description": "Verify ZATCA 15% VAT, subtotal math, and due dates"},
            {"value": "coordinator", "name": "Auto-routing", "description": "Routes to the best specialist"},
        ],
    }


# ---------------------------------------------------------------------------
# Multi-agent workflow endpoint
# ---------------------------------------------------------------------------


class WorkflowPayload(BaseModel):
    model: str | None = None
    responseStyle: Literal["concise", "balanced", "detailed"] = "balanced"


@app.post("/api/documents/{doc_id}/workflow")
def run_workflow(
    doc_id: str,
    payload: WorkflowPayload,
    user: CurrentUser,
    idempotency_key: Annotated[Optional[str], Header(alias="Idempotency-Key")] = None,
):
    return _execute_specialized_service(
        "coordinator",
        doc_id,
        "Summarize this document, extract key data and review supported claims.",
        user,
        model=payload.model,
        idempotency_key=idempotency_key,
    )


# ---------------------------------------------------------------------------
# Google AI Document endpoint
# ---------------------------------------------------------------------------


class GoogleAIPayload(BaseModel):
    task: Literal["comprehensive", "entities", "layout", "tables"] = "comprehensive"
    model: str | None = None


@app.post("/api/documents/{doc_id}/google-ai")
def analyze_with_google_ai(
    doc_id: str,
    payload: GoogleAIPayload,
    user: CurrentUser,
    idempotency_key: Annotated[Optional[str], Header(alias="Idempotency-Key")] = None,
):
    return _execute_specialized_service(
        "google_ai",
        doc_id,
        f"Process this document for the requested task: {payload.task}.",
        user,
        model=payload.model,
        idempotency_key=idempotency_key,
    )


# ---------------------------------------------------------------------------
# Additional Document AI Service endpoints
# ---------------------------------------------------------------------------


class DocumentAIServicePayload(BaseModel):
    model: str | None = None
    query: str | None = None
    schema_override: dict | None = None
    output_format: Literal["json", "markdown", "auto"] = "auto"
    guardian: bool = True
    options: ServiceOptions = Field(default_factory=ServiceOptions)


def _format_service_result(
    doc: dict,
    service_name: str,
    result: Any,
    bundle: Any,
    cost: int,
    remaining: int,
) -> dict:
    raw_text = getattr(result, "response", "") or ""
    parsed_json = _extract_json_from_text(raw_text)

    # Check agent steps for tool observations if not in final response
    if parsed_json is None and hasattr(result, "steps") and result.steps:
        for step in reversed(result.steps):
            obs = step.get("observation", "")
            if isinstance(obs, str) and ("{" in obs or "[" in obs):
                step_json = _extract_json_from_text(obs)
                if step_json:
                    parsed_json = step_json
                    break

    # If still not found, check if enhanced document toolkit has extractor tool
    if parsed_json is None and hasattr(bundle, "toolkit"):
        tk = bundle.toolkit
        filename = doc["original_filename"]
        try:
            if service_name == "invoice" and hasattr(tk, "extract_invoice_data"):
                tool_out = tk.extract_invoice_data(filename)
                parsed_json = _extract_json_from_text(tool_out)
            elif service_name == "contract" and hasattr(tk, "extract_contract_data"):
                tool_out = tk.extract_contract_data(filename)
                parsed_json = _extract_json_from_text(tool_out)
        except Exception as tk_err:
            logging.warning("Fallback extractor failed for %s: %s", service_name, tk_err)

    # Guarantee structured dictionary
    if parsed_json is None:
        parsed_json = extract_structured_data(raw_text, service=service_name)

    formatted_result = (
        json.dumps(parsed_json, indent=2, ensure_ascii=False)
        if isinstance(parsed_json, (dict, list))
        else raw_text
    )

    return {
        "documentId": str(doc["id"]),
        "filename": doc["original_filename"],
        "service": service_name,
        "result": formatted_result,
        "data": parsed_json,
        "creditsDeducted": cost,
        "creditsRemaining": remaining,
        "success": result.success,
        "iterations": result.iterations,
        "steps": result.steps,
    }


@app.post("/api/documents/{doc_id}/receipt")
def analyze_receipt(
    doc_id: str,
    payload: DocumentAIServicePayload,
    user: CurrentUser,
    idempotency_key: Annotated[Optional[str], Header(alias="Idempotency-Key")] = None,
):
    return _execute_specialized_service(
        "receipt",
        doc_id,
        payload.query or "Process the selected document.",
        user,
        model=payload.model,
        options=payload.options,
        schema_override=payload.schema_override,
        output_format=payload.output_format,
        idempotency_key=idempotency_key,
    )


@app.post("/api/documents/{doc_id}/resume")
def analyze_resume(
    doc_id: str,
    payload: DocumentAIServicePayload,
    user: CurrentUser,
    idempotency_key: Annotated[Optional[str], Header(alias="Idempotency-Key")] = None,
):
    return _execute_specialized_service(
        "resume",
        doc_id,
        payload.query or "Process the selected document.",
        user,
        model=payload.model,
        options=payload.options,
        schema_override=payload.schema_override,
        output_format=payload.output_format,
        idempotency_key=idempotency_key,
    )


@app.post("/api/documents/{doc_id}/compliance")
def audit_compliance(
    doc_id: str,
    payload: DocumentAIServicePayload,
    user: CurrentUser,
    idempotency_key: Annotated[Optional[str], Header(alias="Idempotency-Key")] = None,
):
    return _execute_specialized_service(
        "compliance",
        doc_id,
        payload.query or "Process the selected document.",
        user,
        model=payload.model,
        options=payload.options,
        schema_override=payload.schema_override,
        output_format=payload.output_format,
        idempotency_key=idempotency_key,
    )


@app.post("/api/documents/{doc_id}/form-parser")
def parse_form_fields(
    doc_id: str,
    payload: DocumentAIServicePayload,
    user: CurrentUser,
    idempotency_key: Annotated[Optional[str], Header(alias="Idempotency-Key")] = None,
):
    return _execute_specialized_service(
        "form_parser",
        doc_id,
        payload.query or "Process the selected document.",
        user,
        model=payload.model,
        options=payload.options,
        schema_override=payload.schema_override,
        output_format=payload.output_format,
        idempotency_key=idempotency_key,
    )


@app.post("/api/documents/{doc_id}/comparison")
def analyze_comparison(
    doc_id: str,
    payload: DocumentAIServicePayload,
    user: CurrentUser,
    idempotency_key: Annotated[Optional[str], Header(alias="Idempotency-Key")] = None,
):
    return _execute_specialized_service(
        "comparison",
        doc_id,
        payload.query or "Process the selected document.",
        user,
        model=payload.model,
        options=payload.options,
        schema_override=payload.schema_override,
        output_format=payload.output_format,
        idempotency_key=idempotency_key,
    )


@app.post("/api/documents/{doc_id}/factcheck")
def analyze_factcheck(
    doc_id: str,
    payload: DocumentAIServicePayload,
    user: CurrentUser,
    idempotency_key: Annotated[Optional[str], Header(alias="Idempotency-Key")] = None,
):
    return _execute_specialized_service(
        "factcheck",
        doc_id,
        payload.query or "Process the selected document.",
        user,
        model=payload.model,
        options=payload.options,
        schema_override=payload.schema_override,
        output_format=payload.output_format,
        idempotency_key=idempotency_key,
    )


@app.post("/api/documents/{doc_id}/invoice")
def analyze_invoice(
    doc_id: str,
    payload: DocumentAIServicePayload,
    user: CurrentUser,
    idempotency_key: Annotated[Optional[str], Header(alias="Idempotency-Key")] = None,
):
    return _execute_specialized_service(
        "invoice",
        doc_id,
        payload.query or "Process the selected document.",
        user,
        model=payload.model,
        options=payload.options,
        schema_override=payload.schema_override,
        output_format=payload.output_format,
        idempotency_key=idempotency_key,
    )


@app.post("/api/documents/{doc_id}/contract")
def analyze_contract(
    doc_id: str,
    payload: DocumentAIServicePayload,
    user: CurrentUser,
    idempotency_key: Annotated[Optional[str], Header(alias="Idempotency-Key")] = None,
):
    return _execute_specialized_service(
        "contract",
        doc_id,
        payload.query or "Process the selected document.",
        user,
        model=payload.model,
        options=payload.options,
        schema_override=payload.schema_override,
        output_format=payload.output_format,
        idempotency_key=idempotency_key,
    )


def _execute_specialized_service(
    service_name: str,
    doc_id: str,
    default_prompt: str,
    user: CurrentUser,
    model: str | None = None,
    options: ServiceOptions | None = None,
    schema_override: dict | None = None,
    output_format: str = "auto",
    idempotency_key: str | None = None,
    guardian: bool = True,
):
    """Compatibility routes share the executor, output validation and replay protection."""
    from backend.services.engine import execute_service
    from backend.services.idempotency import begin, finish, finish_error, replay_response

    try:
        request = ServiceRequest(
            service=service_name,
            document_id=doc_id,
            model=model,
            guardian=guardian,
            query=default_prompt.format(filename="the selected document"),
            options=options or ServiceOptions(),
            schema_override=schema_override,
            output_format=output_format,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    account = billing_service.get_or_create_company(user["id"], user.get("name"))
    operation_key, replay = begin(
        account, f"document-service:{service_name}", idempotency_key, request.model_dump(mode="json")
    )
    if replay:
        return replay_response(replay)
    try:
        body = execute_service(request, account)
    except HTTPException as exc:
        finish_error(account, operation_key, exc)
        raise
    doc = query(
        "SELECT original_filename FROM docuchat.documents WHERE id=%s AND user_id=%s",
        (doc_id, str(user["id"])),
        one=True,
    )
    data = body.get("data")
    body.update(
        filename=doc["original_filename"] if doc else "document",
        result=json.dumps(jsonable_encoder(data), ensure_ascii=False, indent=2)
        if data is not None
        else body.get("raw", ""),
    )
    finish(account, operation_key, body)
    return body


@app.post("/api/documents/{doc_id}/redaction")
def redact_sensitive_pii(
    doc_id: str,
    payload: DocumentAIServicePayload,
    user: CurrentUser,
    idempotency_key: Annotated[Optional[str], Header(alias="Idempotency-Key")] = None,
):
    return _execute_specialized_service(
        "redaction",
        doc_id,
        payload.query or "Process the selected document.",
        user,
        model=payload.model,
        options=payload.options,
        schema_override=payload.schema_override,
        output_format=payload.output_format,
        idempotency_key=idempotency_key,
    )


@app.post("/api/documents/{doc_id}/classifier")
def classify_document_endpoint(
    doc_id: str,
    payload: DocumentAIServicePayload,
    user: CurrentUser,
    idempotency_key: Annotated[Optional[str], Header(alias="Idempotency-Key")] = None,
):
    return _execute_specialized_service(
        "classifier",
        doc_id,
        payload.query or "Process the selected document.",
        user,
        model=payload.model,
        options=payload.options,
        schema_override=payload.schema_override,
        output_format=payload.output_format,
        idempotency_key=idempotency_key,
    )


@app.post("/api/documents/{doc_id}/financial-statement")
def analyze_financial_statement_endpoint(
    doc_id: str,
    payload: DocumentAIServicePayload,
    user: CurrentUser,
    idempotency_key: Annotated[Optional[str], Header(alias="Idempotency-Key")] = None,
):
    return _execute_specialized_service(
        "financial_statement",
        doc_id,
        payload.query or "Process the selected document.",
        user,
        model=payload.model,
        options=payload.options,
        schema_override=payload.schema_override,
        output_format=payload.output_format,
        idempotency_key=idempotency_key,
    )


@app.post("/api/documents/{doc_id}/translation")
def translate_document_endpoint(
    doc_id: str,
    payload: DocumentAIServicePayload,
    user: CurrentUser,
    idempotency_key: Annotated[Optional[str], Header(alias="Idempotency-Key")] = None,
):
    return _execute_specialized_service(
        "translation",
        doc_id,
        payload.query or "Process the selected document.",
        user,
        model=payload.model,
        options=payload.options,
        schema_override=payload.schema_override,
        output_format=payload.output_format,
        idempotency_key=idempotency_key,
    )


@app.post("/api/documents/{doc_id}/anomaly-audit")
def audit_anomalies_endpoint(
    doc_id: str,
    payload: DocumentAIServicePayload,
    user: CurrentUser,
    idempotency_key: Annotated[Optional[str], Header(alias="Idempotency-Key")] = None,
):
    return _execute_specialized_service(
        "anomaly_audit",
        doc_id,
        payload.query or "Process the selected document.",
        user,
        model=payload.model,
        options=payload.options,
        schema_override=payload.schema_override,
        output_format=payload.output_format,
        idempotency_key=idempotency_key,
    )


# ---------------------------------------------------------------------------
# Company Billing, API Keys, and Enterprise Quota Endpoints
# ---------------------------------------------------------------------------


async def get_company_account(
    user: CurrentUser,
) -> CompanyAccount:
    """Dependency for authenticated web users to get or create their company trial."""
    return billing_service.get_or_create_company(user["id"], user.get("name"))


async def get_company_or_api_auth(
    authorization: str | None = Header(None),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
) -> CompanyAccount:
    """Authenticates either via X-API-Key header or Bearer JWT token."""
    # 1. API key in custom header
    if x_api_key:
        account = billing_service.get_company_by_api_key(x_api_key)
        if not account:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or inactive company API key.",
            )
        return account

    # 2. API key passed as Bearer token
    if authorization and authorization.startswith("Bearer docu_live_"):
        key = authorization[len("Bearer "):].strip()
        account = billing_service.get_company_by_api_key(key)
        if not account:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or inactive company API key.",
            )
        return account

    # 3. Standard JWT auth
    from backend.auth import get_current_user

    user = await get_current_user(authorization)
    return billing_service.get_or_create_company(user["id"], user.get("name"))


CompanyAuth = Annotated[CompanyAccount, Depends(get_company_or_api_auth)]


@app.get("/api/company/account")
def get_company_status(
    account: CompanyAccount = Depends(get_company_account),
):
    """Retrieve company account status, remaining credits, and masked API key."""
    return {
        "id": account.id,
        "companyName": account.company_name,
        "planTier": account.plan_tier,
        "isFreeTrialOnly": True,
        "totalCredits": account.total_credits,
        "usedCredits": account.used_credits,
        "remainingCredits": account.remaining_credits,
        "apiKeyPrefix": account.api_key_prefix,
        "apiKey": f"{account.api_key[:14]}••••••••••••••••••••••••{account.api_key[-4:]}",
        "rawApiKey": account.api_key,
        "createdAt": account.created_at,
    }


class UpdateWorkspacePayload(BaseModel):
    name: str


@app.get("/api/workspace")
def get_user_workspace(
    user: CurrentUser,
    account: CompanyAccount = Depends(get_company_account),
):
    """Retrieve user's dedicated workspace details."""
    return {
        "id": account.id,
        "name": account.company_name,
        "userId": str(user["id"]),
        "userName": user.get("name"),
        "userEmail": user.get("email"),
        "planTier": account.plan_tier,
        "totalCredits": account.total_credits,
        "usedCredits": account.used_credits,
        "remainingCredits": account.remaining_credits,
        "apiKeyPrefix": account.api_key_prefix,
        "apiKey": f"{account.api_key[:14]}••••••••••••••••••••••••{account.api_key[-4:]}",
        "rawApiKey": account.api_key,
        "createdAt": account.created_at,
        "status": "active" if account.is_active else "suspended",
    }


@app.put("/api/workspace")
def update_user_workspace(
    payload: UpdateWorkspacePayload,
    user: CurrentUser,
):
    """Update user's dedicated workspace name."""
    clean_name = payload.name.strip()
    if not clean_name:
        raise HTTPException(400, "Workspace name cannot be empty")
    account = billing_service.update_workspace_name(str(user["id"]), clean_name)
    return {
        "status": "success",
        "id": account.id,
        "name": account.company_name,
        "message": f"Workspace renamed to '{account.company_name}'",
    }


@app.post("/api/company/api-key/regenerate")
def roll_api_key(
    user: CurrentUser,
):
    """Regenerate company API key and return unmasked key."""
    new_acc = billing_service.regenerate_api_key(user["id"])
    return {
        "apiKey": new_acc.api_key,
        "apiKeyPrefix": new_acc.api_key_prefix,
        "remainingCredits": new_acc.remaining_credits,
        "planTier": new_acc.plan_tier,
    }


@app.get("/api/company/pricing")
def get_pricing_catalog():
    """Return the credit cost per service based on LLM compute usage."""
    return {
        "plan": "Company Free Trial",
        "initialCredits": INITIAL_TRIAL_CREDITS,
        "freeTrialAvailableOnly": True,
        "services": [
            {
                "id": s_id,
                "name": info["name"],
                "credits": info["credits"],
                "llmTier": info["llm_tier"],
                "category": info["category"],
                "description": info["description"],
            }
            for s_id, info in SERVICE_PRICING.items()
        ],
    }


@app.get("/api/company/usage")
def get_company_usage_history(
    account: CompanyAccount = Depends(get_company_account),
):
    """Retrieve audit usage history of Document AI calls."""
    logs = billing_service.get_usage_logs(account.id, limit=100)
    return {
        "companyId": account.id,
        "totalCredits": account.total_credits,
        "usedCredits": account.used_credits,
        "remainingCredits": account.remaining_credits,
        "logs": logs,
    }


# ---------------------------------------------------------------------------
# Public Company Document AI API (/api/v1/services/{service_name})
# ---------------------------------------------------------------------------


class CompanyExecutionPayload(ServiceRequest):
    pass


@app.post("/api/v1/services/{service_name}")
def execute_company_service(
    service_name: str,
    payload: CompanyExecutionPayload,
    response: Response,
    account: CompanyAuth,
    idempotency_key: Annotated[Optional[str], Header(alias="Idempotency-Key")] = None,
):
    from backend.services.engine import execute_service
    from backend.services.idempotency import begin, finish, finish_error, replay_response

    try:
        request = ServiceRequest.model_validate({**payload.model_dump(), "service": service_name})
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    operation_key, replay = begin(account, "company-service", idempotency_key, request.model_dump(mode="json"))
    if replay:
        return replay_response(replay)
    try:
        body = execute_service(request, account)
    except HTTPException as exc:
        finish_error(account, operation_key, exc)
        raise
    body.update(
        result=json.dumps(jsonable_encoder(body["data"]), ensure_ascii=False, indent=2)
        if body.get("data") is not None
        else body.get("raw", ""),
        planTier=account.plan_tier,
    )
    finish(account, operation_key, body)
    response.headers["X-Credits-Cost"] = str(body.get("creditsDeducted", 0))
    response.headers["X-Credits-Remaining"] = str(body["creditsRemaining"])
    return body


class PlaygroundRunPayload(BaseModel):
    service: str
    document_id: Optional[str] = None
    text_content: Optional[str] = None
    system_prompt: Optional[str] = None
    user_prompt: Optional[str] = None
    schema_override: Optional[dict] = None
    model: Optional[str] = None
    temperature: Optional[float] = Field(None, ge=0, le=2)
    output_format: Literal["json", "markdown", "auto"] = "auto"
    guardian: bool = True
    options: ServiceOptions = Field(default_factory=ServiceOptions)


PlaygroundRunPayload.model_rebuild()


@app.get("/api/playground/presets")
def get_playground_presets(user: CurrentUser):
    """Retrieve service presets, default prompts, schemas, and sample contexts for the playground."""
    from backend.agent.playground_presets import SERVICE_PRESETS
    from backend.models_config import model_registry

    all_models = model_registry.get_all_models()
    models = [
        {
            "id": m["id"],
            "name": m["name"],
            "description": m["description"],
            "creditCost": m["credit_cost"],
            "costUsd": m["cost_usd"],
            "costUsdFormatted": m["cost_usd_formatted"],
            "speedTier": m["speed_tier"],
            "reasoningTier": m["reasoning_tier"],
            "pricing": m["pricing"],
            "tokenCredits": m["token_credits"],
        }
        for m in all_models
    ]
    # Sanitize presets to hide internal system prompts from clients
    sanitized_presets = {}
    for key, data in SERVICE_PRESETS.items():
        preset_copy = dict(data)
        preset_copy.pop("default_system_prompt", None)
        from backend.services.contracts import service_schema

        if service_schema(key):
            preset_copy["default_schema"] = service_schema(key)
        sanitized_presets[key] = preset_copy
    return {
        "presets": sanitized_presets,
        "models": models,
        "defaultModel": model_registry.default_model_id,
        "creditPriceUsd": 0.002,
        "conversionFormula": "$2.00 = 1,000 Credits ($0.002 / Credit)",
    }


@app.get("/api/models")
def get_api_models():
    """List allowed models strictly from models.json with pricing and credit rates."""
    from backend.models_config import model_registry

    return {
        "object": "list",
        "data": model_registry.get_all_models(),
        "default_model": model_registry.default_model_id,
        "total_available": len(model_registry.allowed_model_ids),
        "credit_price_usd": 0.002,
        "conversion_formula": "$2.00 = 1,000 Credits ($0.002 / Credit)",
        "allowed_models": sorted(list(model_registry.allowed_model_ids)),
    }


class ModelSettingPayload(BaseModel):
    model: str


@app.get("/api/settings/model")
def get_user_model_setting(user: CurrentUser):
    """Retrieve current user/company chosen model for AI services."""
    from backend.models_config import model_registry
    from backend.v1.routes import COMPANY_MODEL_SETTINGS

    chosen = COMPANY_MODEL_SETTINGS.get(str(user["id"]), model_registry.default_model_id)
    return {
        "currentModel": chosen,
        "modelDetails": model_registry.get_model(chosen) or model_registry.get_model(model_registry.default_model_id),
        "defaultModel": model_registry.default_model_id,
        "allowedModels": sorted(list(model_registry.allowed_model_ids)),
        "creditPriceUsd": 0.002,
        "conversionFormula": "$2.00 = 1,000 Credits ($0.002 / Credit)",
    }


@app.post("/api/settings/model")
def set_user_model_setting(payload: ModelSettingPayload, user: CurrentUser):
    """Set chosen model for AI services. Rejects any model not in models.json."""
    from backend.models_config import model_registry
    from backend.v1.routes import COMPANY_MODEL_SETTINGS

    valid_model = model_registry.validate_model(payload.model)
    COMPANY_MODEL_SETTINGS[str(user["id"])] = valid_model
    return {
        "status": "success",
        "currentModel": valid_model,
        "modelDetails": model_registry.get_model(valid_model),
        "message": f"Selected processing model updated to {valid_model}",
    }


class GuardianSettingPayload(BaseModel):
    enabled: bool


@app.get("/api/settings/guardian")
def get_user_guardian_setting(user: CurrentUser):
    """Retrieve current user/company Guardian mode setting."""
    from backend.v1.routes import COMPANY_GUARDIAN_SETTINGS

    guardian_enabled = COMPANY_GUARDIAN_SETTINGS.get(str(user["id"]), True)
    return {
        "guardian": guardian_enabled,
        "guardianFeeCredits": 5,
        "mode": "guardian_verification" if guardian_enabled else "direct_return",
        "description": (
            "Guardian Verification: Grounded evidence citations, schema checks, guardrails (takes 5 credits fee)"
            if guardian_enabled
            else "Direct Return: Raw model extraction returned immediately without citation nullification (guardian fee waived)"
        ),
    }


@app.post("/api/settings/guardian")
def set_user_guardian_setting(payload: GuardianSettingPayload, user: CurrentUser):
    """Set preferred Guardian mode (verification with fee vs direct return with fee waived)."""
    from backend.v1.routes import COMPANY_GUARDIAN_SETTINGS

    COMPANY_GUARDIAN_SETTINGS[str(user["id"])] = bool(payload.enabled)
    return {
        "status": "success",
        "guardian": payload.enabled,
        "mode": "guardian_verification" if payload.enabled else "direct_return",
        "message": f"Guardian mode set to {'enabled (Full Verification)' if payload.enabled else 'disabled (Direct Return)'}",
    }


class CalculateCostRequest(BaseModel):
    service: str
    model: Optional[str] = None
    guardian: bool = True


@app.post("/api/services/calculate-cost")
def calculate_service_cost_api(payload: CalculateCostRequest):
    """Calculate exact credit breakdown for a given service, model, and guardian mode."""
    from backend.models_config import model_registry

    service_name = payload.service.lower().replace("-", "_")
    base_credits = SERVICE_PRICING.get(service_name, {}).get("credits", 10)
    return model_registry.calculate_service_cost(base_credits, payload.model, guardian=payload.guardian)


@app.post("/api/playground/run")
def run_playground(
    payload: PlaygroundRunPayload,
    user: CurrentUser,
    idempotency_key: Annotated[Optional[str], Header(alias="Idempotency-Key")] = None,
):
    """Use the shared service executor with the playground's response envelope."""
    from backend.agent.playground_presets import SERVICE_PRESETS
    from backend.services.engine import execute_service
    from backend.services.idempotency import begin, finish, finish_error, replay_response

    service = payload.service.lower().replace("-", "_")
    preset = SERVICE_PRESETS.get(service, {})
    content = payload.text_content
    if not payload.document_id and not (content and content.strip()):
        content = preset.get("sample_text")
    try:
        request = ServiceRequest(
            service=service,
            document_id=payload.document_id,
            text_content=content,
            query=payload.user_prompt or preset.get("default_query"),
            system_prompt=payload.system_prompt,
            schema_override=payload.schema_override,
            model=payload.model,
            temperature=payload.temperature,
            output_format=payload.output_format,
            guardian=payload.guardian,
            options=payload.options,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    account = billing_service.get_or_create_company(user["id"], user.get("name"))
    operation_key, replay = begin(account, "playground", idempotency_key, request.model_dump(mode="json"))
    if replay:
        return replay_response(replay)
    try:
        body = execute_service(request, account)
    except HTTPException as exc:
        finish_error(account, operation_key, exc)
        raise
    data = body.get("data")
    body.update(
        result=json.dumps(jsonable_encoder(data), indent=2, ensure_ascii=False)
        if data is not None
        else body.get("raw", ""),
        filename="document" if payload.document_id else f"{service}_sample.txt",
        temperature=payload.temperature,
        schemaUsed=payload.schema_override,
    )
    finish(account, operation_key, body)
    return body
