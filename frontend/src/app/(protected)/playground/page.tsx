"use client";
import { useLanguage } from "@/components/providers/language-provider";
import { serviceCatalog } from "@/lib/service-catalog";
import { UPLOAD_LIMIT_LABEL } from "@/lib/upload-limits";

import { useEffect, useState, useMemo } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  Sparkles,
  Play,
  Copy,
  Check,
  Download,
  RotateCcw,
  Upload,
  FileText,
  Clock,
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  ChevronDown,
  Layers,
  Code2,
  FileCheck,
  X,
  ExternalLink,
  ShieldCheck,
  ShieldAlert,
  Terminal,
  Zap,
  Timer,
  RefreshCw,
  Database,
  Server,
  Key,
  ChevronRight,
  FileCode,
  CheckCircle2,
  History,
  BookOpen,
} from "lucide-react";
import {
  fetchPlaygroundPresets,
  runPlayground,
  fetchDocuments,
  uploadDocument,
  fetchCompanyAccount,
  type PlaygroundPreset,
  type PlaygroundRunResult,
  type CompanyAccountInfo,
} from "@/lib/api";
import type { Document } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { useModelSettings } from "@/components/providers/model-provider";

export default function PlaygroundPage() {
  const { t, language: interfaceLanguage } = useLanguage();
  const { availableModels, selectedModel, guardianMode, calculateCost } = useModelSettings();
  const searchParams = useSearchParams();
  const router = useRouter();
  const serviceKey = searchParams.get("service") || "invoice";
  const initialShowCode = searchParams.get("code") === "true";

  const [preset, setPreset] = useState<PlaygroundPreset | null>(null);
  const [defaultEnvModel, setDefaultEnvModel] = useState<string>("gpt-4o-mini");
  const [currentModel, setCurrentModel] = useState<string>(selectedModel);
  const [guardianEnabled, setGuardianEnabled] = useState<boolean>(guardianMode);

  useEffect(() => {
    setGuardianEnabled(guardianMode);
  }, [guardianMode]);
  const [docs, setDocs] = useState<Document[]>([]);
  const [account, setAccount] = useState<CompanyAccountInfo | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  // Input Context States
  const [sourceType, setSourceType] = useState<"document" | "text">("document");
  const [textContent, setTextContent] = useState<string>("");
  const [selectedDocId, setSelectedDocId] = useState<string>("");
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [uploadError, setUploadError] = useState<string>("");

  // Prompt & Schema
  const [userPrompt, setUserPrompt] = useState<string>("");
  const [schemaText, setSchemaText] = useState<string>("");

  // Execution & Output
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [result, setResult] = useState<PlaygroundRunResult | null>(null);
  const [error, setError] = useState<string>("");
  const [activeTab, setActiveTab] = useState<"json" | "blocks" | "rendered" | "steps">("json");
  const [copied, setCopied] = useState<boolean>(false);

  // API Code Documentation States
  const [docEndpoint, setDocEndpoint] = useState<"pipeline" | "upload" | "ocr" | "status" | "multi_workflow">("pipeline");
  const [docSubTab, setDocSubTab] = useState<"params" | "response" | "lifecycle">("params");
  const [apiModalTab, setApiModalTab] = useState<"curl" | "python" | "typescript" | "full_workflow">("curl");
  const [apiModalAsync, setApiModalAsync] = useState<boolean>(false);
  const [codeCopied, setCodeCopied] = useState<boolean>(false);

  useEffect(() => {
    if (initialShowCode) {
      setTimeout(() => {
        document.getElementById("api-documentation")?.scrollIntoView({ behavior: "smooth" });
      }, 300);
    }
  }, [initialShowCode]);

  // Load preset, documents, and company account
  useEffect(() => {
    let active = true;
    Promise.all([
      fetchPlaygroundPresets(),
      fetchDocuments().catch(() => []),
      fetchCompanyAccount().catch(() => null),
    ])
      .then(([presetData, docList, accData]) => {
        if (!active) return;
        const envModel = presetData.defaultModel || selectedModel || "gpt-4o-mini";
        setDefaultEnvModel(envModel);
        if (!currentModel) setCurrentModel(envModel);
        setDocs(docList);
        if (accData) {
          setAccount(accData);
        }
        const targetDocId = searchParams.get("doc");
        if (targetDocId && docList.some((d) => d.id === targetDocId)) {
          setSelectedDocId(targetDocId);
          setSourceType("document");
        } else if (docList.length > 0) {
          setSelectedDocId(docList[0].id);
          setSourceType("document");
        }

        const current = presetData.presets[serviceKey] || presetData.presets["invoice"];
        if (current) {
          setPreset(current);
          setUserPrompt(current.default_query || "");
          setSchemaText(
            current.default_schema ? JSON.stringify(current.default_schema, null, 2) : ""
          );
          setTextContent(current.sample_text || "");
        }
      })
      .catch((err) => {
        console.error("Failed to load playground:", err);
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [serviceKey]);

  const selectedDoc = useMemo(() => {
    return docs.find((d) => d.id === selectedDocId) || docs[0] || null;
  }, [docs, selectedDocId]);

  const processUploadedFile = async (file: File) => {
    setIsUploading(true);
    setUploadError("");
    try {
      const up = await uploadDocument(file);
      const newDoc: Document = {
        id: up.id,
        userId: "",
        filename: up.filename,
        originalFilename: up.filename,
        pageCount: up.pageCount,
        fileSize: file.size,
        mimeType: file.type || "application/pdf",
        createdAt: new Date().toISOString(),
      };
      setDocs((prev) => [newDoc, ...prev.filter((d) => d.id !== newDoc.id)]);
      setSelectedDocId(up.id);
      setSourceType("document");
    } catch (err: any) {
      setUploadError(err.message || "File upload failed");
    } finally {
      setIsUploading(false);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      await processUploadedFile(file);
    }
    e.target.value = "";
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) {
      await processUploadedFile(file);
    }
  };

  const handleRun = async () => {
    setIsRunning(true);
    setError("");

    let parsedSchema = undefined;
    if (schemaText.trim()) {
      try {
        parsedSchema = JSON.parse(schemaText);
      } catch {
        parsedSchema = schemaText;
      }
    }

    const payload: any = {
      service: serviceKey,
      model: currentModel || defaultEnvModel,
      user_prompt: userPrompt || undefined,
      schema_override: parsedSchema,
      output_format: "json",
      guardian: guardianEnabled,
    };

    if (sourceType === "document" && selectedDocId) {
      payload.document_id = selectedDocId;
    } else {
      payload.text_content = textContent;
    }

    runPlayground(payload)
      .then((res) => {
        setResult(res);
      })
      .catch((err) => {
        setError(err.message || "Execution failed");
      })
      .finally(() => {
        setIsRunning(false);
        if (typeof window !== "undefined") {
          window.dispatchEvent(new CustomEvent("doctool:credit-updated"));
        }
      });
  };

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = (data: any) => {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = window.document.createElement("a");
    a.href = url;
    a.download = `${serviceKey}_result.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const isSchemaValid = useMemo(() => {
    if (!schemaText.trim()) return true;
    try {
      JSON.parse(schemaText);
      return true;
    } catch {
      return false;
    }
  }, [schemaText]);

  const apiKey = account?.rawApiKey || account?.apiKey || "docu_live_your_api_key_here";

  // Dynamic code generators for current state
  const curlCode = useMemo(() => {
    const isDoc = sourceType === "document" && selectedDocId;
    let inputSnippet = "";
    if (isDoc) {
      inputSnippet = `    "document_id": "${selectedDocId}",\n`;
    } else {
      const truncated = (textContent || "").slice(0, 300);
      inputSnippet = `    "text_content": ${JSON.stringify(truncated)},\n`;
    }

    let schemaSnippet = "";
    if (schemaText.trim()) {
      try {
        const obj = JSON.parse(schemaText);
        schemaSnippet = `    "schema_override": ${JSON.stringify(obj, null, 4).replace(/\n/g, "\n    ")},\n`;
      } catch {
        schemaSnippet = `    "schema_override": ${JSON.stringify(schemaText)},\n`;
      }
    }

    let promptSnippet = "";
    if (userPrompt.trim()) {
      promptSnippet = `    "user_prompt": ${JSON.stringify(userPrompt)},\n`;
    }

    let asyncSnippet = "";
    if (apiModalAsync) {
      asyncSnippet = `    "async": true,\n    "webhook_url": "https://your-api.company.com/webhooks/doctool",\n`;
    }

    return `# 1. Direct Pipeline Run Endpoint
curl -X POST "http://localhost:8000/api/v1/pipeline/run" \\
  -H "X-API-Key: ${apiKey}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "service": "${serviceKey}",
${inputSnippet}${promptSnippet}${schemaSnippet}${asyncSnippet}    "output_format": "json"
  }'`;
  }, [apiKey, serviceKey, sourceType, selectedDocId, textContent, schemaText, userPrompt, apiModalAsync]);

  const pythonCode = useMemo(() => {
    const isDoc = sourceType === "document" && selectedDocId;
    const body: any = {
      service: serviceKey,
      output_format: "json",
    };
    if (isDoc) {
      body.document_id = selectedDocId;
    } else {
      body.text_content = (textContent || "").slice(0, 300);
    }
    if (userPrompt.trim()) body.user_prompt = userPrompt;
    if (schemaText.trim()) {
      try {
        body.schema_override = JSON.parse(schemaText);
      } catch {
        body.schema_override = schemaText;
      }
    }
    if (apiModalAsync) {
      body.async = true;
      body.webhook_url = "https://your-api.company.com/webhooks/doctool";
    }

    return `import requests

url = "http://localhost:8000/api/v1/pipeline/run"
headers = {
    "X-API-Key": "${apiKey}",
    "Content-Type": "application/json"
}

payload = ${JSON.stringify(body, null, 4)}

response = requests.post(url, headers=headers, json=payload)
data = response.json()

if response.status_code == 200:
    print(f"Status: {data.get('status')}")
    print(f"Credits Remaining: {data.get('creditsRemaining')}")
    print("Structured Extraction:", data.get("data"))
else:
    print(f"Error {response.status_code}:", data.get("detail"))`;
  }, [apiKey, serviceKey, sourceType, selectedDocId, textContent, schemaText, userPrompt, apiModalAsync]);

  const typescriptCode = useMemo(() => {
    const isDoc = sourceType === "document" && selectedDocId;
    const body: any = {
      service: serviceKey,
      output_format: "json",
    };
    if (isDoc) {
      body.document_id = selectedDocId;
    } else {
      body.text_content = (textContent || "").slice(0, 300);
    }
    if (userPrompt.trim()) body.user_prompt = userPrompt;
    if (schemaText.trim()) {
      try {
        body.schema_override = JSON.parse(schemaText);
      } catch {
        body.schema_override = schemaText;
      }
    }
    if (apiModalAsync) {
      body.async = true;
      body.webhook_url = "https://your-api.company.com/webhooks/doctool";
    }

    return `// In Node.js 18+ or modern backend worker
async function runDocumentPipeline() {
  const url = "http://localhost:8000/api/v1/pipeline/run";
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "X-API-Key": "${apiKey}",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(${JSON.stringify(body, null, 2)}),
  });

  const json = await response.json();
  if (!response.ok) {
    throw new Error(json.detail || "Pipeline execution failed");
  }

  console.log("Status:", json.status);
  console.log("Structured JSON Output:", json.data);
  return json.data;
}

runDocumentPipeline().catch(console.error);`;
  }, [apiKey, serviceKey, sourceType, selectedDocId, textContent, schemaText, userPrompt, apiModalAsync]);

  const workflowCode = useMemo(() => {
    return `# ==============================================================================
# DOC Tool — Multi-Service Document AI Workflow (10-Min Inactivity Sliding TTL)
# ==============================================================================

# [STEP 1] Ingest document once: returns documentId and sets 10-min countdown clock
UPLOAD_RES=$(curl -s -X POST "http://localhost:8000/api/v1/documents/upload" \\
  -H "X-API-Key: ${apiKey}" \\
  -F "file=@./invoice_contract.pdf" \\
  -F "ttl_minutes=10")

DOCUMENT_ID=$(echo "$UPLOAD_RES" | jq -r '.documentId')
echo "Session active: $DOCUMENT_ID (TTL: 10 minutes)"

# [STEP 2] Process Service 1: Advanced Semantic OCR (⚡ Resets inactivity timer to 10 min)
curl -s -X POST "http://localhost:8000/api/v1/ocr/advanced" \\
  -H "X-API-Key: ${apiKey}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "document_id": "'"$DOCUMENT_ID"'",
    "start_page": 1,
    "end_page": 5,
    "language": "auto"
  }' | jq .

# [STEP 3] Process Service 2: Invoice Line Items Extraction (⚡ Resets inactivity timer to 10 min)
curl -s -X POST "http://localhost:8000/api/v1/pipeline/run" \\
  -H "X-API-Key: ${apiKey}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "service": "${serviceKey || "invoice"}",
    "document_id": "'"$DOCUMENT_ID"'",
    "output_format": "json"
  }' | jq .

# [STEP 4] Process Service 3: Executive Summary (⚡ Resets inactivity timer to 10 min)
curl -s -X POST "http://localhost:8000/api/v1/pipeline/run" \\
  -H "X-API-Key: ${apiKey}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "service": "summary",
    "document_id": "'"$DOCUMENT_ID"'",
    "output_format": "json"
  }' | jq .

# [STEP 5] Check remaining TTL without modifying countdown
curl -s -X GET "http://localhost:8000/api/v1/documents/'"$DOCUMENT_ID"'/status" \\
  -H "X-API-Key: ${apiKey}" | jq .

# Note: After 10 minutes without requests, files and index are automatically wiped.`;
  }, [apiKey, serviceKey]);

  const activeCurlCode = useMemo(() => {
    if (docEndpoint === "upload") {
      return `# Ingest document once and initialize 10-minute sliding window session
curl -X POST "http://localhost:8000/api/v1/documents/upload" \\
  -H "X-API-Key: ${apiKey}" \\
  -F "file=@./your_document.pdf" \\
  -F "ttl_minutes=10"`;
    }
    if (docEndpoint === "ocr") {
      return `# Run Advanced Semantic OCR with documentId (⚡ Resets 10-min window)
curl -X POST "http://localhost:8000/api/v1/ocr/advanced" \\
  -H "X-API-Key: ${apiKey}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "document_id": "${selectedDocId || "YOUR_DOCUMENT_ID"}",
    "start_page": 1,
    "end_page": 5,
    "language": "auto"
  }'`;
    }
    if (docEndpoint === "status") {
      return `# Check session remaining seconds and expiration timestamp
curl -X GET "http://localhost:8000/api/v1/documents/${selectedDocId || "YOUR_DOCUMENT_ID"}/status" \\
  -H "X-API-Key: ${apiKey}"`;
    }
    if (docEndpoint === "multi_workflow" || apiModalTab === "full_workflow") {
      return workflowCode;
    }
    return curlCode;
  }, [docEndpoint, apiModalTab, apiKey, selectedDocId, workflowCode, curlCode]);

  const activePythonCode = useMemo(() => {
    if (docEndpoint === "upload") {
      return `import requests

url = "http://localhost:8000/api/v1/documents/upload"
headers = {"X-API-Key": "${apiKey}"}
files = {"file": open("your_document.pdf", "rb")}
data = {"ttl_minutes": 10}  # Inactivity sliding timeout

resp = requests.post(url, headers=headers, files=files, data=data)
data = resp.json()
print("Document ID:", data["documentId"])
print(f"Active for: {data['remainingSeconds']}s ({data['ttlMinutes']} min)")`;
    }
    if (docEndpoint === "ocr") {
      return `import requests

url = "http://localhost:8000/api/v1/ocr/advanced"
headers = {
    "X-API-Key": "${apiKey}",
    "Content-Type": "application/json"
}
payload = {
    "document_id": "${selectedDocId || "YOUR_DOCUMENT_ID"}",
    "start_page": 1,
    "end_page": 5,
    "language": "auto"
}

resp = requests.post(url, headers=headers, json=payload)
print("OCR Blocks:", resp.json().get("blocks"))
print("TTL Renewed:", resp.json().get("remaining_seconds"), "seconds")`;
    }
    if (docEndpoint === "status") {
      return `import requests

url = "http://localhost:8000/api/v1/documents/${selectedDocId || "YOUR_DOCUMENT_ID"}/status"
headers = {"X-API-Key": "${apiKey}"}

resp = requests.get(url, headers=headers)
print("Status:", resp.json())`;
    }
    if (docEndpoint === "multi_workflow" || apiModalTab === "full_workflow") {
      return `# Complete Python Multi-Service Pipeline
import requests

API_KEY = "${apiKey}"
BASE_URL = "http://localhost:8000/api/v1"
headers = {"X-API-Key": API_KEY}

# 1. Ingest PDF once (10 min sliding TTL)
with open("invoice_sample.pdf", "rb") as f:
    up = requests.post(f"{BASE_URL}/documents/upload", headers=headers, files={"file": f}, data={"ttl_minutes": 10}).json()

doc_id = up["documentId"]
print(f"Uploaded {doc_id}, expires in {up['remainingSeconds']}s")

# 2. Run OCR (Resets 10 min clock)
ocr_res = requests.post(f"{BASE_URL}/ocr/advanced", headers=headers, json={"document_id": doc_id, "start_page": 1}).json()
print("OCR Page Blocks:", len(ocr_res.get("blocks", [])))

# 3. Run Invoice extraction (Resets 10 min clock again!)
inv_res = requests.post(f"{BASE_URL}/pipeline/run", headers=headers, json={"service": "invoice", "document_id": doc_id, "output_format": "json"}).json()
print("Invoice Extracted:", inv_res.get("data"))

# 4. Check remaining TTL
status = requests.get(f"{BASE_URL}/documents/{doc_id}/status", headers=headers).json()
print(f"Remaining seconds: {status['remainingSeconds']}s")`;
    }
    return pythonCode;
  }, [docEndpoint, apiModalTab, apiKey, selectedDocId, pythonCode]);

  const activeTypescriptCode = useMemo(() => {
    if (docEndpoint === "upload") {
      return `import FormData from "form-data";
import fs from "fs";
import fetch from "node-fetch";

const form = new FormData();
form.append("file", fs.createReadStream("./document.pdf"));
form.append("ttl_minutes", "10");

const res = await fetch("http://localhost:8000/api/v1/documents/upload", {
  method: "POST",
  headers: {
    "X-API-Key": "${apiKey}",
    ...form.getHeaders(),
  },
  body: form,
});

const session = await res.json();
console.log("Active Session:", session.documentId);
console.log("Expires in:", session.remainingSeconds, "seconds");`;
    }
    if (docEndpoint === "status") {
      return `const res = await fetch("http://localhost:8000/api/v1/documents/${selectedDocId || "YOUR_DOCUMENT_ID"}/status", {
  headers: { "X-API-Key": "${apiKey}" }
});
const status = await res.json();
console.log("TTL Status:", status);`;
    }
    return typescriptCode;
  }, [docEndpoint, apiKey, selectedDocId, typescriptCode]);

  const handleCopyCode = (code: string) => {
    navigator.clipboard.writeText(code);
    setCodeCopied(true);
    setTimeout(() => setCodeCopied(false), 2000);
  };

  // Keyboard shortcut listener: Cmd+Enter or Ctrl+Enter to execute
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
        e.preventDefault();
        if (!isRunning) {
          handleRun();
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isRunning, sourceType, selectedDocId, textContent, schemaText, userPrompt]);

  if (loading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <Spinner size={28} />
      </div>
    );
  }

  const catalogService = serviceCatalog.find((service) => service.id === serviceKey);
  const serviceTitle = catalogService?.title[interfaceLanguage] || preset?.name || serviceKey;

  return (
    <div className="mx-auto max-w-7xl animate-enter space-y-4">
      {/* Studio Header & Breadcrumb */}
      <div className="border-b border-slate-200 pb-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="flex items-center gap-2 text-xs font-semibold text-slate-400">
              <Link href="/services" className="hover:text-slate-800 transition flex items-center gap-1">
                <ArrowLeft size={13} />
                <span>{t("AI Services")}</span>
              </Link>
              <span>/</span>
              <span className="font-mono text-slate-700 uppercase tracking-wider text-[11px] font-semibold">{serviceKey}</span>
            </div>

            <div className="mt-1 flex flex-wrap items-center gap-2.5">
              <h1 className="text-xl font-bold tracking-tight text-slate-900">
                {serviceTitle}
              </h1>
              <div className="flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-2 py-0.5 shadow-2xs">
                <span className="text-[10px] text-slate-400 uppercase font-semibold">Model:</span>
                <select
                  value={currentModel || defaultEnvModel}
                  onChange={(e) => setCurrentModel(e.target.value)}
                  className="bg-transparent font-mono text-[11px] font-bold text-slate-800 outline-none cursor-pointer"
                >
                  {availableModels.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name} ({m.credit_cost} cr • ${(m.credit_cost * 0.002).toFixed(3)})
                    </option>
                  ))}
                </select>
              </div>

              {/* Guardian Mode Pill */}
              <button
                type="button"
                onClick={() => setGuardianEnabled(!guardianEnabled)}
                title={guardianEnabled ? "Guardian Verification Active (+5 cr)" : "Direct Return (Guardian Waived)"}
                className={`flex items-center gap-1.5 rounded-lg border px-2 py-0.5 shadow-2xs font-mono text-[11px] font-semibold transition cursor-pointer ${
                  guardianEnabled
                    ? "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300"
                    : "border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300"
                }`}
              >
                {guardianEnabled ? (
                  <ShieldCheck size={13} className="text-emerald-600" />
                ) : (
                  <ShieldAlert size={13} className="text-amber-600" />
                )}
                <span>{guardianEnabled ? "Guardian ON (+5cr)" : "Direct Return (Waived)"}</span>
              </button>

              <span className="hidden sm:inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-0.5 font-mono text-[10px] font-medium text-slate-600 border border-slate-200">
                {t("REST API Sandbox")}</span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="hidden lg:inline-flex text-[11px] font-mono text-slate-400">
              {t("Press")}<kbd className="rounded border border-slate-300 bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-600 font-mono">⌘+↵</kbd>
            </span>

            <Button
              onClick={() => {
                document.getElementById("api-documentation")?.scrollIntoView({ behavior: "smooth" });
              }}
              variant="outline"
              className="h-9 gap-1.5 border-slate-300 bg-white font-medium text-slate-700 hover:bg-slate-50 text-xs shadow-2xs"
            >
              <Code2 size={14} className="text-[#087f74]" />
              <span>{t("</> API Documentation & Code ↓")}</span>
            </Button>

            <Button
              onClick={handleRun}
              disabled={isRunning}
              className="h-9 gap-2 bg-[#087f74] hover:bg-[#06675e] text-white font-semibold px-4 text-xs shadow-xs transition"
            >
              {isRunning ? (
                <Spinner size={13} className="text-white" />
              ) : (
                <Play size={13} className="fill-current" />
              )}
              <span>{isRunning ? t("Running…", "جارٍ التشغيل…") : t(`Run ${serviceTitle}`, `تشغيل ${serviceTitle}`)}</span>
            </Button>
          </div>
        </div>
      </div>

      {/* Main Studio Two-Column Workbench */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12 items-start">
        {/* Left Panel: Inputs & Configuration Workbench (5 cols on lg) */}
        <div className="lg:col-span-5 flex flex-col rounded-xl border border-slate-200 bg-white shadow-xs overflow-hidden">
          {/* Top Panel Header: Segmented Source Selector */}
          <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50/80 px-4 py-2">
            <span className="text-[11px] font-bold text-slate-600 uppercase tracking-wider">
              {t("Input Source")}</span>
            <div className="inline-flex rounded-lg border border-slate-200 bg-white p-0.5 text-xs shadow-2xs font-medium">
              <button
                type="button"
                onClick={() => setSourceType("document")}
                className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs transition ${
                  sourceType === "document"
                    ? "bg-slate-900 text-white font-semibold shadow-2xs"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                <FileText size={12} />
                <span>{t("Document (")}{docs.length})</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  setSourceType("text");
                  if (!textContent && preset?.sample_text) {
                    setTextContent(preset.sample_text);
                  }
                }}
                className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs transition ${
                  sourceType === "text"
                    ? "bg-slate-900 text-white font-semibold shadow-2xs"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                <Code2 size={12} />
                <span>{t("Direct Text")}</span>
              </button>
            </div>
          </div>

          <div className="p-4 space-y-4 flex-1">
            {/* Document Source View */}
            {sourceType === "document" ? (
              <div className="space-y-2.5">
                <div className="flex items-center gap-2">
                  <div className="relative flex-1">
                    <select
                      value={selectedDocId}
                      onChange={(e) => setSelectedDocId(e.target.value)}
                      className="h-9 w-full appearance-none rounded-lg border border-slate-300 bg-white px-3 pr-8 text-xs font-semibold text-slate-900 shadow-2xs hover:border-slate-400 focus:border-teal-600 focus:outline-none"
                    >
                      {docs.length === 0 && <option value="">{t("No files uploaded yet")}</option>}
                      {docs.map((d) => (
                        <option key={d.id} value={d.id}>
                          {d.filename} ({d.pageCount} {d.pageCount === 1 ? t("page") : "pages"})
                        </option>
                      ))}
                    </select>
                    <ChevronDown
                      size={14}
                      className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400"
                    />
                  </div>

                  {/* Compact Upload Action */}
                  <label className="relative flex h-9 shrink-0 cursor-pointer items-center gap-1.5 rounded-lg border border-slate-300 bg-slate-50 px-3 text-xs font-medium text-slate-700 hover:bg-slate-100 hover:text-slate-900 shadow-2xs transition">
                    <input
                      type="file"
                      accept=".pdf,.docx,.xlsx,.xls,.csv,.txt,.png,.jpg,.jpeg"
                      onChange={handleFileUpload}
                      disabled={isUploading}
                      className="hidden"
                    />
                    <Upload size={13} className="text-slate-500" />
                    <span>{isUploading ? "Uploading..." : "Upload File"}</span>
                  </label>
                </div>

                {/* Drag and Drop Minimal Dropzone */}
                <div
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                  className={`rounded-lg border border-dashed px-3 py-2 text-center transition ${
                    isDragging
                      ? "border-teal-600 bg-teal-50/60"
                      : "border-slate-200 bg-slate-50/40 hover:border-slate-300"
                  }`}
                >
                  <p className="text-[11px] text-slate-500">
                    {t("Drag & drop PDF or document here •")}{t(UPLOAD_LIMIT_LABEL)}
                  </p>
                </div>

                {uploadError && (
                  <p className="text-xs text-rose-600 flex items-center gap-1">
                    <AlertCircle size={12} /> {uploadError}
                  </p>
                )}

                {/* Selected File Status Strip */}
                {selectedDoc && (
                  <div className="flex items-center justify-between rounded-lg border border-slate-200/80 bg-slate-50/80 px-3 py-1.5 text-xs">
                    <div className="flex items-center gap-2 truncate">
                      <FileText size={13} className="text-teal-700 shrink-0" />
                      <span className="font-semibold text-slate-800 truncate text-[11px]">{selectedDoc.filename}</span>
                    </div>
                    <span className="shrink-0 font-mono text-[10px] text-slate-500">
                      {selectedDoc.pageCount} {selectedDoc.pageCount === 1 ? t("page") : "pages"} {t("• OCR Ready")}</span>
                  </div>
                )}
              </div>
            ) : (
              /* Text Source View */
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-[11px] text-slate-500">
                  <span>{t("Direct text context:")}</span>
                  {preset?.sample_text && (
                    <button
                      type="button"
                      onClick={() => setTextContent(preset.sample_text)}
                      className="text-teal-700 hover:underline flex items-center gap-1 font-medium"
                    >
                      <RotateCcw size={10} /> {t("Reset Sample")}</button>
                  )}
                </div>
                <textarea
                  value={textContent}
                  onChange={(e) => setTextContent(e.target.value)}
                  rows={4}
                  placeholder={t("Paste document text or invoice OCR output...")}
                  className="w-full rounded-lg border border-slate-200 bg-[#fafbfc] p-3 font-mono text-xs text-slate-900 focus:border-teal-600 focus:bg-white focus:outline-none"
                />
              </div>
            )}

            {/* Task Prompt / Instruction */}
            <div className="space-y-1">
              <label className="text-[11px] font-bold text-slate-700 uppercase tracking-wider">
                {t("Task Query / Prompt")}</label>
              <input
                type="text"
                value={userPrompt}
                onChange={(e) => setUserPrompt(e.target.value)}
                placeholder={t("e.g. Extract structured invoice data, itemized rows, and calculate VAT.")}
                className="h-9 w-full rounded-lg border border-slate-300 px-3 text-xs text-slate-900 placeholder:text-slate-400 focus:border-teal-600 focus:outline-none shadow-2xs font-medium"
              />
            </div>

            {/* Target JSON Schema Configuration (System Prompt is strictly internal) */}
            <div className="space-y-2 pt-1 border-t border-slate-100">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-800">
                  {t("Target JSON Schema")}</span>

                <div className="flex items-center gap-2 text-[11px]">
                  <span
                    className={`font-mono text-[10px] font-medium px-1.5 py-0.5 rounded ${
                      isSchemaValid
                        ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                        : "bg-rose-50 text-rose-700 border border-rose-200"
                    }`}
                  >
                    {isSchemaValid ? "Valid JSON" : "Invalid JSON"}
                  </span>
                  <button
                    type="button"
                    onClick={() => {
                      try {
                        setSchemaText(JSON.stringify(JSON.parse(schemaText), null, 2));
                      } catch {}
                    }}
                    disabled={!isSchemaValid}
                    className="text-slate-600 hover:text-slate-900 disabled:opacity-40"
                  >
                    {t("Format")}</button>
                  <span className="text-slate-300">•</span>
                  <button
                    type="button"
                    onClick={() =>
                      setSchemaText(
                        preset?.default_schema ? JSON.stringify(preset.default_schema, null, 2) : ""
                      )
                    }
                    className="text-teal-700 hover:underline"
                  >
                    {t("Reset")}</button>
                </div>
              </div>

              <textarea
                value={schemaText}
                onChange={(e) => setSchemaText(e.target.value)}
                rows={7}
                placeholder={t("Target JSON schema template...")}
                className="w-full rounded-lg border border-slate-800 bg-[#0c1222] p-3 font-mono text-[11px] leading-relaxed text-emerald-400 focus:outline-none"
              />
            </div>
          </div>
        </div>

        {/* Right Panel: Execution Output & Inspector (7 cols on lg) */}
        <div className="lg:col-span-7 flex flex-col rounded-xl border border-slate-200 bg-white shadow-xs overflow-hidden">
          {/* Header Bar */}
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 bg-slate-50/80 px-4 py-2">
            <div className="inline-flex rounded-lg border border-slate-200 bg-white p-0.5 text-xs font-medium shadow-2xs">
              <button
                onClick={() => setActiveTab("json")}
                className={`rounded px-2.5 py-1 text-xs transition ${
                  activeTab === "json"
                    ? "bg-slate-900 text-white font-semibold shadow-2xs"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                {t("Structured JSON")}</button>
              <button
                onClick={() => setActiveTab("blocks")}
                className={`rounded px-2.5 py-1 text-xs transition ${
                  activeTab === "blocks"
                    ? "bg-slate-900 text-white font-semibold shadow-2xs"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                {t("Layout Blocks")}</button>
              <button
                onClick={() => setActiveTab("rendered")}
                className={`rounded px-2.5 py-1 text-xs transition ${
                  activeTab === "rendered"
                    ? "bg-slate-900 text-white font-semibold shadow-2xs"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                {t("Raw Text")}</button>
              <button
                onClick={() => setActiveTab("steps")}
                className={`rounded px-2.5 py-1 text-xs transition ${
                  activeTab === "steps"
                    ? "bg-slate-900 text-white font-semibold shadow-2xs"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                {t("Agent Steps (")}{result?.steps?.length || 0})
              </button>
            </div>

            <div className="flex items-center gap-2">
              {result && (
                <div className="flex items-center gap-1.5 font-mono text-[11px] text-slate-500">
                  <span className="flex items-center gap-1 rounded bg-slate-200/70 px-2 py-0.5 font-semibold text-slate-700">
                    <Clock size={11} className="text-teal-700" /> {result.latencyMs} ms
                  </span>
                  <span className="rounded bg-teal-50 px-2 py-0.5 font-semibold text-teal-800 border border-teal-200">
                    {result.model}
                  </span>
                  <span
                    className={`rounded px-2 py-0.5 font-semibold border ${
                      result.guardianEnabled !== false
                        ? "bg-emerald-50 text-emerald-800 border-emerald-200"
                        : "bg-amber-50 text-amber-800 border-amber-200"
                    }`}
                  >
                    {result.guardianEnabled !== false ? "Guardian (+5cr)" : "Direct Return"}
                  </span>
                </div>
              )}

              {result?.data && (
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => handleCopy(JSON.stringify(result.data, null, 2))}
                    className="flex items-center gap-1 rounded-md border border-slate-200 bg-white px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 transition shadow-2xs"
                  >
                    {copied ? <Check size={12} className="text-emerald-600" /> : <Copy size={12} />}
                    <span>{copied ? t("Copied") : t("Copy")}</span>
                  </button>
                  <button
                    onClick={() => handleDownload(result.data)}
                    className="flex items-center gap-1 rounded-md border border-slate-200 bg-white px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 transition shadow-2xs"
                  >
                    <Download size={12} />
                    <span>{t("Export")}</span>
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Viewport Content */}
          <div className="flex-1 p-4 overflow-auto min-h-[460px]">
            {/* Running State */}
            {isRunning && (
              <div className="flex h-96 flex-col items-center justify-center text-center">
                <Spinner size={24} className="text-teal-700" />
                <p className="mt-3 text-xs font-semibold text-slate-800">
                  {t("Executing")}{serviceTitle} {t("Pipeline...")}</p>
                <p className="mt-1 font-mono text-[11px] text-slate-400">
                  {t("Running model")}: {currentModel || defaultEnvModel} {t("with layout verification")}</p>
              </div>
            )}

            {/* Error State */}
            {error && !isRunning && (
              <div className="flex items-start gap-2.5 rounded-lg border border-red-200 bg-red-50 p-4 text-xs text-red-800">
                <AlertCircle size={15} className="shrink-0 text-red-600 mt-0.5" />
                <div>
                  <p className="font-semibold">{t("Pipeline Execution Failed")}</p>
                  <p className="mt-0.5 text-[11px] leading-relaxed font-mono">{error}</p>
                </div>
              </div>
            )}

            {/* Output View */}
            {result && !isRunning && (
              <div>
                {/* Structured JSON Tab */}
                {activeTab === "json" && (
                  <pre className="max-h-[560px] overflow-auto rounded-lg border border-slate-800 bg-[#0a0f1d] p-4 font-mono text-[12px] leading-relaxed text-emerald-400 shadow-inner">
                    {JSON.stringify(result.data || result.result, null, 2)}
                  </pre>
                )}

                {/* Layout Blocks Tab */}
                {activeTab === "blocks" && (
                  <div className="max-h-[560px] overflow-auto space-y-3">
                    {Array.isArray(result.data?.blocks) && result.data.blocks.length > 0 ? (
                      result.data.blocks.map((blk: any, idx: number) => (
                        <div key={idx} className="rounded-lg border border-slate-200 bg-slate-50/60 p-3 text-xs space-y-1.5">
                          <div className="flex items-center justify-between">
                            <span className="font-mono text-[10px] font-bold uppercase rounded bg-slate-200 px-1.5 py-0.5 text-slate-700">
                              {t("Block #")}{blk.metadata?.reading_order || idx + 1} • {blk.type}
                            </span>
                            <span className="font-mono text-[10px] text-slate-400">
                              {t("page")}{blk.metadata?.page_number || 1}
                            </span>
                          </div>
                          {blk.title && (
                            <p className="font-bold text-slate-900 text-sm">{blk.title}</p>
                          )}
                          {blk.table?.content_md ? (
                            <pre className="font-mono text-[11px] bg-white p-2 rounded border border-slate-200 overflow-x-auto text-slate-800">
                              {blk.table.content_md}
                            </pre>
                          ) : blk.image?.description ? (
                            <p className="italic text-teal-800 bg-teal-50 p-2 rounded border border-teal-200">
                              {t("Image:")}{blk.image.description}
                            </p>
                          ) : (
                            <p className="text-slate-700 leading-relaxed whitespace-pre-wrap">{blk.content}</p>
                          )}
                        </div>
                      ))
                    ) : (
                      <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-6 text-center text-xs text-slate-500">
                        <p>{t("Direct JSON payload received.")}</p>
                        <p className="mt-1 text-[11px] text-slate-400 font-mono">
                          {t("Inspect the Structured JSON tab to view extracted fields.")}</p>
                      </div>
                    )}
                  </div>
                )}

                {/* Formatted Text Tab */}
                {activeTab === "rendered" && (
                  <div className="max-h-[560px] overflow-auto whitespace-pre-wrap rounded-lg border border-slate-200 bg-slate-50/50 p-4 font-mono text-xs leading-relaxed text-slate-800">
                    {result.result}
                  </div>
                )}

                {/* Agent Steps Tab */}
                {activeTab === "steps" && (
                  <div className="max-h-[560px] overflow-auto space-y-2">
                    {result.steps && result.steps.length > 0 ? (
                      result.steps.map((st, idx) => (
                        <div
                          key={idx}
                          className="rounded-lg border border-slate-200 bg-white p-3 text-xs shadow-2xs space-y-1"
                        >
                          <div className="flex items-center justify-between">
                            <span className="font-semibold text-teal-800 font-mono text-[11px]">
                              {t("Step")}{idx + 1}: {st.action || "Agent Reasoning"}
                            </span>
                          </div>
                          {st.thought && <p className="italic text-slate-600 text-[11px]">{st.thought}</p>}
                          {st.observation && (
                            <pre className="max-h-24 overflow-auto rounded bg-slate-50 p-2 font-mono text-[10px] text-slate-700 border border-slate-100">
                              {st.observation}
                            </pre>
                          )}
                        </div>
                      ))
                    ) : (
                      <p className="p-4 text-xs text-slate-500 text-center">
                        {t("Single-pass direct model execution completed without multi-step iterations.")}</p>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Empty State */}
            {!result && !isRunning && !error && (
              <div className="flex h-96 flex-col items-center justify-center text-center">
                <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-slate-100 text-slate-500 mb-3 border border-slate-200">
                  <Code2 size={22} />
                </div>
                <p className="text-sm font-semibold text-slate-800">{t("Ready to execute")}</p>
                <p className="text-xs text-slate-400 mt-1 max-w-xs">
                  {t("Click")}<span className="font-semibold text-slate-700">{t("Run")}</span> {t("or press")}{" "}
                  <kbd className="rounded border border-slate-300 bg-slate-100 px-1 py-0.5 text-[10px] font-mono text-slate-600">
                    ⌘+Enter
                  </kbd>{" "}
                  {t("to execute pipeline with")}<span className="font-mono text-teal-700 font-semibold">{defaultEnvModel}</span>.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* =========================================================================
          INLINE DEVELOPER API DOCUMENTATION & INTERACTIVE CODE EXPLORER
          Enhanced DOC Tool Developer Platform: Stateless with 10-min sliding TTL
         ========================================================================= */}
      <section
        id="api-documentation"
        className="mt-12 rounded-2xl border border-slate-200/90 bg-white p-6 md:p-8 shadow-sm space-y-8 scroll-mt-6"
      >
        {/* Section Header with Badges */}
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between border-b border-slate-100 pb-6">
          <div className="space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1 rounded-md bg-teal-100 px-2 py-0.5 text-[11px] font-bold text-teal-800 uppercase tracking-wide">
                <Code2 size={13} /> DOC Tool REST API v1
              </span>
              <span className="inline-flex items-center gap-1 rounded-md bg-amber-100 px-2 py-0.5 text-[11px] font-bold text-amber-900">
                <Timer size={13} className="text-amber-700" /> 10-Min Sliding Inactivity Window
              </span>
              <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-0.5 text-[11px] font-mono font-semibold text-slate-700">
                Luna (gpt-6-luna)
              </span>
            </div>
            <h3 className="text-xl font-extrabold text-slate-900 tracking-tight">
              Developer API Documentation &amp; Pipeline Explorer
            </h3>
            <p className="text-xs text-slate-500 max-w-2xl leading-relaxed">
              Upload your document once, obtain a <code className="text-teal-700 font-bold">documentId</code>, and chain multiple Document AI services within a 10-minute sliding inactivity window. Every request automatically resets the timer.
            </p>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <Link
              href={`/docs?service=${serviceKey}`}
              className="inline-flex items-center gap-1.5 rounded-xl bg-slate-900 px-3.5 py-2 text-xs font-semibold text-white hover:bg-slate-800 transition shadow-sm"
            >
              <BookOpen size={14} />
              <span>{t("Full Platform Docs ↗")}</span>
            </Link>
            <Link
              href="/usage"
              className="inline-flex items-center gap-1.5 rounded-xl border border-teal-200 bg-teal-50 px-3.5 py-2 text-xs font-semibold text-teal-800 hover:bg-teal-100 transition shadow-2xs"
            >
              <Zap size={14} className="text-teal-600 fill-teal-600" />
              <span>{t("Usage Logs & Quotas →")}</span>
            </Link>
          </div>
        </div>

        {/* 10-MINUTE SLIDING INACTIVITY TTL LIFECYCLE FLOWCHART */}
        <div className="rounded-xl border border-teal-100 bg-gradient-to-r from-teal-50/70 via-slate-50/50 to-teal-50/40 p-5">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <RefreshCw size={15} className="text-teal-700 animate-spin-slow" />
              <h4 className="text-xs font-bold uppercase tracking-wider text-teal-900">
                How Ephemeral Document Sessions Work (Sliding TTL)
              </h4>
            </div>
            <span className="text-[11px] text-teal-700 font-semibold font-mono">
              Configurable: DOC_TTL_MINUTES=10
            </span>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4 text-xs">
            <div className="rounded-xl border border-white bg-white/90 p-3.5 shadow-2xs space-y-1 relative">
              <span className="absolute top-2.5 right-2.5 flex h-5 w-5 items-center justify-center rounded-full bg-teal-100 text-[10px] font-bold text-teal-800">
                1
              </span>
              <p className="font-bold text-slate-900 flex items-center gap-1.5">
                <Upload size={14} className="text-teal-600" />
                Upload Once
              </p>
              <p className="text-[11px] text-slate-500 leading-relaxed">
                Ingest PDF via <code className="font-mono text-teal-800">/documents/upload</code>. Receives <code className="font-mono text-slate-700">documentId</code> and starts 10-min countdown.
              </p>
            </div>

            <div className="rounded-xl border border-white bg-white/90 p-3.5 shadow-2xs space-y-1 relative">
              <span className="absolute top-2.5 right-2.5 flex h-5 w-5 items-center justify-center rounded-full bg-teal-100 text-[10px] font-bold text-teal-800">
                2
              </span>
              <p className="font-bold text-slate-900 flex items-center gap-1.5">
                <Zap size={14} className="text-teal-600 fill-teal-600" />
                Run Service A
              </p>
              <p className="text-[11px] text-slate-500 leading-relaxed">
                Call OCR or Invoice extraction with <code className="font-mono text-slate-700">documentId</code>. <strong>Sliding reset:</strong> timer resets back to 10 minutes!
              </p>
            </div>

            <div className="rounded-xl border border-white bg-white/90 p-3.5 shadow-2xs space-y-1 relative">
              <span className="absolute top-2.5 right-2.5 flex h-5 w-5 items-center justify-center rounded-full bg-teal-100 text-[10px] font-bold text-teal-800">
                3
              </span>
              <p className="font-bold text-slate-900 flex items-center gap-1.5">
                <Layers size={14} className="text-teal-600" />
                Run Service B &amp; C
              </p>
              <p className="text-[11px] text-slate-500 leading-relaxed">
                Chain Contracts, Compliance, or Summary. Reuses same document without re-uploading. Clock resets every time!
              </p>
            </div>

            <div className="rounded-xl border border-white bg-white/90 p-3.5 shadow-2xs space-y-1 relative">
              <span className="absolute top-2.5 right-2.5 flex h-5 w-5 items-center justify-center rounded-full bg-rose-100 text-[10px] font-bold text-rose-800">
                4
              </span>
              <p className="font-bold text-slate-900 flex items-center gap-1.5">
                <ShieldCheck size={14} className="text-emerald-600" />
                Zero-Trace Purge
              </p>
              <p className="text-[11px] text-slate-500 leading-relaxed">
                After 10 continuous minutes without requests, files, embeddings, and buffers are purged permanently.
              </p>
            </div>
          </div>
        </div>

        {/* INTERACTIVE ENDPOINT SELECTOR TABS */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-400">
              {t("Select API Endpoint")}</span>
            <span className="text-[11px] text-slate-400">
              {t("Active Service:")}<span className="font-semibold text-teal-700">{serviceTitle}</span>
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => {
                setDocEndpoint("pipeline");
                setApiModalTab("curl");
              }}
              className={`flex items-center gap-2 rounded-xl px-3.5 py-2 text-xs font-semibold transition ${
                docEndpoint === "pipeline"
                  ? "bg-slate-900 text-white shadow-md ring-2 ring-teal-500/20"
                  : "border border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
              }`}
            >
              <span className="rounded bg-teal-500/20 px-1.5 py-0.5 text-[10px] font-mono font-bold text-teal-400">
                POST
              </span>
              <span>/api/v1/pipeline/run</span>
              <span className="rounded bg-slate-800 px-1.5 py-0.2 text-[9px] text-slate-300">
                19 Services
              </span>
            </button>

            <button
              onClick={() => {
                setDocEndpoint("upload");
                setApiModalTab("curl");
              }}
              className={`flex items-center gap-2 rounded-xl px-3.5 py-2 text-xs font-semibold transition ${
                docEndpoint === "upload"
                  ? "bg-slate-900 text-white shadow-md ring-2 ring-teal-500/20"
                  : "border border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
              }`}
            >
              <span className="rounded bg-teal-500/20 px-1.5 py-0.5 text-[10px] font-mono font-bold text-teal-400">
                POST
              </span>
              <span>/api/v1/documents/upload</span>
              <span className="rounded bg-teal-900/60 px-1.5 py-0.2 text-[9px] text-teal-200 font-mono">
                10-Min Session
              </span>
            </button>

            <button
              onClick={() => {
                setDocEndpoint("ocr");
                setApiModalTab("curl");
              }}
              className={`flex items-center gap-2 rounded-xl px-3.5 py-2 text-xs font-semibold transition ${
                docEndpoint === "ocr"
                  ? "bg-slate-900 text-white shadow-md ring-2 ring-teal-500/20"
                  : "border border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
              }`}
            >
              <span className="rounded bg-teal-500/20 px-1.5 py-0.5 text-[10px] font-mono font-bold text-teal-400">
                POST
              </span>
              <span>/api/v1/ocr/advanced</span>
              <span className="rounded bg-slate-800 px-1.5 py-0.2 text-[9px] text-slate-300">
                {t("Layout Blocks")}</span>
            </button>

            <button
              onClick={() => {
                setDocEndpoint("status");
                setApiModalTab("curl");
              }}
              className={`flex items-center gap-2 rounded-xl px-3.5 py-2 text-xs font-semibold transition ${
                docEndpoint === "status"
                  ? "bg-slate-900 text-white shadow-md ring-2 ring-teal-500/20"
                  : "border border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
              }`}
            >
              <span className="rounded bg-sky-500/20 px-1.5 py-0.5 text-[10px] font-mono font-bold text-sky-400">
                GET
              </span>
              <span>/api/v1/documents/:id/status</span>
              <span className="rounded bg-slate-800 px-1.5 py-0.2 text-[9px] text-slate-300">
                TTL Polling
              </span>
            </button>

            <button
              onClick={() => {
                setDocEndpoint("multi_workflow");
                setApiModalTab("full_workflow");
              }}
              className={`flex items-center gap-2 rounded-xl px-3.5 py-2 text-xs font-semibold transition ${
                docEndpoint === "multi_workflow"
                  ? "bg-[#087f74] text-white shadow-md"
                  : "border border-teal-200 bg-teal-50/60 text-teal-900 hover:bg-teal-100/70"
              }`}
            >
              <Zap size={13} className="text-teal-600 fill-teal-600" />
              <span>Multi-Service Workflow Script</span>
            </button>
          </div>
        </div>

        {/* TWO-COLUMN EXPLORER: SPECS (LEFT) & CODE SANDBOX (RIGHT) */}
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
          {/* LEFT 6 COLS: DOCUMENTATION, PARAMETERS, & RESPONSE SCHEMAS */}
          <div className="lg:col-span-6 flex flex-col space-y-4">
            {/* Sub-Tabs: Parameters vs Response vs Error Codes */}
            <div className="flex items-center justify-between border-b border-slate-200 pb-2">
              <div className="inline-flex rounded-lg border border-slate-200 bg-slate-100 p-0.5 text-xs font-semibold">
                <button
                  onClick={() => setDocSubTab("params")}
                  className={`rounded-md px-3 py-1 transition ${
                    docSubTab === "params"
                      ? "bg-white text-slate-900 shadow-2xs"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  {t("Request Parameters")}</button>
                <button
                  onClick={() => setDocSubTab("response")}
                  className={`rounded-md px-3 py-1 transition ${
                    docSubTab === "response"
                      ? "bg-white text-slate-900 shadow-2xs"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  {t("Response Schema")}</button>
                <button
                  onClick={() => setDocSubTab("lifecycle")}
                  className={`rounded-md px-3 py-1 transition ${
                    docSubTab === "lifecycle"
                      ? "bg-white text-slate-900 shadow-2xs"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  {t("Status & Errors")}</button>
              </div>

              <span className="text-[11px] font-mono text-slate-400">
                Content-Type: {docEndpoint === "upload" ? "multipart/form-data" : "application/json"}
              </span>
            </div>

            {/* SubTab 1: Request Parameters Table */}
            {docSubTab === "params" && (
              <div className="overflow-x-auto rounded-xl border border-slate-200 bg-slate-50/50">
                <table className="w-full text-left text-xs">
                  <thead className="border-b border-slate-200 bg-slate-100/70 text-[11px] font-bold uppercase text-slate-500">
                    <tr>
                      <th className="px-3.5 py-2.5">{t("Field")}</th>
                      <th className="px-3.5 py-2.5">{t("Type & In")}</th>
                      <th className="px-3.5 py-2.5">{t("Required")}</th>
                      <th className="px-3.5 py-2.5">{t("Description")}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200/70 bg-white">
                    <tr className="hover:bg-slate-50/50">
                      <td className="px-3.5 py-2 font-mono font-bold text-slate-900">X-API-Key</td>
                      <td className="px-3.5 py-2 font-mono text-[11px] text-slate-500">string (header)</td>
                      <td className="px-3.5 py-2 font-semibold text-rose-600 text-[11px]">{t("Required")}</td>
                      <td className="px-3.5 py-2 text-slate-600 text-[11px]">Enterprise company API key.</td>
                    </tr>

                    {docEndpoint === "upload" && (
                      <>
                        <tr className="hover:bg-slate-50/50">
                          <td className="px-3.5 py-2 font-mono font-bold text-slate-900">file</td>
                          <td className="px-3.5 py-2 font-mono text-[11px] text-slate-500">binary (form)</td>
                          <td className="px-3.5 py-2 font-semibold text-rose-600 text-[11px]">{t("Required")}</td>
                          <td className="px-3.5 py-2 text-slate-600 text-[11px]">PDF or document (up to 5 MB and 3 pages).</td>
                        </tr>
                        <tr className="hover:bg-slate-50/50">
                          <td className="px-3.5 py-2 font-mono font-bold text-slate-900">ttl_minutes</td>
                          <td className="px-3.5 py-2 font-mono text-[11px] text-slate-500">integer (form)</td>
                          <td className="px-3.5 py-2 font-normal text-slate-400 text-[11px]">Optional (10)</td>
                          <td className="px-3.5 py-2 text-slate-600 text-[11px]">Sliding inactivity window in minutes.</td>
                        </tr>
                      </>
                    )}

                    {docEndpoint === "pipeline" && (
                      <>
                        <tr className="hover:bg-slate-50/50">
                          <td className="px-3.5 py-2 font-mono font-bold text-slate-900">service</td>
                          <td className="px-3.5 py-2 font-mono text-[11px] text-slate-500">string (body)</td>
                          <td className="px-3.5 py-2 font-semibold text-rose-600 text-[11px]">{t("Required")}</td>
                          <td className="px-3.5 py-2 text-slate-600 text-[11px]">
                            Target AI pipeline (e.g. <code className="text-teal-700">{serviceKey}</code>, <code>contract</code>, <code>compliance</code>).
                          </td>
                        </tr>
                        <tr className="hover:bg-slate-50/50">
                          <td className="px-3.5 py-2 font-mono font-bold text-slate-900">document_id</td>
                          <td className="px-3.5 py-2 font-mono text-[11px] text-slate-500">string (body)</td>
                          <td className="px-3.5 py-2 font-semibold text-rose-600 text-[11px]">{t("Required")}</td>
                          <td className="px-3.5 py-2 text-slate-600 text-[11px]">
                            Target session ID. <strong>⚡ Resets 10-minute inactivity timer.</strong>
                          </td>
                        </tr>
                        <tr className="hover:bg-slate-50/50">
                          <td className="px-3.5 py-2 font-mono font-bold text-slate-900">output_format</td>
                          <td className="px-3.5 py-2 font-mono text-[11px] text-slate-500">string (body)</td>
                          <td className="px-3.5 py-2 font-normal text-slate-400 text-[11px]">{t("Optional")}</td>
                          <td className="px-3.5 py-2 text-slate-600 text-[11px]">Defaults to <code>"json"</code>.</td>
                        </tr>
                      </>
                    )}

                    {docEndpoint === "ocr" && (
                      <>
                        <tr className="hover:bg-slate-50/50">
                          <td className="px-3.5 py-2 font-mono font-bold text-slate-900">document_id</td>
                          <td className="px-3.5 py-2 font-mono text-[11px] text-slate-500">string (body)</td>
                          <td className="px-3.5 py-2 font-normal text-slate-400 text-[11px]">Or file</td>
                          <td className="px-3.5 py-2 text-slate-600 text-[11px]">Active session ID. Resets 10-minute timer.</td>
                        </tr>
                        <tr className="hover:bg-slate-50/50">
                          <td className="px-3.5 py-2 font-mono font-bold text-slate-900">start_page</td>
                          <td className="px-3.5 py-2 font-mono text-[11px] text-slate-500">integer (body)</td>
                          <td className="px-3.5 py-2 font-normal text-slate-400 text-[11px]">Optional (1)</td>
                          <td className="px-3.5 py-2 text-slate-600 text-[11px]">1-indexed starting page.</td>
                        </tr>
                        <tr className="hover:bg-slate-50/50">
                          <td className="px-3.5 py-2 font-mono font-bold text-slate-900">language</td>
                          <td className="px-3.5 py-2 font-mono text-[11px] text-slate-500">string (body)</td>
                          <td className="px-3.5 py-2 font-normal text-slate-400 text-[11px]">{t("Optional")}</td>
                          <td className="px-3.5 py-2 text-slate-600 text-[11px]"><code>auto</code>, <code>ar</code>, <code>en</code>, or <code>mixed</code>.</td>
                        </tr>
                      </>
                    )}

                    {docEndpoint === "status" && (
                      <tr className="hover:bg-slate-50/50">
                        <td className="px-3.5 py-2 font-mono font-bold text-slate-900">id</td>
                        <td className="px-3.5 py-2 font-mono text-[11px] text-slate-500">path param</td>
                        <td className="px-3.5 py-2 font-semibold text-rose-600 text-[11px]">{t("Required")}</td>
                        <td className="px-3.5 py-2 text-slate-600 text-[11px]">The documentId to inspect.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            )}

            {/* SubTab 2: Response Schema Preview */}
            {docSubTab === "response" && (
              <div className="rounded-xl border border-slate-800 bg-[#0c1222] p-4 font-mono text-[11px] leading-relaxed text-emerald-400 shadow-inner overflow-auto max-h-72">
                <pre>{docEndpoint === "upload" ? `{
  "status": "success",
  "documentId": "4b7d11dd-fc1d-4d5b-aec4-9b0c7239ea17",
  "filename": "invoice_sample.pdf",
  "fileSize": 1048576,
  "pageCount": 4,
  "chunkCount": 12,
  "ttlMinutes": 10,
  "remainingSeconds": 600,
  "expiresAt": "2026-10-27T16:05:00Z",
  "creditsRemaining": 1175,
  "message": "Document session active. Retained for 10 minutes without usage."
}` : docEndpoint === "status" ? `{
  "status": "active",
  "documentId": "4b7d11dd-fc1d-4d5b-aec4-9b0c7239ea17",
  "filename": "invoice_sample.pdf",
  "ttlMinutes": 10,
  "remainingSeconds": 482,
  "isExpired": false,
  "expiresAt": "2026-10-27T16:05:00Z"
}` : `{
  "status": "success",
  "service": "${serviceKey}",
  "documentId": "${selectedDocId || "4b7d11dd-fc1d-4d5b-aec4-9b0c7239ea17"}",
  "creditsDeducted": 25,
  "creditsRemaining": 1150,
  "ttlMinutes": 10,
  "remainingSeconds": 600,
  "expiresAt": "2026-10-27T16:15:00Z",
  "data": {
    "vendor": "Global Tech Corp",
    "invoice_number": "INV-2026-991",
    "total": 4500.00,
    "line_items": [...]
  }
}`}</pre>
              </div>
            )}

            {/* SubTab 3: Status Codes & Error Handling */}
            {docSubTab === "lifecycle" && (
              <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 text-xs">
                <div className="rounded-lg border border-emerald-200 bg-emerald-50/60 p-3 space-y-0.5">
                  <div className="flex items-center gap-1.5 font-bold text-emerald-900 font-mono">
                    <span className="rounded bg-emerald-200 px-1.5 py-0.2 text-[10px]">200 OK</span>
                    <span>{t("Success")}</span>
                  </div>
                  <p className="text-[11px] text-emerald-800 leading-snug">
                    Processed successfully. Sliding inactivity timer renewed for 10 minutes.
                  </p>
                </div>

                <div className="rounded-lg border border-amber-200 bg-amber-50/60 p-3 space-y-0.5">
                  <div className="flex items-center gap-1.5 font-bold text-amber-900 font-mono">
                    <span className="rounded bg-amber-200 px-1.5 py-0.2 text-[10px]">410 GONE</span>
                    <span>{t("Session Expired")}</span>
                  </div>
                  <p className="text-[11px] text-amber-800 leading-snug">
                    Document inactive for &gt;10 min. Automatically purged. Upload new PDF.
                  </p>
                </div>

                <div className="rounded-lg border border-rose-200 bg-rose-50/60 p-3 space-y-0.5">
                  <div className="flex items-center gap-1.5 font-bold text-rose-900 font-mono">
                    <span className="rounded bg-rose-200 px-1.5 py-0.2 text-[10px]">402 PAYMENT</span>
                    <span>{t("Credits Needed")}</span>
                  </div>
                  <p className="text-[11px] text-rose-800 leading-snug">
                    Insufficient credit quota. Top up credits or request tier upgrade.
                  </p>
                </div>

                <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 space-y-0.5">
                  <div className="flex items-center gap-1.5 font-bold text-slate-800 font-mono">
                    <span className="rounded bg-slate-200 px-1.5 py-0.2 text-[10px]">422 UNPROCESSABLE</span>
                    <span>{t("Invalid Input")}</span>
                  </div>
                  <p className="text-[11px] text-slate-600 leading-snug">
                    Invalid PDF or corrupt range. Double check start_page and end_page.
                  </p>
                </div>
              </div>
            )}
          </div>

          {/* RIGHT 6 COLS: CODE GENERATOR & COPY BOX */}
          <div className="lg:col-span-6 flex flex-col space-y-3">
            {/* Language Switcher Bar */}
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="inline-flex rounded-xl border border-slate-200 bg-slate-100 p-1 text-xs font-semibold">
                <button
                  onClick={() => setApiModalTab("curl")}
                  className={`rounded-lg px-3 py-1.5 transition ${
                    apiModalTab === "curl"
                      ? "bg-white text-slate-900 font-bold shadow-2xs"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  cURL
                </button>
                <button
                  onClick={() => setApiModalTab("python")}
                  className={`rounded-lg px-3 py-1.5 transition ${
                    apiModalTab === "python"
                      ? "bg-white text-slate-900 font-bold shadow-2xs"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  Python
                </button>
                <button
                  onClick={() => setApiModalTab("typescript")}
                  className={`rounded-lg px-3 py-1.5 transition ${
                    apiModalTab === "typescript"
                      ? "bg-white text-slate-900 font-bold shadow-2xs"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  Node / TS
                </button>
                <button
                  onClick={() => {
                    setApiModalTab("full_workflow");
                    setDocEndpoint("multi_workflow");
                  }}
                  className={`rounded-lg px-3 py-1.5 transition ${
                    apiModalTab === "full_workflow"
                      ? "bg-white text-teal-800 font-bold shadow-2xs"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  {t("Multi-Service Script")}</button>
              </div>

              {/* Copy Code Button */}
              <button
                onClick={() => {
                  const code =
                    apiModalTab === "curl"
                      ? activeCurlCode
                      : apiModalTab === "python"
                      ? activePythonCode
                      : apiModalTab === "typescript"
                      ? activeTypescriptCode
                      : workflowCode;
                  handleCopyCode(code);
                }}
                className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-800 hover:text-white transition shadow-sm"
              >
                {codeCopied ? (
                  <>
                    <Check size={13} className="text-emerald-400" />
                    <span className="text-emerald-400 font-bold">{t("Copied!")}</span>
                  </>
                ) : (
                  <>
                    <Copy size={13} />
                    <span>{t("Copy Code")}</span>
                  </>
                )}
              </button>
            </div>

            {/* Dark Syntax Highlighted Editor */}
            <div className="relative rounded-2xl border border-slate-800 bg-[#080d19] p-4 text-xs font-mono text-emerald-300 shadow-xl overflow-hidden flex-1">
              <div className="flex items-center justify-between pb-3 mb-2 border-b border-slate-800 text-[10px] text-slate-400">
                <span className="flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                  {t("Ready to execute in terminal or backend service")}</span>
                <span className="font-mono text-slate-500">UTF-8 • REST</span>
              </div>

              <pre className="max-h-[380px] overflow-auto leading-relaxed whitespace-pre font-mono text-[12px] text-emerald-300 pr-2">
                {apiModalTab === "curl" && activeCurlCode}
                {apiModalTab === "python" && activePythonCode}
                {apiModalTab === "typescript" && activeTypescriptCode}
                {apiModalTab === "full_workflow" && workflowCode}
              </pre>
            </div>
          </div>
        </div>

        {/* FOOTER CALLOUT CARDS: AUTH, INACTIVITY TTL, AND LUNA ENGINE */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3 text-xs pt-2">
          <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-4 space-y-1.5">
            <div className="flex items-center gap-1.5 font-bold text-slate-800">
              <ShieldCheck size={15} className="text-emerald-600" />
              <span>{t("Authentication Header")}</span>
            </div>
            <p className="text-[11px] text-slate-500 font-mono">
              X-API-Key: {account?.apiKeyPrefix || "docu_live_"}••••••••••
            </p>
            <p className="text-[10px] text-slate-400">
              Pass via <code className="font-mono">X-API-Key</code> or <code className="font-mono">Authorization: Bearer</code> header.
            </p>
          </div>

          <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-4 space-y-1.5">
            <div className="flex items-center gap-1.5 font-bold text-slate-800">
              <Timer size={15} className="text-amber-600" />
              <span>{t("Configurable Sliding TTL")}</span>
            </div>
            <p className="text-[11px] text-slate-700 font-semibold">
              Default: 10 min without usage
            </p>
            <p className="text-[10px] text-slate-400">
              Configured via <code className="font-mono font-bold text-slate-600">DOC_TTL_MINUTES=10</code> in environment.
            </p>
          </div>

          <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-4 space-y-1.5">
            <div className="flex items-center gap-1.5 font-bold text-slate-800">
              <Terminal size={15} className="text-teal-700" />
              <span>{t("Active Model Engine")}</span>
            </div>
            <p className="text-[11px] text-slate-800 font-bold font-mono">
              Luna (gpt-6-luna)
            </p>
            <p className="text-[10px] text-slate-400">
              128k context, visual layout parsing &amp; deterministic structured JSON.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}
