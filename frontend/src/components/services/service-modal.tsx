"use client";
import { getUploadSizeError, UPLOAD_LIMIT_LABEL } from "@/lib/upload-limits";

import { useState, useRef, useMemo, useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  X,
  UploadCloud,
  HardDrive,
  FileText,
  FileSpreadsheet,
  FileCode,
  Search,
  CheckCircle2,
  Sparkles,
  ArrowRight,
  Play,
  MessageSquare,
  Copy,
  Check,
  AlertCircle,
  Coins,
  FileJson,
  Table2,
  Code2,
  ShieldCheck,
  ShieldAlert,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import {
  createSession,
  uploadDocument,
  runDocumentService,
  ApiError,
  type DocumentAIServiceResponse,
} from "@/lib/api";
import { formatBytes } from "@/lib/utils";
import type { Document } from "@/lib/types";
import { useModelSettings } from "@/components/providers/model-provider";
import { getModelIcon } from "@/components/ui/model-selector";

export interface ServiceCardInfo {
  id: string;
  title: string;
  category: string;
  description: string;
  badge: string;
  credits: number;
  llmTier: string;
  icon: React.ReactNode;
  workflowId: string;
  color: string;
  detail: string;
}

interface ServiceLauncherModalProps {
  service: ServiceCardInfo | null;
  open: boolean;
  onClose: () => void;
  docs: Document[];
  onDocumentAdded: (doc: Document) => void;
  remainingCredits?: number;
}

export function ServiceLauncherModal({
  service,
  open,
  onClose,
  docs,
  onDocumentAdded,
  remainingCredits,
}: ServiceLauncherModalProps) {
  const router = useRouter();
  const { availableModels, selectedModel, guardianMode, calculateCost } = useModelSettings();
  const [modalModel, setModalModel] = useState<string>(selectedModel);
  const [modalGuardian, setModalGuardian] = useState<boolean>(guardianMode);

  useEffect(() => {
    setModalModel(selectedModel);
  }, [selectedModel]);

  useEffect(() => {
    setModalGuardian(guardianMode);
  }, [guardianMode]);

  // Tab: 'upload'
  const [sourceTab, setSourceTab] = useState<"drive" | "upload">("upload");
  const [selectedDocId, setSelectedDocId] = useState<string>("");
  const [searchFilter, setSearchFilter] = useState("");

  // Local file upload states
  const [localFile, setLocalFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Direct run states
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState("");
  const [runResult, setRunResult] = useState<DocumentAIServiceResponse | null>(null);
  const [resultTab, setResultTab] = useState<"structured" | "json" | "raw">("json");
  const [copied, setCopied] = useState(false);

  // Reset state when opening/closing
  const handleClose = () => {
    setRunResult(null);
    setRunError("");
    setLocalFile(null);
    setUploadError("");
    onClose();
  };

  // Filter existing drive documents
  const filteredDocs = useMemo(() => {
    if (!searchFilter.trim()) return docs;
    const q = searchFilter.toLowerCase().trim();
    return docs.filter(
      (d) =>
        d.originalFilename.toLowerCase().includes(q) ||
        (d.filename && d.filename.toLowerCase().includes(q)),
    );
  }, [docs, searchFilter]);

  // Selected document object
  const activeDoc = useMemo(() => {
    return docs.find((d) => d.id === selectedDocId) || null;
  }, [docs, selectedDocId]);

  // File selection for upload
  const onFileSelect = (f: File | null) => {
    if (uploading) return;
    setUploadError("");
    setLocalFile(null);
    if (!f) return;
    if (!/\.(pdf|docx|xlsx|xls|csv|txt|md)$/i.test(f.name)) {
      setUploadError("Choose a PDF, Word (.docx), Excel (.xlsx / .xls), CSV, TXT, or Markdown file.");
      return;
    }
    const sizeError = getUploadSizeError(f);
    if (sizeError) {
      setUploadError(sizeError);
      return;
    }
    setLocalFile(f);
  };

  // Upload local document and select it
  const handleUploadLocal = async () => {
    if (!localFile) return;
    setUploading(true);
    setUploadError("");
    try {
      const res = await uploadDocument(localFile);
      const newDoc: Document = {
        id: res.id,
        userId: "",
        filename: res.filename,
        originalFilename: localFile.name,
        fileSize: localFile.size,
        mimeType: localFile.type || "application/octet-stream",
        pageCount: res.pageCount || 1,
        createdAt: new Date().toISOString(),
      };
      onDocumentAdded(newDoc);
      setSelectedDocId(newDoc.id);
      setLocalFile(null);
      setSourceTab("upload");
    } catch (err) {
      setUploadError(
        err instanceof ApiError ? err.message : "Upload failed. Please try again.",
      );
    } finally {
      setUploading(false);
    }
  };

  // Start conversational session
  const handleStartChatSession = async () => {
    if (!activeDoc || !service) return;
    setRunning(true);
    setRunError("");
    try {
      const title = `${service.title} — ${activeDoc.originalFilename}`;
      const session = await createSession(activeDoc.id, title);
      router.push(`/chat/${session.id}?workflow=${service.workflowId}`);
    } catch (err) {
      setRunError(
        err instanceof ApiError ? err.message : "Could not create session. Please try again.",
      );
      setRunning(false);
    }
  };

  // Direct one-click run
  const handleDirectRun = async () => {
    if (!activeDoc || !service) return;
    setRunning(true);
    setRunError("");
    setRunResult(null);
    try {
      const res = await runDocumentService(activeDoc.id, service.id, {
        model: modalModel || selectedModel,
        guardian: modalGuardian,
      });
      setRunResult(res);
    } catch (err) {
      setRunError(
        err instanceof ApiError ? err.message : "Service execution encountered an error.",
      );
    } finally {
      setRunning(false);
    }
  };

  const jsonData = useMemo(() => {
    if (!runResult) return null;
    if (runResult.data && typeof runResult.data === "object") {
      return runResult.data;
    }
    if (runResult.result) {
      try {
        const parsed = JSON.parse(runResult.result);
        if (typeof parsed === "object") return parsed;
      } catch {
        const match = runResult.result.match(/```(?:json)?\s*([\s\S]*?)\s*```/);
        if (match) {
          try {
            return JSON.parse(match[1]);
          } catch {}
        }
      }
    }
    return null;
  }, [runResult]);

  const copyResult = () => {
    if (!runResult?.result) return;
    navigator.clipboard.writeText(runResult.result);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const copyJson = () => {
    const textToCopy = jsonData ? JSON.stringify(jsonData, null, 2) : runResult?.result || "";
    if (!textToCopy) return;
    navigator.clipboard.writeText(textToCopy);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (!open || !service) return null;

  const getDocIcon = (filename: string) => {
    if (/\.(xlsx|xls|csv)$/i.test(filename)) {
      return <FileSpreadsheet size={18} className="text-emerald-600" />;
    }
    if (/\.docx$/i.test(filename)) {
      return <FileCode size={18} className="text-blue-600" />;
    }
    return <FileText size={18} className="text-teal-700" />;
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4 backdrop-blur-sm animate-enter">
      <div className="relative flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl">
        {/* Header */}
        <div className="flex items-start justify-between border-b border-slate-100 p-6 pb-4">
          <div className="flex items-center gap-3.5">
            <span
              className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-xl shadow-xs ${service.color}`}
            >
              {service.icon}
            </span>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-bold text-slate-900">{service.title}</h2>
                <span className="rounded-md bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-600 uppercase">
                  {service.badge}
                </span>
                <span className="inline-flex items-center gap-1 rounded bg-teal-50 px-2 py-0.5 text-[10px] font-semibold text-teal-700 border border-teal-100">
                  <Coins size={10} /> {service.credits} credits
                </span>
              </div>
              <p className="mt-1 text-xs text-slate-500">{service.description}</p>
            </div>
          </div>
          <button
            onClick={handleClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </div>

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-6 pt-4 space-y-5">
          {/* Direct Run Result Screen */}
          {runResult ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between rounded-lg bg-emerald-50 p-3 text-xs text-emerald-800 border border-emerald-200">
                <div className="flex items-center gap-2">
                  <CheckCircle2 size={16} className="text-emerald-600" />
                  <span className="font-semibold">Analysis completed successfully!</span>
                </div>
                <div className="flex items-center gap-2">
                  {jsonData && (
                    <button
                      onClick={copyJson}
                      className="inline-flex items-center gap-1 font-semibold text-teal-800 bg-teal-100 hover:bg-teal-200 px-2.5 py-1 rounded transition-colors"
                      title="Copy structured JSON"
                    >
                      {copied ? <Check size={12} /> : <FileJson size={12} />}
                      {copied ? "Copied JSON" : "Copy JSON"}
                    </button>
                  )}
                  <button
                    onClick={copyResult}
                    className="inline-flex items-center gap-1 font-medium text-emerald-900 hover:underline"
                  >
                    {copied ? <Check size={13} /> : <Copy size={13} />}
                    {copied ? "Copied" : "Copy output"}
                  </button>
                </div>
              </div>

              {/* Superset Execution Telemetry Strip */}
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 rounded-xl border border-slate-200 bg-slate-50 p-2.5 dark:border-slate-800 dark:bg-slate-900 text-center font-mono text-xs">
                <div>
                  <span className="block text-[10px] text-slate-400 font-sans uppercase">Model Used</span>
                  <span className="font-semibold text-slate-800 dark:text-slate-200 truncate block">
                    {runResult.model || modalModel}
                  </span>
                </div>
                <div>
                  <span className="block text-[10px] text-slate-400 font-sans uppercase">Guardian Mode</span>
                  <span className={`font-bold truncate block ${runResult.guardianEnabled !== false ? "text-emerald-600 dark:text-emerald-400" : "text-amber-500"}`}>
                    {runResult.guardianEnabled !== false ? "Verified (+5cr)" : "Direct (Waived)"}
                  </span>
                </div>
                <div>
                  <span className="block text-[10px] text-slate-400 font-sans uppercase">Deducted</span>
                  <span className="font-bold text-amber-600 dark:text-amber-400">
                    {runResult.creditsDeducted ?? 0} cr
                  </span>
                </div>
                <div>
                  <span className="block text-[10px] text-slate-400 font-sans uppercase">USD Value</span>
                  <span className="font-bold text-emerald-600 dark:text-emerald-400">
                    ${((runResult.creditsDeducted ?? 0) * 0.002).toFixed(3)}
                  </span>
                </div>
                <div>
                  <span className="block text-[10px] text-slate-400 font-sans uppercase">Balance</span>
                  <span className="font-semibold text-slate-700 dark:text-slate-300">
                    {runResult.creditsRemaining ?? 0} cr
                  </span>
                </div>
              </div>

              {/* Result View Tabs */}
              {jsonData && (
                <div className="flex items-center gap-1 border-b border-slate-200 pb-2">
                  <button
                    type="button"
                    onClick={() => setResultTab("json")}
                    className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${
                      resultTab === "json"
                        ? "bg-slate-900 text-white shadow-xs"
                        : "text-slate-600 hover:bg-slate-100"
                    }`}
                  >
                    <FileJson size={13} /> JSON Payload
                  </button>
                  <button
                    type="button"
                    onClick={() => setResultTab("structured")}
                    className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${
                      resultTab === "structured"
                        ? "bg-teal-700 text-white shadow-xs"
                        : "text-slate-600 hover:bg-slate-100"
                    }`}
                  >
                    <Table2 size={13} /> Structured Cards
                  </button>
                  <button
                    type="button"
                    onClick={() => setResultTab("raw")}
                    className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${
                      resultTab === "raw"
                        ? "bg-slate-200 text-slate-800 shadow-xs"
                        : "text-slate-600 hover:bg-slate-100"
                    }`}
                  >
                    <Code2 size={13} /> Raw Output
                  </button>
                </div>
              )}

              {/* View Content */}
              {resultTab === "json" && jsonData ? (
                <div className="rounded-xl border border-slate-800 bg-slate-950 p-4 font-mono text-xs text-emerald-400 max-h-80 overflow-y-auto whitespace-pre leading-relaxed shadow-inner">
                  {JSON.stringify(jsonData, null, 2)}
                </div>
              ) : resultTab === "structured" && jsonData ? (
                <div className="space-y-3 max-h-80 overflow-y-auto pr-1">
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                    {Object.entries(jsonData)
                      .filter(([k]) => !["line_items", "items", "raw", "raw_text", "steps"].includes(k))
                      .slice(0, 9)
                      .map(([k, v]) => (
                        <div key={k} className="rounded-lg border border-slate-200 bg-white p-2.5 shadow-xs">
                          <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                            {k.replace(/_/g, " ")}
                          </p>
                          <p className="mt-1 text-xs font-semibold text-slate-800 truncate" title={typeof v === "object" ? JSON.stringify(v) : String(v)}>
                            {typeof v === "object" ? (v && (v as any).name ? String((v as any).name) : JSON.stringify(v)) : String(v ?? "—")}
                          </p>
                        </div>
                      ))}
                  </div>

                  {/* Line Items Table if available */}
                  {(Array.isArray(jsonData.line_items) || Array.isArray(jsonData.items)) && (
                    <div className="mt-3 overflow-hidden rounded-lg border border-slate-200">
                      <div className="bg-slate-100 px-3 py-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-600">
                        Line Items Breakdown
                      </div>
                      <div className="overflow-x-auto">
                        <table className="w-full text-left text-xs">
                          <thead className="bg-slate-50 text-slate-600 font-semibold border-b border-slate-100">
                            <tr>
                              <th className="p-2">Description</th>
                              <th className="p-2 text-center">Qty</th>
                              <th className="p-2 text-right">Price</th>
                              <th className="p-2 text-right">Amount</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-100 bg-white">
                            {(jsonData.line_items || jsonData.items).map((item: any, idx: number) => (
                              <tr key={idx} className="hover:bg-slate-50">
                                <td className="p-2 font-medium text-slate-800">
                                  {item.description || item.item || item.name || `Item ${idx + 1}`}
                                </td>
                                <td className="p-2 text-center text-slate-600">
                                  {item.quantity || item.qty || 1}
                                </td>
                                <td className="p-2 text-right text-slate-600">
                                  {item.unit_price || item.price || "—"}
                                </td>
                                <td className="p-2 text-right font-semibold text-slate-900">
                                  {item.amount || item.total || "—"}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-4 font-mono text-xs text-slate-800 max-h-72 overflow-y-auto whitespace-pre-wrap leading-relaxed shadow-inner">
                  {runResult.result}
                </div>
              )}

              <div className="flex items-center justify-between pt-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setRunResult(null)}
                >
                  Run another document
                </Button>
                <Button
                  size="sm"
                  onClick={handleStartChatSession}
                  className="gap-2"
                >
                  <MessageSquare size={14} /> Open full chat session
                </Button>
              </div>
            </div>
          ) : (
            <>
              {/* Document Source Selection Tabs */}
              <div>
                <p className="mb-2 text-xs font-semibold text-slate-700">
                  Step 1: Choose Document Source
                </p>
                <div className="grid grid-cols-2 gap-2 rounded-xl bg-slate-100 p-1 text-xs font-medium">
                  <button
                    onClick={() => setSourceTab("drive")}
                    className={`flex items-center justify-center gap-2 rounded-lg py-2 transition ${
                      sourceTab === "drive"
                        ? "bg-white text-slate-900 shadow-xs"
                        : "text-slate-600 hover:text-slate-900"
                    }`}
                  >
                    <HardDrive size={15} className="text-teal-600" />
                    <span>From Workspace Drive ({docs.length})</span>
                  </button>
                  <button
                    onClick={() => setSourceTab("upload")}
                    className={`flex items-center justify-center gap-2 rounded-lg py-2 transition ${
                      sourceTab === "upload"
                        ? "bg-white text-slate-900 shadow-xs"
                        : "text-slate-600 hover:text-slate-900"
                    }`}
                  >
                    <UploadCloud size={15} className="text-teal-600" />
                    <span>Upload Local File</span>
                  </button>
                </div>
              </div>

              {/* Source Tab 1: Drive Documents List */}
              {sourceTab === "drive" && (
                <div className="space-y-3">
                  <div className="relative">
                    <Search
                      size={14}
                      className="absolute left-3 top-2.5 text-slate-400"
                    />
                    <input
                      type="text"
                      placeholder="Search existing documents in drive…"
                      value={searchFilter}
                      onChange={(e) => setSearchFilter(e.target.value)}
                      className="w-full rounded-lg border border-slate-200 bg-slate-50/50 py-2 pl-9 pr-3 text-xs text-slate-800 outline-none focus:border-teal-600 focus:bg-white"
                    />
                  </div>

                  <div className="max-h-52 overflow-y-auto space-y-1.5 rounded-xl border border-slate-200 bg-slate-50/30 p-2">
                    {filteredDocs.length === 0 ? (
                      <div className="py-8 text-center text-xs text-slate-500">
                        <p>No matching documents found in drive.</p>
                        <button
                          onClick={() => setSourceTab("upload")}
                          className="mt-2 text-xs font-semibold text-teal-700 hover:underline"
                        >
                          Upload a local document now →
                        </button>
                      </div>
                    ) : (
                      filteredDocs.map((doc) => {
                        const isSelected = selectedDocId === doc.id;
                        return (
                          <div
                            key={doc.id}
                            onClick={() => setSelectedDocId(doc.id)}
                            className={`flex cursor-pointer items-center justify-between rounded-lg p-2.5 transition border ${
                              isSelected
                                ? "border-teal-600 bg-teal-50/60 ring-1 ring-teal-600"
                                : "border-slate-200 bg-white hover:border-slate-300"
                            }`}
                          >
                            <div className="flex items-center gap-2.5 min-w-0">
                              <span className="shrink-0">{getDocIcon(doc.originalFilename)}</span>
                              <div className="min-w-0">
                                <p className="truncate text-xs font-medium text-slate-900">
                                  {doc.originalFilename}
                                </p>
                                <p className="text-[10px] text-slate-400">
                                  {formatBytes(doc.fileSize)} • {doc.pageCount || 1} pages
                                </p>
                              </div>
                            </div>
                            <div
                              className={`h-4 w-4 rounded-full border flex items-center justify-center shrink-0 ${
                                isSelected
                                  ? "border-teal-600 bg-teal-600 text-white"
                                  : "border-slate-300"
                              }`}
                            >
                              {isSelected && <Check size={10} strokeWidth={3} />}
                            </div>
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>
              )}

              {/* Source Tab 2: Local File Upload */}
              {sourceTab === "upload" && (
                <div className="space-y-3">
                  <div
                    onDragOver={(e) => {
                      e.preventDefault();
                      if (!uploading) setDragging(true);
                    }}
                    onDragLeave={() => setDragging(false)}
                    onDrop={(e) => {
                      e.preventDefault();
                      setDragging(false);
                      onFileSelect(e.dataTransfer.files[0] ?? null);
                    }}
                    className={`rounded-xl border-2 border-dashed p-6 text-center transition ${
                      dragging
                        ? "border-teal-600 bg-teal-50"
                        : "border-slate-300 bg-slate-50/60"
                    }`}
                  >
                    <span className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-white text-teal-700 shadow-xs">
                      <UploadCloud size={20} />
                    </span>
                    <p className="text-xs font-medium text-slate-800">
                      Drop local document here, or{" "}
                      <button
                        type="button"
                        disabled={uploading}
                        onClick={() => fileInputRef.current?.click()}
                        className="font-semibold text-teal-700 underline underline-offset-2"
                      >
                        browse files
                      </button>
                    </p>
                    <p className="mt-1 text-[10px] text-slate-400">
                      PDF, DOCX, XLSX, CSV, TXT, or MD ({UPLOAD_LIMIT_LABEL})
                    </p>
                    <input
                      ref={fileInputRef}
                      type="file"
                      aria-label="Upload document file"
                      accept=".pdf,.docx,.xlsx,.xls,.csv,.txt,.md"
                      className="hidden"
                      onChange={(e) => {
                        onFileSelect(e.target.files?.[0] ?? null);
                        e.target.value = "";
                      }}
                    />
                  </div>

                  {localFile && (
                    <div className="flex items-center justify-between rounded-lg border border-teal-200 bg-teal-50/60 p-3 text-xs">
                      <div className="flex items-center gap-2">
                        <FileText size={16} className="text-teal-700" />
                        <span className="font-semibold text-slate-900">
                          {localFile.name} ({formatBytes(localFile.size)})
                        </span>
                      </div>
                      <Button
                        size="sm"
                        disabled={uploading}
                        onClick={handleUploadLocal}
                        className="h-8 gap-1 text-xs"
                      >
                        {uploading ? (
                          <>
                            <Spinner size={13} /> Ingesting…
                          </>
                        ) : (
                          "Upload & Select"
                        )}
                      </Button>
                    </div>
                  )}

                  {uploadError && (
                    <div className="flex items-center gap-1.5 text-xs text-rose-600">
                      <AlertCircle size={14} />
                      <span>{uploadError}</span>
                    </div>
                  )}
                </div>
              )}

              {/* Selected Target Summary */}
              {activeDoc && (
                <div className="flex items-center justify-between rounded-xl border border-teal-200 bg-teal-50/40 p-3 text-xs">
                  <div className="flex items-center gap-2">
                    <CheckCircle2 size={16} className="text-teal-700" />
                    <div>
                      <span className="text-slate-500">Selected target: </span>
                      <strong className="text-slate-900">{activeDoc.originalFilename}</strong>
                    </div>
                  </div>
                  <span className="text-[10px] text-slate-500">
                    {formatBytes(activeDoc.fileSize)}
                  </span>
                </div>
              )}

              {/* OpenAI & Superset Model Selector and Cost Breakdown */}
              {service && (
                <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-3.5 dark:border-slate-800 dark:bg-slate-900/60 space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <label className="text-xs font-semibold text-slate-700 dark:text-slate-300 flex items-center gap-1.5">
                      <Sparkles size={13} className="text-emerald-500" />
                      <span>Processing Model (models.json)</span>
                    </label>
                    <select
                      value={modalModel}
                      onChange={(e) => setModalModel(e.target.value)}
                      disabled={running}
                      className="rounded-lg border border-slate-300 bg-white px-2.5 py-1 text-xs font-mono font-medium text-slate-800 outline-none focus:border-emerald-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
                    >
                      {availableModels.map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.name} ({m.credit_cost} cr • ${(m.credit_cost * 0.002).toFixed(3)})
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Guardian Verification Toggle */}
                  <div className="flex items-center justify-between p-2.5 rounded-lg bg-white dark:bg-slate-800/80 border border-slate-200/50 dark:border-slate-700/50">
                    <div className="flex items-center gap-2">
                      {modalGuardian ? (
                        <ShieldCheck size={16} className="text-emerald-500 shrink-0" />
                      ) : (
                        <ShieldAlert size={16} className="text-amber-500 shrink-0" />
                      )}
                      <div>
                        <div className="text-xs font-semibold text-slate-800 dark:text-slate-200 flex items-center gap-1.5">
                          <span>Guardian Verification</span>
                          <span
                            className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
                              modalGuardian
                                ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300"
                                : "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300"
                            }`}
                          >
                            {modalGuardian ? "+5 cr Guardian Fee" : "Fee Waived (Direct Return)"}
                          </span>
                        </div>
                        <p className="text-[11px] text-slate-500 dark:text-slate-400">
                          {modalGuardian
                            ? "Strict evidence citation check, schema validation & guardrails."
                            : "Raw model values returned directly without evidence citation nullification."}
                        </p>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => setModalGuardian(!modalGuardian)}
                      disabled={running}
                      className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                        modalGuardian ? "bg-emerald-600" : "bg-slate-300 dark:bg-slate-600"
                      }`}
                    >
                      <span
                        className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                          modalGuardian ? "translate-x-4" : "translate-x-0"
                        }`}
                      />
                    </button>
                  </div>

                  {(() => {
                    const pricing = calculateCost(service.credits, modalModel, modalGuardian);
                    return (
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2 border-t border-slate-200/60 dark:border-slate-800 text-center">
                        <div className="rounded-lg bg-white p-2 dark:bg-slate-800/80 border border-slate-200/50 dark:border-slate-700/50">
                          <span className="block text-[10px] text-slate-400 font-medium uppercase">Base Service</span>
                          <span className="font-mono text-xs font-bold text-slate-700 dark:text-slate-300">{service.credits} cr</span>
                        </div>
                        <div className="rounded-lg bg-white p-2 dark:bg-slate-800/80 border border-slate-200/50 dark:border-slate-700/50">
                          <span className="block text-[10px] text-slate-400 font-medium uppercase">Model Rate</span>
                          <span className="font-mono text-xs font-bold text-slate-700 dark:text-slate-300">
                            {pricing.modelCost} cr ({pricing.modelDelta >= 0 ? `+${pricing.modelDelta}` : pricing.modelDelta})
                          </span>
                        </div>
                        <div className="rounded-lg bg-white p-2 dark:bg-slate-800/80 border border-slate-200/50 dark:border-slate-700/50">
                          <span className="block text-[10px] text-slate-400 font-medium uppercase">Guardian</span>
                          <span className={`font-mono text-xs font-bold ${modalGuardian ? "text-emerald-600 dark:text-emerald-400" : "text-amber-600 dark:text-amber-400"}`}>
                            {modalGuardian ? "+5 cr" : `-${pricing.guardianDiscount} cr`}
                          </span>
                        </div>
                        <div className="rounded-lg bg-emerald-50 dark:bg-emerald-950/40 p-2 border border-emerald-200 dark:border-emerald-800">
                          <span className="block text-[10px] text-emerald-700 dark:text-emerald-300 font-medium uppercase">Total Charge</span>
                          <span className="font-mono text-xs font-black text-emerald-800 dark:text-emerald-200">
                            {pricing.totalCredits} cr <span className="text-[10px] font-normal">({pricing.costUsdFormatted})</span>
                          </span>
                        </div>
                      </div>
                    );
                  })()}
                </div>
              )}

              {runError && (
                <div className="flex items-center gap-2 rounded-lg bg-rose-50 p-3 text-xs text-rose-700 border border-rose-200">
                  <AlertCircle size={15} />
                  <span>{runError}</span>
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer Actions */}
        {!runResult && (
          <div className="flex flex-col sm:flex-row items-center justify-between gap-3 border-t border-slate-100 bg-slate-50/50 p-4 px-6">
            <div className="text-[11px] text-slate-500">
              {remainingCredits !== undefined && (
                <span>Available Balance: <strong>{remainingCredits.toLocaleString()}</strong> credits</span>
              )}
            </div>

            <div className="flex w-full sm:w-auto items-center gap-2.5">
              <Button
                variant="outline"
                size="sm"
                onClick={handleClose}
                disabled={running}
              >
                Cancel
              </Button>

              <Button
                variant="secondary"
                size="sm"
                disabled={!activeDoc || running}
                onClick={handleDirectRun}
                className="gap-1.5"
              >
                {running ? <Spinner size={14} /> : <Play size={13} fill="currentColor" />}
                Quick Run
              </Button>

              <Button
                size="sm"
                disabled={!activeDoc || running}
                onClick={handleStartChatSession}
                className="gap-1.5"
              >
                {running ? <Spinner size={14} /> : <Sparkles size={14} />}
                Interactive Chat <ArrowRight size={13} />
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

