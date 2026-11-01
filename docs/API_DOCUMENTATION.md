# DOC Tool Document AI — Complete API Reference & Developer Guide

For output validation, source evidence, configurable tax and translation options, invoice/PO matching, contract version comparison, company rules and idempotent requests, see [Validated document services](DOCUMENT_SERVICES.md).

Welcome to the **DOC Tool Document AI** API documentation. This platform delivers enterprise-grade, stateless Document Intelligence powered by high-accuracy vision models.

---

## 1. Quick Overview & Architecture

- **Base URL**: `http://localhost:8000/api/v1` (or relative path `/api/v1`)
- **10-Minute Sliding Inactivity TTL**: Upload a document once and receive a `documentId`. The document is retained ephemerally for **10 minutes without usage**. Every time you call a service (OCR, invoice, contract, summary, etc.) with that `documentId`, the 10-minute countdown resets.
- **Configurable TTL**: Configure the inactivity window via `DOC_TTL_MINUTES=10` in environment or per-upload via `ttl_minutes`.
- **Zero Permanent Retention**: If 10 minutes elapse without usage, all associated files, embeddings, and temporary memory buffers are automatically wiped.
- **Authentication**: Authenticate using your company API key (`docu_live_...`) or session Bearer JWT.
- **Credit Billing**: Every API call atomically verifies and deducts credits from your company balance (starts with **300 free trial credits**).

---

## 2. Authentication

All requests to `/api/v1/*` (except public endpoints like `/pricing` and `/models`) require authentication.

### Methods:

1. **Header (Recommended)**:
   ```http
   X-API-Key: docu_live_xxxxxxxxxxxxxxxxxxxxxxxx
   ```
2. **Bearer Token**:
   ```http
   Authorization: Bearer docu_live_xxxxxxxxxxxxxxxxxxxxxxxx
   ```
3. **Session JWT**:
   ```http
   Authorization: Bearer <jwt_access_token>
   ```

If authentication fails or is missing, the API returns:
```json
{
  "detail": "Authentication required. Provide 'X-API-Key' header with your company key (docu_live_...)."
}
```
Status: `401 Unauthorized`

---

## 3. Available Models (Luna Engine)

DOC Tool runs on **Luna (`gpt-6-luna`)**, our vision and structured document reasoning model.

### Get Available Models

```http
GET /api/v1/models
```

#### Request:
```bash
curl -X GET "http://localhost:8000/api/v1/models"
```

#### Response:
```json
{
  "object": "list",
  "data": [
    {
      "id": "gpt-6-luna",
      "name": "Luna (GPT-6 Luna)",
      "description": "High-accuracy vision, layout-aware semantic OCR, and bilingual reasoning engine.",
      "capabilities": [
        "vision",
        "semantic_ocr",
        "arabic_english",
        "structured_json",
        "rag"
      ],
      "context_window": 128000,
      "status": "available",
      "is_default": true
    }
  ],
  "default_model": "gpt-6-luna",
  "total_available": 1
}
```

### Luna Capabilities & Behavior:
- **Vision OCR & Semantic Layout**: Accurately recognizes headings, nested tables, formulas, visual figures, and footnotes.
- **Bilingual Arabic & English**: Native handling of RTL/LTR direction, mixed Arabic/English technical terms, and Saudi/GCC dialects.
- **Continuation Linking**: Maintains reading order and references across page breaks (e.g., `previous_block_id`).
- **Temperature Configuration**: Configured with optimal preset temperature (`1.0`) for deterministic, schema-compliant JSON extraction.

---

## 4. Pricing & Credit Billing

DOC Tool operates on a transparent, pay-per-call credit system.

- **Free Trial Allocation**: **300 Free Trial Credits** are instantly granted to every company account upon creation.
- **Atomic Deduction**: Balance is verified before execution and deducted atomically in a database transaction with audit logging.
- **Zero Balance Behavior**: If remaining credits are lower than the service cost, returns `402 Payment Required`.

### 4.1 Get Service Pricing Catalog

