"""
B2B SaaS Pipeline & Developer API Router (v1).

Provides enterprise-ready endpoints for data pipelines (Airflow, Celery,
ETL scripts, CI/CD) and AI agent integrations (Claude, ChatGPT, OpenAI tool calling).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import tempfile
import time
import uuid
from pathlib import Path
from typing import Annotated, Any, Dict, List, Literal, Optional

import httpx
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from backend import rag
from backend.billing import (
    INITIAL_TRIAL_CREDITS,
    SERVICE_PRICING,
    CompanyAccount,
    billing_service,
)
from backend.config import settings
from backend.db import query
from backend.documents.limits import (
    MAX_UPLOAD_BYTES,
    UploadSizeError,
    validate_pdf_pages,
    validate_upload_size,
)
from backend.documents.loader import SUPPORTED_EXTENSIONS
from backend.jobs import job_queue
from backend.services.engine import execute_service
from backend.services.idempotency import begin, finish, finish_error, replay_response
from backend.services.models import DocumentRule, ServiceRequest
from backend.services.persistence import operation_store
from backend.storage import storage_service
from backend.storage.ephemeral import EphemeralDocument, ephemeral_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["B2B SaaS Pipeline API"])


# ---------------------------------------------------------------------------
# Authentication Dependency
# ---------------------------------------------------------------------------


async def get_company_or_api_auth(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    api_key: Optional[str] = Query(None),
) -> CompanyAccount:
    """Authenticates via X-API-Key header, Bearer API key, query param, or JWT."""
    # 1. Check direct API key
    key = x_api_key or api_key
    if not key and authorization and authorization.startswith("Bearer docu_live_"):
        key = authorization[len("Bearer ") :].strip()

    if key:
        account = billing_service.get_company_by_api_key(key)
        if not account:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or inactive company API key.",
            )
        return account

    # 2. Check JWT bearer token
    from backend.auth import get_current_user

    try:
        user = await get_current_user(authorization)
        return billing_service.get_or_create_company(user["id"], user.get("name"))
    except HTTPException:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide 'X-API-Key' header with your company key (docu_live_...).",
        )


CompanyAuth = Depends(get_company_or_api_auth)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class RawUploadPayload(BaseModel):
    content: str = Field(..., description="Raw text or markdown content of document")
    filename: str = Field("document.txt", description="Filename including extension")


class PipelineRunPayload(ServiceRequest):
    """Validated service options used by all service execution paths."""


class BatchTaskPayload(ServiceRequest):
    pass


class PipelineBatchPayload(BaseModel):
    tasks: List[BatchTaskPayload] = Field(min_length=1, max_length=100)
    webhook_url: Optional[str] = None


class OcrBlocksPayload(BaseModel):
    document_id: str = Field(..., description="Target document ID")
    page: Optional[int] = Field(None, description="Optional 1-indexed page number")
    language: str = Field("auto", description="Language mode: 'auto', 'ar' (Arabic), 'en' (English), or 'mixed'")
    force_ocr: bool = Field(False, description="Force vision-based OCR re-extraction")


class OcrPageBlocksPayload(BaseModel):
    document_id: str = Field(..., description="Target document ID")
    page_number: int = Field(1, description="1-indexed page number")
    language: str = Field("auto", description="Language mode: 'auto', 'ar', 'en', or 'mixed'")
    force_ocr: bool = Field(False, description="Force vision-based OCR re-extraction")


class AdvancedOcrPayload(BaseModel):
    document_id: str = Field(..., min_length=1, description="Uploaded PDF document ID")
    start_page: int = Field(1, ge=1)
    end_page: Optional[int] = Field(None, ge=1, description="Inclusive; defaults to the last page")
    language: Literal["auto", "ar", "en", "mixed"] = "auto"


# ---------------------------------------------------------------------------
# Webhook Helper
# ---------------------------------------------------------------------------


async def _dispatch_webhook(url: str, payload: Dict[str, Any], secret: Optional[str] = None) -> None:
    """Send cryptographically signed HMAC-SHA256 webhook notification for enterprise pipelines."""
    try:
        raw_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        timestamp = str(int(time.time()))
        signing_secret = secret or settings.JWT_SECRET
        signature = hmac.new(
            signing_secret.encode("utf-8"),
            f"{timestamp}.".encode("utf-8") + raw_body,
            hashlib.sha256,
        ).hexdigest()

        headers = {
            "Content-Type": "application/json",
            "X-DOCTool-Timestamp": timestamp,
            "X-DOCTool-Signature": f"sha256={signature}",
            "X-DocuChat-Timestamp": timestamp,
            "X-DocuChat-Signature": f"sha256={signature}",
            "User-Agent": "DOCTool-Enterprise-Webhook/1.0",
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, content=raw_body, headers=headers)
            logger.info("Dispatched signed webhook to %s, status=%d", url, resp.status_code)
    except Exception as exc:
        logger.warning("Failed to dispatch webhook to %s: %s", url, exc)


def _extract_json_from_text(text: str) -> Optional[Dict[str, Any] | List[Any]]:
    """Extract embedded JSON blocks or valid JSON from agent response."""
    if not text:
        return None
    text = text.strip()
    # 1. Try direct parse
    try:
        return json.loads(text)
    except Exception:
        pass

    # 2. Try fenced code blocks ```json ... ```
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except Exception:
            pass

    # 3. Try balanced braces search
    start = text.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            c = text[i]
            if c == '"' and not escape:
                in_string = not in_string
            elif not in_string:
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = text[start : i + 1]
                        try:
                            res = json.loads(candidate)
                            if isinstance(res, (dict, list)):
                                return res
                        except Exception:
                            pass
                        break
            escape = (c == "\\" and not escape)
        start = text.find("{", start + 1)

    # 4. Try greedy curly brackets fallback
    curly = re.search(r"(\{[\s\S]*\})", text)
    if curly:
        try:
            return json.loads(curly.group(1))
        except Exception:
            pass

    return None


def extract_structured_data(text: str, service: str = "general") -> Dict[str, Any]:
    """Extract structured dictionary from text, falling back to parsed key-value lines."""
    parsed = _extract_json_from_text(text)
    if isinstance(parsed, dict) and parsed:
        return parsed
    if isinstance(parsed, list):
        return {"items": parsed, "count": len(parsed)}

    # Parse prose bullet points or key-value lines
    data: Dict[str, Any] = {}
    current_key = None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("```") or line.startswith("==="):
            continue
        clean = re.sub(r"^[-*•#\d\.\s]+", "", line).strip()
        if ":" in clean:
            k, v = clean.split(":", 1)
            k = re.sub(r"[*_#]", "", k).strip().lower().replace(" ", "_").replace("-", "_")
            v = re.sub(r"^\*\*|\*\*$", "", v).strip()
            if k and v:
                data[k] = v
                current_key = k
        elif current_key and clean:
            if isinstance(data[current_key], str):
                data[current_key] += " " + clean
    if data:
        return data

    return {"summary": text.strip() if text else "No content extracted", "service": service}


# ---------------------------------------------------------------------------
# Pipeline Routes
# ---------------------------------------------------------------------------


@router.post("/documents/upload", summary="Pipeline Document Ingestion")
async def pipeline_upload_document(
    request: Request,
    account: CompanyAccount = CompanyAuth,
):
    """
    Ingest and index a document into the B2B pipeline.
    Accepts multipart file or raw JSON content payload.
    Returns document ID and indexing metrics immediately for subsequent pipeline steps.
    """
    content_type = request.headers.get("content-type", "")
    filename = "document.txt"
    mime_type = "text/plain"
    raw_bytes = b""
    ttl_minutes: Optional[int] = None

    if "application/json" in content_type:
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON payload.")
        text_content = body.get("content", "")
        if not text_content:
            raise HTTPException(400, "Field 'content' is required in JSON payload.")
        filename = body.get("filename", "document.txt")
        raw_bytes = text_content.encode("utf-8")
        mime_type = "text/plain"
        if body.get("ttl_minutes"):
            try:
                ttl_minutes = int(body["ttl_minutes"])
            except (ValueError, TypeError):
                pass
    elif "multipart/form-data" in content_type:
        form = await request.form()
        uploaded_file = form.get("file")
        if not uploaded_file or not hasattr(uploaded_file, "filename"):
            raise HTTPException(400, "Multipart file 'file' field is required.")
        filename = Path((uploaded_file.filename or "").replace("\\", "/")).name
        ext = Path(filename).suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported format '{ext}'. Supported: {', '.join(SUPPORTED_EXTENSIONS)}",
            )
        raw_bytes = await uploaded_file.read(MAX_UPLOAD_BYTES + 1)
        if not raw_bytes or len(raw_bytes) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "Document size must be between 1 byte and 5 MB.")
        mime_type = uploaded_file.content_type or "application/octet-stream"
        raw_ttl = form.get("ttl_minutes")
        if raw_ttl:
            try:
                ttl_minutes = int(raw_ttl)
            except (ValueError, TypeError):
                pass
    else:
        # Raw bytes stream
        raw_bytes = await request.body()
        if not raw_bytes:
            raise HTTPException(400, "Empty upload payload.")
        filename = request.headers.get("X-Filename", "document.txt")
        mime_type = content_type or "application/octet-stream"

    try:
        validate_upload_size(len(raw_bytes))
    except UploadSizeError as exc:
        raise HTTPException(413, str(exc)) from exc

    file_size = len(raw_bytes)
    ext = Path(filename).suffix.lower() or ".txt"

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(raw_bytes)
        tmp_path = tmp.name

    try:
        upload_result = await run_in_threadpool(
            rag.process_upload,
            user_id=str(account.user_id),
            file_path=Path(tmp_path),
            original_filename=filename,
            file_size=file_size,
            mime=mime_type,
        )
        chunk_count = upload_result[0]
        page_count = upload_result[1]
        doc_id = getattr(upload_result, "document_id", None) or str(uuid.uuid4())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.exception("Pipeline document processing failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Pipeline ingestion failed: {exc}",
        )
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except OSError:
            pass

    # Register in Ephemeral Store with configurable inactivity TTL
    dest_path = Path(settings.UPLOAD_DIR) / doc_id / filename
    if not dest_path.exists():
        e_doc = ephemeral_store.store_bytes(
            raw_bytes=raw_bytes,
            filename=filename,
            user_id=str(account.user_id),
            mime_type=mime_type,
            ttl_minutes=ttl_minutes,
            doc_id=doc_id,
        )
    else:
        e_doc = ephemeral_store.register_file(
            doc_id=doc_id,
            user_id=str(account.user_id),
            file_path=dest_path,
            filename=filename,
            file_size=file_size,
            mime_type=mime_type,
            page_count=page_count,
            chunk_count=chunk_count,
            ttl_minutes=ttl_minutes,
        )

    return {
        "status": "success",
        "documentId": doc_id,
        "filename": filename,
        "fileSize": file_size,
        "pageCount": page_count,
        "chunkCount": chunk_count,
        "ttlMinutes": e_doc.ttl_minutes,
        "remainingSeconds": e_doc.remaining_seconds,
        "expiresAt": e_doc.expires_at.isoformat(),
        "creditsRemaining": account.remaining_credits,
        "message": f"Document session active. Retained for {e_doc.ttl_minutes} minutes without usage. Inactivity resets on each service call.",
    }


@router.get("/documents", summary="List Company Pipeline Documents")
def pipeline_list_documents(
    account: CompanyAccount = CompanyAuth,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List documents indexed for the company account."""
    try:
        rows = (
            query(
                "SELECT id, filename, original_filename, file_size, mime_type, page_count, created_at "
                "FROM docuchat.documents WHERE user_id = %s ORDER BY created_at DESC LIMIT %s OFFSET %s",
                (account.user_id, limit, offset),
            )
            or []
        )
    except Exception:
        # Fallback to in-memory registry if DB query fails
        rows = []

    return {
        "companyId": account.id,
        "total": len(rows),
        "limit": limit,
        "offset": offset,
        "documents": [
            {
                "id": str(r["id"]),
                "filename": r["original_filename"],
                "fileSize": r["file_size"],
                "pageCount": r["page_count"],
                "mimeType": r["mime_type"],
                "createdAt": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ],
    }


@router.get("/documents/{doc_id}", summary="Get Pipeline Document Details")
def pipeline_get_document(
    doc_id: str,
    account: CompanyAccount = CompanyAuth,
):
    """Retrieve document status, page count, and indexing bundle."""
    try:
        row = query(
            "SELECT id, original_filename, file_size, mime_type, page_count, created_at "
            "FROM docuchat.documents WHERE id = %s",
            (doc_id,),
            one=True,
        )
    except Exception:
        row = None

    if not row:
        # Check if bundle is loaded in-memory
        bundle = rag._registry.get(doc_id)
        if not bundle:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document '{doc_id}' not found.",
            )
        return {
            "id": doc_id,
            "filename": f"doc_{doc_id}.pdf",
            "pageCount": len(bundle.pdf_docs[0].pages) if bundle.pdf_docs else 1,
            "isReady": bundle.vector_store is not None,
        }

    return {
        "id": str(row["id"]),
        "filename": row["original_filename"],
        "fileSize": row["file_size"],
        "mimeType": row["mime_type"],
        "pageCount": row["page_count"],
        "createdAt": row["created_at"].isoformat() if row["created_at"] else None,
        "isReady": True,
    }


