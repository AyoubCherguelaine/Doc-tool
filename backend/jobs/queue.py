"""
Redis-Powered Distributed Job Queue, Caching & Rate Limiting Engine.

Stores job state across worker nodes and provides transparent fallback
to thread-safe in-memory storage when Redis is unavailable.
"""

from __future__ import annotations

import datetime
import json
import logging
import queue
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

import redis
from fastapi.encoders import jsonable_encoder

from backend.config import settings

logger = logging.getLogger("docuchat.jobs")


@dataclass
class Job:
    id: str
    service: str
    document_id: str
    status: str  # queued, processing, completed, failed, cancelled
    progress: int
    user_id: Optional[str] = None
    company_id: Optional[str] = None
    query: Optional[str] = None
    output_format: str = "auto"
    request_payload: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    webhook_url: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""
    completed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RedisJobQueue:
    """Enterprise distributed job queue and cache manager."""

    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or settings.REDIS_URL
        self._redis_client: Optional[redis.Redis] = None
        self._redis_available: Optional[bool] = None
        self._lock = threading.Lock()

        # In-memory fallback
        self._mem_jobs: Dict[str, Job] = {}
        self._mem_queue: queue.Queue[str] = queue.Queue()
        self._mem_cache: Dict[str, Any] = {}

    def _get_redis(self) -> Optional[redis.Redis]:
        """Lazy-connect to Redis with short timeout."""
        if self._redis_available is False:
            return None
        if self._redis_client is not None:
            return self._redis_client

        try:
            r = redis.from_url(
                self.redis_url,
                socket_connect_timeout=0.5,
                socket_timeout=1.0,
                decode_responses=True,
            )
            r.ping()
            self._redis_client = r
            self._redis_available = True
            logger.info("Connected to Redis at %s", self.redis_url)
            return self._redis_client
        except Exception as exc:
            logger.info("Redis unavailable at %s (%s). Using in-memory job queue.", self.redis_url, exc)
            self._redis_available = False
            return None

    def is_healthy(self) -> bool:
        """Check if Redis is connected and responsive."""
        try:
            r = self._get_redis()
            return r is not None and r.ping()
        except Exception:
            return False

    def enqueue(
        self,
        service: str,
        document_id: str,
        user_id: Optional[str] = None,
        company_id: Optional[str] = None,
        query: Optional[str] = None,
        output_format: str = "auto",
        webhook_url: Optional[str] = None,
        request_payload: Optional[Dict[str, Any]] = None,
    ) -> Job:
        """Enqueue an asynchronous pipeline job."""
        job_id = f"job_{uuid.uuid4().hex[:16]}"
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        job = Job(
            id=job_id,
            service=service,
            document_id=document_id,
            status="queued",
            progress=0,
            user_id=user_id,
            company_id=company_id,
            query=query,
            output_format=output_format,
            webhook_url=webhook_url,
            request_payload=request_payload,
            created_at=now,
            updated_at=now,
        )

        r = self._get_redis()
        if r is not None:
            try:
                # Store job metadata
                r.set(f"docuchat:job:{job_id}", json.dumps(jsonable_encoder(job.to_dict())))
                # Push to default queue
                r.rpush("docuchat:queue:default", job_id)
                logger.info("Enqueued job %s (%s) to Redis", job_id, service)
                return job
            except Exception as exc:
                logger.warning("Failed to enqueue to Redis (%s), falling back to in-memory.", exc)

        with self._lock:
            self._mem_jobs[job_id] = job
            self._mem_queue.put(job_id)
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        """Retrieve job state by ID."""
        r = self._get_redis()
        if r is not None:
            try:
                raw = r.get(f"docuchat:job:{job_id}")
                if raw:
                    data = json.loads(raw)
                    return Job(**data)
            except Exception:
                pass

        with self._lock:
            return self._mem_jobs.get(job_id)

    def update_job(
        self,
        job_id: str,
        status: Optional[str] = None,
        progress: Optional[int] = None,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> Optional[Job]:
        """Update job status, progress, and result."""
        job = self.get_job(job_id)
        if not job:
            return None

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        job.updated_at = now
        if status is not None:
            job.status = status
        if progress is not None:
            job.progress = progress
        if result is not None:
            job.result = result
        if error is not None:
            job.error = error
        if status in ("completed", "failed", "cancelled"):
            job.completed_at = now
            job.request_payload = None

        r = self._get_redis()
        if r is not None:
            try:
                r.set(f"docuchat:job:{job_id}", json.dumps(jsonable_encoder(job.to_dict())))
                return job
            except Exception:
                pass

        with self._lock:
            self._mem_jobs[job_id] = job
        return job

    def claim_job(self, job_id: str) -> Optional[Job]:
        """Atomically claim only queued jobs, preventing duplicate worker execution/charges."""
        r = self._get_redis()
        if r is not None:
            for _ in range(5):
                try:
                    with r.pipeline() as pipe:
                        key = f"docuchat:job:{job_id}"
                        pipe.watch(key)
                        raw = pipe.get(key)
                        if not raw:
                            return None
                        job = Job(**json.loads(raw))
                        if job.status != "queued":
                            return None
                        job.status, job.progress = "processing", 15
                        job.updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
                        pipe.multi()
                        pipe.set(key, json.dumps(jsonable_encoder(job.to_dict())))
                        pipe.execute()
                        return job
                except redis.WatchError:
                    continue
            raise RuntimeError("Could not claim job after concurrent updates")
        with self._lock:
            job = self._mem_jobs.get(job_id)
            if not job or job.status != "queued":
                return None
            job.status, job.progress = "processing", 15
            return job

    def pop_job(self, timeout_seconds: int = 1) -> Optional[str]:
        """Pop next job ID from queue for worker processing."""
        r = self._get_redis()
        if r is not None:
            try:
                item = r.blpop("docuchat:queue:default", timeout=timeout_seconds)
                if item:
                    # item is tuple (queue_name, job_id)
                    return item[1]
            except Exception:
                pass

        try:
            return self._mem_queue.get(timeout=timeout_seconds)
        except queue.Empty:
            return None

    def list_jobs(self, limit: int = 50, user_id: Optional[str] = None) -> List[Job]:
        """List recent jobs."""
        with self._lock:
            jobs = list(self._mem_jobs.values())
        if user_id:
            jobs = [j for j in jobs if j.user_id == user_id]
        return sorted(jobs, key=lambda x: x.created_at, reverse=True)[:limit]

    # -----------------------------------------------------------------------
    # Distributed Caching & Rate Limiting
    # -----------------------------------------------------------------------

    def cache_get(self, key: str) -> Optional[Any]:
        """Get cached value."""
        r = self._get_redis()
        if r is not None:
            try:
                val = r.get(f"docuchat:cache:{key}")
                return json.loads(val) if val else None
            except Exception:
                pass
        with self._lock:
            return self._mem_cache.get(key)

    def cache_set(self, key: str, value: Any, ttl_seconds: int = 300) -> None:
        """Store value in cache with TTL."""
        r = self._get_redis()
        if r is not None:
            try:
                r.setex(f"docuchat:cache:{key}", ttl_seconds, json.dumps(value))
                return
            except Exception:
                pass
        with self._lock:
            self._mem_cache[key] = value

    def check_rate_limit(self, key: str, max_requests: int = 100, window_seconds: int = 60) -> bool:
        """
        Token bucket / sliding window rate limiter.
        Returns True if request is allowed, False if limit exceeded.
        """
        r = self._get_redis()
        if r is not None:
            try:
                rate_key = f"docuchat:ratelimit:{key}"
                current = r.incr(rate_key)
                if current == 1:
                    r.expire(rate_key, window_seconds)
                return current <= max_requests
            except Exception:
                pass

        with self._lock:
            now = time.time()
            if not hasattr(self, "_rate_limits"):
                self._rate_limits: Dict[str, List[float]] = {}
            timestamps = self._rate_limits.setdefault(key, [])
            # Filter timestamps within window
            timestamps = [t for t in timestamps if now - t < window_seconds]
            if len(timestamps) >= max_requests:
                self._rate_limits[key] = timestamps
                return False
            timestamps.append(now)
            self._rate_limits[key] = timestamps
            return True


job_queue = RedisJobQueue()