```http
GET /api/v1/company/pricing
```

#### Request:
```bash
curl -X GET "http://localhost:8000/api/v1/company/pricing"
```

#### Response:
```json
{
  "initialTrialCredits": 300,
  "services": [
    {
      "id": "chat",
      "name": "Document Chat",
      "credits": 5,
      "llmTier": "Light",
      "category": "General",
      "description": "Fast conversational Q&A over document chunks"
    },
    {
      "id": "summary",
      "name": "Executive Summary",
      "credits": 10,
      "llmTier": "Light-Moderate",
      "category": "General",
      "description": "Multi-section executive summary with key findings"
    },
    {
      "id": "extraction",
      "name": "Data Extraction",
      "credits": 15,
      "llmTier": "Moderate",
      "category": "Extraction",
      "description": "Structured table and metrics extraction into Markdown"
    },
    {
      "id": "form_parser",
      "name": "Intelligent Form Parser",
      "credits": 20,
      "llmTier": "Moderate",
      "category": "Extraction",
      "description": "Form key-values, checkboxes [X], and signature blocks"
    },
    {
      "id": "receipt",
      "name": "Receipt & Expenses",
      "credits": 20,
      "llmTier": "Moderate",
      "category": "Finance",
      "description": "Itemized receipt line items, taxes, tips, and math check"
    },
    {
      "id": "invoice",
      "name": "Invoice Processing",
      "credits": 25,
      "llmTier": "Moderate-Heavy",
      "category": "Finance",
      "description": "Vendor/client extraction, line items, and verified JSON"
    },
    {
      "id": "resume",
      "name": "Resume & Talent Intelligence",
      "credits": 25,
      "llmTier": "Moderate-Heavy",
      "category": "HR",
      "description": "Candidate skills taxonomy, career timeline, seniority rating"
    },
    {
      "id": "compliance",
      "name": "PII & Compliance Audit",
      "credits": 30,
      "llmTier": "Heavy",
      "category": "Legal & Security",
      "description": "Full document PII scan, GDPR/HIPAA risk scoring, redaction"
    },
    {
      "id": "contract",
      "name": "Contract Analysis",
      "credits": 35,
      "llmTier": "Heavy",
      "category": "Legal",
      "description": "Legal clauses, liabilities, indemnification, risk engine"
    },
    {
      "id": "financial_statement",
      "name": "Financial Statement",
      "credits": 35,
      "llmTier": "Heavy",
      "category": "Finance",
      "description": "Income Statement & Balance Sheet metrics, solvency ratios"
    },
    {
      "id": "redaction",
      "name": "Bilingual PII Redaction",
      "credits": 25,
      "llmTier": "Moderate",
      "category": "Legal",
      "description": "Mask Saudi National IDs, GCC IBANs, and ZATCA VAT numbers"
    },
    {
      "id": "bilingual_translate",
      "name": "Bilingual Document Translation",
      "credits": 35,
      "llmTier": "Heavy",
      "category": "Localization",
      "description": "High-fidelity Arabic-English document translation"
    },
    {
      "id": "arabic_ocr",
      "name": "Arabic Specialized OCR",
      "credits": 35,
      "llmTier": "Multimodal Heavy",
      "category": "Multimodal",
      "description": "Diacritic preservation and Arabic dialect recognition"
    },
    {
      "id": "semantic_search",
      "name": "Cross-Lingual Semantic Search",
      "credits": 15,
      "llmTier": "Moderate",
      "category": "Search",
      "description": "Query English documents in Arabic and vice-versa"
    },
    {
      "id": "multi_doc_compare",
      "name": "Multi-Document Diff & Reconcile",
      "credits": 40,
      "llmTier": "Heavy",
      "category": "Analysis",
      "description": "Side-by-side clause and data reconciliation"
    },
    {
      "id": "custom_schema",
      "name": "Custom Schema Extractor",
      "credits": 30,
      "llmTier": "Heavy",
      "category": "Extraction",
      "description": "Extract any user-provided Pydantic or JSON schema"
    },
    {
      "id": "google_ai",
      "name": "Google AI Document",
      "credits": 40,
      "llmTier": "Multimodal Heavy",
      "category": "Multimodal",
      "description": "Multimodal layout hierarchy, entities, and vision OCR"
    },
    {
      "id": "coordinator",
      "name": "Auto-Routing Coordinator",
      "credits": 45,
      "llmTier": "Coordinator Tier",
      "category": "Orchestration",
      "description": "Intelligent classification and multi-pipeline execution"
    },
    {
      "id": "medical",
      "name": "Clinical & Medical AI",
      "credits": 45,
      "llmTier": "Specialized Heavy",
      "category": "Healthcare",
      "description": "ICD-10 coding, lab reports, and prescription parsing"
    }
  ]
}
```

