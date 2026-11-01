"""
Company Billing & API Usage Service.

Handles company free trial allocation (300 credits), API key generation,
per-service pricing based on LLM compute intensity, credit validation,
atomic deductions, and usage audit logging.
"""

from __future__ import annotations

import logging
import secrets
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

INITIAL_TRIAL_CREDITS = 300
API_KEY_PREFIX = "docu_live_"

# ---------------------------------------------------------------------------
# Per-Service Pricing based on LLM token & multimodal compute intensity
# ---------------------------------------------------------------------------
SERVICE_PRICING: Dict[str, Dict[str, Any]] = {
    "chat": {
        "name": "Document Chat",
        "credits": 1,
        "llm_tier": "Light",
        "description": "Fast conversational Q&A over document chunks",
        "category": "General",
    },
    "summary": {
        "name": "Executive Summary",
        "credits": 10,
        "llm_tier": "Light-Moderate",
        "description": "Multi-section executive summary with key findings",
        "category": "General",
    },
    "extraction": {
        "name": "Data Extraction",
        "credits": 15,
        "llm_tier": "Moderate",
        "description": "Structured table and metrics extraction into Markdown",
        "category": "Extraction",
    },
    "form_parser": {
        "name": "Intelligent Form Parser",
        "credits": 20,
        "llm_tier": "Moderate",
        "description": "Form key-values, checkboxes [X], and signature blocks",
        "category": "Extraction",
    },
    "receipt": {
        "name": "Receipt & Expenses",
        "credits": 20,
        "llm_tier": "Moderate",
        "description": "Itemized receipt line items, taxes, tips, and math check",
        "category": "Finance",
    },
    "invoice": {
        "name": "Invoice Processing",
        "credits": 25,
        "llm_tier": "Moderate-Heavy",
        "description": "Vendor/client extraction, line items, and verified JSON",
        "category": "Finance",
    },
    "resume": {
        "name": "Resume & Talent Intelligence",
        "credits": 25,
        "llm_tier": "Moderate-Heavy",
        "description": "Candidate skills taxonomy, career timeline, seniority rating",
        "category": "HR",
    },
    "compliance": {
        "name": "PII & Compliance Audit",
        "credits": 30,
        "llm_tier": "Heavy",
        "description": "Full document PII scan, GDPR/HIPAA risk scoring, redaction",
        "category": "Legal & Security",
    },
    "contract": {
        "name": "Contract Analysis",
        "credits": 35,
        "llm_tier": "Heavy",
        "description": "Legal clauses, liabilities, indemnification, risk engine",
        "category": "Legal",
    },
    "google_ai": {
        "name": "Google AI Document",
        "credits": 40,
        "llm_tier": "Multimodal Heavy",
        "description": "Multimodal layout hierarchy, entities, and vision OCR",
        "category": "Multimodal",
    },
    "coordinator": {
        "name": "Auto-Routing Coordinator",
        "credits": 45,
        "llm_tier": "Multi-Agent Orchestration",
        "description": "Autonomous coordinator routing across specialized agents",
        "category": "Orchestration",
    },
    "research": {
        "name": "Deep Research",
        "credits": 50,
        "llm_tier": "Multi-Step ReAct Agent",
        "description": "Iterative investigation with grounded page citations",
        "category": "Research",
    },
    "comparison": {
        "name": "Document Comparison",
        "credits": 30,
        "llm_tier": "Moderate-Heavy",
        "description": "Multi-document comparative analysis and discrepancy detection",
        "category": "Analysis",
    },
    "factcheck": {
        "name": "Claim Verification",
        "credits": 20,
        "llm_tier": "Moderate",
        "description": "Evidence-grounded claim validation and verdict reporting",
        "category": "Verification",
    },
    "redaction": {
        "name": "Bilingual Data Redaction & Sanitization",
        "credits": 25,
        "llm_tier": "Moderate-Heavy",
        "description": "Bilingual anonymization of PII, national IDs, Iqama, IBANs, and confidential terms (EN & AR)",
        "category": "Security & Legal",
    },
    "classifier": {
        "name": "Bilingual Document Classification & Triage",
        "credits": 15,
        "llm_tier": "Moderate",
        "description": "Intelligent document categorization, urgency scoring, and target department routing (EN & AR)",
        "category": "Workflow Automation",
    },
    "financial_statement": {
        "name": "Financial Statement Intelligence",
        "credits": 35,
        "llm_tier": "Heavy",
        "description": "P&L, balance sheet, and cash flow extraction with ratio analytics in English & Arabic (IFRS/SOCPA)",
        "category": "Finance",
    },
    "translation": {
        "name": "Legal & Enterprise Translation",
        "credits": 20,
        "llm_tier": "Moderate",
        "description": "Bidirectional EN ↔ AR translation with glossary and number-preservation checks",
        "category": "Localization",
    },
    "anomaly_audit": {
        "name": "Fraud & Anomaly Audit",
        "credits": 25,
        "llm_tier": "Moderate-Heavy",
        "description": "Arithmetic checks with configurable tax rates, rounding tolerances and date order",
        "category": "Audit & Risk",
    },
    "invoice_matching": {
        "name": "Invoice and Purchase Order Matching",
        "credits": 50,
        "llm_tier": "Two-document extraction",
        "category": "Finance",
        "description": "Compare item quantities, prices, amounts and totals with source evidence",
    },
    "contract_comparison": {
        "name": "Contract Version Comparison",
        "credits": 15,
        "llm_tier": "Deterministic text comparison",
        "category": "Legal",
        "description": "Compare contract versions with before/after text and page references",
    },
    "document_checks": {
        "name": "Configurable Document Checks",
        "credits": 20,
        "llm_tier": "Extraction and deterministic rules",
        "category": "Workflow Automation",
        "description": "Check required fields, allowed values and company approval thresholds",
    },
    "advanced_ocr": {
        "name": "Advanced Semantic OCR",
        "credits": 5,
        "llm_tier": "Vision Layout OCR",
        "description": "Extract layout-aware semantic blocks, markdown tables, and reading direction",
        "category": "Extraction",
    },
}