@router.get("/documents/{doc_id}/status", summary="Check Ephemeral Document Inactivity TTL Status")
def pipeline_get_document_status(
    doc_id: str,
    account: CompanyAccount = CompanyAuth,
):
    """Check remaining seconds and expiration for an active document session."""
    e_doc = ephemeral_store.get_and_touch(doc_id, extend_ttl=False)
    if not e_doc:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=f"Document session '{doc_id}' has expired after {settings.DOC_TTL_MINUTES} minutes of inactivity or does not exist.",
        )
    return {
        "status": "active",
        **e_doc.to_dict(),
    }


@router.delete("/documents/{doc_id}", summary="Delete Ephemeral Document Session")
def pipeline_delete_document(
    doc_id: str,
    account: CompanyAccount = CompanyAuth,
):
    """Purge document session and delete all associated files immediately."""
    deleted = ephemeral_store.delete(doc_id)
    return {
        "status": "success" if deleted else "not_found",
        "documentId": doc_id,
        "message": "Document session and storage purged." if deleted else "Document session not found or already purged.",
    }


@router.get("/documents/{doc_id}/search", summary="Pipeline Hybrid Chunk Retrieval")
def pipeline_search_document(
    doc_id: str,
    query_text: str = Query(..., alias="query", description="Search query"),
    top_k: int = Query(5, ge=1, le=20, description="Number of chunks to return"),
    account: CompanyAccount = CompanyAuth,
):
    """
    Search document chunks using hybrid semantic embeddings + BM25 keyword search.
    Provides page citations and content for external RAG pipelines.
    """
    try:
        bundle = rag.get_bundle(doc_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Failed to load document '{doc_id}': {exc}",
        )

    if bundle.vector_store is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document vector store is not indexed.",
        )

    docs = bundle.vector_store.search(query_text, top_k=top_k)
    results = []
    for d in docs:
        results.append(
            {
                "page": d.metadata.get("start_page") or d.metadata.get("page") or 1,
                "chunkIndex": d.metadata.get("chunk_index"),
                "source": d.metadata.get("source"),
                "content": d.page_content,
            }
        )

    return {
        "documentId": doc_id,
        "query": query_text,
        "count": len(results),
        "results": results,
    }


