# Validated document services

The service executor is shared by `/api/v1/pipeline/run`, `/api/v1/services/{service}`, the playground, background jobs, document-specific service endpoints and in-process MCP service calls. Structured chat modes use the same output validator before sending an answer. Advanced OCR extraction is unchanged.

## Request and response

Authenticate with `X-API-Key` or a session token. Provide exactly one of `document_id` or `text_content`. Documents, reference documents, jobs and saved rule sets are checked against the authenticated account.

```http
POST /api/v1/pipeline/run
X-API-Key: <company-key>
Idempotency-Key: invoice-2026-042
Content-Type: application/json
```

```json
{
  "service": "invoice",
  "text_content": "Vendor: Acme\nInvoice: INV-042\nSubtotal: SAR 100.00\nVAT 20%: SAR 20.00\nTotal: SAR 120.00",
  "output_format": "json",
  "options": {
    "financial": {
      "tax_rate": "0.20",
      "tolerance": "0.01",
      "decimal_places": 2,
      "date_order": "DMY",
      "tax_inclusive": false
    }
  }
}
```

Successful responses retain `success`, `service`, `documentId`, `data`, `raw`, `creditsDeducted` and `creditsRemaining`. They also include:

- `validation`: output-schema validation and whether a result needs review.
- `fieldEvidence`: extracted values with `field`, `value`, `originalValue`, `status`, `reason` and source citations containing the document ID, filename, page and original quote.
- `checks`: independent financial, translation or company-rule checks.
- `latencyMs`: execution time after document loading.

Missing default fields become `null`. Literal extracted values that cannot be located in the source also become `null`, with the original proposed value and the reason recorded in `fieldEvidence`. `supported` means the normalized value occurs in the cited source; it does not prove that the model interpreted its meaning correctly. Sensitive-data findings with explicit detected values or quotes receive source evidence too. Generated risk descriptions, classifications, redacted text and translations are not represented as literal extracted facts.

Invalid JSON, wrong field types, unknown fields in the default contract, unavailable evidence, and failed translation-preservation checks return `success: false`, `status: failed`, `data: null`, validation errors, and a credit refund. They are not replaced with a prose-derived dictionary. A successfully executed financial or rule check can find a discrepancy: the response remains `success: true`, while `checks` and `validation` indicate that review is needed. Check `success` and the check results, rather than relying only on the HTTP status.

### Custom output schemas

`schema_override` accepts a JSON Schema object. Example templates are supported and converted into schemas. Only local `$ref` values are allowed; schemas cannot fetch URLs or files. A custom schema replaces the default output contract and is validated after source matching. If it requires a non-null value that is missing or unsupported, the run fails and is refunded. Financial checks use the standard field names where available. Translation schemas must retain `translated_text` for preservation checks.

Default contracts cover invoices, receipts, contracts, resumes, sensitive-data review, forms, financial statements, redaction, classification, translation and anomaly auditing. Summaries and conversational answers may remain free text unless JSON or a schema is requested. The playground exposes the current default contracts in its presets.

## Financial and Arabic data

Financial calculations use `Decimal` internally, including JSON decimal inputs. Decimal values are converted only at response serialization. `originalValue` and source quotes retain the original notation; use those when exact source formatting matters.

Arabic and Persian digits, Arabic decimal/thousands separators, grouped English numbers and parentheses for negative amounts are supported. Ambiguous separators such as `1,25` are not guessed. Missing or ambiguous currency is `null`; a bare “ريال” does not establish a country/currency.

Dates support Gregorian `YYYY-MM-DD`, `DD/MM/YYYY` and `MM/DD/YYYY` forms, including Arabic digits. Ambiguous day/month values require `date_order`. Unsupported calendars or textual date formats are not converted. Dates that cannot be interpreted safely are `null`, with a reason.

Tax rates are fractions: `0.20` means 20%. No country-specific rate is assumed. A configured rate overrides a stated rate for the check. If neither exists, the tax calculation is `not_checked`. Defaults are two decimal places, half-up rounding, and a tolerance of `0.01`.

Checks include:

- Each available line quantity × unit price, less an explicit line discount.
- Sum of available line amounts versus subtotal.
- Subtotal − document discount + shipping + tip + tax versus total.
- Tax on the discounted subtotal using the stated/configured rate.
- Due date versus issue date, after date normalization.

For `tax_inclusive: true`, the subtotal is treated as tax-inclusive and tax is not added again. Missing optional discount, shipping and tip are treated as zero. Missing required calculation inputs produce `not_checked`; an empty document is not reported as clean. Financial ratios retain legitimate zeros and report missing inputs or a zero denominator explicitly.

## Translation

```json
{
  "service": "translation",
  "document_id": "<document-id>",
  "options": {
    "translation": {
      "source_language": "en",
      "target_language": "ar",
      "glossary": {"purchase order": "أمر شراء"},
      "preserve_names": ["Acme Ltd."]
    }
  }
}
```

Source language may be `auto`, `ar` or `en`; target language is `ar` or `en` and defaults to `ar`. Explicit source and target languages must differ. Numbers, their sequence, currency codes, configured names and relevant glossary terms are checked. A target-language script check catches clearly untranslated output; it does not evaluate translation quality. Name checks cover the explicit `preserve_names` list. The prompt also instructs the model to preserve other proper names, layout, tables and clause numbering. These translations are not described as certified.

## Invoice and purchase order matching

```json
{
  "service": "invoice_matching",
  "document_id": "<invoice-id>",
  "options": {
    "reference_document_id": "<purchase-order-id>",
    "financial": {"tolerance": "0.01"}
  }
}
```

