"""Behavioral coverage for validated document services. No model or network calls."""

from __future__ import annotations

import copy
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.agent.agents.base import AgentResult
from backend.agent.tools.bilingual import BilingualDocumentKit
from backend.billing import SERVICE_PRICING, CompanyAccount
from backend.documents.pdf_loader import PageText, PDFDocument
from backend.services import engine, idempotency
from backend.services.contracts import OutputValidationError, compile_override, prepare_data
from backend.services.evidence import SourcePage, attach_evidence
from backend.services.finance import extract_financial_fields, financial_checks, financial_ratios
from backend.services.models import DocumentRule, FinancialOptions, ServiceRequest, TranslationOptions
from backend.services.normalization import decimal_value, detect_currency, normalize_date
from backend.services.rules import evaluate_rules
from backend.services.workflows import compare_contracts, match_invoice, translation_checks
from backend.v1 import routes


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("١٬٢٣٤٫٥٠", "1234.50"),
        ("۱٬۲۳۴٫۵۰", "1234.50"),
        ("(1,250.25 SAR)", "-1250.25"),
        ("0", "0"),
        ("١٢٣٫٤٥", "123.45"),
        ("-42.10", "-42.10"),
    ],
)
def test_decimal_arabic_and_negative(raw, expected):
    assert decimal_value(raw) == Decimal(expected)


@pytest.mark.parametrize("raw", ["1,25", "12,34,567", "invoice 100", "NaN", True, "1e3", "100 and 200"])
def test_decimal_does_not_guess(raw):
    assert decimal_value(raw) is None


def test_ambiguous_dates_and_nonlexical_order():
    assert normalize_date("٠٣/٠٤/٢٠٢٦") == (None, "ambiguous_date_order")
    assert normalize_date("03/04/2026", "DMY")[0] == "2026-04-03"
    assert normalize_date("03/04/2026", "MDY")[0] == "2026-03-04"
    assert normalize_date("2026-02-30")[1] == "invalid_date"
    report = financial_checks(
        {"invoice_date": "30/01/2026", "due_date": "02/02/2026"}, FinancialOptions(date_order="DMY")
    )
    assert next(check for check in report["checks"] if check["check"] == "date_order")["status"] == "passed"


def test_currency_not_assumed_and_zero_ratios_retained():
    assert detect_currency("Revenue: 500") is None
    assert detect_currency("SAR 100 and USD 100") is None
    result = BilingualDocumentKit.analyze_financial_statement(
        "Revenue: 100\nNet income: 0\nTotal liabilities: 0\nEquity: 50"
    )
    assert result["currency"] is None
    assert result["financial_ratios"]["net_profit_margin_pct"] == 0
    assert result["financial_ratios"]["debt_to_equity_ratio"] == 0
    assert financial_ratios({"net_income": 5, "revenue": 0})["net_profit_margin_pct"]["value"] is None


def test_financial_labels_tax_and_discount():
    fields = extract_financial_fields(
        "Subtotal: SAR 1,000.00\nDiscount: SAR 100.00\nVAT 20%: SAR 180.00\nTotal: SAR 1,080.00"
    )
    assert fields["total"] == 1080  # never match subtotal as total
    assert fields["tax_rate"] == Decimal(".2")
    result = financial_checks(fields)
    assert next(row for row in result["checks"] if row["check"] == "tax")["status"] == "passed"
    assert result["status"] == "passed"
    assert (
        financial_checks({"subtotal": 100, "tax_total": 10, "total": 110})["checks"][1]["reason"]
        == "tax_rate_not_provided"
    )
    assert financial_checks({}, FinancialOptions())["status"] == "insufficient_data"
    inclusive = financial_checks(
        {"subtotal": 120, "tax_total": 20, "total": 120}, FinancialOptions(tax_rate=".2", tax_inclusive=True)
    )
    assert inclusive["status"] == "passed"


def test_arabic_financial_text_no_default_tax():
    report = BilingualDocumentKit.audit_anomalies(
        "المجموع قبل الضريبة: ١٠٠\nضريبة القيمة المضافة ٢٠%: ٢٠\nالمجموع الكلي: ١٢٠"
    )
    assert report["is_clean"]
    assert BilingualDocumentKit.audit_anomalies("There are no amounts here")["is_clean"] is False