def _resolve_document_file_path(doc_id: str) -> tuple[Path, str]:
    """Helper to locate document on disk or storage and touch sliding inactivity TTL."""
    e_doc = ephemeral_store.get_and_touch(doc_id, extend_ttl=True)
    if e_doc and e_doc.file_path and e_doc.file_path.exists():
        return e_doc.file_path, e_doc.filename

    filename = f"doc_{doc_id}.pdf"
    file_path = None
    try:
        row = query(
            "SELECT original_filename, file_path FROM docuchat.documents WHERE id = %s",
            (doc_id,),
            one=True,
        )
        if row:
            filename = row["original_filename"]
            if row.get("file_path") and Path(row["file_path"]).exists():
                file_path = Path(row["file_path"])
    except Exception:
        pass

    if not file_path:
        for p in [
            rag._pdf_path(doc_id),
            Path(f"backend/storage/uploads/{doc_id}.pdf"),
            Path(f"backend/storage/uploads/{doc_id}"),
            Path(f"/tmp/{doc_id}.pdf"),
            Path(f"/tmp/{filename}"),
        ]:
            if p and p.exists():
                file_path = p
                break

    if not file_path:
        bundle = rag._registry.get(doc_id)
        if bundle and getattr(bundle, "pdf_docs", None) and bundle.pdf_docs:
            pdf_doc = bundle.pdf_docs[0]
            if getattr(pdf_doc, "file_path", None) and Path(pdf_doc.file_path).exists():
                file_path = Path(pdf_doc.file_path)

    if not file_path or not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document file for ID '{doc_id}' not found on storage.",
        )
    return file_path, filename


