"use client";

import { useEffect, useState } from "react";
import {
  Key,
  Copy,
  Check,
  RefreshCw,
  CreditCard,
  Sparkles,
  ShieldCheck,
  Terminal,
  History,
  Eye,
  EyeOff,
  AlertCircle,
  Zap,
  Coins,
} from "lucide-react";
import {
  CompanyAccountInfo,
  CompanyUsageResponse,
  PricingCatalogResponse,
  fetchCompanyAccount,
  fetchCompanyPricing,
  fetchCompanyUsage,
  regenerateCompanyApiKey,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { useModelSettings } from "@/components/providers/model-provider";
import { ModelSelectorButton } from "@/components/ui/model-selector";

export default function ApiUsagePage() {
  const { availableModels, selectedModel, openModelModal } = useModelSettings();
  const [account, setAccount] = useState<CompanyAccountInfo | null>(null);
  const [pricing, setPricing] = useState<PricingCatalogResponse | null>(null);
  const [usage, setUsage] = useState<CompanyUsageResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [showKey, setShowKey] = useState(false);
  const [copied, setCopied] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [activeCodeTab, setActiveCodeTab] = useState<"curl" | "python" | "typescript">("curl");
  const [error, setError] = useState("");

  const loadData = async () => {
    try {
      const [accData, pricingData, usageData] = await Promise.all([
        fetchCompanyAccount(),
        fetchCompanyPricing(),
        fetchCompanyUsage(),
      ]);
      setAccount(accData);
      setPricing(pricingData);
      setUsage(usageData);
    } catch {
      setError("Failed to load company billing and API usage details.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleCopy = () => {
    if (!account) return;
    const keyToCopy = account.rawApiKey || account.apiKey;
    navigator.clipboard.writeText(keyToCopy);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleRegenerate = async () => {
    if (
      !confirm(
        "Are you sure you want to regenerate your company API key? Any existing backend integrations using the current key will stop working."
      )
    ) {
      return;
    }
    setRegenerating(true);
    setError("");
    try {
      const res = await regenerateCompanyApiKey();
      setAccount((prev) =>
        prev
          ? {
              ...prev,
              apiKey: res.apiKey,
              rawApiKey: res.apiKey,
              apiKeyPrefix: res.apiKeyPrefix,
              remainingCredits: res.remainingCredits,
            }
          : null
      );
      setShowKey(true);
    } catch {
      setError("Failed to regenerate API key. Please try again.");
    } finally {
      setRegenerating(false);
    }
  };

  if (loading) {
    return (
      <div className="py-20 text-center">
        <Spinner size={32} />
      </div>
    );
  }

  const remaining = account?.remainingCredits ?? 300;
  const total = account?.totalCredits ?? 300;
  const used = account?.usedCredits ?? 0;
  const percentRemaining = Math.max(0, Math.min(100, Math.round((remaining / total) * 100)));

  const displayKey = account?.rawApiKey || account?.apiKey || "docu_live_••••••••••••••••••••••••";
  const maskedKey = `${account?.apiKeyPrefix || "docu_live_"}••••••••••••••••••••••••${displayKey.slice(-4)}`;

  return (
    <div className="mx-auto max-w-6xl animate-enter pb-16">
      {/* Header */}
      <div className="mb-8">
        <p className="eyebrow mb-2">Company / API Usage & Billing</p>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-[28px] font-bold tracking-tight text-slate-900 dark:text-white">
              Company API Usage & Credit Quota
            </h1>
            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
              Enterprise API access with automated credit billing per LLM compute usage.
            </p>
          </div>
          <div>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-3.5 py-1 text-xs font-semibold text-emerald-800 shadow-xs dark:border-emerald-800/60 dark:bg-emerald-950/40 dark:text-emerald-300">
              <Zap size={14} className="text-emerald-600" /> Free Trial Tier Available Only
            </span>
          </div>
        </div>
      </div>

      {error && (
        <div role="alert" className="mb-6 flex items-center gap-2 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          <AlertCircle size={17} /> {error}
        </div>
      )}

      {/* Credit Balance Card */}
      <div className="mb-8 overflow-hidden rounded-2xl border border-slate-200 bg-white p-6 shadow-xs dark:border-slate-800 dark:bg-[#121820]">
        <div className="grid gap-6 md:grid-cols-12 md:items-center">
          <div className="md:col-span-7">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              <CreditCard size={15} className="text-emerald-600 dark:text-emerald-400" /> Free Trial Credit Quota
            </div>
            <div className="mt-2 flex items-baseline gap-3">
              <span className="text-4xl font-extrabold tracking-tight text-slate-900 dark:text-white">
                {remaining.toLocaleString()}
              </span>
              <span className="text-sm font-medium text-slate-500 dark:text-slate-400">
                / {total.toLocaleString()} credits remaining
              </span>
            </div>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              Every company receives <strong>300 starting credits</strong> to run all enterprise Document AI services.
            </p>

            {/* Visual Progress Bar */}
            <div className="mt-4">
              <div className="flex justify-between text-xs font-medium text-slate-600 dark:text-slate-300 mb-1.5">
                <span>{percentRemaining}% credits available</span>
                <span>{used.toLocaleString()} credits consumed</span>
              </div>
              <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-teal-600 to-emerald-500 transition-all duration-500"
                  style={{ width: `${percentRemaining}%` }}
                />
              </div>
            </div>
          </div>

          <div className="flex flex-col gap-3 rounded-xl border border-slate-100 bg-slate-50/70 p-4 md:col-span-5 dark:border-slate-800 dark:bg-slate-900/60">
            <div className="flex items-center justify-between text-xs">
              <span className="text-slate-500 dark:text-slate-400">Account Plan</span>
              <span className="font-semibold text-slate-800 dark:text-slate-200">Company Free Trial</span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-slate-500 dark:text-slate-400">Trial Credits Included</span>
              <span className="font-semibold text-emerald-600 dark:text-emerald-400">300 Credits</span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-slate-500 dark:text-slate-400">Active API Keys</span>
              <span className="font-semibold text-slate-800 dark:text-slate-200">1 Live Key</span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-slate-500 dark:text-slate-400">Billing Model</span>
              <span className="font-semibold text-slate-800 dark:text-slate-200">Pay-per-Service Usage</span>
            </div>
          </div>
        </div>
      </div>

      {/* API Key Management Box */}
      <div className="mb-8 rounded-2xl border border-slate-200 bg-white p-6 shadow-xs dark:border-slate-800 dark:bg-[#121820]">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-50 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300">
              <Key size={18} />
            </div>
            <div>
              <h2 className="text-base font-semibold text-slate-900 dark:text-white">Company API Key</h2>
              <p className="text-xs text-slate-500 dark:text-slate-400">Use this secret key to authenticate corporate API requests.</p>
            </div>
          </div>
          <Button
            onClick={handleRegenerate}
            disabled={regenerating}
            className="flex items-center gap-1.5 border border-slate-200 bg-white text-xs font-semibold text-slate-700 hover:bg-slate-50 shadow-xs dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            <RefreshCw size={13} className={regenerating ? "animate-spin" : ""} />
            {regenerating ? "Rolling key…" : "Regenerate Key"}
          </Button>
        </div>

        <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="relative flex-1">
            <input
              type="text"
              readOnly
              value={showKey ? displayKey : maskedKey}
              className="w-full font-mono text-xs rounded-xl border border-slate-200 bg-slate-50/80 px-4 py-3 text-slate-800 outline-none focus:border-emerald-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200"
            />
            <button
              onClick={() => setShowKey(!showKey)}
              className="absolute right-3 top-3 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
              title={showKey ? "Hide key" : "Reveal key"}
            >
              {showKey ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </div>
          <Button
            onClick={handleCopy}
            className="flex shrink-0 items-center gap-2 bg-slate-900 text-white hover:bg-slate-800 dark:bg-emerald-600 dark:hover:bg-emerald-500 dark:text-slate-950 font-bold"
          >
            {copied ? <Check size={16} className="text-emerald-400 dark:text-slate-950" /> : <Copy size={16} />}
            {copied ? "Copied to clipboard" : "Copy API Key"}
          </Button>
        </div>

        <div className="mt-3 flex items-center gap-1.5 text-[11px] text-slate-500 dark:text-slate-400">
          <ShieldCheck size={13} className="text-emerald-600 dark:text-emerald-400" />
          Pass your key in the header: <code className="rounded bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 text-slate-700 dark:text-slate-300">X-API-Key: {account?.apiKeyPrefix || "docu_live_"}...</code> or <code className="rounded bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 text-slate-700 dark:text-slate-300">Authorization: Bearer &lt;key&gt;</code>
        </div>
      </div>

      {/* Pricing Catalog based on LLM Usage */}
      <div className="mb-8 rounded-2xl border border-slate-200 bg-white p-6 shadow-xs">
        <div className="mb-4">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
            <Sparkles size={14} className="text-teal-700" /> Service Pricing Catalog
          </div>
          <h2 className="mt-1 text-lg font-semibold text-slate-900">
            Credit Cost per Service (Based on LLM Usage)
          </h2>
          <p className="text-xs text-slate-500">
            Pricing is automatically weighted by model inference cost, multimodal processing, and reasoning steps.
          </p>
        </div>

        <div className="overflow-x-auto rounded-xl border border-slate-100">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-slate-200 bg-slate-50 text-slate-600 uppercase tracking-wider font-semibold">
              <tr>
                <th className="px-4 py-3">Document AI Service</th>
                <th className="px-4 py-3">Category</th>
                <th className="px-4 py-3">LLM Compute Tier</th>
                <th className="px-4 py-3">Cost / Call</th>
                <th className="px-4 py-3 text-right">Free Trial Capacity</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {pricing?.services.map((item) => {
                const callsCapacity = Math.floor((account?.totalCredits ?? 300) / item.credits);
                return (
                  <tr key={item.id} className="hover:bg-slate-50/50 transition">
                    <td className="px-4 py-3 font-medium text-slate-900">
                      <div>{item.name}</div>
                      <div className="text-[10px] text-slate-400 font-normal">{item.description}</div>
                    </td>
                    <td className="px-4 py-3 text-slate-500">{item.category}</td>
                    <td className="px-4 py-3">
                      <span className="inline-flex rounded-md bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-700">
                        {item.llmTier}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-semibold text-emerald-700">
                      {item.credits} credits
                    </td>
                    <td className="px-4 py-3 text-right text-slate-500">
                      ~{callsCapacity} calls
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Superset & OpenAI Model Economics Catalog (from models.json) */}
      <div className="mb-8 rounded-2xl border border-slate-200 bg-white p-6 shadow-xs">
        <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
              <Coins size={14} className="text-emerald-600" /> LLM Model Economics &amp; Pricing (models.json)
            </div>
            <h2 className="mt-1 text-lg font-semibold text-slate-900">
              Model Inference Rates ($2.00 USD = 1,000 Credits)
            </h2>
            <p className="text-xs text-slate-500">
              Every Document AI request strictly uses models from models.json. 1 credit = $0.002 USD (500 cr / $1.00).
            </p>
          </div>
          <ModelSelectorButton size="sm" />
        </div>

        <div className="overflow-x-auto rounded-xl border border-slate-100">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-slate-200 bg-slate-50 text-slate-600 uppercase tracking-wider font-semibold text-[10px]">
              <tr>
                <th className="px-4 py-3">Model Name &amp; ID</th>
                <th className="px-4 py-3">Speed &amp; Reasoning Tier</th>
                <th className="px-4 py-3 text-right">Credit Fee / Run</th>
                <th className="px-4 py-3 text-right">USD Equivalent</th>
                <th className="px-4 py-3 text-right">Input ($ / 1M)</th>
                <th className="px-4 py-3 text-right">Output ($ / 1M)</th>
                <th className="px-4 py-3 text-center">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700 font-mono text-[11px]">
              {availableModels.map((m) => {
                const isSelected = selectedModel === m.id;
                const costUsd = (m.credit_cost * 0.002).toFixed(3);
                return (
                  <tr
                    key={m.id}
                    className={`transition ${
                      isSelected ? "bg-emerald-50/50 font-bold" : "hover:bg-slate-50/50"
                    }`}
                  >
                    <td className="px-4 py-3 font-medium text-slate-900">
                      <div>{m.name}</div>
                      <div className="text-[10px] text-slate-400 font-normal">{m.id}</div>
                    </td>
                    <td className="px-4 py-3 font-sans">
                      <span className="rounded bg-slate-100 px-2 py-0.5 text-[10px] text-slate-700">
                        {m.speed_tier} • {m.reasoning_tier}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right font-bold text-emerald-700">
                      {m.credit_cost} cr
                    </td>
                    <td className="px-4 py-3 text-right text-slate-800">
                      ${costUsd}
                    </td>
                    <td className="px-4 py-3 text-right text-slate-500">
                      ${m.pricing?.input_per_million}/M
                    </td>
                    <td className="px-4 py-3 text-right text-slate-500">
                      ${m.pricing?.output_per_million}/M
                    </td>
                    <td className="px-4 py-3 text-center font-sans">
                      {isSelected ? (
                        <span className="inline-flex items-center gap-1 rounded bg-emerald-600 px-2 py-0.5 text-[10px] font-semibold text-white">
                          Active
                        </span>
                      ) : (
                        <button
                          type="button"
                          onClick={() => openModelModal()}
                          className="text-[10px] text-slate-500 hover:text-emerald-700 hover:underline"
                        >
                          Select
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Developer Quickstart & Code Examples */}
      <div className="mb-8 rounded-2xl border border-slate-200 bg-white p-6 shadow-xs">
        <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2">
            <Terminal size={17} className="text-teal-700" />
            <h2 className="text-base font-semibold text-slate-900">Developer API Quickstart</h2>
          </div>
          <div className="flex gap-1.5 rounded-lg border border-slate-200 bg-slate-100 p-1">
            <button
              onClick={() => setActiveCodeTab("curl")}
              className={`rounded px-3 py-1 text-xs font-semibold transition ${
                activeCodeTab === "curl" ? "bg-white text-slate-900 shadow-xs" : "text-slate-500 hover:text-slate-900"
              }`}
            >
              cURL
            </button>
            <button
              onClick={() => setActiveCodeTab("python")}
              className={`rounded px-3 py-1 text-xs font-semibold transition ${
                activeCodeTab === "python" ? "bg-white text-slate-900 shadow-xs" : "text-slate-500 hover:text-slate-900"
              }`}
            >
              Python
            </button>
            <button
              onClick={() => setActiveCodeTab("typescript")}
              className={`rounded px-3 py-1 text-xs font-semibold transition ${
                activeCodeTab === "typescript" ? "bg-white text-slate-900 shadow-xs" : "text-slate-500 hover:text-slate-900"
              }`}
            >
              TypeScript / Node
            </button>
          </div>
        </div>

        <div className="overflow-hidden rounded-xl bg-slate-900 p-4 text-xs font-mono text-emerald-400 shadow-inner">
          {activeCodeTab === "curl" && (
            <pre className="overflow-x-auto leading-relaxed">
{`# Execute Document AI Pipeline with company API key
curl -X POST "http://localhost:8000/api/v1/pipeline/run" \\
  -H "X-API-Key: ${displayKey}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "service": "invoice",
    "document_id": "YOUR_DOCUMENT_UUID",
    "output_format": "json"
  }'`}
            </pre>
          )}

          {activeCodeTab === "python" && (
            <pre className="overflow-x-auto leading-relaxed">
{`import requests

url = "http://localhost:8000/api/v1/pipeline/run"
headers = {
    "X-API-Key": "${displayKey}",
    "Content-Type": "application/json"
}
payload = {
    "service": "invoice",
    "document_id": "YOUR_DOCUMENT_UUID",
    "output_format": "json"
}

response = requests.post(url, headers=headers, json=payload)
data = response.json()

print(f"Status: {data['status']}")
print(f"Credits Remaining: {data['creditsRemaining']}")
print(f"Extracted Data: {data.get('data')}")`}
            </pre>
          )}

          {activeCodeTab === "typescript" && (
            <pre className="overflow-x-auto leading-relaxed">
{`// Run in Node.js, Next.js API route, or AWS Lambda
async function extractDocumentData() {
  const response = await fetch("http://localhost:8000/api/v1/pipeline/run", {
    method: "POST",
    headers: {
      "X-API-Key": "${displayKey}",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      service: "invoice",
      document_id: "YOUR_DOCUMENT_UUID",
      output_format: "json",
    }),
  });

  const result = await response.json();
  console.log("Structured JSON:", result.data);
  return result.data;
}

extractDocumentData().catch(console.error);`}
            </pre>
          )}
        </div>
      </div>

      {/* Enterprise SaaS API Endpoints Reference */}
      <div className="mb-8 rounded-2xl border border-slate-200 bg-white p-6 shadow-xs">
        <div className="mb-4">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
            <Sparkles size={14} className="text-teal-700" /> API Architecture
          </div>
          <h2 className="mt-1 text-lg font-semibold text-slate-900">
            Core Enterprise SaaS Endpoints
          </h2>
          <p className="text-xs text-slate-500">
            Unified REST endpoints for ETL ingestion, asynchronous queue processing, and OCR layout inspection.
          </p>
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-4 space-y-1.5">
            <div className="flex items-center gap-2 font-mono text-xs font-semibold text-slate-900">
              <span className="rounded bg-teal-100 px-1.5 py-0.5 text-teal-800 text-[10px] font-bold">POST</span>
              <span>/api/v1/ocr/advanced</span>
            </div>
            <p className="text-xs text-slate-600">
              Direct stateless PDF upload. Extracts layout-aware semantic blocks (text, tables, formulas, visuals) with page continuity without saving files.
            </p>
          </div>

          <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-4 space-y-1.5">
            <div className="flex items-center gap-2 font-mono text-xs font-semibold text-slate-900">
              <span className="rounded bg-teal-100 px-1.5 py-0.5 text-teal-800 text-[10px] font-bold">POST</span>
              <span>/api/v1/pipeline/run</span>
            </div>
            <p className="text-xs text-slate-600">
              Run any document AI service (invoice, contract, resume, receipt, compliance, tables) synchronously or asynchronously with custom schema &amp; prompts.
            </p>
          </div>

          <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-4 space-y-1.5">
            <div className="flex items-center gap-2 font-mono text-xs font-semibold text-slate-900">
              <span className="rounded bg-blue-100 px-1.5 py-0.5 text-blue-800 text-[10px] font-bold">GET</span>
              <span>/api/v1/models</span>
            </div>
            <p className="text-xs text-slate-600">
              List available AI models strictly loaded from <code className="text-emerald-700 font-semibold font-mono">models.json</code> with token pricing and credit conversion ($2.00 USD = 1,000 Credits).
            </p>
          </div>

          <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-4 space-y-1.5">
            <div className="flex items-center gap-2 font-mono text-xs font-semibold text-slate-900">
              <span className="rounded bg-blue-100 px-1.5 py-0.5 text-blue-800 text-[10px] font-bold">GET</span>
              <span>/api/v1/company/pricing</span>
            </div>
            <p className="text-xs text-slate-600">
              Retrieve full pricing catalog across all 19 Document AI services, LLM compute tiers, and free trial allocations (300 credits).
            </p>
          </div>
        </div>
      </div>

      {/* Audit Usage History */}
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs">
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <History size={16} className="text-teal-700" />
            <h2 className="text-base font-semibold text-slate-900">Recent API Transactions</h2>
          </div>
          <span className="text-xs text-slate-400">{usage?.logs.length || 0} calls recorded</span>
        </div>

        {usage?.logs.length === 0 ? (
          <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50/50 py-10 text-center text-xs text-slate-500">
            No API calls recorded yet. Make your first request using your company API key.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-slate-100 bg-slate-50/50 font-semibold text-slate-500">
                <tr>
                  <th className="px-4 py-2.5">Date & Time</th>
                  <th className="px-4 py-2.5">Service</th>
                  <th className="px-4 py-2.5">Document</th>
                  <th className="px-4 py-2.5">Credits Cost</th>
                  <th className="px-4 py-2.5">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {usage?.logs.map((log) => (
                  <tr key={log.id} className="hover:bg-slate-50/50 transition">
                    <td className="px-4 py-2.5 text-slate-400 font-mono text-[11px]">
                      {log.createdAt ? new Date(log.createdAt).toLocaleString() : "Just now"}
                    </td>
                    <td className="px-4 py-2.5 font-semibold text-slate-900 capitalize">
                      {log.serviceName.replace("_", " ")}
                    </td>
                    <td className="px-4 py-2.5 font-mono text-[11px] text-slate-500">
                      {log.documentId ? `${log.documentId.slice(0, 8)}…` : "—"}
                    </td>
                    <td className="px-4 py-2.5 font-semibold text-rose-600">
                      -{log.creditsCost}
                    </td>
                    <td className="px-4 py-2.5">
                      <span className="inline-flex items-center gap-1 rounded bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-700">
                        {log.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
