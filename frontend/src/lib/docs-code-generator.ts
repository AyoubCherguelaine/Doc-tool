import type { DocServiceItem } from "./docs-data";

export function generateCurlCode(
  item: DocServiceItem,
  apiKey: string = "docu_live_sample_key_9912",
  docId: string = "4b7d11dd-fc1d-4d5b-aec4-9b0c7239ea17",
  model?: string
): string {
  const base = "http://localhost:8000";

  if (item.id === "upload") {
    return `# 1. Ingest PDF and start 10-minute sliding session
curl -X POST "${base}/api/v1/documents/upload" \\
  -H "X-API-Key: ${apiKey}" \\
  -F "file=@sample_invoice.pdf" \\
  -F "ttl_minutes=10"`;
  }

  if (item.id === "status") {
    return `# Poll active sliding TTL status
curl -X GET "${base}/api/v1/documents/${docId}/status" \\
  -H "X-API-Key: ${apiKey}"`;
  }

  if (item.id === "ocr") {
    const ocrPayload = JSON.stringify(
      {
        document_id: docId,
        start_page: 1,
        end_page: 2,
        language: "auto",
        ...(model ? { model } : {}),
      },
      null,
      2
    );
    return `# Extract layout-aware bilingual OCR blocks
curl -X POST "${base}/api/v1/ocr/advanced" \\
  -H "X-API-Key: ${apiKey}" \\
  -H "Content-Type: application/json" \\
  -d '${ocrPayload}'`;
  }

  if (item.id === "pricing") {
    return `# Get live B2B service pricing catalog
curl -X GET "${base}/api/v1/company/pricing"`;
  }

  if (item.id === "models") {
    return `# List available vision & reasoning models
curl -X GET "${base}/api/v1/models"`;
  }

  if (item.type === "guide") {
    return `# Test company authentication & get balance
curl -X GET "${base}/api/v1/company/account" \\
  -H "X-API-Key: ${apiKey}"`;
  }

  // Pipeline service
  const payload = JSON.stringify(
    {
      service: item.serviceKey || item.id,
      document_id: docId,
      output_format: "json",
      ...(model ? { model } : {}),
      ...(item.id === "chat" ? { query: "What is the total amount due and payment terms?" } : {}),
      ...(item.id === "translation" ? { query: "Translate document to Arabic" } : {}),
      ...(item.id === "factcheck" ? { query: "Verify if revenue grew by 28% in 2025." } : {}),
    },
    null,
    2
  );

  return `# Call ${item.title} (${item.credits} credits, resets 10-min TTL)
curl -X POST "${base}/api/v1/pipeline/run" \\
  -H "X-API-Key: ${apiKey}" \\
  -H "Content-Type: application/json" \\
  -d '${payload}'`;
}

export function generatePythonCode(
  item: DocServiceItem,
  apiKey: string = "docu_live_sample_key_9912",
  docId: string = "4b7d11dd-fc1d-4d5b-aec4-9b0c7239ea17",
  model?: string
): string {
  const base = "http://localhost:8000";

  if (item.id === "upload") {
    return `import httpx

API_KEY = "${apiKey}"
BASE_URL = "${base}/api/v1"

with open("sample_invoice.pdf", "rb") as f:
    response = httpx.post(
        f"{BASE_URL}/documents/upload",
        headers={"X-API-Key": API_KEY},
        files={"file": ("sample_invoice.pdf", f, "application/pdf")},
        data={"ttl_minutes": 10},
        timeout=60.0
    )

res = response.json()
print("Session Created:", res["documentId"])
print("Remaining TTL:", res["remainingSeconds"], "seconds")`;
  }

  if (item.id === "status") {
    return `import httpx

API_KEY = "${apiKey}"
BASE_URL = "${base}/api/v1"
DOCUMENT_ID = "${docId}"

response = httpx.get(
    f"{BASE_URL}/documents/{DOCUMENT_ID}/status",
    headers={"X-API-Key": API_KEY}
)
res = response.json()
print("TTL Status:", res.get("status"))
print("Seconds Remaining:", res.get("remainingSeconds"))`;
  }

  if (item.id === "pricing") {
    return `import httpx

BASE_URL = "${base}/api/v1"

response = httpx.get(f"{BASE_URL}/company/pricing")
print("Pricing Catalog:", response.json())`;
  }

  if (item.id === "models") {
    return `import httpx

BASE_URL = "${base}/api/v1"

response = httpx.get(f"{BASE_URL}/models")
print("Available Models:", response.json())`;
  }

  if (item.type === "guide") {
    return `import httpx

API_KEY = "${apiKey}"
BASE_URL = "${base}/api/v1"

response = httpx.get(
    f"{BASE_URL}/company/account",
    headers={"X-API-Key": API_KEY}
)
print("Account Balance:", response.json())`;
  }

  const sKey = item.serviceKey || item.id;
  return `import httpx

API_KEY = "${apiKey}"
BASE_URL = "${base}/api/v1"
DOCUMENT_ID = "${docId}"

payload = {
    "service": "${sKey}",
    "document_id": DOCUMENT_ID,
    "output_format": "json"${model ? `,\n    "model": "${model}"` : ""}
}

# ⚡ Atomic execution: deducts ${item.credits} credits & resets 10-min sliding TTL
response = httpx.post(
    f"{BASE_URL}/pipeline/run",
    headers={
        "X-API-Key": API_KEY,
        "Content-Type": "application/json"
    },
    json=payload,
    timeout=60.0
)

if response.status_code == 200:
    result = response.json()
    print("Credits Deducted:", result.get("creditsDeducted"))
    print("Credits Remaining:", result.get("creditsRemaining"))
    print("TTL Reset To:", result.get("remainingSeconds"), "seconds")
    print("Extracted Data:", result.get("data"))
elif response.status_code == 410:
    print("Error: Document session expired after 10 min inactivity. Please re-upload.")
elif response.status_code == 402:
    print("Error: Insufficient credits. Please upgrade tier or top up balance.")
else:
    print("API Error:", response.status_code, response.text)`;
}