@router.post("/ocr/advanced", summary="Advanced OCR: Flexible Semantic Page Blocks", tags=["Advanced OCR"])
async def pipeline_advanced_ocr(
    request: Request,
    account: CompanyAccount = CompanyAuth,
):
    """Extract semantic blocks from an uploaded PDF or active ephemeral document session.

    Stateless ephemeral Document AI: documents are retained for 10 minutes without usage.
    Each usage resets the 10-minute inactivity timer. After 10 minutes of inactivity,
    files and resources are automatically purged.
    Documents are limited to 5 MB and 3 pages, including when selecting a page range. The first selected page has no predecessor context.
    """
    from backend.agent.tools.advanced_ocr import AdvancedOcrService
    from backend.agent.tools.ocr import OcrError

    content_type = request.headers.get("content-type", "")
    target_path: Optional[Path] = None
    target_filename: str = "document.pdf"
    target_doc_id: Optional[str] = None
    e_doc: Optional[EphemeralDocument] = None
    tmp_path_to_clean: Optional[Path] = None

    start_page: int = 1
    end_page: Optional[int] = None
    language: str = "auto"
    selected_model: Optional[str] = None

    if "application/json" in content_type:
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=422, detail="Invalid JSON payload.")
        doc_id = body.get("document_id")
        if not doc_id:
            raise HTTPException(status_code=422, detail="Field 'document_id' or 'file' is required.")
        e_doc = ephemeral_store.get_and_touch(str(doc_id), extend_ttl=True)
        if not e_doc:
            raise HTTPException(
                status_code=422,
                detail=f"Document session '{doc_id}' not found or expired after inactivity.",
            )
        target_path = e_doc.file_path
        target_filename = e_doc.filename
        target_doc_id = e_doc.doc_id

        raw_start = body.get("start_page", 1)
        try:
            start_page = int(raw_start)
            if start_page < 1:
                raise ValueError("start_page must be >= 1")
        except (ValueError, TypeError):
            raise HTTPException(status_code=422, detail="start_page must be an integer >= 1")

        raw_end = body.get("end_page")
        if raw_end is not None and str(raw_end).strip() != "":
            try:
                end_page = int(raw_end)
                if end_page < start_page:
                    raise ValueError("end_page must be >= start_page")
            except (ValueError, TypeError):
                raise HTTPException(status_code=422, detail="end_page must be an integer >= start_page")

        language = str(body.get("language", "auto")).lower()
        if body.get("model"):
            from backend.models_config import model_registry
            selected_model = model_registry.validate_model(str(body.get("model")).strip())

    elif "multipart/form-data" in content_type:
        form = await request.form()
        if form.get("model"):
            from backend.models_config import model_registry
            selected_model = model_registry.validate_model(str(form.get("model")).strip())
        uploaded_file = form.get("file")
        form_doc_id = form.get("document_id")

        if not uploaded_file and not form_doc_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="A PDF document 'file' or active 'document_id' is required.",
            )

        if form_doc_id and not uploaded_file:
            e_doc = ephemeral_store.get_and_touch(str(form_doc_id), extend_ttl=True)
            if not e_doc:
                raise HTTPException(
                    status_code=422,
                    detail=f"Document session '{form_doc_id}' not found or expired after inactivity.",
                )
            target_path = e_doc.file_path
            target_filename = e_doc.filename
            target_doc_id = e_doc.doc_id
        elif uploaded_file:
            if not hasattr(uploaded_file, "filename"):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="A valid PDF document 'file' is required.",
                )
            raw_filename = Path((uploaded_file.filename or "document.pdf").replace("\\", "/")).name
            if Path(raw_filename).suffix.lower() != ".pdf":
                raise HTTPException(status_code=422, detail="Advanced OCR requires a PDF document")

            raw_bytes = await uploaded_file.read(MAX_UPLOAD_BYTES + 1)
            if not raw_bytes or len(raw_bytes) > MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail="PDF size must be between 1 byte and 5 MB.")

            try:
                validate_pdf_pages(raw_bytes)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc

            # Store in ephemeral store with sliding inactivity TTL (default 10 min)
            try:
                e_doc = ephemeral_store.store_bytes(
                    raw_bytes=raw_bytes,
                    filename=raw_filename,
                    user_id=str(account.user_id),
                    mime_type="application/pdf",
                )
                target_path = e_doc.file_path
                target_filename = e_doc.filename
                target_doc_id = e_doc.doc_id
            except Exception:
                # Fallback to temp file if ephemeral directory writing fails
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                    tmp.write(raw_bytes)
                    tmp_path_to_clean = Path(tmp.name)
                target_path = tmp_path_to_clean
                target_filename = raw_filename

        try:
            start_page = int(form.get("start_page", 1))
            if start_page < 1:
                raise ValueError("start_page must be >= 1")
        except (ValueError, TypeError):
            raise HTTPException(status_code=422, detail="start_page must be an integer >= 1")

        raw_end = form.get("end_page")
        if raw_end is not None and str(raw_end).strip() != "":
            try:
                end_page = int(raw_end)
                if end_page < start_page:
                    raise ValueError("end_page must be >= start_page")
            except (ValueError, TypeError):
                raise HTTPException(status_code=422, detail="end_page must be an integer >= start_page")

        language = str(form.get("language", "auto")).lower()
        if form.get("model"):
            selected_model = str(form.get("model")).strip()
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="PDF file upload or document_id is required. Drive storage lookup is disabled.",
        )

    if language not in ("auto", "ar", "en", "mixed"):
        language = "auto"

    if not target_path or not target_path.exists():
        raise HTTPException(status_code=422, detail="Unable to resolve document file path.")

    from backend.models_config import model_registry
    if selected_model:
        selected_model = model_registry.validate_model(selected_model)
    else:
        account_id = getattr(account, "id", None) or getattr(account, "user_id", "default")
        selected_model = COMPANY_MODEL_SETTINGS.get(str(account_id), model_registry.default_model_id)

    model_obj = model_registry.get_model(selected_model) if selected_model else None
    ocr_cost = model_obj.get("credit_cost", 5) if model_obj else 5
    if account.remaining_credits < ocr_cost:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Insufficient credits for Advanced OCR. Required: {ocr_cost}, Remaining: {account.remaining_credits}.",
        )

    charged_credits = False
    try:
        billing_service.check_and_deduct_credits(
            account,
            service_name="advanced_ocr",
            document_id=target_doc_id,
            request_summary=f"Advanced OCR ({selected_model}) on {target_filename}",
            model_id=selected_model,
            guardian=False,
        )
        charged_credits = True

        validate_upload_size(target_path.stat().st_size)
        validate_pdf_pages(target_path)
        data = await run_in_threadpool(
            AdvancedOcrService().extract,
            target_path,
            start_page=start_page,
            end_page=end_page,
            language=language,
        )
        return {
            **data,
            "status": "success",
            "model": selected_model,
            "document_id": target_doc_id,
            "filename": target_filename,
            "credits_cost": ocr_cost,
            "credits_deducted": ocr_cost,
            "credits_remaining": account.remaining_credits,
            "ttl_minutes": e_doc.ttl_minutes if e_doc else settings.DOC_TTL_MINUTES,
            "remaining_seconds": e_doc.remaining_seconds if e_doc else None,
            "expires_at": e_doc.expires_at.isoformat() if e_doc else None,
        }
    except UploadSizeError as exc:
        if charged_credits:
            billing_service.refund_credits(account, "advanced_ocr", ocr_cost, target_doc_id, "Upload size exceeded")
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except ValueError as exc:
        if charged_credits:
            billing_service.refund_credits(account, "advanced_ocr", ocr_cost, target_doc_id, "Invalid parameters")
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OcrError as exc:
        if charged_credits:
            billing_service.refund_credits(account, "advanced_ocr", ocr_cost, target_doc_id, "OCR service failure")
        logger.warning("Advanced OCR failed for file %s: %s", target_filename, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        if charged_credits:
            billing_service.refund_credits(account, "advanced_ocr", ocr_cost, target_doc_id, "Unexpected failure")
        raise
    finally:
        if tmp_path_to_clean and tmp_path_to_clean.exists():
            tmp_path_to_clean.unlink(missing_ok=True)


@router.get("/ocr/document/{doc_id}", summary="Extract Layout-Aware Document Blocks")
def pipeline_get_document_ocr_blocks(
    doc_id: str,
    page: Optional[int] = Query(None, description="Optional 1-indexed page number"),
    language: str = Query("auto", description="Target language: 'auto', 'ar' (Arabic), 'en' (English), or 'mixed'"),
    force_ocr: bool = Query(False, description="Force vision-based OCR re-extraction"),
    account: CompanyAccount = CompanyAuth,
):
    """
    Retrieve structured layout blocks from a document (titles, text, metadata,
    tables with content_md, and images with descriptions) with Arabic and English support.
    """
    from backend.agent.tools.ocr import OcrService

    file_path, filename = _resolve_document_file_path(doc_id)
    ocr_service = OcrService()
    try:
        data = ocr_service.ocr_extract_blocks(file_path, page_number=page, language=language, force_ocr=force_ocr)
        return {
            "status": "success",
            "document_id": doc_id,
            "filename": filename,
            "total_pages": data.get("total_pages", 1),
            "page": page,
            "language_detected": data.get("language_detected", language),
            "direction": data.get("direction", "rtl" if language == "ar" else "ltr"),
            "ocr_text": data.get("ocr_text", ""),
            "coordinate_system": data.get("coordinate_system", "normalized_0_1000"),
            "blocks": data.get("blocks", []),
            "pages": data.get("pages", []),
        }
    except Exception as exc:
        logger.error("OCR block extraction failed for %s: %s", doc_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"OCR block extraction failed: {exc}",
        )


@router.post("/ocr/blocks", summary="Extract Layout Blocks from Document")
def pipeline_post_ocr_blocks(
    payload: OcrBlocksPayload,
    account: CompanyAccount = CompanyAuth,
):
    """Extract structural layout blocks with titles, text, tables (content_md), and images."""
    return pipeline_get_document_ocr_blocks(
        doc_id=payload.document_id,
        page=payload.page,
        language=payload.language,
        force_ocr=payload.force_ocr,
        account=account,
    )


@router.post("/ocr/page/blocks", summary="Extract Bilingual Arabic & English Layout Blocks by Page")
def pipeline_post_page_ocr_blocks(
    payload: OcrPageBlocksPayload,
    account: CompanyAccount = CompanyAuth,
):
    """
    Extract bilingual Arabic and English layout blocks for a specific page.
    Returns blocks with reading direction, language classification, markdown tables, and visual descriptions.
    """
    from backend.agent.tools.ocr import OcrService

    file_path, filename = _resolve_document_file_path(payload.document_id)
    ocr_service = OcrService()
    try:
        data = ocr_service.ocr_read_page_blocks(
            file_path,
            page_number=payload.page_number,
            language=payload.language,
            force_ocr=payload.force_ocr,
        )
        return {
            "status": "success",
            "document_id": payload.document_id,
            "filename": filename,
            "page_number": payload.page_number,
            "language_detected": data.get("language_detected", payload.language),
            "direction": data.get("direction", "rtl" if payload.language == "ar" else "ltr"),
            "block_count": data.get("block_count", len(data.get("blocks", []))),
            "ocr_text": data.get("ocr_text", ""),
            "coordinate_system": data.get("coordinate_system", "normalized_0_1000"),
            "blocks": data.get("blocks", []),
        }
    except Exception as exc:
        logger.error("Page OCR block extraction failed for %s (page %d): %s", payload.document_id, payload.page_number, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Page OCR extraction failed: {exc}",
        )


@router.get("/ocr/document/{doc_id}/page/{page_number}/blocks", summary="Extract Layout Blocks for Specific Page")
def pipeline_get_page_ocr_blocks(
    doc_id: str,
    page_number: int,
    language: str = Query("auto", description="Target language: 'auto', 'ar', 'en', 'mixed'"),
    force_ocr: bool = Query(False, description="Force vision-based OCR re-extraction"),
    account: CompanyAccount = CompanyAuth,
):
    """Retrieve bilingual layout blocks for a specific page number."""
    from backend.agent.tools.ocr import OcrService

    file_path, filename = _resolve_document_file_path(doc_id)
    ocr_service = OcrService()
    try:
        data = ocr_service.ocr_read_page_blocks(
            file_path,
            page_number=page_number,
            language=language,
            force_ocr=force_ocr,
        )
        return {
            "status": "success",
            "document_id": doc_id,
            "filename": filename,
            "page_number": page_number,
            "language_detected": data.get("language_detected", language),
            "direction": data.get("direction", "rtl" if language == "ar" else "ltr"),
            "block_count": data.get("block_count", len(data.get("blocks", []))),
            "ocr_text": data.get("ocr_text", ""),
            "coordinate_system": data.get("coordinate_system", "normalized_0_1000"),
            "blocks": data.get("blocks", []),
        }
    except Exception as exc:
        logger.error("Page OCR block extraction failed for %s (page %d): %s", doc_id, page_number, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Page OCR extraction failed: {exc}",
        )


@router.post("/pipeline/run", summary="Execute a validated document service")
async def pipeline_run_service(
    payload: PipelineRunPayload,
    response: Response,
    background_tasks: BackgroundTasks,
    account: CompanyAccount = CompanyAuth,
    idempotency_key: Annotated[Optional[str], Header(alias="Idempotency-Key")] = None,
):
    operation_key, replay = await run_in_threadpool(
        begin, account, "pipeline", idempotency_key, payload.model_dump(mode="json")
    )
    if replay:
        return replay_response(replay)
    try:
        body = await run_in_threadpool(execute_service, payload, account)
    except HTTPException as exc:
        await run_in_threadpool(finish_error, account, operation_key, exc)
        raise
    # Persist before dispatching callbacks. A retry replays the result without a second charge or callback.
    await run_in_threadpool(finish, account, operation_key, body)
    response.headers["X-Credits-Cost"] = str(body.get("creditsDeducted", 0))
    response.headers["X-Credits-Remaining"] = str(body["creditsRemaining"])
    if payload.webhook_url:
        background_tasks.add_task(_dispatch_webhook, payload.webhook_url, body)
    return body


@router.post("/pipeline/batch", summary="Batch Pipeline Execution")
async def pipeline_batch_run(
    payload: PipelineBatchPayload,
    background_tasks: BackgroundTasks,
    account: CompanyAccount = CompanyAuth,
    idempotency_key: Annotated[Optional[str], Header(alias="Idempotency-Key")] = None,
):
    """
    Execute multiple pipeline document tasks in a single batch request.
    Collects results and can trigger an asynchronous webhook when complete.
    """
    operation_key, replay = await run_in_threadpool(
        begin, account, "batch", idempotency_key, payload.model_dump(mode="json")
    )
    if replay:
        return replay_response(replay)
    results = []
    total_cost = 0

    for task in payload.tasks:
        sub_payload = PipelineRunPayload.model_validate(task.model_dump())
        dummy_resp = Response()
        try:
            res = await pipeline_run_service(
                payload=sub_payload,
                response=dummy_resp,
                background_tasks=background_tasks,
                account=account,
            )
            results.append(res)
            total_cost += res.get("creditsDeducted", 0)
        except Exception as exc:
            results.append(
                {
                    "status": "failed",
                    "documentId": task.document_id,
                    "service": task.service,
                    "error": str(exc),
                    "success": False,
                }
            )

    batch_summary = {
        "status": "completed",
        "totalTasks": len(payload.tasks),
        "totalCost": total_cost,
        "creditsRemaining": account.remaining_credits,
        "results": results,
    }

    await run_in_threadpool(finish, account, operation_key, batch_summary)
    if payload.webhook_url:
        background_tasks.add_task(_dispatch_webhook, payload.webhook_url, batch_summary)

    return batch_summary


# ---------------------------------------------------------------------------
# Asynchronous Background Job Endpoints (Redis / Worker Queue)
# ---------------------------------------------------------------------------


class AsyncJobSubmitPayload(ServiceRequest):
    pass


@router.post("/pipeline/jobs", status_code=status.HTTP_202_ACCEPTED, summary="Submit a validated service job")
async def submit_async_pipeline_job(
    payload: AsyncJobSubmitPayload,
    account: CompanyAccount = CompanyAuth,
    idempotency_key: Annotated[Optional[str], Header(alias="Idempotency-Key")] = None,
):
    service = payload.service.lower().replace("-", "_")
    if service not in SERVICE_PRICING:
        raise HTTPException(404, f"Unknown service '{service}'")
    operation_key, replay = await run_in_threadpool(
        begin, account, "job-submit", idempotency_key, payload.model_dump(mode="json")
    )
    if replay:
        return replay_response(replay)
    try:
        job = await run_in_threadpool(
            job_queue.enqueue,
            service=service,
            document_id=payload.document_id or "",
            user_id=str(account.user_id),
            company_id=str(account.id),
            query=payload.query,
            output_format=payload.output_format,
            webhook_url=payload.webhook_url,
            request_payload=payload.model_dump(mode="json"),
        )
    except Exception as exc:
        error = HTTPException(503, "Job submission failed")
        # Leave an uncertain enqueue pending: never submit the same operation twice.
        raise error from exc
    body = {
        "status": "accepted",
        "jobId": job.id,
        "service": job.service,
        "documentId": job.document_id,
        "state": job.status,
        "estimatedCredits": billing_service.get_service_cost(service),
        "pollUrl": f"/api/v1/pipeline/jobs/{job.id}",
        "createdAt": job.created_at,
    }
    await run_in_threadpool(finish, account, operation_key, body, 202)
    return body


class RuleSetPayload(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    rules: List[DocumentRule] = Field(min_length=1, max_length=100)


@router.post("/rule-sets", status_code=201, summary="Create a company document rule set")
def create_rule_set(payload: RuleSetPayload, account: CompanyAccount = CompanyAuth):
    return operation_store.save_rules(
        str(account.id), str(uuid.uuid4()), payload.name, [rule.model_dump() for rule in payload.rules]
    )


@router.get("/rule-sets", summary="List company document rule sets")
def list_rule_sets(account: CompanyAccount = CompanyAuth):
    return {"ruleSets": operation_store.list_rules(str(account.id))}


@router.get("/rule-sets/{rule_id}", summary="Get a company document rule set")
def get_rule_set(rule_id: uuid.UUID, account: CompanyAccount = CompanyAuth):
    return operation_store.get_rules(str(account.id), str(rule_id))


@router.put("/rule-sets/{rule_id}", summary="Update a company document rule set")
def update_rule_set(rule_id: uuid.UUID, payload: RuleSetPayload, account: CompanyAccount = CompanyAuth):
    operation_store.get_rules(str(account.id), str(rule_id))
    return operation_store.save_rules(
        str(account.id), str(rule_id), payload.name, [rule.model_dump() for rule in payload.rules]
    )


@router.delete("/rule-sets/{rule_id}", status_code=204, summary="Delete a company document rule set")
def delete_rule_set(rule_id: uuid.UUID, account: CompanyAccount = CompanyAuth):
    operation_store.delete_rules(str(account.id), str(rule_id))
    return Response(status_code=204)


@router.get("/pipeline/jobs/{job_id}", summary="Get Async Pipeline Job Status")
def get_async_pipeline_job(
    job_id: str,
    account: CompanyAccount = CompanyAuth,
):
    """Poll the status, progress (0-100), and result of a background job."""
    job = job_queue.get_job(job_id)
    if not job or str(job.company_id) != str(account.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )

    return {
        "jobId": job.id,
        "service": job.service,
        "documentId": job.document_id,
        "status": job.status,
        "progress": job.progress,
        "result": job.result,
        "error": job.error,
        "createdAt": job.created_at,
        "updatedAt": job.updated_at,
        "completedAt": job.completed_at,
    }


@router.get("/pipeline/jobs", summary="List Company Pipeline Jobs")
def list_async_pipeline_jobs(
    limit: int = Query(50, ge=1, le=200),
    account: CompanyAccount = CompanyAuth,
):
    """List recent background pipeline jobs."""
    jobs = job_queue.list_jobs(limit=limit, user_id=str(account.user_id))
    return {
        "total": len(jobs),
        "jobs": [j.to_dict() for j in jobs],
    }


# ---------------------------------------------------------------------------
# SeaweedFS S3 Storage Endpoints
# ---------------------------------------------------------------------------


@router.get("/storage/status", summary="Check SeaweedFS S3 Storage Status")
def get_storage_status(account: CompanyAccount = CompanyAuth):
    """Inspect SeaweedFS S3 storage health."""
    healthy = storage_service.is_healthy()
    return {
        "provider": "SeaweedFS (S3-Compatible)",
        "endpoint": storage_service.public_endpoint,
        "bucket": storage_service.bucket,
        "isHealthy": healthy,
        "storageBackend": "seaweedfs",
    }


@router.get("/storage/documents/{doc_id}/presigned-url", summary="Generate Expiring Download URL")
def get_document_presigned_url(
    doc_id: str,
    expires_seconds: int = Query(3600, ge=60, le=86400),
    account: CompanyAccount = CompanyAuth,
):
    """Generate a secure presigned GET URL for client document downloads."""
    # Look up document original filename
    try:
        doc = query("SELECT original_filename FROM docuchat.documents WHERE id = %s", (doc_id,), one=True)
        fname = doc["original_filename"] if doc else f"{doc_id}.pdf"
    except Exception:
        fname = f"{doc_id}.pdf"

    object_name = f"documents/{doc_id}/{fname}"
    # Publish existing ingestion files to the object store when first requested.
    if not storage_service.exists(object_name):
        source, _ = _resolve_document_file_path(doc_id)
        storage_service.upload(object_name, source)
    url = storage_service.get_presigned_url(object_name, expires_seconds=expires_seconds)
    return {
        "documentId": doc_id,
        "objectName": object_name,
        "url": url,
        "expiresInSeconds": expires_seconds,
    }


# ---------------------------------------------------------------------------
# ChatGPT Custom GPTs & OpenAI Tool Calling Endpoints
# ---------------------------------------------------------------------------


@router.get("/gpt/openapi.json", summary="OpenAPI Specification for ChatGPT Actions")
def get_chatgpt_actions_openapi():
    """
    Returns an OpenAPI 3.1 specification optimized for ChatGPT Custom GPT Actions.
    Enter this URL in ChatGPT's 'Create a GPT' -> 'Configure' -> 'Actions' -> 'Import from URL'.
    """
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "DOCTool B2B Document AI API",
            "version": "1.0.0",
            "description": "Enterprise Document Intelligence API: invoice extraction, contract analysis, PII audit, search, and RAG Q&A.",
        },
        "servers": [
            {
                "url": "http://127.0.0.1:8000/api/v1",
                "description": "Local DOCTool Server",
            }
        ],
        "paths": {
            "/documents": {
                "get": {
                    "operationId": "listDocuments",
                    "summary": "List available documents",
                    "responses": {"200": {"description": "List of indexed documents"}},
                }
            },
            "/documents/{doc_id}/search": {
                "get": {
                    "operationId": "searchDocumentChunks",
                    "summary": "Search document content with hybrid vector and keyword search",
                    "parameters": [
                        {"name": "doc_id", "in": "path", "required": True, "schema": {"type": "string"}},
                        {"name": "query", "in": "query", "required": True, "schema": {"type": "string"}},
                        {"name": "top_k", "in": "query", "schema": {"type": "integer", "default": 5}},
                    ],
                    "responses": {"200": {"description": "Matching chunk snippets and citations"}},
                }
            },
            "/pipeline/run": {
                "post": {
                    "operationId": "runDocumentAiService",
                    "summary": "Run AI service on document (invoice, contract, compliance, summary, form_parser)",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["document_id", "service"],
                                    "properties": {
                                        "document_id": {"type": "string"},
                                        "service": {
                                            "type": "string",
                                            "enum": [
                                                "invoice",
                                                "contract",
                                                "compliance",
                                                "summary",
                                                "form_parser",
                                                "receipt",
                                                "resume",
                                                "research",
                                                "redaction",
                                                "classifier",
                                                "financial_statement",
                                                "translation",
                                                "anomaly_audit",
                                                "chat",
                                            ],
                                        },
                                        "query": {"type": "string"},
                                        "output_format": {"type": "string", "enum": ["json", "markdown", "auto"]},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {"200": {"description": "Service analysis result"}},
                }
            },
        },
        "components": {
            "securitySchemes": {
                "ApiKeyAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-API-Key",
                }
            }
        },
        "security": [{"ApiKeyAuth": []}],
    }