def test_schema_aliases_nulls_and_invalid_types():
    data, original = prepare_data(
        "invoice", {"vendor": "Acme", "total_amount": "١٠٠٫٥٠", "issue_date": "03/04/2026"}, "Acme ١٠٠٫٥٠"
    )
    assert data["total"] == 100.5
    assert data["invoice_date"] is None
    assert original["invoice_date:reason"] == "ambiguous_date_order"
    assert data["client"] is None
    with pytest.raises(OutputValidationError):
        prepare_data("invoice", {"total": "not a number"}, "source")
    with pytest.raises(OutputValidationError):
        prepare_data("invoice", {"vendor": False}, "source")
    with pytest.raises(ValueError):
        compile_override({"$ref": "https://example.test/schema"})


def test_field_evidence_preserves_original_and_rejects_unsourced_value():
    data, original = prepare_data("invoice", {"vendor": "Acme", "total": "١٠٠٫٥٠", "invoice_number": "INVENTED"}, "")
    rows = attach_evidence(data, [SourcePage("doc", "invoice.pdf", 2, "Vendor: Acme\nTotal: ١٠٠٫٥٠")], original)
    assert data["invoice_number"] is None
    total = next(row for row in rows if row["field"] == "total")
    assert total["originalValue"] == "١٠٠٫٥٠"
    assert total["sources"][0] == {"documentId": "doc", "document": "invoice.pdf", "page": 2, "quote": "Total: ١٠٠٫٥٠"}
    assert next(row for row in rows if row["field"] == "invoice_number")["reason"] == "not_found_in_source"


def test_translation_checks_numbers_names_and_glossary():
    options = TranslationOptions(
        source_language="en", target_language="ar", glossary={"invoice": "فاتورة"}, preserve_names=["Acme"]
    )
    good = translation_checks("Acme invoice 1: SAR 100.00", "Acme فاتورة ١: SAR ١٠٠٫٠٠", options)
    assert good["status"] == "passed"
    bad = translation_checks("Acme invoice 1: SAR 100", "فاتورة ١: SAR ٢٠٠", options)
    assert {row["check"] for row in bad["issues"]} == {"numbers_and_numbering", "preserved_name"}
    with pytest.raises(ValidationError):
        TranslationOptions(source_language="ar", target_language="ar")


def test_configurable_required_and_approval_rules():
    rules = [
        DocumentRule(field="invoice_number", operator="required"),
        DocumentRule(field="total", operator="lte", value=500),
        DocumentRule(field="currency", operator="in", value=["SAR", "USD"]),
    ]
    assert evaluate_rules({"invoice_number": "I-1", "total": 400, "currency": "SAR"}, rules)["status"] == "passed"
    assert evaluate_rules({"total": 600, "currency": "SAR"}, rules)["status"] == "rejected"
    assert (
        evaluate_rules({"total": None}, [DocumentRule(field="total", operator="neq", value=0)])["status"] == "rejected"
    )
    with pytest.raises(ValidationError):
        DocumentRule(field="total", operator="lte", value="foo")


def test_contract_version_changes_include_both_sources():
    old = [SourcePage("old", "v1.txt", 1, "Article 1\nThe buyer shall pay USD 100 by 2026-01-01.\nUnchanged clause.")]
    new = [SourcePage("new", "v2.txt", 2, "Article 1\nThe buyer shall pay USD 150 by 2026-02-01.\nUnchanged clause.")]
    result = compare_contracts(old, new)
    assert result["change_count"] == 1
    assert set(result["changes"][0]["categories"]) == {
        "clause_text",
        "amounts_or_payment",
        "dates_or_terms",
        "obligations",
    }
    assert result["changes"][0]["beforeSources"][0]["documentId"] == "old"
    assert result["changes"][0]["afterSources"][0]["page"] == 2
    assert compare_contracts(old, old)["status"] == "unchanged"


def test_invoice_matching_no_silent_missing_or_duplicate_items():
    invoice = {
        "currency": "SAR",
        "po_number": "PO1",
        "total": 100,
        "line_items": [{"description": "Paper", "quantity": 2, "unit_price": 50, "amount": 100}],
    }
    assert match_invoice(invoice, invoice, FinancialOptions())["status"] == "matched"
    order = copy.deepcopy(invoice)
    order["line_items"][0]["quantity"] = 3
    assert match_invoice(invoice, order, FinancialOptions())["status"] == "needs_review"
    order["line_items"].append(copy.deepcopy(order["line_items"][0]))
    assert match_invoice(invoice, order, FinancialOptions())["differences"][0]["reason"] == "duplicate_identifier"


