"use client";
import { useLanguage } from "@/components/providers/language-provider";
import { useModelSettings } from "@/components/providers/model-provider";
import { getUploadSizeError, UPLOAD_LIMIT_LABEL } from "@/lib/upload-limits";

import { useState, useRef, useId, useEffect } from "react";
import {
  ScanText,
  UploadCloud,
  FileText,
  Download,
  Copy,
  Check,
  RefreshCw,
  X,
  Search,
  Sparkles,
  Layers,
  FileCode,
  AlignLeft,
  AlertCircle,
  Link as LinkIcon,
  FileCheck2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import {
  extractAdvancedOcr,
  type AdvancedOcrResult,
  type SemanticOcrBlock,
} from "@/lib/api";

type ViewMode = "blocks" | "text" | "json";
type BlockTypeFilter =
  | "all"
  | "paragraph"
  | "title"
  | "table"
  | "formula"
  | "image";

function formatBytes(bytes: number, decimals = 1): string {
  if (bytes === 0) return "0 Bytes";
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ["Bytes", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
}

function getBlockBadgeStyle(type: string) {
  const normalized = (type || "").toLowerCase();
  if (normalized.includes("title") || normalized.includes("header")) {
    return "bg-purple-50 text-purple-700 border-purple-200";
  }
  if (normalized.includes("table")) {
    return "bg-blue-50 text-blue-700 border-blue-200";
  }
  if (
    normalized.includes("formula") ||
    normalized.includes("equation") ||
    normalized.includes("math")
  ) {
    return "bg-amber-50 text-amber-700 border-amber-200";
  }
  if (
    normalized.includes("image") ||
    normalized.includes("figure") ||
    normalized.includes("visual")
  ) {
    return "bg-emerald-50 text-emerald-700 border-emerald-200";
  }
  if (normalized.includes("question")) {
    return "bg-indigo-50 text-indigo-700 border-indigo-200";
  }
  return "bg-slate-100 text-slate-700 dark:text-slate-300 border-slate-200 dark:border-slate-700";
}

export default function AdvancedOcrPage() {
  const { t } = useLanguage();
  const { selectedModel, availableModels } = useModelSettings();
  const fileInputId = useId();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [ocrModel, setOcrModel] = useState<string>(selectedModel || "gpt-4o-mini");

  useEffect(() => {
    if (selectedModel) {
      setOcrModel(selectedModel);
    }
  }, [selectedModel]);

  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [startPage, setStartPage] = useState(1);
  const [endPage, setEndPage] = useState<number | "">("");
  const [language, setLanguage] = useState<"auto" | "ar" | "en" | "mixed">(
    "auto",
  );

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<AdvancedOcrResult | null>(null);

  const [viewMode, setViewMode] = useState<ViewMode>("blocks");
  const [blockFilter, setBlockFilter] = useState<BlockTypeFilter>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [copied, setCopied] = useState(false);

  const fieldClass =
    "mt-2 w-full rounded-xl border border-slate-300 dark:border-slate-800 bg-white dark:bg-slate-900 p-3 text-sm text-slate-900 dark:text-slate-100 focus:border-emerald-600 focus:outline-none focus:ring-1 focus:ring-emerald-600 disabled:opacity-50 dark:focus:border-emerald-500";

  function handleFileSelection(candidate: File | null) {
    if (!candidate) return;
    if (
      !candidate.name.toLowerCase().endsWith(".pdf") &&
      candidate.type !== "application/pdf"
    ) {
      setError(
        t(
          "Please select a valid PDF file. Other file formats are not supported for PDF OCR.",
        ),
      );
      return;
    }
    const sizeError = getUploadSizeError(candidate);
    if (sizeError) {
      setError(sizeError);
      return;
    }
    setFile(candidate);
    setError("");
    setResult(null);
  }

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault();
    setIsDragging(true);
  }

  function handleDragLeave(e: React.DragEvent) {
    e.preventDefault();
    setIsDragging(false);
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setIsDragging(false);
    const droppedFile = e.dataTransfer.files?.[0];
    if (droppedFile) {
      handleFileSelection(droppedFile);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) {
      setError(t("Please upload a PDF file to run OCR extraction."));
      return;
    }
    if (startPage < 1 || startPage > 3) {
      setError(t("Start page must be between 1 and 3."));
      return;
    }
    if (typeof endPage === "number" && endPage < startPage) {
      setError(t("End page must be greater than or equal to start page."));
      return;
    }
    if (typeof endPage === "number" && endPage > 3) {
      setError(t("Documents are limited to 3 pages."));
      return;
    }

    setBusy(true);
    setError("");
    setResult(null);

    try {
      const data = await extractAdvancedOcr({
        file,
        start_page: startPage,
        end_page: typeof endPage === "number" ? endPage : undefined,
        language,
        model: ocrModel,
      });
      setResult(data);
      if (typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent("doctool:credit-updated"));
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : t("OCR extraction failed. Please try again."),
      );
    } finally {
      setBusy(false);
    }
  }

  function downloadJson() {
    if (!result) return;
    const baseName = (result.filename || file?.name || "document").replace(
      /\.pdf$/i,
      "",
    );
    const blob = new Blob([JSON.stringify(result, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${baseName}-ocr-blocks.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function downloadMarkdown() {
    if (!result) return;
    const baseName = (result.filename || file?.name || "document").replace(
      /\.pdf$/i,
      "",
    );

    let md = `# OCR Document Extraction: ${result.filename || file?.name}\n\n`;
    md += `> **Processed Pages:** ${result.processed_pages} | **Total Blocks:** ${result.block_count}\n\n---\n\n`;

    for (const page of result.pages) {
      md += `## Page ${page.page_number} (${page.block_count} blocks)\n\n`;
      for (const b of page.blocks) {
        const cont = b.previous_block_id
          ? ` *(Continues ${b.previous_block_id})*`
          : "";
        md += `### [${b.type.toUpperCase()}] ${b.id}${cont}\n\n`;
        if (typeof b.content === "string") {
          md += `${b.content}\n\n`;
        } else {
          md += "```json\n" + JSON.stringify(b.content, null, 2) + "\n```\n\n";
        }
        if (b.ocr_text && b.ocr_text.trim()) {
          md += `**Transcription:**\n> ${b.ocr_text.replace(/\n/g, "\n> ")}\n\n`;
        }
      }
      md += `---\n\n`;
    }

    const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${baseName}-ocr-text.md`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function copyAllText() {
    if (!result) return;
    let full = result.ocr_text || "";
    if (!full.trim()) {
      full = result.pages
        .flatMap((p) =>
          p.blocks.map(
            (b) =>
              b.ocr_text ||
              (typeof b.content === "string"
                ? b.content
                : JSON.stringify(b.content)),
          ),
        )
        .join("\n\n");
    }
    navigator.clipboard.writeText(full).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  function filterBlock(block: SemanticOcrBlock): boolean {
    if (blockFilter !== "all") {
      const type = (block.type || "").toLowerCase();
      if (
        blockFilter === "title" &&
        !type.includes("title") &&
        !type.includes("header")
      )
        return false;
      if (blockFilter === "table" && !type.includes("table")) return false;
      if (
        blockFilter === "formula" &&
        !type.includes("formula") &&
        !type.includes("equation") &&
        !type.includes("math")
      )
        return false;
      if (
        blockFilter === "image" &&
        !type.includes("image") &&
        !type.includes("visual") &&
        !type.includes("figure")
      )
        return false;
      if (
        blockFilter === "paragraph" &&
        (type.includes("table") ||
          type.includes("title") ||
          type.includes("image") ||
          type.includes("formula"))
      )
        return false;
    }

    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      const contentStr =
        typeof block.content === "string"
          ? block.content
          : JSON.stringify(block.content);
      const textMatch = (block.ocr_text || "").toLowerCase().includes(query);
      const contentMatch = contentStr.toLowerCase().includes(query);
      const idMatch = block.id.toLowerCase().includes(query);
      return textMatch || contentMatch || idMatch;
    }

    return true;
  }

  return (
    <div className="mx-auto max-w-6xl space-y-8 pb-16">
      {/* Header */}
      <header className="space-y-3">
        <div className="inline-flex items-center gap-2 rounded-full border border-teal-200 bg-teal-50 px-3 py-1 text-xs font-semibold text-teal-800">
          <Sparkles size={14} className="text-teal-600" />
          <span>{t("Document AI • Vision OCR Engine")}</span>
        </div>
        <h1 className="text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-100 sm:text-4xl">
          {t("Advanced Document OCR")}
        </h1>
        <p className="max-w-3xl text-sm leading-relaxed text-slate-600 dark:text-slate-400 sm:text-base">
          {t(
            "Extract text, tables and page sections from a PDF. Choose the page range and document language, then review or download the result.",
            "استخرج النص والجداول وأقسام الصفحات من ملف PDF. اختر نطاق الصفحات ولغة المستند، ثم راجع النتيجة أو نزّلها.",
          )}
        </p>
      </header>

      {/* Upload and Configuration Form */}
      <form onSubmit={handleSubmit} className="surface space-y-6 p-6 sm:p-8">
        <div>
          <label
            htmlFor={fileInputId}
            className="block text-sm font-semibold text-slate-900 dark:text-slate-100 mb-2"
          >
            {t("Upload PDF Document")}
          </label>

          {!file ? (
            <div
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              role="button"
              tabIndex={busy ? -1 : 0}
              aria-disabled={busy}
              onKeyDown={(event) => {
                if (!busy && (event.key === "Enter" || event.key === " ")) {
                  event.preventDefault();
                  fileInputRef.current?.click();
                }
              }}
              className={`flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed p-8 transition-colors ${
                isDragging
                  ? "border-teal-500 bg-teal-50/50"
                  : "border-slate-300 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-900/50 hover:border-teal-400 hover:bg-slate-50"
              }`}
            >
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-teal-100 text-teal-700">
                <UploadCloud size={24} />
              </div>
              <p className="mt-3 text-sm font-medium text-slate-800 dark:text-slate-200">
                {t("Click or drag & drop a PDF here")}
              </p>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                {t("PDF documents", "ملفات PDF")} • {t(UPLOAD_LIMIT_LABEL)}
              </p>
              <input
                id={fileInputId}
                ref={fileInputRef}
                type="file"
                accept="application/pdf,.pdf"
                className="hidden"
                disabled={busy}
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) handleFileSelection(f);
                }}
              />
            </div>
          ) : (
            <div className="flex items-center justify-between rounded-xl border border-teal-200 bg-teal-50/50 p-4">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-teal-600 text-white shadow-sm">
                  <FileText size={20} />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                      {file.name}
                    </p>
                    <span className="rounded bg-teal-100 px-1.5 py-0.5 text-[10px] font-semibold text-teal-800">
                      PDF
                    </span>
                  </div>
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    {formatBytes(file.size)}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={busy}
                  onClick={() => fileInputRef.current?.click()}
                  leftIcon={<RefreshCw size={14} />}
                >
                  {t("Change")}
                </Button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    setFile(null);
                    setResult(null);
                    setError("");
                    if (fileInputRef.current) fileInputRef.current.value = "";
                  }}
                  className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600 disabled:opacity-50"
                  aria-label={t("Remove selected PDF")}
                >
                  <X size={18} />
                </button>
              </div>

              <input
                id={fileInputId}
                ref={fileInputRef}
                type="file"
                accept="application/pdf,.pdf"
                className="hidden"
                disabled={busy}
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) handleFileSelection(f);
                }}
              />
            </div>
          )}
        </div>

        {/* Extraction Settings */}
        <div className="grid gap-5 sm:grid-cols-4">
          <label className="text-sm font-medium text-slate-700 dark:text-slate-300">
            {t("AI Model")}
            <select
              disabled={busy}
              value={ocrModel}
              onChange={(e) => setOcrModel(e.target.value)}
              className={fieldClass}
            >
              {availableModels.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name} ({m.credit_cost} cr)
                </option>
              ))}
            </select>
          </label>

          <label className="text-sm font-medium text-slate-700 dark:text-slate-300">
            {t("Start page")}
            <input
              required
              disabled={busy}
              type="number"
              min={1}
              max={3}
              value={startPage}
              onChange={(e) =>
                setStartPage(Math.max(1, Number(e.target.value) || 1))
              }
              className={fieldClass}
            />
          </label>

          <label className="text-sm font-medium text-slate-700 dark:text-slate-300">
            {t("End page (optional)")}
            <input
              disabled={busy}
              type="number"
              min={startPage}
              max={3}
              placeholder={t("e.g. 3 (default: all pages)")}
              value={endPage}
              onChange={(e) => {
                const val = e.target.value;
                setEndPage(val === "" ? "" : Math.max(startPage, Number(val)));
              }}
              className={fieldClass}
            />
          </label>

          <label className="text-sm font-medium text-slate-700 dark:text-slate-300">
            {t("Language hint")}
            <select
              disabled={busy}
              value={language}
              onChange={(e) => setLanguage(e.target.value as typeof language)}
              className={fieldClass}
            >
              <option value="auto">{t("Auto detect language")}</option>
              <option value="ar">{t("Arabic (العربية)")}</option>
              <option value="en">{t("English")}</option>
              <option value="mixed">{t("Arabic & English (Mixed)")}</option>
            </select>
          </label>
        </div>

        {/* Information note */}
        <div className="flex items-start gap-2 rounded-xl bg-slate-50 p-3.5 text-xs text-slate-500 dark:text-slate-400 dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800">
          <FileCheck2
            size={16}
            className="mt-0.5 shrink-0 text-emerald-600 dark:text-emerald-400"
          />
          <span>
            {t(
              "Upload a PDF up to 5 MB and 3 pages. Scans with clear text give better results. Check the extracted content against the original before using it.",
              "ارفع ملف PDF بحجم لا يتجاوز 5 ميغابايت و3 صفحات. تعطي الصور الممسوحة ذات النص الواضح نتائج أفضل. راجع المحتوى المستخرج بمقارنته مع الأصل قبل استخدامه.",
            )}
          </span>
        </div>

        {/* Action Button & Status */}
        <div className="flex flex-wrap items-center gap-4">
          <Button
            type="submit"
            disabled={busy || !file}
            className="bg-gradient-to-r from-teal-700 to-emerald-600 px-6 font-medium text-white hover:from-teal-800 hover:to-emerald-700 disabled:opacity-50"
            leftIcon={busy ? <Spinner size={16} /> : <ScanText size={18} />}
          >
            {busy
              ? t("Analyzing PDF with Vision AI…")
              : t("Extract Document Blocks")}
          </Button>

          {busy && (
            <p
              role="status"
              className="text-sm text-slate-500 dark:text-slate-400 flex items-center gap-2"
            >
              {t(
                "Processing PDF pages in order. This may take a few moments for large documents…",
              )}
            </p>
          )}
        </div>

        {/* Error Alert */}
        {error && (
          <div
            role="alert"
            className="flex items-start gap-2.5 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800"
          >
            <AlertCircle size={18} className="mt-0.5 shrink-0 text-red-600" />
            <span>{t(error)}</span>
          </div>
        )}
      </form>

      {/* OCR Results Section */}
      {result && (
        <section className="space-y-6" aria-label={t("OCR extraction results")}>
          {/* Result Header & Actions */}
          <div className="surface flex flex-wrap items-center justify-between gap-4 p-5 sm:p-6">
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-xl font-bold text-slate-900 dark:text-slate-100">
                  {result.filename || file?.name}
                </h2>
                <span className="rounded-md border border-teal-200 bg-teal-50 px-2 py-0.5 text-xs font-semibold text-teal-800">
                  {t("Ready")}
                </span>
                {(result.model || ocrModel) && (
                  <span className="rounded-md border border-slate-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-xs font-mono font-medium text-slate-700 dark:text-slate-300">
                    Model: {result.model || ocrModel}
                  </span>
                )}
              </div>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400 sm:text-sm">
                {result.processed_pages}{" "}
                {result.processed_pages === 1 ? t("page") : "pages"} processed ·{" "}
                {result.block_count} semantic blocks extracted
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={downloadJson}
                leftIcon={<Download size={15} />}
              >
                {t("Download JSON")}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={downloadMarkdown}
                leftIcon={<Download size={15} />}
              >
                {t("Download Markdown")}
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={copyAllText}
                leftIcon={
                  copied ? (
                    <Check size={15} className="text-teal-600" />
                  ) : (
                    <Copy size={15} />
                  )
                }
              >
                {copied ? t("Copied!") : t("Copy Text")}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setFile(null);
                  setResult(null);
                  window.scrollTo({ top: 0, behavior: "smooth" });
                }}
                leftIcon={<RefreshCw size={14} />}
              >
                {t("Upload New PDF")}
              </Button>
            </div>
          </div>

          {/* View Toolbar: View Modes & Filters */}
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-1 text-xs font-medium text-slate-600 dark:text-slate-400 shadow-sm">
              <button
                type="button"
                onClick={() => setViewMode("blocks")}
                className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 transition-colors ${
                  viewMode === "blocks"
                    ? "bg-teal-700 text-white shadow-sm"
                    : "hover:bg-slate-100 hover:text-slate-900"
                }`}
              >
                <Layers size={14} />
                <span>{t("Semantic Blocks")}</span>
              </button>
              <button
                type="button"
                onClick={() => setViewMode("text")}
                className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 transition-colors ${
                  viewMode === "text"
                    ? "bg-teal-700 text-white shadow-sm"
                    : "hover:bg-slate-100 hover:text-slate-900"
                }`}
              >
                <AlignLeft size={14} />
                <span>{t("Full Text")}</span>
              </button>
              <button
                type="button"
                onClick={() => setViewMode("json")}
                className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 transition-colors ${
                  viewMode === "json"
                    ? "bg-teal-700 text-white shadow-sm"
                    : "hover:bg-slate-100 hover:text-slate-900"
                }`}
              >
                <FileCode size={14} />
                <span>{t("Raw JSON")}</span>
              </button>
            </div>

            {viewMode === "blocks" && (
              <div className="flex flex-wrap items-center gap-3">
                {/* Search in blocks */}
                <div className="relative">
                  <Search
                    size={14}
                    className="absolute start-3 top-2.5 text-slate-400"
                  />
                  <input
                    type="text"
                    placeholder={t("Search blocks…")}
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="h-9 w-48 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 ps-8 pe-3 text-xs focus:border-teal-600 focus:outline-none focus:ring-1 focus:ring-teal-600 sm:w-60"
                  />
                  {searchQuery && (
                    <button
                      type="button"
                      onClick={() => setSearchQuery("")}
                      className="absolute end-2.5 top-2.5 text-slate-400 hover:text-slate-600"
                    >
                      <X size={14} />
                    </button>
                  )}
                </div>

                {/* Block Type Filters */}
                <div className="flex flex-wrap items-center gap-1 text-xs">
                  {(
                    [
                      "all",
                      "paragraph",
                      "title",
                      "table",
                      "formula",
                      "image",
                    ] as BlockTypeFilter[]
                  ).map((filter) => (
                    <button
                      key={t(
                        filter,
                        {
                          all: "الكل",
                          paragraph: "الفقرات",
                          title: "العناوين",
                          table: "الجداول",
                          formula: "المعادلات",
                          image: "الصور",
                        }[filter],
                      )}
                      type="button"
                      onClick={() => setBlockFilter(filter)}
                      className={`rounded-lg px-2.5 py-1 capitalize transition-colors ${
                        blockFilter === filter
                          ? "bg-teal-100 font-semibold text-teal-800"
                          : "bg-slate-100 text-slate-600 dark:text-slate-400 hover:bg-slate-200"
                      }`}
                    >
                      {t(
                        filter,
                        {
                          all: "الكل",
                          paragraph: "الفقرات",
                          title: "العناوين",
                          table: "الجداول",
                          formula: "المعادلات",
                          image: "الصور",
                        }[filter],
                      )}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* VIEW: Blocks View */}
          {viewMode === "blocks" && (
            <div className="space-y-6">
              {result.pages.map((page) => {
                const visibleBlocks = page.blocks.filter(filterBlock);
                return (
                  <article
                    key={page.page_number}
                    className="surface space-y-4 p-5 sm:p-6"
                  >
                    <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                      <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">
                        Page {page.page_number}
                        <span className="ms-2 text-xs font-normal text-slate-500 dark:text-slate-400">
                          ({visibleBlocks.length} {t("of")}
                          {page.block_count} blocks shown)
                        </span>
                      </h3>
                    </div>

                    {visibleBlocks.length === 0 && (
                      <p className="py-4 text-center text-sm text-slate-400">
                        {page.blocks.length === 0
                          ? t("No visible blocks detected on this page.")
                          : t(
                              "No blocks match the current filter or search criteria.",
                            )}
                      </p>
                    )}

                    <div className="space-y-4">
                      {visibleBlocks.map((block) => (
                        <div
                          key={block.id}
                          className="rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50/70 dark:bg-slate-900/70 p-4 transition-all hover:border-slate-300 hover:bg-slate-50"
                        >
                          <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                            <div className="flex flex-wrap items-center gap-2">
                              <span
                                className={`rounded-md border px-2 py-0.5 font-semibold uppercase tracking-wider text-[11px] ${getBlockBadgeStyle(
                                  block.type,
                                )}`}
                              >
                                {block.type}
                              </span>
                              <span className="font-mono text-slate-500 dark:text-slate-400">
                                {block.id}
                              </span>
                              {block.previous_block_id && (
                                <span className="inline-flex items-center gap-1 rounded bg-teal-50 px-1.5 py-0.5 text-teal-700 border border-teal-100 font-medium">
                                  <LinkIcon size={11} />
                                  Continues {block.previous_block_id}
                                </span>
                              )}
                            </div>

                            {Array.isArray(block.bbox) && (
                              <span className="font-mono text-[10px] text-slate-400">
                                bbox: [{block.bbox.join(", ")}]
                              </span>
                            )}
                          </div>

                          {/* Block Formatted Content */}
                          <div className="mt-3">
                            {typeof block.content === "string" ? (
                              <div
                                dir="auto"
                                className="whitespace-pre-wrap break-words font-sans text-sm leading-relaxed text-slate-800 dark:text-slate-200"
                              >
                                {block.content}
                              </div>
                            ) : (
                              <pre className="overflow-x-auto rounded-lg bg-white dark:bg-slate-900 p-3 font-mono text-xs leading-5 text-slate-800 dark:text-slate-200 border border-slate-200 dark:border-slate-700">
                                {JSON.stringify(block.content, null, 2)}
                              </pre>
                            )}
                          </div>

                          {/* OCR Transcription Accordion */}
                          {block.ocr_text && (
                            <details className="mt-3 text-xs text-slate-600 dark:text-slate-400">
                              <summary className="cursor-pointer font-medium text-slate-500 dark:text-slate-400 hover:text-slate-800">
                                {t("OCR raw transcription")}
                              </summary>
                              <pre
                                dir="auto"
                                className="mt-2 whitespace-pre-wrap break-words rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-3 font-mono leading-5 text-slate-700 dark:text-slate-300"
                              >
                                {block.ocr_text}
                              </pre>
                            </details>
                          )}

                          {/* Details JSON Accordion */}
                          <details className="mt-2 text-xs text-slate-500 dark:text-slate-400">
                            <summary className="cursor-pointer hover:text-slate-700">
                              {t("JSON metadata & fields")}
                            </summary>
                            <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-100 p-2.5 font-mono text-[11px] text-slate-700 dark:text-slate-300">
                              {JSON.stringify(block, null, 2)}
                            </pre>
                          </details>
                        </div>
                      ))}
                    </div>
                  </article>
                );
              })}
            </div>
          )}

          {/* VIEW: Plain Text / Markdown View */}
          {viewMode === "text" && (
            <article className="surface space-y-4 p-6">
              <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">
                  Extracted Document Text
                </h3>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={copyAllText}
                  leftIcon={
                    copied ? (
                      <Check size={14} className="text-teal-600" />
                    ) : (
                      <Copy size={14} />
                    )
                  }
                >
                  {copied ? t("Copied") : "Copy All"}
                </Button>
              </div>
              <pre
                dir="auto"
                className="max-h-[70vh] overflow-y-auto whitespace-pre-wrap font-sans text-sm leading-relaxed text-slate-800 dark:text-slate-200"
              >
                {result.ocr_text ||
                  result.pages
                    .flatMap((p) =>
                      p.blocks.map(
                        (b) =>
                          b.ocr_text ||
                          (typeof b.content === "string"
                            ? b.content
                            : JSON.stringify(b.content)),
                      ),
                    )
                    .join("\n\n")}
              </pre>
            </article>
          )}

          {/* VIEW: Raw JSON View */}
          {viewMode === "json" && (
            <article className="surface space-y-4 p-6">
              <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">
                  Full JSON Response
                </h3>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    navigator.clipboard.writeText(
                      JSON.stringify(result, null, 2),
                    );
                    setCopied(true);
                    setTimeout(() => setCopied(false), 2000);
                  }}
                  leftIcon={
                    copied ? (
                      <Check size={14} className="text-teal-600" />
                    ) : (
                      <Copy size={14} />
                    )
                  }
                >
                  {copied ? t("Copied") : "Copy JSON"}
                </Button>
              </div>
              <pre className="max-h-[70vh] overflow-auto rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-900 p-4 font-mono text-xs leading-5 text-slate-100">
                {JSON.stringify(result, null, 2)}
              </pre>
            </article>
          )}
        </section>
      )}
    </div>
  );
}