@router.get("/openai/tools", summary="OpenAI Function Calling Tools Specification")
def get_openai_function_tools():
    """
    Returns OpenAI-compatible function calling schemas (`tools` parameter)
    for direct integration into GPT chats (`client.chat.completions.create`).
    """
    return {
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "docuchat_list_documents",
                    "description": "List documents uploaded to DOCTool with their page count and IDs.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "limit": {"type": "integer", "description": "Maximum documents to return", "default": 20}
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "docuchat_search_chunks",
                    "description": "Hybrid semantic and keyword search across document chunks with page citations.",
                    "parameters": {
                        "type": "object",
                        "required": ["document_id", "query"],
                        "properties": {
                            "document_id": {"type": "string", "description": "ID of document to search"},
                            "query": {"type": "string", "description": "Keywords or semantic question"},
                            "top_k": {"type": "integer", "description": "Number of snippets to retrieve", "default": 5},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "docuchat_extract_invoice",
                    "description": "Extract structured financial invoice data (vendor, line items, taxes, totals).",
                    "parameters": {
                        "type": "object",
                        "required": ["document_id"],
                        "properties": {
                            "document_id": {"type": "string", "description": "Document ID"},
                            "query": {"type": "string", "description": "Optional specific extraction prompt"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "docuchat_analyze_contract",
                    "description": "Analyze contract clauses, legal liabilities, indemnities, and termination terms.",
                    "parameters": {
                        "type": "object",
                        "required": ["document_id"],
                        "properties": {
                            "document_id": {"type": "string", "description": "Document ID"},
                            "query": {"type": "string", "description": "Optional specific legal focus area"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "docuchat_audit_compliance",
                    "description": "Scan document for PII, GDPR/HIPAA compliance risks, and security flags.",
                    "parameters": {
                        "type": "object",
                        "required": ["document_id"],
                        "properties": {
                            "document_id": {"type": "string", "description": "Document ID"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "docuchat_summarize_document",
                    "description": "Generate multi-section executive summary with grounded citations.",
                    "parameters": {
                        "type": "object",
                        "required": ["document_id"],
                        "properties": {
                            "document_id": {"type": "string", "description": "Document ID"},
                            "query": {"type": "string", "description": "Optional summary focus"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "docuchat_redact_document",
                    "description": "Sanitize and redact sensitive PII (National IDs, Iqama, IBANs, Credit Cards, Phones) in English and Arabic.",
                    "parameters": {
                        "type": "object",
                        "required": ["document_id"],
                        "properties": {
                            "document_id": {"type": "string", "description": "Document ID"},
                            "query": {"type": "string", "description": "Optional specific redaction instructions"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "docuchat_classify_document",
                    "description": "Classify document category, language, and routing department in English and Arabic.",
                    "parameters": {
                        "type": "object",
                        "required": ["document_id"],
                        "properties": {
                            "document_id": {"type": "string", "description": "Document ID"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "docuchat_analyze_financial_statement",
                    "description": "Extract financial statement metrics (revenue, EBIT, net income, assets, equity) and compute financial ratios in EN & AR.",
                    "parameters": {
                        "type": "object",
                        "required": ["document_id"],
                        "properties": {
                            "document_id": {"type": "string", "description": "Document ID"},
                            "query": {"type": "string", "description": "Optional financial focus"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "docuchat_translate_document",
                    "description": "Bidirectional certified enterprise translation between English and Arabic (EN <-> AR) preserving clauses and tables.",
                    "parameters": {
                        "type": "object",
                        "required": ["document_id"],
                        "properties": {
                            "document_id": {"type": "string", "description": "Document ID"},
                            "target_language": {"type": "string", "description": "Target language: Arabic or English", "default": "Arabic"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "docuchat_audit_anomalies",
                    "description": "Forensic audit for arithmetic errors, ZATCA VAT 15%, inverted dates, and contractual contradictions in EN & AR.",
                    "parameters": {
                        "type": "object",
                        "required": ["document_id"],
                        "properties": {
                            "document_id": {"type": "string", "description": "Document ID"},
                            "query": {"type": "string", "description": "Optional audit focus"},
                        },
                    },
                },
            },
        ]
    }


# ---------------------------------------------------------------------------
# Account & Pricing Endpoints
# ---------------------------------------------------------------------------


@router.get("/company/account", summary="Get Company Balance and Tier")
def get_company_account_v1(account: CompanyAccount = CompanyAuth):
    """Get company account details, remaining free trial credits, and usage stats."""
    return {
        "companyId": account.id,
        "companyName": account.company_name,
        "planTier": account.plan_tier,
        "totalCredits": account.total_credits,
        "usedCredits": account.used_credits,
        "remainingCredits": account.remaining_credits,
        "apiKeyPrefix": account.api_key_prefix,
        "createdAt": account.created_at,
    }


@router.get("/company/pricing", summary="Get B2B Service Pricing Catalog")
def get_service_pricing_catalog():
    """Retrieve catalog of Document AI services and credit rates."""
    return {
        "initialTrialCredits": INITIAL_TRIAL_CREDITS,
        "services": [
            {
                "id": k,
                "name": v["name"],
                "credits": v["credits"],
                "llmTier": v["llm_tier"],
                "category": v["category"],
                "description": v["description"],
            }
            for k, v in SERVICE_PRICING.items()
        ],
    }


class CalculateCostPayload(BaseModel):
    service: str
    model: Optional[str] = None
    guardian: bool = True


class SetModelSettingPayload(BaseModel):
    model: str


class GuardianSettingPayload(BaseModel):
    enabled: bool


# In-memory store for company preferred model & guardian settings
COMPANY_MODEL_SETTINGS: Dict[str, str] = {}
COMPANY_GUARDIAN_SETTINGS: Dict[str, bool] = {}


@router.get("/models", summary="List Available AI Models", tags=["Models"])
def list_available_models():
    """Retrieve available AI models for document intelligence strictly loaded from models.json.
    
    Includes token rates and credit economic conversions ($2.00 USD = 1,000 Credits).
    """
    from backend.models_config import model_registry

    all_models = model_registry.get_all_models()
    return {
        "object": "list",
        "data": all_models,
        "default_model": model_registry.default_model_id,
        "total_available": len(all_models),
        "credit_price_usd": 0.002,
        "conversion_formula": "$2.00 = 1,000 Credits ($0.002 / Credit)",
        "allowed_models": sorted(list(model_registry.allowed_model_ids)),
    }


@router.post("/services/calculate-cost", summary="Calculate Credit Cost for Service and Model", tags=["Pricing"])
def calculate_service_cost_endpoint(payload: CalculateCostPayload):
    """Calculate the exact base service credits, model differential, guardian fee, and USD conversion."""
    from backend.models_config import model_registry

    service_name = payload.service.lower().replace("-", "_")
    base_credits = SERVICE_PRICING.get(service_name, {}).get("credits", 10)
    return model_registry.calculate_service_cost(base_credits, payload.model, guardian=payload.guardian)


@router.get("/settings/model", summary="Get Current Model Setting", tags=["Settings"])
def get_model_setting(account: CompanyAccount = CompanyAuth):
    """Retrieve the company's active model for AI services."""
    from backend.models_config import model_registry

    chosen = COMPANY_MODEL_SETTINGS.get(str(account.id), model_registry.default_model_id)
    model_info = model_registry.get_model(chosen) or model_registry.get_model(model_registry.default_model_id)
    return {
        "current_model": chosen,
        "model_details": model_info,
        "default_model": model_registry.default_model_id,
        "allowed_models": sorted(list(model_registry.allowed_model_ids)),
        "credit_price_usd": 0.002,
        "conversion_formula": "$2.00 = 1,000 Credits ($0.002 / Credit)",
    }


@router.post("/settings/model", summary="Set Preferred Model for AI Services", tags=["Settings"])
def set_model_setting(payload: SetModelSettingPayload, account: CompanyAccount = CompanyAuth):
    """Update the company's active model for AI services. Model must exist in models.json."""
    from backend.models_config import model_registry

    valid_model = model_registry.validate_model(payload.model)
    COMPANY_MODEL_SETTINGS[str(account.id)] = valid_model
    model_info = model_registry.get_model(valid_model)
    return {
        "status": "success",
        "current_model": valid_model,
        "model_details": model_info,
        "message": f"Default processing model set to {valid_model}",
    }


@router.get("/settings/guardian", summary="Get Current Guardian Mode Setting", tags=["Settings"])
def get_guardian_setting(account: CompanyAccount = CompanyAuth):
    """Retrieve the company's active Guardian mode setting."""
    guardian_enabled = COMPANY_GUARDIAN_SETTINGS.get(str(account.id), True)
    return {
        "guardian": guardian_enabled,
        "guardian_fee_credits": 5,
        "mode": "guardian_verification" if guardian_enabled else "direct_return",
        "description": (
            "Guardian Verification: Grounded evidence citations, schema checks, guardrails (takes 5 credits fee)"
            if guardian_enabled
            else "Direct Return: Raw model extraction returned immediately without citation nullification (guardian fee waived)"
        ),
    }


@router.post("/settings/guardian", summary="Set Preferred Guardian Mode", tags=["Settings"])
def set_guardian_setting(payload: GuardianSettingPayload, account: CompanyAccount = CompanyAuth):
    """Update the company's Guardian mode setting."""
    COMPANY_GUARDIAN_SETTINGS[str(account.id)] = bool(payload.enabled)
    return {
        "status": "success",
        "guardian": payload.enabled,
        "mode": "guardian_verification" if payload.enabled else "direct_return",
        "message": f"Guardian mode set to {'enabled (Full Verification)' if payload.enabled else 'disabled (Direct Return)'}",
    }


class UpdateWorkspacePayload(BaseModel):
    name: str


@router.get("/workspace", summary="Get User Dedicated Workspace", tags=["Workspace"])
def get_workspace_info(account: CompanyAccount = CompanyAuth):
    """Retrieve details for the current user's dedicated workspace."""
    return {
        "id": account.id,
        "name": account.company_name,
        "userId": account.user_id,
        "planTier": account.plan_tier,
        "totalCredits": account.total_credits,
        "usedCredits": account.used_credits,
        "remainingCredits": account.remaining_credits,
        "apiKeyPrefix": account.api_key_prefix,
        "apiKey": f"{account.api_key[:14]}••••••••••••••••••••••••{account.api_key[-4:]}",
        "createdAt": account.created_at,
        "status": "active" if account.is_active else "suspended",
    }


@router.put("/workspace", summary="Rename Workspace", tags=["Workspace"])
def update_workspace_info(payload: UpdateWorkspacePayload, account: CompanyAccount = CompanyAuth):
    """Rename user's dedicated workspace."""
    clean_name = payload.name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Workspace name cannot be empty")
    from backend.billing import billing_service

    updated = billing_service.update_workspace_name(account.user_id, clean_name)
    return {
        "status": "success",
        "id": updated.id,
        "name": updated.company_name,
        "message": f"Workspace renamed to '{updated.company_name}'",
    }