class MemoryLedger:
    """Test double for the durable ledger, including concurrent pending operations."""

    def __init__(self):
        self.rows = {}
        self.rules = {}
        self.lock = threading.Lock()

    def claim(self, company, key, fingerprint):
        with self.lock:
            row = self.rows.get((company, key))
            if row:
                if row["fingerprint"] != fingerprint:
                    raise HTTPException(409, "Different parameters")
                if row["body"] is None:
                    raise HTTPException(409, "In progress")
                return {"body": row["body"], "status_code": row["code"]}
            self.rows[company, key] = {"fingerprint": fingerprint, "body": None}

    def complete(self, company, key, body, status_code=200):
        with self.lock:
            self.rows[company, key].update(body=copy.deepcopy(body), code=status_code)

    def get_rules(self, company, rule_id):
        row = self.rules.get((company, rule_id))
        if row is None:
            raise HTTPException(404, "Rule set not found")
        return row


@pytest.fixture
def runtime(monkeypatch):
    account = CompanyAccount("company-a", "user-a", "Test", "trial", 1200, 0, "key", "key", True, "", "")
    ledger = MemoryLedger()
    state = SimpleNamespace(
        account=account,
        ledger=ledger,
        charges=0,
        refunds=0,
        calls=0,
        result={
            "vendor": "Acme",
            "invoice_number": "I-1",
            "subtotal": 100,
            "tax_total": 20,
            "tax_rate": ".2",
            "total": 120,
        },
        text="Vendor: Acme\nInvoice: I-1\nSubtotal: 100\nVAT 20%: 20\nTotal: 120\nCurrency: SAR",
    )

    def bundle(text, name="source.txt"):
        return SimpleNamespace(
            doc_id="memory-doc",
            vector_store=object(),
            pdf_docs=[PDFDocument(name=name, pages=[PageText(1, text, name, 1)])],
        )

    state.bundle = bundle
    monkeypatch.setattr(engine.rag, "create_text_bundle", lambda text, name: bundle(text, name))

    def charge(account, service, **kwargs):
        state.charges += 1
        account.used_credits += SERVICE_PRICING[service]["credits"]
        return account.remaining_credits

    def refund(account, service, amount=None, *args, **kwargs):
        state.refunds += 1
        account.used_credits -= amount or SERVICE_PRICING[service]["credits"]
        return account.remaining_credits

    def build(*args, **kwargs):
        def run(prompt):
            state.calls += 1
            state.prompt = prompt
            raw = state.result if isinstance(state.result, str) else json.dumps(state.result, ensure_ascii=False)
            return AgentResult(raw)

        return SimpleNamespace(run=run)

    monkeypatch.setattr(engine.billing_service, "check_and_deduct_credits", charge)
    monkeypatch.setattr(engine.billing_service, "refund_credits", refund)
    monkeypatch.setattr(engine.rag, "_build_agent", build)
    monkeypatch.setattr(idempotency, "operation_store", ledger)
    monkeypatch.setattr(engine, "operation_store", ledger)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.get_company_or_api_auth] = lambda: account
    state.client = TestClient(app)
    return state


def test_pipeline_validates_and_exposes_evidence(runtime):
    response = runtime.client.post("/api/v1/pipeline/run", json={"text_content": runtime.text, "service": "invoice"})
    assert response.status_code == 200
    body = response.json()
    assert body["success"], body
    assert body["data"]["total"] == 120
    assert body["data"]["client"] is None
    assert body["creditsDeducted"] == 25
    assert body["guardianEnabled"] is True
    assert body["guardianCreditCost"] == 5
    assert body["checks"]["financial"]["status"] == "passed"
    assert next(row for row in body["fieldEvidence"] if row["field"] == "total")["sources"][0]["page"] == 1


