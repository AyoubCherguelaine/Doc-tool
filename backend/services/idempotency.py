"""HTTP replay helpers for the shared durable operation ledger."""

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from backend.services.persistence import operation_identity, operation_store


def begin(account, namespace, key, payload):
    if key is None:
        return None, None
    operation_key, fingerprint = operation_identity(namespace, key, payload)
    replay = operation_store.claim(str(account.id), operation_key, fingerprint)
    return operation_key, replay


def replay_response(replay):
    return JSONResponse(
        content=jsonable_encoder(replay["body"]),
        status_code=replay["status_code"],
        headers={"X-Idempotency-Replayed": "true"},
    )


def finish(account, operation_key, body, status_code=200):
    if operation_key:
        operation_store.complete(str(account.id), operation_key, jsonable_encoder(body), status_code)


def finish_error(account, operation_key, error: HTTPException):
    finish(account, operation_key, {"detail": error.detail}, error.status_code)
