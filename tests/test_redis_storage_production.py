"""
Unit and Integration Tests for Production Infrastructure:
- SeaweedFS (S3-Compatible) Object Storage & Presigned URLs
- Redis Distributed Job Queue & Rate Limiter
- Asynchronous Background Pipeline Worker
- Production Readiness Probes (/api/health)
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend import server
from backend.billing import billing_service
from backend.jobs.queue import RedisJobQueue
from backend.jobs.worker import execute_job_task
from backend.sdk.client import DocuChatClient
from backend.storage import S3StorageService


@pytest.fixture
def client():
    return TestClient(server.app)


@pytest.fixture
def b2b_account():
    user_id = str(uuid.uuid4())
    return billing_service.get_or_create_company(user_id, company_name="Production Cloud Corp")


# ===========================================================================
# 1. SeaweedFS Object Storage Tests
# ===========================================================================


def test_s3_storage_upload_and_retrieve():
    """Test uploading and retrieving bytes via storage service."""
    service = S3StorageService()
    if not service.is_healthy():
        pytest.skip("SeaweedFS is not running")
    test_content = b"Production SeaweedFS Document Payload 2026"
    obj_name = f"tests/doc_{uuid.uuid4().hex[:8]}.txt"

    uri = service.upload(obj_name, test_content)
    assert uri is not None
    assert obj_name in uri

    retrieved = service.get_bytes(obj_name)
    assert retrieved == test_content

    presigned = service.get_presigned_url(obj_name, expires_seconds=1800)
    assert presigned is not None
    assert len(presigned) > 5

    deleted = service.delete(obj_name)
    assert deleted is True


def test_storage_status_endpoint(client, b2b_account):
    """Test /api/v1/storage/status reporting SeaweedFS configuration."""
    resp = client.get(
        "/api/v1/storage/status",
        headers={"X-API-Key": b2b_account.api_key},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "SeaweedFS (S3-Compatible)"
    assert "bucket" in data
    assert "storageBackend" in data


def test_presigned_url_endpoint(client, b2b_account):
    """Test generating presigned document URL via API."""
    doc_id = str(uuid.uuid4())
    from backend.v1.routes import storage_service

    with patch.object(storage_service, "exists", return_value=True):
        resp = client.get(
            f"/api/v1/storage/documents/{doc_id}/presigned-url",
            headers={"X-API-Key": b2b_account.api_key},
            params={"expires_seconds": 600},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["documentId"] == doc_id
    assert "url" in data
    assert data["expiresInSeconds"] == 600


# ===========================================================================
# 2. Redis Job Queue & Distributed Utilities Tests
# ===========================================================================


def test_redis_job_queue_enqueue_and_poll():
    """Test enqueuing and polling an async pipeline job."""
    queue = RedisJobQueue()
    queue._redis_available = False  # Isolate from external live Docker worker container
    job = queue.enqueue(
        service="invoice",
        document_id="doc-async-001",
        user_id="user-123",
        query="Extract line items",
    )
    assert job.id.startswith("job_")
    assert job.status == "queued"
    assert job.progress == 0

    fetched = queue.get_job(job.id)
    assert fetched is not None
    assert fetched.document_id == "doc-async-001"

    # Test state update
    queue.update_job(job.id, status="processing", progress=50)
    updated = queue.get_job(job.id)
    assert updated.status == "processing"
    assert updated.progress == 50


def test_redis_rate_limiter():
    """Test token bucket rate limiter under burst threshold."""
    queue = RedisJobQueue()
    key = f"test_rate_{uuid.uuid4().hex[:6]}"
    # 5 requests within limit
    for _ in range(5):
        assert queue.check_rate_limit(key, max_requests=10, window_seconds=10) is True


def test_async_job_submission_endpoint(client, b2b_account):
    """Test submitting an async job returning 202 Accepted."""
    payload = {
        "document_id": "doc-async-777",
        "service": "invoice",
        "query": "Full analysis",
    }
    resp = client.post(
        "/api/v1/pipeline/jobs",
        headers={"X-API-Key": b2b_account.api_key},
        json=payload,
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "accepted"
    assert "jobId" in data
    assert data["state"] in {"queued", "processing", "completed", "failed"}  # A live worker may start immediately.
    assert data["estimatedCredits"] == 25

    # Poll status immediately
    job_id = data["jobId"]
    poll_resp = client.get(
        f"/api/v1/pipeline/jobs/{job_id}",
        headers={"X-API-Key": b2b_account.api_key},
    )
    assert poll_resp.status_code == 200
    poll_data = poll_resp.json()
    assert poll_data["jobId"] == job_id
    assert poll_data["status"] in ("queued", "processing", "failed", "completed")


def test_list_async_jobs_endpoint(client, b2b_account):
    """Test listing recent jobs for the authenticated company."""
    resp = client.get(
        "/api/v1/pipeline/jobs",
        headers={"X-API-Key": b2b_account.api_key},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "jobs" in data
    assert isinstance(data["jobs"], list)


# ===========================================================================
# 3. Worker Execution Tests
# ===========================================================================


def test_execute_job_task_success(b2b_account, monkeypatch):
    """Test worker executing a job successfully with mock bundle & agent."""
    from backend.jobs import worker

    queue = RedisJobQueue()
    monkeypatch.setattr(queue, "_get_redis", lambda: None)
    monkeypatch.setattr(worker, "job_queue", queue)
    monkeypatch.setattr("backend.services.engine.query", lambda *args, **kwargs: {"id": "doc-worker-1"})
    job = queue.enqueue(
        service="summary",
        document_id="doc-worker-1",
        user_id=str(b2b_account.user_id),
        company_id=str(b2b_account.id),
    )

    mock_bundle = MagicMock()
    mock_bundle.vector_store = MagicMock()
    mock_bundle.doc_id = "doc-worker-1"

    mock_agent = MagicMock()
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.iterations = 1
    mock_result.steps = []
    mock_result.response = "Executive Summary: Q3 revenue grew 42% YoY."
    mock_agent.run.return_value = mock_result

    with (
        patch("backend.rag.get_bundle", return_value=mock_bundle),
        patch("backend.rag._build_agent", return_value=mock_agent),
    ):
        completed_job = execute_job_task(job)
        assert completed_job.status == "completed"
        assert completed_job.progress == 100
        assert completed_job.result["status"] == "success"
        assert "revenue grew" in completed_job.result["raw"]


# ===========================================================================
# 4. Production Health Check & SDK Async Methods
# ===========================================================================


def test_production_health_check(client):
    """Test /api/health returns full stack status (DB, Redis, SeaweedFS, JobWorker)."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "database" in data
    assert "redis" in data
    assert "storage" in data
    assert data["jobWorker"] == "active"
    assert data["version"] == "1.0.0"