def test_pipeline_direct_return_mode_bypasses_evidence_and_validation(runtime):
    # Model returns hallucinated values not present in source text
    runtime.result = {"vendor": "Hallucinated Vendor LLC", "total": "9999.99"}
    # With guardian=False (Direct Return Mode)
    response = runtime.client.post(
        "/api/v1/pipeline/run",
        json={"text_content": runtime.text, "service": "invoice", "guardian": False},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["guardianEnabled"] is False
    assert body["guardianCreditCost"] == 0
    # Values are returned directly without being nullified by evidence matching
    assert body["data"]["vendor"] == "Hallucinated Vendor LLC"
    assert body["data"]["total"] == "9999.99"
    assert body["guardian"]["mode"] == "direct_return"


@pytest.mark.parametrize("bad", ["Not JSON", {"vendor": False, "total": 120}, {"unexpected": "value"}])
def test_invalid_output_refunded_once(runtime, bad):
    runtime.result = bad
    body = runtime.client.post("/api/v1/pipeline/run", json={"text_content": runtime.text, "service": "invoice"}).json()
    assert body["success"] is False
    assert body["data"] is None
    assert body["creditsDeducted"] == 0
    assert runtime.charges == runtime.refunds == 1
    assert runtime.account.remaining_credits == 1200


def test_idempotent_replay_conflict_and_failed_result(runtime):
    payload = {"text_content": runtime.text, "service": "invoice"}
    headers = {"Idempotency-Key": "invoice-1"}
    first = runtime.client.post("/api/v1/pipeline/run", json=payload, headers=headers)
    second = runtime.client.post("/api/v1/pipeline/run", json=payload, headers=headers)
    assert second.json() == first.json()
    assert second.headers["X-Idempotency-Replayed"] == "true"
    assert runtime.charges == runtime.calls == 1
    conflict = runtime.client.post("/api/v1/pipeline/run", json={**payload, "query": "different"}, headers=headers)
    assert conflict.status_code == 409
    runtime.result = "bad"
    headers = {"Idempotency-Key": "failed-1"}
    first = runtime.client.post("/api/v1/pipeline/run", json=payload, headers=headers)
    runtime.client.post("/api/v1/pipeline/run", json=payload, headers=headers)
    assert first.json()["success"] is False
    assert runtime.charges == 2 and runtime.refunds == 1


def test_override_enforced_and_remote_schema_rejected_without_charge(runtime):
    schema = {"type": "object", "required": ["missing"], "properties": {"missing": {"type": "number"}}}
    body = runtime.client.post(
        "/api/v1/pipeline/run", json={"text_content": runtime.text, "service": "invoice", "schema_override": schema}
    ).json()
    assert body["success"] is False
    response = runtime.client.post(
        "/api/v1/pipeline/run",
        json={"text_content": runtime.text, "service": "invoice", "schema_override": {"$ref": "https://example.test"}},
    )
    assert response.status_code == 422
    assert runtime.charges == 1


def test_translator_rejects_changed_amount_and_receives_options(runtime):
    runtime.result = {"translated_text": "Acme فاتورة ١: SAR ٢٠٠", "terminology_notes": []}
    response = runtime.client.post(
        "/api/v1/pipeline/run",
        json={
            "service": "translation",
            "text_content": "Acme invoice 1: SAR 100",
            "options": {
                "translation": {
                    "source_language": "en",
                    "target_language": "ar",
                    "glossary": {"invoice": "فاتورة"},
                    "preserve_names": ["Acme"],
                }
            },
        },
    )
    assert response.json()["success"] is False
    assert "glossary" in runtime.prompt
    assert runtime.refunds == 1


def test_document_checks_rules_and_tenant_rule_set(runtime):
    runtime.result = {"total": 120, "invoice_number": "I-1"}
    runtime.ledger.rules["company-a", "rule-1"] = {"rules": [{"field": "total", "operator": "lte", "value": 100}]}
    response = runtime.client.post(
        "/api/v1/pipeline/run",
        json={"service": "document_checks", "text_content": runtime.text, "options": {"rule_set_id": "rule-1"}},
    )
    assert response.json()["success"]
    assert response.json()["checks"]["rules"]["status"] == "rejected"
    runtime.account.id = "company-b"
    response = runtime.client.post(
        "/api/v1/pipeline/run",
        json={"service": "document_checks", "text_content": runtime.text, "options": {"rule_set_id": "rule-1"}},
    )
    assert response.status_code == 404
    assert runtime.charges == 1


def test_reference_document_authorization_before_billing(runtime, monkeypatch):
    monkeypatch.setattr(engine.ephemeral_store, "get_and_touch", lambda _: None)
    monkeypatch.setattr(engine, "query", lambda *args, **kwargs: None)
    response = runtime.client.post(
        "/api/v1/pipeline/run",
        json={
            "service": "contract_comparison",
            "text_content": "old",
            "options": {"reference_document_id": "other-tenant"},
        },
    )
    assert response.status_code == 404
    assert runtime.charges == 0


def test_contract_comparison_endpoint(runtime):
    response = runtime.client.post(
        "/api/v1/pipeline/run",
        json={
            "service": "contract_comparison",
            "text_content": "Pay USD 10.",
            "options": {"reference_text": "Pay USD 20."},
        },
    )
    assert response.json()["data"]["change_count"] == 1
    assert runtime.calls == 0  # exact comparison does not need a model


def test_invoice_matching_endpoint(runtime):
    runtime.result = {
        "vendor": "Acme",
        "currency": "SAR",
        "po_number": "PO1",
        "total": 100,
        "line_items": [{"description": "Paper", "quantity": 2, "unit_price": 50, "amount": 100}],
    }
    text = "Acme SAR PO1\nPaper 2 50 100\nTotal: 100"
    response = runtime.client.post(
        "/api/v1/pipeline/run",
        json={"service": "invoice_matching", "text_content": text, "options": {"reference_text": text}},
    )
    assert response.json()["success"], response.json()
    assert response.json()["data"]["status"] == "matched"
    assert runtime.charges == 1 and runtime.calls == 2


def test_custom_schema_replaces_builtin_without_extra_fields(runtime):
    runtime.result = {"amount_due": 120}
    schema = {
        "type": "object",
        "properties": {"amount_due": {"type": "number"}},
        "required": ["amount_due"],
        "additionalProperties": False,
    }
    body = runtime.client.post(
        "/api/v1/pipeline/run", json={"service": "invoice", "text_content": runtime.text, "schema_override": schema}
    ).json()
    assert body["success"], body
    assert body["data"] == {"amount_due": 120}
    assert body["validation"]["schemaValidated"] is True


def test_decimal_calculations_keep_large_cent_amounts(runtime):
    runtime.result = '{"subtotal": 9007199254740993.01, "tax_total": 0.00, "total": 9007199254740993.02}'
    body = engine.execute_service(
        ServiceRequest(
            service="invoice",
            text_content="Subtotal: 9007199254740993.01\nTax: 0.00\nTotal: 9007199254740993.02",
            options={"financial": {"tax_rate": 0, "tolerance": 0}},
        ),
        runtime.account,
    )
    assert body["success"]
    check = next(row for row in body["checks"]["financial"]["checks"] if row["check"] == "document_total")
    assert check["status"] == "failed" and check["difference"] == 0.01
    assert body["data"]["subtotal"] == Decimal("9007199254740993.01")


def test_concurrent_http_duplicate_never_executes_twice(runtime, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    execute = routes.execute_service

    def slow(request, account):
        entered.set()
        assert release.wait(5)
        return execute(request, account)

    monkeypatch.setattr(routes, "execute_service", slow)
    payload = {"service": "invoice", "text_content": runtime.text}
    headers = {"Idempotency-Key": "concurrent"}
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(runtime.client.post, "/api/v1/pipeline/run", json=payload, headers=headers)
        try:
            assert entered.wait(5)
            second = runtime.client.post("/api/v1/pipeline/run", json=payload, headers=headers)
            assert second.status_code == 409
        finally:
            release.set()
        assert first.result().json()["success"]
    assert runtime.charges == runtime.calls == 1


def test_batch_idempotency_and_options(runtime):
    payload = {
        "tasks": [
            {
                "service": "invoice",
                "text_content": runtime.text,
                "options": {"rules": [{"field": "total", "operator": "lte", "value": 100}]},
            }
        ]
    }
    headers = {"Idempotency-Key": "batch-1"}
    first = runtime.client.post("/api/v1/pipeline/batch", json=payload, headers=headers)
    second = runtime.client.post("/api/v1/pipeline/batch", json=payload, headers=headers)
    assert first.json() == second.json()
    assert first.json()["results"][0]["checks"]["rules"]["status"] == "rejected"
    assert runtime.charges == 1


def test_queued_job_preserves_options_and_is_claimed_once(runtime, monkeypatch):
    from fastapi.encoders import jsonable_encoder

    from backend.jobs import worker
    from backend.jobs.queue import RedisJobQueue

    queue = RedisJobQueue()
    monkeypatch.setattr(queue, "_get_redis", lambda: None)
    monkeypatch.setattr(routes, "job_queue", queue)
    monkeypatch.setattr(worker, "job_queue", queue)
    monkeypatch.setattr(worker.billing_service, "get_company_by_id", lambda _: runtime.account)
    payload = {
        "service": "invoice",
        "text_content": runtime.text,
        "model": "configured-test-model",
        "options": {"financial": {"tax_rate": ".2"}, "rules": [{"field": "total", "operator": "lte", "value": 100}]},
    }
    first = runtime.client.post("/api/v1/pipeline/jobs", json=payload, headers={"Idempotency-Key": "job-1"})
    second = runtime.client.post("/api/v1/pipeline/jobs", json=payload, headers={"Idempotency-Key": "job-1"})
    assert first.status_code == second.status_code == 202
    assert first.json()["jobId"] == second.json()["jobId"]
    job = queue.get_job(first.json()["jobId"])
    assert job.request_payload["options"]["financial"]["tax_rate"] == "0.2"
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(worker.execute_job_task, [job] * 4))
    completed = queue.get_job(job.id)
    assert completed.status == "completed", completed.error
    assert completed.result["checks"]["rules"]["status"] == "rejected"
    assert completed.result["model"] == "configured-test-model"
    assert completed.request_payload is None
    assert runtime.charges == runtime.calls == 1
    polled = runtime.client.get(f"/api/v1/pipeline/jobs/{job.id}")
    assert polled.json()["result"]["data"]["total"] == 120
    sync = runtime.client.post("/api/v1/pipeline/run", json=payload).json()
    assert jsonable_encoder(completed.result["fieldEvidence"]) == sync["fieldEvidence"]
    assert completed.result["checks"] == sync["checks"]
    runtime.account.id = "different-company"
    assert runtime.client.get(f"/api/v1/pipeline/jobs/{job.id}").status_code == 404


def test_failed_worker_is_refunded_and_never_recharged(runtime, monkeypatch):
    from backend.jobs import worker
    from backend.jobs.queue import RedisJobQueue

    queue = RedisJobQueue()
    monkeypatch.setattr(queue, "_get_redis", lambda: None)
    monkeypatch.setattr(worker, "job_queue", queue)
    monkeypatch.setattr(worker.billing_service, "get_company_by_id", lambda _: runtime.account)
    runtime.result = "invalid output"
    job = queue.enqueue(
        "invoice",
        "",
        company_id=runtime.account.id,
        request_payload={"service": "invoice", "text_content": runtime.text},
    )
    worker.execute_job_task(job)
    worker.execute_job_task(job)
    assert queue.get_job(job.id).status == "failed"
    assert runtime.charges == runtime.refunds == 1
    assert runtime.account.remaining_credits == 1200


def test_playground_and_legacy_endpoints_share_validation(runtime, monkeypatch):
    from backend import server
    from backend.auth import get_current_user

    monkeypatch.setattr(server.billing_service, "get_or_create_company", lambda *args: runtime.account)
    monkeypatch.setattr(
        engine, "owned_bundle", lambda doc, account: (runtime.bundle(runtime.text, "invoice_text.txt"), None)
    )
    monkeypatch.setattr(server, "query", lambda *args, **kwargs: {"original_filename": "invoice.txt"})
    server.app.dependency_overrides[get_current_user] = lambda: {"id": "user-a", "name": "Test"}
    try:
        client = TestClient(server.app)
        payload = {"service": "invoice", "text_content": runtime.text}
        first = client.post("/api/playground/run", json=payload, headers={"Idempotency-Key": "playground-1"})
        second = client.post("/api/playground/run", json=payload, headers={"Idempotency-Key": "playground-1"})
        assert first.json() == second.json()
        assert first.json()["data"]["total"] == 120
        assert runtime.charges == 1
        legacy = client.post("/api/documents/doc-a/invoice", json={}).json()
        assert legacy["fieldEvidence"] == first.json()["fieldEvidence"]
        runtime.result = "invalid"
        failed = client.post("/api/documents/doc-a/invoice", json={}).json()
        assert failed["success"] is False and runtime.refunds == 1
    finally:
        server.app.dependency_overrides.clear()


def test_schema_rejects_unknown_fields(runtime):
    runtime.result["approval_status"] = "certified"
    body = runtime.client.post("/api/v1/pipeline/run", json={"service": "invoice", "text_content": runtime.text}).json()
    assert body["success"] is False and runtime.refunds == 1


def test_translation_success_preserves_configured_language_and_amounts(runtime):
    runtime.result = {"translated_text": "Acme فاتورة ١: SAR ١٠٠٫٠٠", "terminology_notes": []}
    response = runtime.client.post(
        "/api/v1/pipeline/run",
        json={
            "service": "translation",
            "text_content": "Acme invoice 1: SAR 100.00",
            "options": {
                "translation": {
                    "source_language": "en",
                    "target_language": "ar",
                    "glossary": {"invoice": "فاتورة"},
                    "preserve_names": ["Acme"],
                }
            },
        },
    )
    assert response.json()["success"], response.json()
    assert response.json()["checks"]["translation"]["status"] == "passed"
    assert runtime.refunds == 0


def test_translation_rejects_number_reordering_and_wrong_target_script():
    options = TranslationOptions(target_language="ar")
    reordered = translation_checks(
        "Article 1 amount 100; Article 2 amount 200", "المادة 2 مبلغ 200؛ المادة 1 مبلغ 100", options
    )
    assert any(row["check"] == "number_sequence" for row in reordered["issues"])
    untranslated = translation_checks("The invoice is due today", "The invoice is due today", options)
    assert any(row["check"] == "target_language" for row in untranslated["issues"])


def test_missing_matching_total_requires_review():
    invoice = {
        "currency": "SAR",
        "po_number": "PO1",
        "total": 100,
        "line_items": [{"description": "Paper", "quantity": 2, "unit_price": 50, "amount": 100}],
    }
    order = {**invoice, "total": None}
    result = match_invoice(invoice, order, FinancialOptions())
    assert result["status"] == "needs_review"
    assert any(row.get("field") == "total" and row.get("status") == "not_checked" for row in result["differences"])


def test_idle_worker_stops_cleanly():
    from backend.jobs.worker import start_background_worker

    stop = threading.Event()
    worker = start_background_worker(stop_check=stop.is_set)
    stop.set()
    worker.join(timeout=2)
    assert not worker.is_alive()


def test_checkbox_evidence_requires_the_marker_next_to_its_label():
    data = {
        "checkboxes": [
            {"label": "موافق", "checked": True},
            {"label": "Declined", "checked": False},
            {"label": "Unstated", "checked": True},
        ]
    }
    records = attach_evidence(data, [SourcePage("doc", "form.pdf", 1, "[X] موافق\nDeclined [ ]")], {})
    assert data["checkboxes"][0]["checked"] is True
    assert data["checkboxes"][1]["checked"] is False
    assert data["checkboxes"][2]["checked"] is None
    assert next(row for row in records if row["field"] == "checkboxes.0.checked")["sources"][0]["quote"] == "[X] موافق"


@pytest.mark.parametrize(
    "text",
    [
        '{"amount_due": NaN}',
        '{"amount_due": Infinity}',
        '{"amount_due": -Infinity}',
        '{"bad": NaN, "nested": {"amount_due": 120}}',
    ],
)
def test_invalid_json_constants_are_not_salvaged(runtime, text):
    runtime.result = text
    schema = {"type": "object", "properties": {"amount_due": {"type": "number"}}, "required": ["amount_due"]}
    body = runtime.client.post(
        "/api/v1/pipeline/run", json={"service": "invoice", "text_content": runtime.text, "schema_override": schema}
    ).json()
    assert body["success"] is False and runtime.refunds == 1


def test_json_schema_without_type_is_enforced(runtime):
    runtime.result = {"total": 120}
    body = runtime.client.post(
        "/api/v1/pipeline/run",
        json={
            "service": "extraction",
            "text_content": runtime.text,
            "schema_override": {"required": ["missing_field"]},
        },
    ).json()
    assert body["success"] is False


def test_multiline_address_has_original_source_quote():
    data = {"vendor": {"address": "12 Main Street\nExample City"}}
    rows = attach_evidence(data, [SourcePage("doc", "invoice", 1, "12 Main Street\nExample City")], {})
    assert data["vendor"]["address"] is not None
    assert rows[0]["sources"][0]["quote"] == "12 Main Street\nExample City"


@pytest.mark.parametrize("schema", [{"type": "invalid_type"}, {"$ref": 10}, {"required": "not-a-list"}])
def test_malformed_schema_rejected_before_charging(runtime, schema):
    response = runtime.client.post(
        "/api/v1/pipeline/run", json={"service": "invoice", "text_content": runtime.text, "schema_override": schema}
    )
    assert response.status_code == 422
    assert runtime.charges == 0


def test_arabic_percent_and_percentage_not_mistaken_for_tax_amount():
    text = "المجموع الفرعي: ١٠٠\nضريبة القيمة المضافة ٢٠٪: ٢٠\nالإجمالي: ١٢٠"
    assert extract_financial_fields(text)["tax_rate"] == Decimal(".2")
    data, originals = prepare_data("invoice", {"tax_rate": "٢٠٪", "tax_total": 20}, "VAT 20%")
    evidence = attach_evidence(data, [SourcePage("doc", "invoice", 1, "VAT 20%")], originals)
    assert data["tax_rate"] == Decimal(".2")
    assert data["tax_total"] is None
    assert next(row for row in evidence if row["field"] == "tax_total")["status"] == "unverified"


def test_sensitive_data_findings_require_source_evidence(runtime):
    runtime.result = {
        "findings": [
            {"type": "email", "value": "actual@example.test"},
            {"type": "email", "value": "invented@example.test"},
        ],
        "recommendations": [],
    }
    body = runtime.client.post(
        "/api/v1/pipeline/run", json={"service": "compliance", "text_content": "Contact actual@example.test"}
    ).json()
    assert body["success"]
    assert body["data"]["findings"][0]["evidence_status"] == "supported"
    assert body["data"]["findings"][1]["value"] is None
    assert body["validation"]["status"] == "needs_review"
    assert body["fieldEvidence"][0]["sources"][0]["quote"] == "Contact actual@example.test"


def test_streamed_chat_replay_does_not_duplicate_turns_or_charge(runtime, monkeypatch):
    from backend import server
    from backend.auth import get_current_user

    monkeypatch.setattr(server.billing_service, "get_or_create_company", lambda *args: runtime.account)
    monkeypatch.setattr(server, "query", lambda *args, **kwargs: {"document_id": "doc"})
    writes = []
    monkeypatch.setattr(server, "execute", lambda sql, args: writes.append(args))
    monkeypatch.setattr(server.rag, "get_history", lambda _: [])
    monkeypatch.setattr(server.rag, "stream_chat", lambda **kwargs: iter(["Grounded ", "answer"]))
    server.app.dependency_overrides[get_current_user] = lambda: {"id": "user-a"}
    try:
        client = TestClient(server.app)
        first = client.post(
            "/api/sessions/session/chat", json={"message": "Question"}, headers={"Idempotency-Key": "chat-1"}
        )
        second = client.post(
            "/api/sessions/session/chat", json={"message": "Question"}, headers={"Idempotency-Key": "chat-1"}
        )
        assert first.text == second.text == "Grounded answer"
        assert second.headers["X-Idempotency-Replayed"] == "true"
        assert runtime.charges == 1
        assert sum(len(args) == 4 and args[2] == "user" for args in writes) == 1
        assert sum(len(args) == 4 and args[2] == "assistant" for args in writes) == 1
    finally:
        server.app.dependency_overrides.clear()


def test_failed_stream_replay_refunds_only_once(runtime, monkeypatch):
    from backend import server
    from backend.auth import get_current_user

    monkeypatch.setattr(server.billing_service, "get_or_create_company", lambda *args: runtime.account)
    monkeypatch.setattr(server, "query", lambda *args, **kwargs: {"document_id": "doc"})
    monkeypatch.setattr(server, "execute", lambda *args: None)
    monkeypatch.setattr(server.rag, "get_history", lambda _: [])

    def stream(**kwargs):
        yield "Partial answer"
        raise RuntimeError("provider interrupted")

    monkeypatch.setattr(server.rag, "stream_chat", stream)
    server.app.dependency_overrides[get_current_user] = lambda: {"id": "user-a"}
    try:
        client = TestClient(server.app)
        first = client.post(
            "/api/sessions/session/chat", json={"message": "Question"}, headers={"Idempotency-Key": "chat-error"}
        )
        second = client.post(
            "/api/sessions/session/chat", json={"message": "Question"}, headers={"Idempotency-Key": "chat-error"}
        )
        assert first.text == second.text
        assert "STREAM ERROR" in first.text
        assert runtime.charges == runtime.refunds == 1
        assert runtime.account.remaining_credits == 1200
    finally:
        server.app.dependency_overrides.clear()


def test_empty_freeform_result_is_refunded(runtime):
    runtime.result = "   "
    body = runtime.client.post("/api/v1/pipeline/run", json={"service": "summary", "text_content": runtime.text}).json()
    assert body["success"] is False and runtime.refunds == 1


def test_agent_catalog_uses_current_billing_prices_and_new_services():
    from backend.agent.tools.enhanced import EnhancedDocumentKit

    catalog = EnhancedDocumentKit().explain_services()
    for service in ["invoice_matching", "contract_comparison", "document_checks", "translation", "factcheck"]:
        assert f"| **{service}** | {SERVICE_PRICING[service]['credits']} |" in catalog
    assert "**arabic_ocr**" not in catalog  # Do not advertise an unregistered paid service.


def test_extracted_tax_rate_must_use_fraction_units(runtime):
    runtime.result["tax_rate"] = 20
    body = runtime.client.post("/api/v1/pipeline/run", json={"service": "invoice", "text_content": runtime.text}).json()
    assert body["success"] is False
    assert runtime.refunds == 1