### 4.2 Check Company Credit Balance

```http
GET /api/v1/company/account
```

#### Headers:
- `X-API-Key: docu_live_...`

#### Response:
```json
{
  "companyId": "c4b3a1d0-1234-5678-9abc-def012345678",
  "companyName": "Acme Corp",
  "planTier": "free_trial",
  "totalCredits": 300,
  "usedCredits": 75,
  "remainingCredits": 225,
  "apiKeyPrefix": "docu_live_ab12",
  "createdAt": "2026-10-27T10:00:00Z"
}
```

### 4.3 Get Usage Audit Logs

```http
GET /api/v1/company/usage
```

Returns paginated execution logs with service name, deducted credits, timestamp, and request summary.

---

## 5. Ephemeral Ingestion & Multi-Service Sessions (10-Min Sliding TTL)

Upload your document once and receive a `documentId` with an active 10-minute sliding inactivity countdown. You can run multiple services (OCR, Invoices, Contracts, Summary) using this single ID without re-uploading.

### 5.1 Ingest Document
```http
POST /api/v1/documents/upload
```

#### Request (`multipart/form-data`):
- `file`: PDF or document file (required)
- `ttl_minutes`: Configurable sliding inactivity window in minutes (optional, default: `10`)

```bash
curl -X POST "http://localhost:8000/api/v1/documents/upload" \
  -H "X-API-Key: docu_live_your_key_here" \
  -F "file=@./invoice_contract.pdf" \
  -F "ttl_minutes=10"
```

#### Response (`200 OK`):
```json
{
  "status": "success",
  "documentId": "4b7d11dd-fc1d-4d5b-aec4-9b0c7239ea17",
  "filename": "invoice_contract.pdf",
  "fileSize": 1048576,
  "pageCount": 4,
  "chunkCount": 12,
  "ttlMinutes": 10,
  "remainingSeconds": 600,
  "expiresAt": "2026-10-27T16:10:00Z",
  "creditsRemaining": 1175,
  "message": "Document session active. Retained for 10 minutes without usage. Inactivity resets on each service call."
}
```

### 5.2 Check Session Inactivity TTL Status
```http
GET /api/v1/documents/{document_id}/status
```

Returns remaining seconds and active expiration timestamp without modifying the countdown timer.

---

## 6. Advanced Semantic OCR

Extracts layout-aware semantic blocks (text, tables, formulas, visuals) directly from any PDF file.

```http
POST /api/v1/ocr/advanced
```

### Request Parameters (`multipart/form-data`):
| Parameter | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `file` | `file` (binary) | **Yes** | The PDF document to analyze (up to 50 MB) |
| `start_page` | `integer` | No | 1-indexed start page (default: `1`) |
| `end_page` | `integer` | No | 1-indexed end page (max 50 pages per request) |
| `language` | `string` | No | Language hint: `"auto"`, `"ar"`, `"en"`, or `"mixed"` |

### cURL Example:
```bash
curl -X POST "http://localhost:8000/api/v1/ocr/advanced" \
  -H "X-API-Key: docu_live_your_key_here" \
  -F "file=@/path/to/invoice_sample.pdf" \
  -F "start_page=1" \
  -F "end_page=5" \
  -F "language=auto"
```

