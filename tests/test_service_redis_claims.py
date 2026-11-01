"""Exercise the Redis WATCH transaction path using Redis-compatible shared test storage."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import fakeredis

from backend.jobs.queue import RedisJobQueue


def test_distributed_queues_claim_once_and_serialize_results():
    server = fakeredis.FakeServer()
    queues = [RedisJobQueue() for _ in range(8)]
    for queue in queues:
        connection = fakeredis.FakeRedis(server=server, decode_responses=True)
        queue._get_redis = lambda connection=connection: connection
    job = queues[0].enqueue(
        "invoice", "doc", company_id="company", request_payload={"service": "invoice", "document_id": "doc"}
    )
    with ThreadPoolExecutor(max_workers=8) as executor:
        claims = list(executor.map(lambda queue: queue.claim_job(job.id), queues))
    assert sum(claim is not None for claim in claims) == 1
    queues[0].update_job(job.id, status="completed", progress=100, result={"data": {"total": Decimal("100.50")}})
    for queue in queues:
        restored = queue.get_job(job.id)
        assert restored.status == "completed"
        assert restored.result["data"]["total"] == 100.5
        assert restored.request_payload is None
        assert queue.claim_job(job.id) is None