export function generateTypescriptCode(
  item: DocServiceItem,
  apiKey: string = "docu_live_sample_key_9912",
  docId: string = "4b7d11dd-fc1d-4d5b-aec4-9b0c7239ea17",
  model?: string
): string {
  const base = "http://localhost:8000";

  if (item.id === "upload") {
    return `import fs from "fs";
import FormData from "form-data";
import axios from "axios";

const API_KEY = "${apiKey}";
const BASE_URL = "${base}/api/v1";

async function uploadDocument() {
  const form = new FormData();
  form.append("file", fs.createReadStream("sample.pdf"));
  form.append("ttl_minutes", "10");

  const response = await axios.post(\`\${BASE_URL}/documents/upload\`, form, {
    headers: {
      "X-API-Key": API_KEY,
      ...form.getHeaders()
    }
  });

  console.log("Document session ID:", response.data.documentId);
  return response.data.documentId;
}`;
  }

  const sKey = item.serviceKey || item.id;
  return `interface DocumentAIResponse<T = Record<string, unknown>> {
  status: "success" | "error";
  service: string;
  documentId: string;
  model?: string;
  creditsDeducted: number;
  creditsRemaining: number;
  ttlMinutes: number;
  remainingSeconds: number;
  expiresAt: string;
  data: T;
}

const API_KEY = "${apiKey}";
const BASE_URL = "${base}/api/v1";
const DOCUMENT_ID = "${docId}";

async function runService(): Promise<DocumentAIResponse> {
  const res = await fetch(\`\${BASE_URL}/pipeline/run\`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": API_KEY
    },
    body: JSON.stringify({
      service: "${sKey}",
      document_id: DOCUMENT_ID,
      output_format: "json"${model ? `,\n      model: "${model}"` : ""}
    })
  });

  if (!res.ok) {
    if (res.status === 410) throw new Error("Document session expired (10-min TTL).");
    if (res.status === 402) throw new Error("Insufficient credits remaining.");
    throw new Error(\`HTTP \${res.status}: \${await res.text()}\`);
  }

  const result: DocumentAIResponse = await res.json();
  console.log(\`Processed via \${result.model || "AI"}! \${result.creditsRemaining} credits left.\`);
  return result;
}

// Execute
runService().then(console.log).catch(console.error);`;
}

export function generateWorkflowCode(
  item: DocServiceItem,
  apiKey: string = "docu_live_sample_key_9912",
  docId: string = "4b7d11dd-fc1d-4d5b-aec4-9b0c7239ea17",
  model?: string
): string {
  const base = "http://localhost:8000";
  const sKey = item.serviceKey || item.id;

  return `"""
Complete End-to-End B2B Pipeline Chaining Example
Demonstrates the 10-Minute Sliding TTL:
1. Ingest document once -> Receive documentId (starts 10-min countdown)
2. Run Service A: ${item.title} -> Resets countdown to 10 min
3. Run Service B: Executive Summary -> Resets countdown to 10 min
4. Document auto-purged from memory 10 minutes after last request
"""

import httpx
import time

API_KEY = "${apiKey}"
BASE_URL = "${base}/api/v1"

client = httpx.Client(headers={"X-API-Key": API_KEY}, timeout=60.0)

# STEP 1: Ingest PDF into 10-minute ephemeral session
with open("contract_or_invoice.pdf", "rb") as f:
    upload_res = client.post(
        f"{BASE_URL}/documents/upload",
        files={"file": ("contract.pdf", f, "application/pdf")},
        data={"ttl_minutes": 10}
    ).json()

doc_id = upload_res["documentId"]
print(f"Step 1: Document uploaded. ID: {doc_id} (10-min sliding timer started)")

# STEP 2: Execute Primary Service (${item.title})
res_a = client.post(f"{BASE_URL}/pipeline/run", json={
    "service": "${sKey}",
    "document_id": doc_id,
    "output_format": "json"${model ? `,\n    "model": "${model}"` : ""}
}).json()
print(f"Step 2: ${item.title} completed. Credits deducted: {res_a['creditsDeducted']}. Timer reset to 10m!")

# STEP 3: Chain Another Service (Executive Summary) without re-uploading
res_b = client.post(f"{BASE_URL}/pipeline/run", json={
    "service": "summary",
    "document_id": doc_id${model ? `,\n    "model": "${model}"` : ""}
}).json()
print(f"Step 3: Executive Summary completed. Credits remaining: {res_b['creditsRemaining']}. Timer reset!")

print("Step 4: All services chained cleanly. No permanent file left on disk.")
`;
}
