"""
Asynchronous Pipeline Job Worker.

Processes background document intelligence jobs, updates status,
and dispatches webhook callbacks when tasks complete.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import threading
import time

import httpx

from backend.billing import billing_service
from backend.config import settings
from backend.jobs.queue import Job, job_queue

logger = logging.getLogger("docuchat.worker")


async def _send_webhook(url: str, payload: dict) -> None:
    """Send cryptographically signed HMAC-SHA256 webhook notification to pipeline consumer."""
    try:
        raw_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        timestamp = str(int(time.time()))
        signing_secret = settings.JWT_SECRET
        signature = hmac.new(
            signing_secret.encode("utf-8"),
            f"{timestamp}.".encode("utf-8") + raw_body,
            hashlib.sha256,
        ).hexdigest()

        headers = {
            "Content-Type": "application/json",
            "X-DocuChat-Timestamp": timestamp,
            "X-DocuChat-Signature": f"sha256={signature}",
            "User-Agent": "DocuChat-Enterprise-Worker/1.0",
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, content=raw_body, headers=headers)
            logger.info("Webhook dispatched to %s, status=%d", url, resp.status_code)
    except Exception as exc:
        logger.warning("Failed to dispatch webhook to %s: %s", url, exc)


def execute_job_task(job: Job) -> Job:
    """Claim once, then use the same executor as synchronous and playground requests."""
    from fastapi import HTTPException

    from backend.services.engine import execute_service
    from backend.services.models import ServiceRequest

    claimed = job_queue.claim_job(job.id)
    if claimed is None:
        return job_queue.get_job(job.id) or job
    account = billing_service.get_company_by_id(claimed.company_id) if claimed.company_id else None
    if account is None and claimed.user_id:
        account = billing_service.get_or_create_company(claimed.user_id)
    if account is None:
        return job_queue.update_job(job.id, status="failed", error="Job account not found", progress=100) or claimed
    try:
        request = ServiceRequest.model_validate(
            claimed.request_payload
            or {
                "service": claimed.service,
                "document_id": claimed.document_id,
                "query": claimed.query,
                "output_format": claimed.output_format,
            }
        )
        body = execute_service(request, account)
        body.update(jobId=job.id, creditsCost=body.get("creditsDeducted", 0))
        job = (
            job_queue.update_job(
                job.id,
                status="completed" if body["success"] else "failed",
                progress=100,
                result=body,
                error=body.get("error"),
            )
            or claimed
        )
    except HTTPException as exc:
        job = job_queue.update_job(job.id, status="failed", progress=100, error=str(exc.detail)) or claimed
        body = {"success": False, "status": "failed", "jobId": job.id, "error": str(exc.detail)}
    except Exception:
        logger.exception("Job %s failed", claimed.id)
        job = job_queue.update_job(job.id, status="failed", progress=100, error="Service execution failed") or claimed
        body = {"success": False, "status": "failed", "jobId": job.id, "error": "Service execution failed"}
    if claimed.webhook_url:
        asyncio.run(_send_webhook(claimed.webhook_url, body))
    return job


def run_worker_loop(stop_check=None) -> None:
    """Continuous polling worker loop for processing queued jobs."""
    logger.info("DocuChat background job worker started. Listening for jobs...")
    while True:
        if stop_check and stop_check():
            break

        job_id = job_queue.pop_job(timeout_seconds=0.1 if stop_check else 2)
        if not job_id:
            time.sleep(0.1)
            continue

        job = job_queue.get_job(job_id)
        if not job:
            continue

        execute_job_task(job)


def start_background_worker(stop_check=None) -> threading.Thread:
    """Start the worker loop in a daemon thread inside the FastAPI application."""
    thread = threading.Thread(
        target=run_worker_loop, kwargs={"stop_check": stop_check}, daemon=True, name="DocuChatJobWorker"
    )
    thread.start()
    return thread


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    run_worker_loop()
