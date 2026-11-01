"use client";
import { useLanguage } from "@/components/providers/language-provider";
import { useModelSettings } from "@/components/providers/model-provider";
import { use, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { ChatInput } from "@/components/chat/chat-input";
import { MessageBubble } from "@/components/chat/message-bubble";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import {
  streamChat,
  fetchSession,
  fetchCapabilities,
  fetchPage,
  ApiError,
} from "@/lib/api";
import type { ChatMode, Message } from "@/lib/types";
import { serviceCatalog } from "@/lib/service-catalog";
import { workflows } from "@/lib/workflows";
import {
  ArrowLeft,
  Download,
  FileText,
  BookOpen,
  ChevronLeft,
  ChevronRight,
  Sparkles,
  PanelRightClose,
  Bot,
  Settings2,
  ArrowUpRight,
  Zap,
  X,
  Info,
  Layers,
  ShieldCheck,
  Search,
} from "lucide-react";

export interface DocumentServiceItem {
  id: ChatMode;
  name: string;
  credits: number;
  category: "Finance" | "Legal" | "Security" | "Extraction" | "General" | "Advanced";
  desc: string;
  prompt: string;
}

export const DOCUMENT_SERVICES: DocumentServiceItem[] = [
  { id: "invoice", name: "Invoice Extraction", credits: 25, category: "Finance", desc: "Extract vendor, invoice date, line items, VAT, and total payment amounts.", prompt: "Extract all structured invoice fields: vendor, invoice date, line items, VAT, and total payment amounts." },
  { id: "contract", name: "Contract Analysis", credits: 35, category: "Legal", desc: "Review liabilities, governing jurisdiction, termination clauses, and risks.", prompt: "Perform complete legal contract analysis: liabilities, governing jurisdiction, termination clauses, and risks." },
  { id: "compliance", name: "PII & Compliance Audit", credits: 30, category: "Security", desc: "Scan document for PII, GDPR/HIPAA compliance risks, and privacy violations.", prompt: "Audit this document for sensitive PII, GDPR/HIPAA compliance risks, and privacy issues." },
  { id: "summary", name: "Executive Summary", credits: 10, category: "General", desc: "Generate a multi-section executive summary with key findings and action items.", prompt: "Generate an executive summary of this document with key findings, metrics, and actionable takeaways." },
  { id: "extraction", name: "Structured Data Extraction", credits: 15, category: "Extraction", desc: "Extract tables, key-value schemas, and document metrics.", prompt: "Extract all tables, key metrics, and structured key-value data from this document." },
  { id: "financial_statement", name: "Financial Statement", credits: 35, category: "Finance", desc: "Extract balance sheet items, income statements, and solvency ratios.", prompt: "Extract balance sheet metrics, income statement figures, and key solvency ratios from this document." },
  { id: "receipt", name: "Receipt & Expenses", credits: 20, category: "Finance", desc: "Extract merchant details, expense categories, taxes, and totals.", prompt: "Parse receipt details: merchant, date, expense line items, taxes, and total paid." },
  { id: "resume", name: "Resume & Talent Taxonomy", credits: 25, category: "General", desc: "Analyze candidate skills taxonomy, career timeline, and seniority.", prompt: "Analyze candidate skills, career timeline, educational background, and seniority level." },
  { id: "redaction", name: "Bilingual PII Redaction", credits: 25, category: "Security", desc: "Identify and mask National IDs, IBANs, and private contact info.", prompt: "Identify all PII (names, national IDs, IBANs, emails, phone numbers) and produce a redaction report." },
  { id: "translation", name: "Bilingual Translation", credits: 35, category: "General", desc: "High-accuracy Arabic-English document translation.", prompt: "Translate the key sections of this document preserving technical terms and context." },
  { id: "form_parser", name: "Form & Field Parser", credits: 25, category: "Extraction", desc: "Parse structured form fields, checkboxes, and signatures.", prompt: "Extract all filled form fields, checkboxes, dates, and signature areas from this document." },
  { id: "anomaly_audit", name: "Anomaly & Fraud Audit", credits: 35, category: "Finance", desc: "Detect numeric irregularities, altered values, and risk patterns.", prompt: "Perform an anomaly and fraud audit: check numeric calculations, inconsistency flags, and irregularities." },
  { id: "classifier", name: "Document Classifier", credits: 15, category: "General", desc: "Classify document types and workflows into standard categories.", prompt: "Classify this document into its primary business taxonomy and identify the document type and purpose." },
  { id: "factcheck", name: "Claim & Fact Verification", credits: 15, category: "General", desc: "Verify factual claims against cited document evidence.", prompt: "Verify key factual claims and assertions against the explicit text in this document." },
  { id: "comparison", name: "Comparative Analysis", credits: 20, category: "General", desc: "Compare multiple clauses or sections side-by-side.", prompt: "Compare the key clauses, pricing terms, or obligations across sections in this document." },
  { id: "coordinator", name: "Multi-Agent Coordinator", credits: 45, category: "Advanced", desc: "Autonomous coordinator that routes queries to specialized sub-agents.", prompt: "Coordinate end-to-end multi-agent analysis on this document to produce a comprehensive report." },
  { id: "conversational", name: "Document Chat", credits: 1, category: "General", desc: "Interactive conversational Q&A and reasoning with Luna.", prompt: "What are the most important points in this document?" },
];

function getServiceCost(mode: string): number {
  const match = DOCUMENT_SERVICES.find((s) => s.id === mode);
  return match ? match.credits : 1;
}

export default function ChatPage({
  params,
}: {
  params: Promise<{ sessionId: string }>;
}) {
  const { t, language } = useLanguage();
  const localizedServices = DOCUMENT_SERVICES.map((service) => {
    const copy = serviceCatalog.find((entry) => entry.id === service.id);
    return { ...service, name: copy?.title[language] || service.name, desc: copy?.description[language] || service.desc };
  });
  const { sessionId } = use(params);
  const search = useSearchParams();
  const initialWorkflow = workflows.find(
    (w) => w.id === search?.get("workflow"),
  );
  const [session, setSession] = useState<Awaited<
    ReturnType<typeof fetchSession>
  > | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState("");
  const [mode, setMode] = useState<ChatMode>(
    initialWorkflow?.mode || "conversational",
  );
  const { availableModels, selectedModel } = useModelSettings();
  const [models, setModels] = useState<string[]>([]);
  const [model, setModel] = useState(selectedModel || "");
  const [style, setStyle] = useState("balanced");
  const [sourceOpen, setSourceOpen] = useState(true);
  const [page, setPage] = useState(1);
  const [source, setSource] = useState("");
  const [sourceError, setSourceError] = useState("");
  const [sourceLoading, setSourceLoading] = useState(false);
  const [draft, setDraft] = useState(initialWorkflow?.prompt || "");
  const [draftKey, setDraftKey] = useState(0);
  const [serviceModalOpen, setServiceModalOpen] = useState(false);
  const [serviceSearch, setServiceSearch] = useState("");
  const [serviceCategory, setServiceCategory] = useState<string>("All");
  const scroll = useRef<HTMLDivElement>(null);
  const abort = useRef<AbortController | null>(null);
  const messageSequence = useRef(0);
  useEffect(() => {
    let active = true;
    fetchSession(sessionId)
      .then((s) => {
        if (active) {
          setSession(s);
          setMessages(s.messages);
        }
      })
      .catch((e) => {
        if (active)
          setError(
            e instanceof ApiError
              ? e.message
              : "Could not load the conversation.",
          );
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    fetchCapabilities()
      .then((c) => {
        if (active) {
          setModels(c.models);
          setModel((prev) => prev || selectedModel || c.defaultModel);
        }
      })
      .catch(() => {});
    return () => {
      active = false;
      abort.current?.abort();
    };
  }, [sessionId, selectedModel]);

  useEffect(() => {
    if (selectedModel) {
      setModel(selectedModel);
    }
  }, [selectedModel]);
  useEffect(() => {
    if (!session || !sourceOpen) return;
    let active = true;
    const load = async () => {
      setSourceLoading(true);
      setSourceError("");
      try {
        const p = await fetchPage(session.document.id, page);
        if (active) setSource(p.text);
      } catch {
        if (active) {
          setSource("");
          setSourceError(
            "Could not read this section. Try another page or reopen the panel.",
          );
        }
      } finally {
        if (active) setSourceLoading(false);
      }
    };
    void load();
    return () => {
      active = false;
    };
  }, [session, sourceOpen, page]);
  useEffect(() => {
    scroll.current?.scrollTo({
      top: scroll.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);
  const send = async (text: string, selectedMode: ChatMode = mode) => {
    if (streaming) return;
    setError("");
    const now = new Date().toISOString();
    // Optimistic message IDs are local UI keys, including on plain HTTP hosts.
    const id = `local-${sessionId}-${Date.now()}-${messageSequence.current++}`;
    setMessages((m) => [
      ...m,
      {
        id: `${id}-user`,
        sessionId,
        role: "user",
        content: text,
        createdAt: now,
      },
      { id, sessionId, role: "assistant", content: "", createdAt: now },
    ]);
    setStreaming(true);
    const controller = new AbortController();
    abort.current = controller;
    let acc = "";
    try {
      for await (const chunk of streamChat(sessionId, text, selectedMode, {
        model: model || undefined,
        responseStyle: style,
        signal: controller.signal,
      })) {
        acc += chunk;
        setMessages((m) =>
          m.map((item) => (item.id === id ? { ...item, content: acc } : item)),
        );
      }
    } catch (e) {
      if (!(e instanceof Error && e.name === "AbortError"))
        setError(
          e instanceof ApiError
            ? e.message
            : "The response was interrupted. Please try again.",
        );
    } finally {
      setStreaming(false);
      abort.current = null;
      if (typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent("doctool:credit-updated"));
      }
    }
  };
  const exportChat = () => {
    const text =
      `# ${session?.title}\n\n` +
      messages
        .map(
          (m) => `## ${m.role === "user" ? "You" : "DOCTool"}\n\n${m.content}`,
        )
        .join("\n\n");
    const url = URL.createObjectURL(
      new Blob([text], { type: "text/markdown" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = "doctool-conversation.md";
    a.click();
    URL.revokeObjectURL(url);
  };
  const apply = (id: string) => {
    const w = workflows.find((x) => x.id === id);
    if (w) {
      setMode(w.mode);
      setDraft(w.prompt);
      setDraftKey((n) => n + 1);
    }
  };
  if (loading)
    return (
      <div className="flex h-[70vh] items-center justify-center">
        <Spinner size={28} />
      </div>
    );
  if (!session)
    return (
      <div role="alert" className="surface p-8">
        <p className="text-sm text-rose-700">
          {error || "Conversation unavailable."}
        </p>
        <Link href="/conversations" className="mt-5 inline-block text-sm text-teal-700">
          {t("Return to conversations")}</Link>
      </div>
    );
  const unit = /\.pdf$/i.test(session.document.originalFilename)
    ? "page"
    : "section";
  return (
    <div className="mx-auto flex h-full w-full max-w-[1600px] flex-col overflow-hidden">
      <header className="mb-2.5 flex shrink-0 flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <Link
            href="/conversations"
            aria-label={t("Back to conversations")}
            className="rounded-lg border border-slate-200 bg-white p-2 text-slate-500"
          >
            <ArrowLeft size={17} />
          </Link>
          <div className="min-w-0">
            <p className="eyebrow mb-0.5">{t("Workspace / Conversations")}</p>
            <h1 className="max-w-[60vw] truncate text-base font-semibold tracking-tight lg:max-w-xl">
              {session.title}
            </h1>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Link
            href="/usage"
            title={t("Chat consumes 1 credit per response")}
            className="hidden sm:inline-flex items-center gap-1.5 rounded-lg border border-teal-200 bg-teal-50 px-2.5 py-1.5 text-xs font-semibold text-teal-800 hover:bg-teal-100 transition shadow-2xs"
          >
            <Zap size={12} className="text-teal-600 fill-teal-600" />
            <span>{t("1 Credit / Response")}</span>
          </Link>
          <Button
            variant="outline"
            size="sm"
            onClick={exportChat}
            disabled={!messages.length || streaming}
            className="gap-2 !border-slate-200 bg-white text-xs"
          >
            <Download size={14} /> {t("Export")}</Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setSourceOpen(!sourceOpen)}
            aria-expanded={sourceOpen}
            className="gap-2 !border-slate-200 bg-white text-xs"
          >
            <BookOpen size={14} /> {t("Source")}</Button>
        </div>
      </header>
      <div
        className={`grid flex-1 min-h-0 gap-3.5 overflow-hidden ${sourceOpen ? "xl:grid-cols-[minmax(0,1fr)_340px]" : "grid-cols-1"}`}
      >
        <section className="surface flex min-w-0 flex-1 flex-col overflow-hidden h-full">
          <div className="flex shrink-0 flex-wrap items-center gap-3 border-b border-slate-100 dark:border-slate-800 px-4 py-2 bg-white dark:bg-[#121820]">
            <div className="mr-auto flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" /> {t("Grounded in your document")}</div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setServiceModalOpen(true)}
                className="inline-flex items-center gap-1.5 rounded-md border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-[11px] font-semibold text-emerald-800 hover:bg-emerald-100 dark:border-emerald-800/60 dark:bg-emerald-950/40 dark:text-emerald-300 dark:hover:bg-emerald-900/50 transition shadow-2xs"
              >
                <Layers size={13} className="text-emerald-600 dark:text-emerald-400" />
                <span>{t("Services (19)")}</span>
              </button>
              <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 dark:bg-slate-800 px-2 py-1 text-[10px] font-semibold text-slate-600 dark:text-slate-300">
                <Zap size={11} className="text-emerald-600 fill-emerald-600 dark:text-emerald-400 dark:fill-emerald-400" />
                {getServiceCost(mode)}{t("c / call")}</span>
              <select
                aria-label={t("Assistant mode")}
                disabled={streaming}
                value={mode}
                onChange={(e) => setMode(e.target.value as ChatMode)}
                className="rounded-md border border-slate-200 bg-white p-1 text-[11px] dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200"
              >
                <option value="conversational">{t("Document chat")}</option>
                <option value="agent">{t("Research agent")}</option>
                <option value="summary">{t("Summary agent")}</option>
                <option value="research">{t("Deep research")}</option>
                <option value="extraction">{t("Data extraction")}</option>
                <option value="comparison">{t("Comparison")}</option>
                <option value="factcheck">{t("Fact-check")}</option>
                <option value="invoice">{t("Invoice processing")}</option>
                <option value="receipt">{t("Receipt & Expenses")}</option>
                <option value="contract">{t("Contract analysis")}</option>
                <option value="resume">{t("Resume & Talent")}</option>
                <option value="compliance">{t("PII & Compliance")}</option>
                <option value="form_parser">{t("Form Parser")}</option>
                <option value="google_ai">{t("Google AI Document")}</option>
                <option value="coordinator">{t("Auto-routing")}</option>
              </select>
            </div>
          </div>
          <div
            ref={scroll}
            aria-live="polite"
            aria-relevant="additions"
            className="flex-1 min-h-0 overflow-y-auto px-4 py-4 sm:px-6"
          >
            {messages.length ? (
              messages.map((m, i) => (
                <MessageBubble
                  key={m.id}
                  message={m}
                  isStreaming={streaming && i === messages.length - 1}
                />
              ))
            ) : (
              <div className="mx-auto max-w-lg py-8 text-slate-900 dark:text-slate-100">
                <span className="mb-5 inline-flex rounded-2xl bg-emerald-50 p-4 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-400">
                  <Sparkles size={29} />
                </span>
                <h2 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
                  {t("What would you like to know about this document?")}</h2>
                <p className="mt-3 text-sm leading-7 text-slate-500 dark:text-slate-400">
                  {t("Ask about")}{session.document.originalFilename}{t(", or choose a task below.")}</p>
                <div className="mt-7 grid gap-3 sm:grid-cols-2">
                  {workflows.map((w) => (
                    <button
                      key={w.id}
                      onClick={() => apply(w.id)}
                      className="rounded-xl border border-slate-200 bg-white p-4 text-left transition hover:border-emerald-500 hover:bg-emerald-50/20 dark:border-slate-800 dark:bg-[#121820] dark:hover:bg-emerald-950/20"
                    >
                      <span className="flex items-center justify-between text-xs font-semibold text-slate-800 dark:text-slate-200">
                        {w.title}
                        <ArrowUpRight size={13} className="text-emerald-600 dark:text-emerald-400" />
                      </span>
                      <span className="mt-2 block text-[11px] leading-5 text-slate-400 dark:text-slate-500">
                        {w.description}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
          <div className="shrink-0 border-t border-slate-100 dark:border-slate-800 p-3 sm:px-5 bg-white dark:bg-[#121820]">
            {error && (
              <div
                role="alert"
                className="mb-2.5 flex items-center justify-between rounded-lg bg-rose-50 p-2.5 text-xs text-rose-700"
              >
                <span>{error}</span>
                {error.toLowerCase().includes("credit") && (
                  <Link
                    href="/usage"
                    className="ml-3 shrink-0 rounded bg-rose-600 px-2 py-0.5 text-[11px] font-medium text-white hover:bg-rose-700 transition"
                  >
                    {t("View API & Credits")}</Link>
                )}
              </div>
            )}
            {/* Quick Action Service Pills */}
            <div className="mb-2 flex items-center gap-1.5 overflow-x-auto pb-1 text-[11px] scrollbar-none">
              <span className="shrink-0 text-[10px] font-medium uppercase tracking-wider text-slate-400">
                {t("Services:")}</span>
              <button
                type="button"
                disabled={streaming}
                onClick={() => {
                  setMode("invoice");
                  send("Extract all structured invoice fields: vendor, invoice date, line items, VAT, and total payment amounts.", "invoice");
                }}
                className="shrink-0 inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-slate-700 hover:border-teal-500 hover:text-teal-800 hover:bg-teal-50/50 transition shadow-2xs disabled:opacity-50"
              >
                <Zap size={11} className="text-teal-600 fill-teal-600" /> {t("Invoice (25c)")}</button>
              <button
                type="button"
                disabled={streaming}
                onClick={() => {
                  setMode("summary");
                  send("Generate an executive summary of this document with key findings, metrics, and actionable takeaways.", "summary");
                }}
                className="shrink-0 inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-slate-700 hover:border-teal-500 hover:text-teal-800 hover:bg-teal-50/50 transition shadow-2xs disabled:opacity-50"
              >
                <Zap size={11} className="text-teal-600 fill-teal-600" /> {t("Summary (10c)")}</button>
              <button
                type="button"
                disabled={streaming}
                onClick={() => {
                  setMode("contract");
                  send("Perform complete legal contract analysis: liabilities, governing jurisdiction, termination clauses, and risks.", "contract");
                }}
                className="shrink-0 inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-slate-700 hover:border-teal-500 hover:text-teal-800 hover:bg-teal-50/50 transition shadow-2xs disabled:opacity-50"
              >
                <Zap size={11} className="text-teal-600 fill-teal-600" /> {t("Contract (35c)")}</button>
              <button
                type="button"
                disabled={streaming}
                onClick={() => {
                  setMode("compliance");
                  send("Audit this document for sensitive PII, GDPR/HIPAA compliance risks, and privacy issues.", "compliance");
                }}
                className="shrink-0 inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-slate-700 hover:border-teal-500 hover:text-teal-800 hover:bg-teal-50/50 transition shadow-2xs disabled:opacity-50"
              >
                <Zap size={11} className="text-teal-600 fill-teal-600" /> {t("Compliance (30c)")}</button>
              <button
                type="button"
                disabled={streaming}
                onClick={() => {
                  send("Please explain all 19 Document AI services available in DOC Tool, what each service does, their credit costs, and how to run them on this document.");
                }}
                className="shrink-0 inline-flex items-center gap-1 rounded-full border border-teal-200 bg-teal-50/80 px-2.5 py-1 text-teal-800 hover:bg-teal-100 transition shadow-2xs disabled:opacity-50 font-medium"
              >
                <Info size={11} className="text-teal-600" /> {t("Explain Services (1c)")}</button>
              <button
                type="button"
                disabled={streaming}
                onClick={() => setServiceModalOpen(true)}
                className="shrink-0 inline-flex items-center gap-1 rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-slate-600 hover:bg-slate-100 transition shadow-2xs font-medium"
              >
                <Layers size={11} /> {t("All 19 Services →")}</button>
            </div>
            <ChatInput
              key={draftKey}
              initialText={draft}
              onSubmit={send}
              disabled={streaming}
              onStop={() => abort.current?.abort()}
            />
            <div className="mt-1.5 flex items-center justify-between gap-2 text-[9px] text-slate-400">
              <span>
                {streaming
                  ? mode === "agent" ||
                    mode === "research" ||
                    mode === "comparison" ||
                    mode === "factcheck" ||
                    mode === "coordinator"
                    ? "Agent is searching and reading your document…"
                    : mode === "extraction"
                      ? "Agent is extracting data from your document…"
                      : mode === "summary"
                        ? "Agent is summarizing your document…"
                        : mode === "invoice"
                          ? "Agent is processing the invoice…"
                          : mode === "contract"
                            ? "Agent is analyzing the contract…"
                            : "Preparing your answer…"
                  : "AI can make mistakes. Check important details against the source."}
              </span>
              <span className="hidden shrink-0 sm:block">
                {mode === "agent"
                  ? t("Research agent")
                  : mode === "summary"
                    ? t("Summary agent")
                    : mode === "research"
                      ? t("Deep research")
                      : mode === "extraction"
                        ? t("Data extraction")
                        : mode === "comparison"
                          ? t("Comparison")
                          : mode === "factcheck"
                            ? t("Fact-check")
                            : mode === "invoice"
                              ? t("Invoice processing")
                              : mode === "contract"
                                ? t("Contract analysis")
                                : mode === "coordinator"
                                  ? t("Auto-routing")
                                  : t("Document chat")}
              </span>
            </div>
          </div>
        </section>
        {sourceOpen && (
          <aside className="flex min-w-0 flex-col gap-3 h-full overflow-hidden">
            <section className="surface shrink-0 p-3.5">
              <div className="flex items-center justify-between mb-2">
                <h2 className="flex items-center gap-1.5 text-xs font-semibold">
                  <Settings2 size={14} className="text-slate-400" />
                  {t("Conversation settings")}</h2>
              </div>
              <div className="grid grid-cols-2 gap-2 text-[10px]">
                <div>
                  <label htmlFor="model" className="mb-1 block text-slate-500">
                    {t("Model")}</label>
                  <select
                    id="model"
                    disabled={streaming || (!models.length && !availableModels.length)}
                    value={model}
                    onChange={(e) => setModel(e.target.value)}
                    className="w-full rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-xs font-mono"
                  >
                    {(models.length ? models : availableModels.map((m) => m.id)).map((m) => {
                      const mInfo = availableModels.find((item) => item.id === m);
                      const label = mInfo
                        ? `${mInfo.name} (${mInfo.credit_cost} credits)`
                        : m;
                      return (
                        <option key={m} value={m}>
                          {label}
                        </option>
                      );
                    })}
                  </select>
                </div>
                <div>
                  <label htmlFor="style" className="mb-1 block text-slate-500">
                    {t("Length")}</label>
                  <select
                    id="style"
                    disabled={streaming}
                    value={style}
                    onChange={(e) => setStyle(e.target.value)}
                    className="w-full rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-xs"
                  >
                    <option value="concise">{t("Concise")}</option>
                    <option value="balanced">{t("Balanced")}</option>
                    <option value="detailed">{t("Detailed")}</option>
                  </select>
                </div>
              </div>
            </section>
            <section className="surface flex flex-1 min-h-0 flex-col overflow-hidden p-3.5">
              <div className="flex shrink-0 items-center justify-between">
                <h2 className="flex items-center gap-1.5 text-xs font-semibold">
                  <BookOpen size={14} className="text-slate-400" /> {t("Source reader")}</h2>
                <button
                  aria-label={t("Close source reader")}
                  onClick={() => setSourceOpen(false)}
                  className="text-slate-400 hover:text-slate-600 transition"
                >
                  <PanelRightClose size={15} />
                </button>
              </div>
              <div className="my-2 flex shrink-0 items-center gap-2 rounded-lg bg-slate-100 dark:bg-slate-800 p-2">
                <FileText size={16} className="shrink-0 text-teal-700" />
                <p
                  title={session.document.originalFilename}
                  className="truncate text-[11px] font-medium"
                >
                  {session.document.originalFilename}
                </p>
              </div>
              <div className="flex shrink-0 items-center justify-between border-b border-slate-100 pb-2">
                <button
                  aria-label={t("Previous section")}
                  disabled={page <= 1 || sourceLoading}
                  onClick={() => setPage((p) => p - 1)}
                  className="rounded p-1 text-slate-500 disabled:opacity-25"
                >
                  <ChevronLeft size={14} />
                </button>
                <span className="text-[10px] capitalize text-slate-500">
                  {unit} {page} {t("of")}{session.document.pageCount}
                </span>
                <button
                  aria-label={t("Next section")}
                  disabled={page >= session.document.pageCount || sourceLoading}
                  onClick={() => setPage((p) => p + 1)}
                  className="rounded p-1 text-slate-500 disabled:opacity-25"
                >
                  <ChevronRight size={14} />
                </button>
              </div>
              <div className="mt-2.5 flex-1 min-h-0 overflow-y-auto whitespace-pre-wrap break-words text-[11px] leading-6 text-slate-500 pr-1">
                {sourceLoading ? (
                  <Spinner size={18} />
                ) : sourceError ? (
                  <p role="alert">{sourceError}</p>
                ) : (
                  source
                )}
              </div>
              <button
                disabled={streaming || sourceLoading || !source}
                onClick={() => {
                  setDraft(
                    `Explain the key points on ${unit} ${page} of this document, citing the source.`,
                  );
                  setDraftKey((k) => k + 1);
                }}
                className="mt-2 shrink-0 flex items-center justify-between border-t border-slate-100 pt-2 text-[10px] font-medium text-teal-700 disabled:opacity-40"
              >
                {t("Ask about this")}{unit}
                <ArrowUpRight size={13} />
              </button>
            </section>
          </aside>
        )}
      </div>

      {/* Service Catalog Modal */}
      {serviceModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4 backdrop-blur-xs">
          <div className="surface flex max-h-[88vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
              <div>
                <h2 className="flex items-center gap-2 text-base font-semibold text-slate-900">
                  <Sparkles size={18} className="text-teal-600" />
                  {t("Document AI Services Catalog")}</h2>
                <p className="mt-0.5 text-xs text-slate-500">
                  {t("Choose a task to run on this document. Review the credit cost before running it.", "اختر مهمة لتشغيلها على هذا المستند. راجع تكلفة الرصيد قبل التشغيل.")}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setServiceModalOpen(false)}
                className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition"
                aria-label={t("Close service catalog")}
              >
                <X size={18} />
              </button>
            </div>

            <div className="flex flex-col sm:flex-row items-center justify-between gap-3 border-b border-slate-100 bg-slate-50/60 px-6 py-3">
              <div className="relative w-full sm:w-72">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  type="text"
                  placeholder={t("Search 19 services...")}
                  value={serviceSearch}
                  onChange={(e) => setServiceSearch(e.target.value)}
                  className="w-full rounded-lg border border-slate-200 bg-white py-1.5 pl-9 pr-3 text-xs text-slate-800 placeholder:text-slate-400 focus:border-teal-500 focus:outline-hidden"
                />
              </div>
              <div className="flex w-full sm:w-auto items-center gap-1 overflow-x-auto pb-1 sm:pb-0 scrollbar-none">
                {(["All", "Finance", "Legal", "Security", "Extraction", "General", "Advanced"] as const).map((cat) => (
                  <button
                    key={cat}
                    type="button"
                    onClick={() => setServiceCategory(cat)}
                    className={`rounded-full px-3 py-1 text-xs font-medium transition ${
                      serviceCategory === cat
                        ? "bg-teal-600 text-white shadow-2xs"
                        : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-100"
                    }`}
                  >
                    {cat}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-6">
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {localizedServices.filter((svc) => {
                  const matchesCat = serviceCategory === "All" || svc.category === serviceCategory;
                  const matchesQuery =
                    !serviceSearch.trim() ||
                    svc.name.toLowerCase().includes(serviceSearch.toLowerCase()) ||
                    svc.desc.toLowerCase().includes(serviceSearch.toLowerCase()) ||
                    serviceCatalog.some((entry) => entry.id === svc.id && `${entry.title.en} ${entry.title.ar}`.toLowerCase().includes(serviceSearch.toLowerCase()));
                  return matchesCat && matchesQuery;
                }).map((svc) => (
                  <div
                    key={svc.id}
                    className="flex flex-col justify-between rounded-xl border border-slate-200 bg-white p-4 shadow-2xs hover:border-teal-400 transition"
                  >
                    <div>
                      <div className="mb-2 flex items-center justify-between gap-2">
                        <span className="rounded-md bg-slate-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-slate-600">
                          {svc.category}
                        </span>
                        <span className="inline-flex items-center gap-1 rounded-md border border-teal-200/60 bg-teal-50 px-2 py-0.5 text-[11px] font-semibold text-teal-700">
                          <Zap size={11} className="fill-teal-600 text-teal-600" />
                          {svc.credits}c
                        </span>
                      </div>
                      <h3 className="text-sm font-semibold text-slate-800">{svc.name}</h3>
                      <p className="mt-1 text-xs leading-5 text-slate-500 line-clamp-3">
                        {svc.desc}
                      </p>
                    </div>
                    <div className="mt-4 flex items-center gap-2 border-t border-slate-100 pt-3">
                      <button
                        type="button"
                        disabled={streaming}
                        onClick={() => {
                          setMode(svc.id);
                          setServiceModalOpen(false);
                          send(svc.prompt, svc.id);
                        }}
                        className="inline-flex flex-1 items-center justify-center gap-1 rounded-lg bg-teal-600 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-teal-700 transition disabled:opacity-50"
                      >
                        <Zap size={12} className="fill-white" />
                        {t("Run")}</button>
                      <button
                        type="button"
                        disabled={streaming}
                        onClick={() => {
                          setServiceModalOpen(false);
                          send(
                            `Explain how the "${svc.name}" service works, what inputs and outputs it uses, its cost (${svc.credits} credits), and how you can run it on this document.`
                          );
                        }}
                        className="inline-flex items-center justify-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 transition disabled:opacity-50"
                      >
                        <Info size={12} className="text-teal-600" />
                        {t("Explain")}</button>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="flex items-center justify-between border-t border-slate-100 bg-slate-50 px-6 py-3 text-xs text-slate-500">
              <span>{t("Document processing tools", "أدوات معالجة المستندات")}</span>
              <button
                type="button"
                onClick={() => setServiceModalOpen(false)}
                className="rounded-lg border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100"
              >
                {t("Close")}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
