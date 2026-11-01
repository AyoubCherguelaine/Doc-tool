from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
# Explicit paths avoid find_dotenv stopping at backend/.env and hiding root credentials.
load_dotenv(REPO_ROOT / ".env")
load_dotenv(REPO_ROOT / "backend" / ".env")


class Settings:
    DEBUG: bool = os.getenv("DEBUG", "0") == "1"

    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:docuchat123@localhost:5436/docuchat",
    )

    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    DEFAULT_MODEL: str = os.getenv("DEFAULT_MODEL", "gpt-4o-mini")
    _env_chat_models = [m.strip() for m in os.getenv("CHAT_MODELS", "").split(",") if m.strip()]
    try:
        import json
        with open(REPO_ROOT / "models.json", "r", encoding="utf-8") as _mf:
            _mdata = json.load(_mf)
            _json_models = [m["id"] for m in _mdata.get("models", []) if "id" in m]
    except Exception:
        _json_models = []
    CHAT_MODELS: list[str] = list(dict.fromkeys([DEFAULT_MODEL] + _json_models + _env_chat_models))
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "backend/uploads")
    INDEX_DIR: str = os.getenv("INDEX_DIR", "backend/faiss_indexes")
    DOC_TTL_MINUTES: int = int(os.getenv("DOC_TTL_MINUTES", "10"))

    # Redis Distributed Cache & Queue
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # SeaweedFS S3 object storage. Public endpoint is used for browser links.
    STORAGE_BACKEND: str = "seaweedfs"
    S3_ENDPOINT_URL: str = os.getenv("S3_ENDPOINT_URL", "http://localhost:8333")
    S3_PUBLIC_ENDPOINT_URL: str = os.getenv("S3_PUBLIC_ENDPOINT_URL", "http://localhost:8333")
    S3_ACCESS_KEY: str = os.getenv("S3_ACCESS_KEY", "docuchat")
    S3_SECRET_KEY: str = os.getenv("S3_SECRET_KEY", "docuchat-s3-development-secret")
    S3_BUCKET: str = os.getenv("S3_BUCKET", "docuchat-documents")
    S3_REGION: str = os.getenv("S3_REGION", "us-east-1")

    JWT_SECRET: str = os.getenv(
        "JWT_SECRET",
        "docuchat-production-secret-key-32bytes-minimum-security-token-2026",
    )
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "10080"))

    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))

    ALLOWED_ORIGINS: list[str] = [
        o.strip()
        for o in os.getenv(
            "ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
        ).split(",")
        if o.strip()
    ]


settings = Settings()
