"use client";
import { useLanguage } from "@/components/providers/language-provider";
import { getUploadSizeError, UPLOAD_LIMIT_LABEL } from "@/lib/upload-limits";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  MessageSquare,
  ArrowUpRight,
  Search,
  Plus,
  X,
  Upload,
  FileText,
  Zap,
  AlertCircle,
  ShieldCheck,
} from "lucide-react";
import {
  fetchSessions,
  uploadDocument,
  createSession,
  fetchCompanyAccount,
  type CompanyAccountInfo,
} from "@/lib/api";
import { Dialog } from "@/components/ui/dialog";
import { Spinner } from "@/components/ui/spinner";
import type { ChatSession } from "@/lib/types";
import { formatDate } from "@/lib/utils";

export default function ConversationsPage() {
  const { t } = useLanguage();
  const router = useRouter();

  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [account, setAccount] = useState<CompanyAccountInfo | null>(null);

  // New Chat Modal States
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [chatTitle, setChatTitle] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [modalError, setModalError] = useState("");
  const [isDragging, setIsDragging] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const [allSessions, companyData] = await Promise.all([
          fetchSessions(),
          fetchCompanyAccount().catch(() => null),
        ]);
        if (active) {
          setSessions(allSessions);
          if (companyData) setAccount(companyData);
        }
      } catch {
        if (active) setError("Could not load conversations. Refresh to retry.");
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  const handleOpenModal = () => {
    setSelectedFile(null);
    setChatTitle("");
    setModalError("");
    setIsModalOpen(true);
  };

  const handleCloseModal = () => {
    if (isUploading) return;
    setIsModalOpen(false);
  };

  const handleFileSelect = (file: File) => {
    // Only accept PDF, DOCX, TXT, CSV, XLSX
    const allowed = /\.(pdf|docx|txt|csv|xlsx|xls)$/i;
    if (!allowed.test(file.name)) {
      setModalError(t("Supported formats: PDF, DOCX, TXT, CSV, XLSX."));
      return;
    }
    const sizeError = getUploadSizeError(file);
    if (sizeError) {
      setModalError(sizeError);
      return;
    }
    setSelectedFile(file);
    setModalError("");
    if (!chatTitle) {
      setChatTitle(file.name.replace(/\.[^/.]+$/, ""));
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileSelect(e.dataTransfer.files[0]);
    }
  };

  const handleStartChat = async () => {
    if (!selectedFile) {
      setModalError(t("Please select a document to start the chat."));
      return;
    }

    setIsUploading(true);
    setModalError("");

    try {
      // 1. Upload document ephemeral
      const doc = await uploadDocument(selectedFile);

      // 2. Create chat session
      const title = chatTitle.trim() || selectedFile.name;
      const session = await createSession(doc.id, title);

      // 3. Close modal & navigate to conversation
      setIsModalOpen(false);
      router.push(`/chat/${session.id}`);
    } catch (err: unknown) {
      const msg =
        err instanceof Error
          ? err.message
          : t("Failed to initialize conversation.");
      setModalError(msg);
      setIsUploading(false);
    }
  };

  const remaining = account?.remainingCredits ?? 300;

  return (
    <div className="mx-auto max-w-6xl space-y-6 text-slate-900 dark:text-slate-100">
      {/* Header with Title & Action Button */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="eyebrow">{t("Workspace / Conversations")}</p>
          <h1 className="mt-1 text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900 dark:text-white">
            {t("Document conversations")}
          </h1>
          <p className="mt-1 text-xs sm:text-sm text-slate-500 dark:text-slate-400">
            {t(
              "Chat directly with your documents (max 3 pages per conversation).",
            )}
          </p>
        </div>

        {/* NEW CHAT BUTTON */}
        <button
          onClick={handleOpenModal}
          className="inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-teal-700 to-emerald-600 px-4 py-2.5 text-xs font-semibold text-white shadow-sm hover:from-teal-800 hover:to-emerald-700 transition shrink-0 active:scale-95"
        >
          <Plus size={16} />
          <span>{t("New Chat")}</span>
          <span className="ms-1 rounded bg-emerald-950/60 px-1.5 py-0.5 text-[10px] font-mono text-emerald-300">
            {t("1 Credit")}
          </span>
        </button>
      </div>

      {/* Search Input Bar */}
      <div className="relative max-w-md">
        <Search size={16} className="absolute start-3.5 top-3 text-slate-400" />
        <input
          aria-label={t("Search conversations")}
          placeholder={t("Find a conversation…")}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full rounded-xl border border-slate-200 bg-white py-2.5 ps-10 pe-4 text-xs shadow-2xs focus:border-emerald-500 focus:outline-none dark:border-slate-800 dark:bg-[#121820] dark:text-slate-100 dark:placeholder:text-slate-500"
        />
      </div>

      {error && (
        <div
          role="alert"
          className="rounded-xl border border-eose-200 bg-rose-50 p-4 text-xs text-rose-700 dark:border-eose-800 dark:bg-rose-950/40 dark:text-rose-300"
        >
          {t(error)}
        </div>
      )}

      {/* Conversations List */}
      {loading ? (
        <div className="flex h-64 items-center justify-center">
          <Spinner size={24} />
        </div>
      ) : sessions.length ? (
        <div className="grid gap-3">
          {!sessions.some((s) =>
            s.title.toLowerCase().includes(search.toLowerCase()),
          ) && (
            <p className="surface p-6 text-sm text-slate-500 dark:text-slate-400">
              {t("No conversations match your search.")}
            </p>
          )}
          {sessions
            .filter((s) => s.title.toLowerCase().includes(search.toLowerCase()))
            .map((s) => (
              <Link
                href={`/chat/${s.id}`}
                key={s.id}
                className="surface flex items-center gap-4 p-4 sm:p-5 hover:!border-emerald-500/50 transition group"
              >
                <span className="rounded-xl bg-emerald-50 p-3 text-emerald-700 group-hover:bg-emerald-100 transition shadow-2xs dark:bg-emerald-950/50 dark:text-emerald-400 dark:group-hover:bg-emerald-900/50">
                  <MessageSquare size={19} />
                </span>
                <div className="min-w-0 flex-1">
                  <h2 className="truncate text-sm font-semibold text-slate-800 group-hover:text-emerald-700 dark:text-slate-200 dark:group-hover:text-emerald-400 transition">
                    {s.title}
                  </h2>
                  <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">
                    {s.messageCount || 0} messages · Updated{" "}
                    {formatDate(s.updatedAt)}
                  </p>
                </div>
                <ArrowUpRight
                  size={18}
                  className="text-slate-400 group-hover:text-emerald-600 dark:group-hover:text-emerald-400 transition"
                />
              </Link>
            ))}
        </div>
      ) : (
        /* Empty State */
        <div className="surface p-10 text-center flex flex-col items-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-50 text-emerald-700 mb-4 shadow-2xs dark:bg-emerald-950/50 dark:text-emerald-400">
            <MessageSquare size={28} />
          </div>
          <h2 className="text-xl font-bold text-slate-900 dark:text-white">
            {t("Start your first document chat.")}
          </h2>
          <p className="mt-2 text-xs sm:text-sm text-slate-500 dark:text-slate-400 max-w-sm">
            {t(
              "Upload a document of up to 3 pages. Ask questions or request a summary of its contents.",
            )}
          </p>
          <button
            onClick={handleOpenModal}
            className="mt-6 inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-teal-700 to-emerald-600 px-5 py-2.5 text-xs font-semibold text-white shadow-sm hover:from-teal-800 hover:to-emerald-700 transition"
          >
            <Plus size={16} />
            <span>{t("Upload Document & Chat")}</span>
          </button>
        </div>
      )}

      {/* =========================================================================
          NEW CHAT MODAL
         ========================================================================= */}
      {isModalOpen && (
        <Dialog
          open={isModalOpen}
          onOpenChange={(open) => {
            if (!open) handleCloseModal();
          }}
          title={t("New Document Chat")}
          description={t("Documents up to 3 pages")}
          className="space-y-5"
        >
          {/* Drag & Drop File Zone */}
          <div className="space-y-3">
            <label
              htmlFor="conversation-file"
              className="block text-xs font-bold text-slate-700 dark:text-slate-300"
            >
              {t("Upload Document")}
              <span className="text-rose-500">*</span>
            </label>

            <input
              id="conversation-file"
              type="file"
              ref={fileInputRef}
              onChange={(e) => {
                if (e.target.files && e.target.files[0]) {
                  handleFileSelect(e.target.files[0]);
                }
              }}
              accept=".pdf,.docx,.txt,.csv,.xlsx,.xls"
              className="hidden"
            />

            {!selectedFile ? (
              <div
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                role="button"
                tabIndex={0}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    fileInputRef.current?.click();
                  }
                }}
                className={`flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-6 text-center cursor-pointer transition ${
                  isDragging
                    ? "border-emerald-500 bg-emerald-50/50 dark:bg-emerald-950/30"
                    : "border-slate-200 bg-slate-50/50 hover:bg-slate-50 hover:border-emerald-400 dark:border-slate-800 dark:bg-slate-900/40 dark:hover:bg-slate-900"
                }`}
              >
                <span className="flex h-10 w-10 items-center justify-center rounded-full bg-emerald-50 text-emerald-700 mb-2 dark:bg-emerald-950/60 dark:text-emerald-400">
                  <Upload size={18} />
                </span>
                <p className="text-xs font-bold text-slate-800 dark:text-slate-200">
                  {t("Click to browse or drop your document here")}
                </p>
                <p className="mt-1 text-[11px] text-slate-400 dark:text-slate-500">
                  PDF, DOCX, CSV, XLSX, TXT ({t(UPLOAD_LIMIT_LABEL)})
                </p>
              </div>
            ) : (
              <div className="flex items-center justify-between rounded-xl border border-emerald-200 bg-emerald-50/40 p-3 text-xs dark:border-emerald-800/60 dark:bg-emerald-950/30">
                <div className="flex items-center gap-2.5 truncate">
                  <FileText
                    size={18}
                    className="text-emerald-700 dark:text-emerald-400 shrink-0"
                  />
                  <div className="min-w-0">
                    <p className="truncate font-semibold text-slate-800 dark:text-slate-200">
                      {selectedFile.name}
                    </p>
                    <p className="text-[11px] text-slate-400 dark:text-slate-500">
                      {(selectedFile.size / 1024).toFixed(1)} KB • Max 3 pages
                      limit
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  disabled={isUploading}
                  aria-label={t("Remove selected file", "إزالة الملف المحدد")}
                  onClick={() => setSelectedFile(null)}
                  className="rounded p-1 text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-800 hover:text-slate-600 transition"
                >
                  <X size={15} />
                </button>
              </div>
            )}
          </div>

          {/* Conversation Title (Optional) */}
          <div className="space-y-1.5">
            <label
              htmlFor="conversation-title"
              className="block text-xs font-bold text-slate-700 dark:text-slate-300"
            >
              {t("Conversation Title")}
              <span className="text-slate-400 dark:text-slate-500 font-normal">
                {t("(optional)")}
              </span>
            </label>
            <input
              id="conversation-title"
              type="text"
              disabled={isUploading}
              value={chatTitle}
              onChange={(e) => setChatTitle(e.target.value)}
              placeholder={t("e.g. Invoice Q3 Review or Legal Clauses")}
              className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs text-slate-800 placeholder:text-slate-400 focus:border-emerald-500 focus:outline-none dark:border-slate-800 dark:bg-slate-900 dark:text-slate-100 dark:placeholder:text-slate-500"
            />
          </div>

          {/* 3 Pages Limit Notice */}
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-2.5 text-[11px] text-slate-500 dark:border-slate-800 dark:bg-slate-900/60 dark:text-slate-400 leading-relaxed flex items-start gap-2">
            <ShieldCheck
              size={14}
              className="text-emerald-600 dark:text-emerald-400 shrink-0 mt-0.5"
            />
            <span>
              {t(
                "Conversations are strictly optimized for rapid interactive Q&A on short documents (up to 3 pages). All services, including Advanced OCR, use the same 5 MB and 3-page upload limits.",
              )}
            </span>
          </div>

          {/* Error Message */}
          {modalError && (
            <div className="flex items-start gap-2 rounded-xl border border-eose-200 bg-rose-50 p-3 text-xs text-rose-800 dark:border-eose-800 dark:bg-rose-950/40 dark:text-rose-300">
              <AlertCircle
                size={15}
                className="shrink-0 text-rose-600 mt-0.5"
              />
              <span className="leading-snug">{t(modalError)}</span>
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex items-center justify-end gap-2.5 pt-2 border-t border-slate-100 dark:border-slate-800">
            <button
              type="button"
              disabled={isUploading}
              onClick={handleCloseModal}
              aria-label={t("Close")}
              className="rounded-xl border border-slate-200 px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50 dark:border-slate-800 dark:text-slate-400 dark:hover:bg-slate-800 transition disabled:opacity-50"
            >
              {t("Cancel")}
            </button>
            <button
              type="button"
              disabled={!selectedFile || isUploading || remaining < 1}
              onClick={handleStartChat}
              className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-teal-700 to-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:from-teal-800 hover:to-emerald-700 transition disabled:opacity-50 disabled:cursor-not-allowed shadow-xs"
            >
              {isUploading ? (
                <>
                  <Spinner size={14} />
                  <span>{t("Preparing document…")}</span>
                </>
              ) : (
                <>
                  <Zap
                    size={14}
                    className="text-emerald-200 fill-emerald-200"
                  />
                  <span>{t("Start chat")}</span>
                </>
              )}
            </button>
          </div>
        </Dialog>
      )}
    </div>
  );
}