Use `reference_text` instead of `reference_document_id` when testing with text. The service extracts both documents, attaches evidence to both outputs, and compares currency, PO number, item identifiers, quantities, unit prices, amounts and available totals. Items match by SKU when present, otherwise by normalized description. Duplicate or missing identifiers and missing comparison values require review. It returns `matched_items` and `differences`, with the extracted invoice and purchase order. Cost: 50 credits per run, including both extraction passes.

## Contract version comparison

```json
{
  "service": "contract_comparison",
  "document_id": "<old-version-id>",
  "options": {"reference_document_id": "<new-version-id>"}
}
```

The service returns added, removed and modified text with before/after page references. Changes are tagged for clause text, amounts/payments, dates/terms and obligation language. Comparison uses normalized line differences; category tags use keywords. It does not infer the legal effect of a change. No model call is needed. Cost: 15 credits per run.

## Company document checks

Inline rules:

```json
{
  "service": "document_checks",
  "document_id": "<document-id>",
  "options": {
    "rules": [
      {"field": "invoice_number", "operator": "required"},
      {"field": "total", "operator": "lte", "value": 5000, "message": "Requires manager approval above 5000"},
      {"field": "currency", "operator": "in", "value": ["SAR", "USD"]}
    ]
  }
}
```

Supported operators: `required`, `eq`, `neq`, `gte`, `lte`, `in`, `contains`. Fields use dotted paths such as `vendor.name` or `line_items.0.amount`. Missing values fail a rule rather than silently passing. `required` accepts a legitimate zero or `false`. `severity` defaults to `error`; `warning` marks a result for review. Numeric comparisons use decimal normalization. No executable expressions or user code are evaluated.

Rules are also available on existing services through `options.rules`. `document_checks` costs 20 credits. Existing services keep their normal credit price when rules are applied.

Reusable rule sets:

| Method | Endpoint | Body |
|---|---|---|
| POST | `/api/v1/rule-sets` | `{"name": "Invoice approval", "rules": [...]}` |
| GET | `/api/v1/rule-sets` | — |
| GET | `/api/v1/rule-sets/{id}` | — |
| PUT | `/api/v1/rule-sets/{id}` | `{"name": "Updated", "rules": [...]}` |
| DELETE | `/api/v1/rule-sets/{id}` | — |

Pass the returned UUID as `options.rule_set_id`. Saved rules and inline rules are combined, with a limit of 100 rules. Rule sets belong to the company that created them.

## Retries and jobs

Send an `Idempotency-Key` for requests that may be retried. Keys are scoped to the company and endpoint family. The same key and same request return the saved result without another execution, charge or callback. The response has `X-Idempotency-Replayed: true`. Replayed credit balances describe the original run.

- Same key with different parameters: HTTP 409.
- Same key while its operation is running: HTTP 409, with `Retry-After` on the pipeline path.
- Saved result expired: HTTP 410. The key remains a tombstone and will not execute or charge again.
- Operation storage unavailable: HTTP 503 before execution for a new keyed request. There is no in-memory idempotency fallback.

The response replay window uses `DOC_TTL_MINUTES`; it is independent of later document touches. Expired response bodies are cleared by the server cleanup task every 30 seconds. Key hashes, request fingerprints and operation status remain to prevent re-execution. Processing claims do not expire automatically: after a process crash, check whether execution and billing occurred before an operator resolves a pending claim. Do not release it blindly and retry. A new key means a new operation and may incur another charge.

The header is supported by the pipeline, batch submission, job submission, playground, company service and document-specific service routes. The MCP generic service tool accepts `idempotency_key`. Streaming chat uses the shared validator for structured modes and accepts the header too. A completed chat retry replays the saved plain-text response without another user/assistant turn or charge. Detected stream failures or interruptions are refunded and replayed as failed responses.

`POST /api/v1/pipeline/jobs` accepts the same service options, schema, model and prompt as `/pipeline/run`. Workers atomically claim queued jobs once. A duplicate worker delivery cannot charge again. Failed output validation is refunded using the same executor as synchronous runs. Poll `/api/v1/pipeline/jobs/{id}`; job access is company-scoped. The existing queue uses Redis when available and a process-local fallback otherwise; process-local queued jobs do not survive a restart.

## Python SDK and MCP

```python
from backend.sdk.client import DOCToolClient

client = DOCToolClient(api_key="<company-key>")
client.match_invoice("<invoice-id>", "<order-id>", idempotency_key="match-42")
client.compare_contract_versions("<old-id>", "<new-id>")
client.translate_document("<doc-id>", "Arabic", source_language="English",
                          glossary={"purchase order": "أمر شراء"}, preserve_names=["Acme Ltd."])
client.check_document("<doc-id>", rules=[{"field": "total", "operator": "lte", "value": 5000}])
client.submit_async_job("<doc-id>", "invoice", options={"financial": {"tax_rate": "0.20"}},
                        idempotency_key="async-invoice-42")
```

The MCP tool `docuchat_run_validated_service` exposes the same service names and options. Existing in-process service tools share validation and billing.

## Database and verification

Apply `backend/migrations/20261030_document_services.sql` to the existing application PostgreSQL database for the operation ledger and rule sets. The code also attempts `CREATE TABLE IF NOT EXISTS` on first use. If runtime DDL is restricted, apply the migration through the normal deployment process. It does not create users, grants or another production database.

Automated tests use fixed source pages and mocked model responses to verify contracts, source matching, Arabic normalization, financial calculations, translation checks, service adapters, refunds, SDK requests, and duplicate job/request handling. Separate PostgreSQL tests verify concurrent claims, restart replay, expiry and company isolation against an isolated local test cluster. These tests do not establish real-model extraction or translation accuracy.