def test_sdk_async_job_and_storage_methods():
    """Test DocuChatClient async job and SeaweedFS presigned URL methods."""
    sdk = DocuChatClient(api_key="docu_live_test_key")

    with patch.object(sdk, "_request") as mock_req:
        mock_req.return_value = {"status": "accepted", "jobId": "job_12345"}
        res = sdk.submit_async_job("doc-1", service="contract")
        assert res["jobId"] == "job_12345"

        mock_req.return_value = {"jobId": "job_12345", "status": "completed", "progress": 100}
        status_res = sdk.get_job_status("job_12345")
        assert status_res["status"] == "completed"

        mock_req.return_value = {"url": "/api/v1/storage/download/doc-1.pdf?expires=123&signature=xyz"}
        url = sdk.get_document_url("doc-1")
        assert "signature=xyz" in url


def test_signed_download_http_flow():
    import httpx

    service = S3StorageService()
    if not service.is_healthy():
        pytest.skip("SeaweedFS is not running")
    name = f"tests/{uuid.uuid4().hex}/report with spaces.pdf"
    try:
        service.upload(name, b"%PDF-test-payload")
        url = service.get_presigned_url(name)
        response = httpx.get(url)
        assert response.status_code == 200
        assert response.content == b"%PDF-test-payload"
        assert httpx.get(url.replace("X-Amz-Signature=", "X-Amz-Signature=forged")).status_code == 403
        assert httpx.get(url.split("?")[0]).status_code == 403
    finally:
        service.delete(name)
    assert httpx.get(url).status_code == 404
