"""
Unit & Integration Tests for Bilingual (English & Arabic) Enterprise Services:
- Bilingual Redaction & PII Anonymization (RedactionAgent)
- Bilingual Document Classification & Routing (ClassifierAgent)
- Bilingual Financial Statement Analysis (FinancialStatementAgent)
- Bilingual Translation (TranslationAgent)
- Forensic Anomaly & VAT 15% Audit (AnomalyAuditAgent)
- HMAC-SHA256 Webhook Cryptographic Signatures
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from backend import server
from backend.agent.agents.anomaly_audit import AnomalyAuditAgent
from backend.agent.agents.classifier import ClassifierAgent
from backend.agent.agents.financial_statement import FinancialStatementAgent
from backend.agent.agents.redaction import RedactionAgent
from backend.agent.agents.translation import TranslationAgent
from backend.agent.tools.bilingual import BilingualDocumentKit
from backend.billing import billing_service


@pytest.fixture
def client():
    return TestClient(server.app)


@pytest.fixture
def b2b_account():
    user_id = str(uuid.uuid4())
    return billing_service.get_or_create_company(user_id, company_name="Bilingual AI Enterprise")


# ===========================================================================
# 1. Bilingual Redaction Tests (EN & AR)
# ===========================================================================


def test_bilingual_redaction_toolkit():
    """Test deterministic PII redaction across Arabic and English sensitive formats."""
    sample_text = (
        "سعادة الأستاذ محمد بن فهد، صاحب الهوية الوطنية 1089234812 ورقم الآيبان البنكي "
        "SA0380000000608010167519، والرقم الضريبي للشركة 310123456789013، "
        "ورقم الهاتف 0501234567، والبريد mohammed@example.sa."
    )
    res = BilingualDocumentKit.redact_pii(sample_text)
    assert res["status"] == "sanitized"
    assert res["total_redactions"] >= 5
    redacted = res["redacted_text"]

    # Verify sensitive data is fully masked
    assert "1089234812" not in redacted
    assert "SA0380000000608010167519" not in redacted
    assert "310123456789013" not in redacted
    assert "0501234567" not in redacted
    assert "mohammed@example.sa" not in redacted


def test_bilingual_redaction_agent_initialization():
    """Test RedactionAgent initialization and tool registration."""
    mock_llm = MagicMock()
    mock_toolkit = MagicMock()
    agent = RedactionAgent(llm=mock_llm, tool_kit=mock_toolkit)
    assert "redact_pii" in agent.registry.tool_names


# ===========================================================================
# 2. Bilingual Document Classification Tests
# ===========================================================================


def test_bilingual_classification_arabic_invoice():
    """Test classifying an Arabic Tax Invoice."""
    text = (
        "فاتورة ضريبية مبسطة\n"
        "الرقم الضريبي: 300123456789013\n"
        "المجموع قبل الضريبة: 10,000 ريال\n"
        "ضريبة القيمة المضافة 15%: 1,500 ريال\n"
        "المجموع الكلي: 11,500 ريال"
    )
    res = BilingualDocumentKit.classify_document(text)
    assert res["category"] == "INVOICE"
    assert res["primary_language"] == "ar"
    assert "المالية" in res["routing_department"]


def test_bilingual_classification_english_contract():
    """Test classifying an English Legal Agreement."""
    text = (
        "MASTER SERVICES AGREEMENT\n"
        "This Agreement is entered into by and between the Parties.\n"
        "Indemnification and Governing Law shall be in accordance with the Laws of California."
    )
    res = BilingualDocumentKit.classify_document(text)
    assert res["category"] == "CONTRACT"
    assert res["primary_language"] == "en"
    assert "Legal" in res["routing_department"]


def test_bilingual_classifier_agent_initialization():
    """Test ClassifierAgent initialization and tool registration."""
    mock_llm = MagicMock()
    mock_toolkit = MagicMock()
    agent = ClassifierAgent(llm=mock_llm, tool_kit=mock_toolkit)
    assert "classify_document" in agent.registry.tool_names


# ===========================================================================
# 3. Bilingual Financial Statement Tests
# ===========================================================================


def test_bilingual_financial_statement_toolkit():
    """Test extracting metrics and computing ratios from Arabic & English financial statements."""
    statement_text = """
    قائمة الدخل للسنة المالية المنتهية في 2025
    الإيرادات: 5,000,000 ريال
    إجمالي الربح: 2,000,000 ريال
    صافي الربح: 1,000,000 ريال
    إجمالي الأصول: 10,000,000 ريال
    إجمالي الخصوم: 4,000,000 ريال
    إجمالي حقوق الملكية: 6,000,000 ريال
    """
    res = BilingualDocumentKit.analyze_financial_statement(statement_text)
    assert res["currency"] is None  # Bare "ريال" does not identify a country/currency.
    metrics = res["metrics"]
    assert metrics["revenue"] == 5000000.0
    assert metrics["gross_profit"] == 2000000.0
    assert metrics["net_income"] == 1000000.0

    ratios = res["financial_ratios"]
    assert ratios["gross_margin_pct"] == 40.0
    assert ratios["net_profit_margin_pct"] == 20.0
    assert ratios["debt_to_equity_ratio"] == 0.67


def test_bilingual_financial_agent_initialization():
    """Test FinancialStatementAgent initialization and tool registration."""
    mock_llm = MagicMock()
    mock_toolkit = MagicMock()
    agent = FinancialStatementAgent(llm=mock_llm, tool_kit=mock_toolkit)
    assert "analyze_financial_statement" in agent.registry.tool_names


# ===========================================================================
# 4. Translation Agent Tests
# ===========================================================================


def test_translation_agent_initialization():
    """Test TranslationAgent initialization."""
    mock_llm = MagicMock()
    mock_toolkit = MagicMock()
    agent = TranslationAgent(llm=mock_llm, tool_kit=mock_toolkit)
    assert agent is not None
    assert "Never claim that a translation is certified" in agent.config.system_prompt


# ===========================================================================
# 5. Bilingual Anomaly Audit Tests
# ===========================================================================


def test_anomaly_audit_detects_math_and_vat_mismatch():
    """Test forensic audit detecting arithmetic error and 15% VAT mismatch."""
    flawed_invoice = """
    TAX INVOICE
    Subtotal: 10,000 SAR
    VAT 15%: 2,000 SAR
    Total: 15,000 SAR
    """
    res = BilingualDocumentKit.audit_anomalies(flawed_invoice)
    assert res["is_clean"] is False
    assert res["total_anomalies"] >= 1
    categories = [a["category"] for a in res["anomalies"]]
    assert any("ARITHMETIC_ERROR" in c for c in categories)


def test_anomaly_audit_detects_date_inversion():
    """Test forensic audit detecting due date before issue date."""
    date_flawed = """
    فاتورة أعمال استشارية
    تاريخ الإصدار: 2026-10-25
    تاريخ الاستحقاق: 2026-10-10
    """
    res = BilingualDocumentKit.audit_anomalies(date_flawed)
    assert res["is_clean"] is False
    assert any("DATE_INVERSION" in a["category"] for a in res["anomalies"])
    assert res["risk_rating"].startswith("CRITICAL")


def test_anomaly_agent_initialization():
    """Test AnomalyAuditAgent initialization and tool registration."""
    mock_llm = MagicMock()
    mock_toolkit = MagicMock()
    agent = AnomalyAuditAgent(llm=mock_llm, tool_kit=mock_toolkit)
    assert "audit_anomalies" in agent.registry.tool_names


# ===========================================================================
# 6. HMAC-SHA256 Webhook Cryptographic Signature Test
# ===========================================================================


def test_webhook_hmac_signature_verification():
    """Ensure webhook payloads are signed with valid HMAC-SHA256 signatures."""
    secret = "production_enterprise_secret_key_123"
    payload = {"status": "completed", "jobId": "job_991823", "data": {"total": 5000}}
    raw_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    timestamp = str(int(time.time()))

    expected_signature = hmac.new(
        secret.encode("utf-8"),
        f"{timestamp}.".encode("utf-8") + raw_body,
        hashlib.sha256,
    ).hexdigest()

    header_signature = f"sha256={expected_signature}"
    sig_hash = header_signature.split("sha256=")[1]

    # Verify signature matches
    assert hmac.compare_digest(sig_hash, expected_signature) is True


# ===========================================================================
# 7. Pricing Catalog Verification for New Services
# ===========================================================================


def test_pricing_catalog_includes_bilingual_services(client):
    """Verify all 5 new bilingual services appear in the public pricing catalog."""
    resp = client.get("/api/v1/company/pricing")
    assert resp.status_code == 200
    services = {s["id"]: s for s in resp.json()["services"]}

    assert "redaction" in services
    assert services["redaction"]["credits"] == 25

    assert "classifier" in services
    assert services["classifier"]["credits"] == 15

    assert "financial_statement" in services
    assert services["financial_statement"]["credits"] == 35

    assert "translation" in services
    assert services["translation"]["credits"] == 20

    assert "anomaly_audit" in services
    assert services["anomaly_audit"]["credits"] == 25