### Response (`200 OK`):
```json
{
  "status": "success",
  "filename": "invoice_sample.pdf",
  "document_id": null,
  "total_pages": 5,
  "processed_pages": 5,
  "block_count": 18,
  "coordinate_system": "normalized_0_1000",
  "ocr_text": "INVOICE #INV-2026-001\nDate: 2026-10-27\n...",
  "pages": [
    {
      "page_number": 1,
      "block_count": 4,
      "blocks": [
        {
          "id": "p1-b1",
          "type": "title",
          "content": "TAX INVOICE / فاتورة ضريبية",
          "ocr_text": "TAX INVOICE / فاتورة ضريبية",
          "bbox": [50, 40, 110, 960],
          "page_number": 1,
          "reading_order": 1,
          "continues_previous_block": false
        },
        {
          "id": "p1-b2",
          "type": "table",
          "content": "| Description | Qty | Unit Price | Total |\n| --- | --- | --- | --- |\n| AI Consultation | 10 | $150.00 | $1,500.00 |",
          "ocr_text": "Description Qty Unit Price Total\nAI Consultation 10 $150.00 $1,500.00",
          "bbox": [150, 40, 400, 960],
          "page_number": 1,
          "reading_order": 2,
          "continues_previous_block": false
        }
      ]
    }
  ]
}
```

---

## 6. Document AI Pipeline Execution

Execute specialized intelligence services (Invoices, Redaction, Contracts, Financial Statements).

```http
POST /api/v1/pipeline/run
```

### Request Headers:
- `Content-Type: application/json`
- `X-API-Key: docu_live_...`

### Request Body:
```json
{
  "service": "invoice",
  "content": "Vendor: Apex Solutions LLC\nDate: 2026-10-27\nTotal: $4,500.00\nVAT: $675.00",
  "filename": "invoice.txt",
  "model": "gpt-6-luna",
  "temperature": 1.0,
  "output_format": "json"
}
```

### Response (`200 OK`):
```json
{
  "status": "success",
  "service": "invoice",
  "latencyMs": 1120,
  "creditsDeducted": 25,
  "creditsRemaining": 1175,
  "result": {
    "vendor": "Apex Solutions LLC",
    "invoice_number": null,
    "date": "2026-10-27",
    "subtotal": 4500.00,
    "tax_amount": 675.00,
    "total": 5175.00,
    "currency": "USD"
  }
}
```

---

## 7. Model Context Protocol (MCP) Integration

DOC Tool includes a built-in **MCP Server** for instant integration with **Claude Desktop**, **Cursor**, **Claude Code**, or any MCP-compatible agent.

### Configuration (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "docuchat": {
      "command": "python",
      "args": ["-m", "backend.mcp.server"],
      "env": {
        "DOCUCHAT_API_KEY": "docu_live_your_company_key_here",
        "DOCUCHAT_BASE_URL": "http://localhost:8000"
      }
    }
  }
}
```

### Available MCP Tools:
- `docuchat_advanced_ocr`: Run layout-aware vision OCR on any local PDF file.
- `docuchat_run_service`: Run services from the current document service catalog.
- `docuchat_get_company_credits`: Check company credit balance and service rates.
- `docuchat_list_models`: List available models (`gpt-6-luna`).

---

## 8. Error Codes & Handling

| HTTP Code | Error Reason | Resolution |
| :--- | :--- | :--- |
| `400 Bad Request` | Malformed payload or unsupported file format | Verify JSON or send a valid `.pdf` |
| `401 Unauthorized` | Missing or invalid API key | Check `X-API-Key` or token |
| `402 Payment Required` | Depleted Free Trial credits | Verify remaining balance via `GET /api/v1/company/account` |
| `413 Payload Too Large` | PDF file exceeds 50 MB | Compress PDF or select smaller file |
| `422 Unprocessable` | Invalid page range or parameters | Ensure `1 <= start_page <= end_page <= 50` |
| `502 Bad Gateway` | Vision model provider failure | Automatic bounded retry; retry request |