@dataclass
class CompanyAccount:
    id: str
    user_id: str
    company_name: str
    plan_tier: str
    total_credits: int
    used_credits: int
    api_key: str
    api_key_prefix: str
    is_active: bool
    created_at: str
    updated_at: str

    @property
    def remaining_credits(self) -> int:
        return max(0, self.total_credits - self.used_credits)

    def to_dict(self, mask_key: bool = True) -> Dict[str, Any]:
        data = asdict(self)
        data["remaining_credits"] = self.remaining_credits
        if mask_key and self.api_key:
            data["api_key"] = f"{self.api_key[:14]}••••••••••••••••••••••••{self.api_key[-4:]}"
        return data


@dataclass
class UsageLog:
    id: str
    company_id: str
    service_name: str
    credits_cost: int
    remaining_balance: int
    document_id: Optional[str]
    request_summary: Optional[str]
    status: str
    created_at: str


class InsufficientCreditsError(Exception):
    """Raised when an account does not have sufficient credits for a service."""

    def __init__(self, required: int, remaining: int):
        self.required = required
        self.remaining = remaining
        super().__init__(
            f"Insufficient credits for this Document AI service. Required: {required}, "
            f"Remaining: {remaining}. Company Free Trial credits depleted."
        )


class CompanyBillingService:
    """Enterprise billing and API usage manager."""

    def __init__(self):
        self._lock = threading.Lock()
        # In-memory storage cache for fast access & database fallback
        self._accounts_by_user: Dict[str, CompanyAccount] = {}
        self._accounts_by_key: Dict[str, CompanyAccount] = {}
        self._accounts_by_id: Dict[str, CompanyAccount] = {}
        self._usage_logs: Dict[str, List[UsageLog]] = {}

    def ensure_tables(self) -> None:
        """Ensure company billing tables exist in Postgres."""
        try:
            from backend.db import execute

            execute("""
                CREATE TABLE IF NOT EXISTS docuchat.company_accounts (
                    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id        UUID NOT NULL UNIQUE REFERENCES docuchat.users(id) ON DELETE CASCADE,
                    company_name   TEXT NOT NULL DEFAULT 'Enterprise Free Trial',
                    plan_tier      TEXT NOT NULL DEFAULT 'free_trial',
                    total_credits  INT NOT NULL DEFAULT 300,
                    used_credits   INT NOT NULL DEFAULT 0,
                    api_key        TEXT UNIQUE NOT NULL,
                    api_key_prefix TEXT NOT NULL,
                    is_active      BOOLEAN NOT NULL DEFAULT true,
                    created_at     TIMESTAMPTZ DEFAULT now(),
                    updated_at     TIMESTAMPTZ DEFAULT now()
                );
                CREATE TABLE IF NOT EXISTS docuchat.api_usage_logs (
                    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    company_id      UUID NOT NULL REFERENCES docuchat.company_accounts(id) ON DELETE CASCADE,
                    service_name    TEXT NOT NULL,
                    credits_cost    INT NOT NULL,
                    document_id     TEXT,
                    request_summary TEXT,
                    status          TEXT NOT NULL DEFAULT 'success',
                    created_at      TIMESTAMPTZ DEFAULT now()
                );
            """)
        except Exception:
            pass

    def _generate_raw_api_key(self) -> str:
        """Create a secure API key with standard prefix."""
        token = secrets.token_hex(20)
        return f"{API_KEY_PREFIX}{token}"

    def get_or_create_company(
        self,
        user_id: str,
        company_name: Optional[str] = None,
    ) -> CompanyAccount:
        """Get or initialize a company account with 300 free trial credits."""
        user_id_str = str(user_id)
        with self._lock:
            # 1. Check in-memory store
            if user_id_str in self._accounts_by_user:
                return self._accounts_by_user[user_id_str]

            # 2. Check Database if available
            try:
                from backend.db import query

                row = query(
                    "SELECT id, user_id, company_name, plan_tier, total_credits, used_credits, "
                    "api_key, api_key_prefix, is_active, created_at, updated_at "
                    "FROM docuchat.company_accounts WHERE user_id = %s",
                    (user_id_str,),
                    one=True,
                )
                if row:
                    account = CompanyAccount(
                        id=str(row["id"]),
                        user_id=str(row["user_id"]),
                        company_name=row["company_name"],
                        plan_tier=row["plan_tier"],
                        total_credits=int(row["total_credits"]),
                        used_credits=int(row["used_credits"]),
                        api_key=row["api_key"],
                        api_key_prefix=row["api_key_prefix"],
                        is_active=bool(row["is_active"]),
                        created_at=row["created_at"].isoformat()
                        if hasattr(row["created_at"], "isoformat")
                        else str(row["created_at"]),
                        updated_at=row["updated_at"].isoformat()
                        if hasattr(row["updated_at"], "isoformat")
                        else str(row["updated_at"]),
                    )
                    self._cache_account(account)
                    return account
            except Exception:
                pass

            # Auto-ensure tables exist in database on first provision
            self.ensure_tables()

            # 3. Create fresh free trial account (300 credits)
            account_id = str(uuid.uuid4())
            if company_name and company_name.strip() and company_name.strip() != "Enterprise Free Trial":
                name = company_name.strip()
            else:
                name = f"User-{user_id_str[:6]}'s Workspace"
            api_key = self._generate_raw_api_key()
            prefix = api_key[:14]
            now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

            account = CompanyAccount(
                id=account_id,
                user_id=user_id_str,
                company_name=name,
                plan_tier="free_trial",
                total_credits=INITIAL_TRIAL_CREDITS,
                used_credits=0,
                api_key=api_key,
                api_key_prefix=prefix,
                is_active=True,
                created_at=now_iso,
                updated_at=now_iso,
            )

            # Persist to database if table exists
            try:
                from backend.db import execute

                execute(
                    "INSERT INTO docuchat.company_accounts "
                    "(id, user_id, company_name, plan_tier, total_credits, used_credits, api_key, api_key_prefix, is_active) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (user_id) DO NOTHING",
                    (
                        account_id,
                        user_id_str,
                        name,
                        "free_trial",
                        INITIAL_TRIAL_CREDITS,
                        0,
                        api_key,
                        prefix,
                        True,
                    ),
                )
            except Exception:
                pass

            self._cache_account(account)
            return account

    def _cache_account(self, account: CompanyAccount) -> None:
        self._accounts_by_user[account.user_id] = account
        self._accounts_by_key[account.api_key] = account
        self._accounts_by_id[account.id] = account

    def get_company_by_id(self, company_id: str) -> Optional[CompanyAccount]:
        """Lookup active company account by company UUID."""
        if not company_id:
            return None
        with self._lock:
            if company_id in self._accounts_by_id:
                return self._accounts_by_id[company_id]

            try:
                from backend.db import query

                row = query(
                    "SELECT id, user_id, company_name, plan_tier, total_credits, used_credits, "
                    "api_key, api_key_prefix, is_active, created_at, updated_at "
                    "FROM docuchat.company_accounts WHERE id = %s",
                    (company_id,),
                    one=True,
                )
                if row:
                    account = CompanyAccount(
                        id=str(row["id"]),
                        user_id=str(row["user_id"]),
                        company_name=row["company_name"],
                        plan_tier=row["plan_tier"],
                        total_credits=row["total_credits"],
                        used_credits=row["used_credits"],
                        api_key=row["api_key"],
                        api_key_prefix=row["api_key_prefix"],
                        is_active=row["is_active"],
                        created_at=str(row["created_at"]),
                        updated_at=str(row["updated_at"]),
                    )
                    self._cache_account(account)
                    return account
            except Exception:
                pass
            return None

    def get_company_by_api_key(self, api_key: str) -> Optional[CompanyAccount]:
        """Lookup active company account by secret API key."""
        if not api_key:
            return None
        clean_key = api_key.strip()
        with self._lock:
            if clean_key in self._accounts_by_key:
                acc = self._accounts_by_key[clean_key]
                return acc if acc.is_active else None

            # Try DB
            try:
                from backend.db import query

                row = query(
                    "SELECT id, user_id, company_name, plan_tier, total_credits, used_credits, "
                    "api_key, api_key_prefix, is_active, created_at, updated_at "
                    "FROM docuchat.company_accounts WHERE api_key = %s",
                    (clean_key,),
                    one=True,
                )
                if row and row["is_active"]:
                    account = CompanyAccount(
                        id=str(row["id"]),
                        user_id=str(row["user_id"]),
                        company_name=row["company_name"],
                        plan_tier=row["plan_tier"],
                        total_credits=int(row["total_credits"]),
                        used_credits=int(row["used_credits"]),
                        api_key=row["api_key"],
                        api_key_prefix=row["api_key_prefix"],
                        is_active=bool(row["is_active"]),
                        created_at=str(row["created_at"]),
                        updated_at=str(row["updated_at"]),
                    )
                    self._cache_account(account)
                    return account
            except Exception:
                pass

        return None

    def regenerate_api_key(self, user_id: str) -> CompanyAccount:
        """Roll a new API key for the company account."""
        account = self.get_or_create_company(user_id)
        with self._lock:
            old_key = account.api_key
            new_key = self._generate_raw_api_key()
            now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

            if old_key in self._accounts_by_key:
                del self._accounts_by_key[old_key]

            account.api_key = new_key
            account.api_key_prefix = new_key[:14]
            account.updated_at = now_iso

            # Update DB
            try:
                from backend.db import execute

                execute(
                    "UPDATE docuchat.company_accounts SET api_key = %s, api_key_prefix = %s, updated_at = now() WHERE id = %s",
                    (new_key, new_key[:14], account.id),
                )
            except Exception:
                pass

            self._cache_account(account)
            return account

    def update_workspace_name(self, user_id: str, new_name: str) -> CompanyAccount:
        """Update the workspace display name for a user's account."""
        account = self.get_or_create_company(user_id)
        with self._lock:
            account.company_name = new_name.strip()
            now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            account.updated_at = now_iso
            try:
                from backend.db import execute

                execute(
                    "UPDATE docuchat.company_accounts SET company_name = %s, updated_at = now() WHERE user_id = %s",
                    (account.company_name, str(user_id)),
                )
            except Exception:
                pass
            self._cache_account(account)
            return account

    GUARDIAN_CREDIT_FEE: int = 5

    def get_service_cost(
        self,
        service_name: str,
        model_id: Optional[str] = None,
        guardian: bool = True,
        model: Optional[str] = None,
    ) -> int:
        """Get the required credits cost for a given service, factoring in chosen model and Guardian verification.
        
        When guardian is True, the Guardian runs full evidence and rule validation and takes credit.
        When guardian is False, the service returns values directly and bypasses the Guardian fee.
        """
        if model and not model_id:
            model_id = model
        info = SERVICE_PRICING.get(service_name)
        base_cost = info["credits"] if info else 10
        total_cost = base_cost
        if model_id is not None:
            try:
                from backend.models_config import model_registry

                calc = model_registry.calculate_service_cost(base_cost, model_id)
                total_cost = calc["total_credits"]
            except Exception:
                total_cost = base_cost

        # If Guardian is disabled (direct value return mode), discount the guardian fee (except OCR)
        if not guardian and service_name != "advanced_ocr":
            discount = min(self.GUARDIAN_CREDIT_FEE, max(0, total_cost - 1))
            total_cost = max(1, total_cost - discount)

        return total_cost

    def check_and_deduct_credits(
        self,
        account: CompanyAccount,
        service_name: str,
        document_id: Optional[str] = None,
        request_summary: Optional[str] = None,
        model_id: Optional[str] = None,
        guardian: bool = True,
    ) -> int:
        """Atomically verify and deduct credits for a service call.

        Raises:
            InsufficientCreditsError: if remaining credits < service cost.

        Returns:
            int: Remaining credits after deduction.
        """
        cost = self.get_service_cost(service_name, model_id=model_id, guardian=guardian)
        with self._lock:
            remaining = account.remaining_credits
            if remaining < cost:
                raise InsufficientCreditsError(required=cost, remaining=remaining)

            account.used_credits += cost
            now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            account.updated_at = now_iso

            # Update DB
            try:
                from backend.db import execute

                execute(
                    "UPDATE docuchat.company_accounts SET used_credits = used_credits + %s, updated_at = now() WHERE id = %s",
                    (cost, account.id),
                )
            except Exception:
                pass

            # Log usage
            log_id = str(uuid.uuid4())
            log_entry = UsageLog(
                id=log_id,
                company_id=account.id,
                service_name=service_name,
                credits_cost=cost,
                remaining_balance=account.remaining_credits,
                document_id=document_id,
                request_summary=request_summary,
                status="success",
                created_at=now_iso,
            )

            if account.id not in self._usage_logs:
                self._usage_logs[account.id] = []
            self._usage_logs[account.id].insert(0, log_entry)

            # Persist log to DB
            try:
                from backend.db import execute

                execute(
                    "INSERT INTO docuchat.api_usage_logs (id, company_id, service_name, credits_cost, document_id, request_summary, status) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (log_id, account.id, service_name, cost, document_id, request_summary, "success"),
                )
            except Exception:
                pass

            return account.remaining_credits

    def refund_credits(
        self,
        account: CompanyAccount,
        service_name: str,
        credits_to_refund: Optional[int] = None,
        document_id: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> int:
        """Atomically refund credits for a failed or degraded service execution.

        Returns:
            int: Remaining credits balance after refund.
        """
        cost = credits_to_refund if credits_to_refund is not None else self.get_service_cost(service_name)
        with self._lock:
            # Revert used credits, capped at 0
            account.used_credits = max(0, account.used_credits - cost)
            now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            account.updated_at = now_iso

            # Update DB
            try:
                from backend.db import execute

                execute(
                    "UPDATE docuchat.company_accounts SET used_credits = %s, updated_at = now() WHERE id = %s",
                    (account.used_credits, account.id),
                )
            except Exception:
                pass

            # Log refund transaction
            log_id = str(uuid.uuid4())
            log_entry = UsageLog(
                id=log_id,
                company_id=account.id,
                service_name=service_name,
                credits_cost=-cost,
                remaining_balance=account.remaining_credits,
                document_id=document_id,
                request_summary=f"REFUND: {reason or 'Service execution failure'}",
                status="refunded",
                created_at=now_iso,
            )

            if account.id not in self._usage_logs:
                self._usage_logs[account.id] = []
            self._usage_logs[account.id].insert(0, log_entry)

            # Persist log to DB
            try:
                from backend.db import execute

                execute(
                    "INSERT INTO docuchat.api_usage_logs (id, company_id, service_name, credits_cost, document_id, request_summary, status) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (
                        log_id,
                        account.id,
                        service_name,
                        -cost,
                        document_id,
                        f"REFUND: {reason or 'Service execution failure'}",
                        "refunded",
                    ),
                )
            except Exception:
                pass

            return account.remaining_credits

    def get_service_status(self) -> Dict[str, Any]:
        """Return operational status and metadata for all Document AI services."""
        return {
            service_id: {
                "name": info["name"],
                "status": "operational",
                "credits": info["credits"],
                "tier": info["llm_tier"],
                "category": info["category"],
            }
            for service_id, info in SERVICE_PRICING.items()
        }

    def get_usage_logs(self, account_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent usage transactions for a company account."""
        with self._lock:
            # Check DB
            try:
                from backend.db import query

                rows = query(
                    "SELECT id, company_id, service_name, credits_cost, document_id, request_summary, status, created_at "
                    "FROM docuchat.api_usage_logs WHERE company_id = %s ORDER BY created_at DESC LIMIT %s",
                    (account_id, limit),
                )
                if rows:
                    return [
                        {
                            "id": str(r["id"]),
                            "serviceName": r["service_name"],
                            "creditsCost": int(r["credits_cost"]),
                            "documentId": str(r["document_id"]) if r["document_id"] else None,
                            "requestSummary": r["request_summary"],
                            "status": r["status"],
                            "createdAt": r["created_at"].isoformat()
                            if hasattr(r["created_at"], "isoformat")
                            else str(r["created_at"]),
                        }
                        for r in rows
                    ]
            except Exception:
                pass

            # In-memory fallback
            logs = self._usage_logs.get(account_id, [])[:limit]
            return [
                {
                    "id": entry.id,
                    "serviceName": entry.service_name,
                    "creditsCost": entry.credits_cost,
                    "documentId": entry.document_id,
                    "requestSummary": entry.request_summary,
                    "status": entry.status,
                    "createdAt": entry.created_at,
                }
                for entry in logs
            ]


# Global singleton instance
billing_service = CompanyBillingService()
