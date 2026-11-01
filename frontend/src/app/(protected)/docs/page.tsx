"use client";

import { useEffect, useState, useMemo } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  Code2,
  Copy,
  Check,
  Search,
  Zap,
  Timer,
  Layers,
  ShieldCheck,
  Sparkles,
  ExternalLink,
  ChevronRight,
  FileCode,
  FileText,
  Key,
  BookOpen,
  ArrowRight,
  Coins,
  Languages,
  CheckCircle2,
  AlertCircle,
  Menu,
  X,
  RefreshCw,
  Terminal,
  Cpu,
} from "lucide-react";
import {
  DOCS_CATEGORIES,
  ALL_DOC_ITEMS,
  getDocItemById,
  type DocServiceItem,
} from "@/lib/docs-data";
import {
  generateCurlCode,
  generatePythonCode,
  generateTypescriptCode,
  generateWorkflowCode,
} from "@/lib/docs-code-generator";
import { fetchCompanyAccount, type CompanyAccountInfo } from "@/lib/api";
import { useModelSettings } from "@/components/providers/model-provider";
import { cn } from "@/lib/utils";

export default function DocsPage() {
  const { availableModels, selectedModel, setSelectedModel, calculateCost } = useModelSettings();
  const searchParams = useSearchParams();
  const router = useRouter();

  const [docModel, setDocModel] = useState<string>(selectedModel);

  useEffect(() => {
    setDocModel(selectedModel);
  }, [selectedModel]);

  // Active service or endpoint ID from query params
  const initialServiceId = searchParams.get("service") || "invoice";

  const [activeItem, setActiveItem] = useState<DocServiceItem>(() => {
    return getDocItemById(initialServiceId) || ALL_DOC_ITEMS[0];
  });

  const [searchQuery, setSearchQuery] = useState("");
  const [codeLanguage, setCodeLanguage] = useState<"curl" | "python" | "typescript" | "workflow">("curl");
  const [copiedCode, setCopiedCode] = useState(false);
  const [copiedEndpoint, setCopiedEndpoint] = useState(false);
  const [copiedKey, setCopiedKey] = useState(false);
  const [copiedJson, setCopiedJson] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  // User Company Account for dynamic API key & credit values
  const [account, setAccount] = useState<CompanyAccountInfo | null>(null);

  useEffect(() => {
    let active = true;
    fetchCompanyAccount()
      .then((data) => {
        if (active) setAccount(data);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);

  // Sync state if URL query param changes
  useEffect(() => {
    const sId = searchParams.get("service");
    if (sId) {
      const found = getDocItemById(sId);
      if (found && found.id !== activeItem.id) {
        setActiveItem(found);
      }
    }
  }, [searchParams, activeItem.id]);

  // Select a service from the sidebar
  const handleSelectItem = (item: DocServiceItem) => {
    setActiveItem(item);
    setMobileSidebarOpen(false);
    router.replace(`/docs?service=${item.id}`, { scroll: false });
    // Scroll top of doc pane
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  // Filter categories and items based on search query
  const filteredCategories = useMemo(() => {
    const q = searchQuery.toLowerCase().trim();
    if (!q) return DOCS_CATEGORIES;

    return DOCS_CATEGORIES.map((cat) => {
      const matchingItems = cat.items.filter(
        (item) =>
          item.title.toLowerCase().includes(q) ||
          item.description.toLowerCase().includes(q) ||
          item.endpoint.toLowerCase().includes(q) ||
          item.badge.toLowerCase().includes(q) ||
          (item.serviceKey && item.serviceKey.toLowerCase().includes(q))
      );
      return {
        ...cat,
        items: matchingItems,
      };
    }).filter((cat) => cat.items.length > 0);
  }, [searchQuery]);

  const rawKey = account?.rawApiKey || account?.apiKey || account?.apiKeyPrefix || "docu_live_sample_key_9912";

  const curlCode = useMemo(() => generateCurlCode(activeItem, rawKey, undefined, docModel), [activeItem, rawKey, docModel]);
  const pythonCode = useMemo(() => generatePythonCode(activeItem, rawKey, undefined, docModel), [activeItem, rawKey, docModel]);
  const tsCode = useMemo(() => generateTypescriptCode(activeItem, rawKey, undefined, docModel), [activeItem, rawKey, docModel]);
  const workflowCode = useMemo(() => generateWorkflowCode(activeItem, rawKey, undefined, docModel), [activeItem, rawKey, docModel]);

  const activeCost = useMemo(() => calculateCost(activeItem.credits, docModel), [calculateCost, activeItem.credits, docModel]);

  const activeCodeSnippet =
    codeLanguage === "curl"
      ? curlCode
      : codeLanguage === "python"
      ? pythonCode
      : codeLanguage === "typescript"
      ? tsCode
      : workflowCode;

  const handleCopyCode = () => {
    navigator.clipboard.writeText(activeCodeSnippet).then(() => {
      setCopiedCode(true);
      setTimeout(() => setCopiedCode(false), 2000);
    });
  };

  const handleCopyEndpoint = () => {
    navigator.clipboard.writeText(activeItem.endpoint).then(() => {
      setCopiedEndpoint(true);
      setTimeout(() => setCopiedEndpoint(false), 2000);
    });
  };

  const handleCopyKey = () => {
    navigator.clipboard.writeText(rawKey).then(() => {
      setCopiedKey(true);
      setTimeout(() => setCopiedKey(false), 2000);
    });
  };

  const handleCopyJson = () => {
    navigator.clipboard.writeText(JSON.stringify(activeItem.sampleResponse, null, 2)).then(() => {
      setCopiedJson(true);
      setTimeout(() => setCopiedJson(false), 2000);
    });
  };

  return (
    <div className="mx-auto max-w-7xl animate-enter">
      {/* Top Breadcrumb & Status Banner */}
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-slate-200/80 pb-4">
        <div>
          <div className="flex items-center gap-2 text-xs text-slate-500 mb-1">
            <span className="font-semibold text-teal-800">Developer Platform</span>
            <span>/</span>
            <span className="text-slate-600">REST API Reference</span>
            <span>/</span>
            <span className="font-bold text-slate-900">{activeItem.category}</span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 flex items-center gap-2.5">
            <BookOpen size={24} className="text-[#087f74]" />
            <span>DOC Tool Platform Documentation</span>
          </h1>
          <p className="mt-1 text-xs text-slate-500">
            Interactive specifications, schema references, and code samples for all 19 Document AI services.
          </p>
        </div>

        {/* Dynamic Credit & API Key Pill */}
        <div className="flex flex-wrap items-center gap-2">
          <Link
            href="/usage"
            className="inline-flex items-center gap-1.5 rounded-full border border-teal-200 bg-teal-50 px-3 py-1 text-xs font-semibold text-teal-800 hover:bg-teal-100 transition shadow-2xs"
          >
            <Zap size={13} className="text-teal-600 fill-teal-600" />
            <span>
              {account ? `${account.remainingCredits.toLocaleString()} Credits` : "300 Free Credits"}
            </span>
          </Link>

          <button
            onClick={handleCopyKey}
            title="Copy Company API Key"
            className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-mono font-medium text-slate-700 hover:bg-slate-50 transition shadow-2xs"
          >
            <Key size={12} className="text-teal-600" />
            <span>{account?.apiKeyPrefix || "docu_live_"}••••</span>
            {copiedKey ? <Check size={12} className="text-emerald-600" /> : <Copy size={11} className="text-slate-400" />}
          </button>
        </div>
      </div>

      {/* Mobile Sidebar Selector Toggle */}
      <div className="mb-4 lg:hidden">
        <button
          onClick={() => setMobileSidebarOpen(!mobileSidebarOpen)}
          className="flex w-full items-center justify-between rounded-xl border border-slate-200 bg-white p-3 text-xs font-semibold text-slate-800 shadow-xs"
        >
          <div className="flex items-center gap-2">
            <Menu size={16} className="text-teal-700" />
            <span>
              API Services &amp; Endpoints: <span className="font-bold text-teal-800">{activeItem.title}</span>
            </span>
          </div>
          <span className="rounded bg-teal-50 px-2 py-0.5 text-[10px] text-teal-800 font-bold uppercase">
            {activeItem.method}
          </span>
        </button>
      </div>

      {/* =========================================================================
          PLATFORM DOCS TWO-COLUMN / THREE-COLUMN SHELL
          - Left: Services Sidebar (sticky on desktop)
          - Center: Interactive Documentation View
          - Right: On this page quick jump (desktop xl)
         ========================================================================= */}
      <div className="grid grid-cols-1 gap-8 lg:grid-cols-12 items-start">
        {/* =======================================================================
            1. SERVICES LIST SIDEBAR (LEFT)
           ======================================================================= */}
        <aside
          className={cn(
            "lg:col-span-4 xl:col-span-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-xs sticky top-20 max-h-[calc(100vh-6rem)] overflow-y-auto space-y-4",
            mobileSidebarOpen ? "block" : "hidden lg:block"
          )}
        >
          {/* Search Input */}
          <div className="relative">
            <Search size={14} className="absolute left-3 top-2.5 text-slate-400" />
            <input
              type="text"
              placeholder="Filter services & endpoints..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full rounded-xl border border-slate-200 bg-slate-50/70 py-2 pl-9 pr-7 text-xs text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-teal-600 focus:bg-white focus:ring-1 focus:ring-teal-600"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery("")}
                className="absolute right-2.5 top-2.5 text-slate-400 hover:text-slate-600"
              >
                <X size={13} />
              </button>
            )}
          </div>

          {/* Categories & Services List */}
          <div className="space-y-5">
            {filteredCategories.length === 0 ? (
              <div className="py-6 text-center text-xs text-slate-500">
                <p>No services match &ldquo;{searchQuery}&rdquo;</p>
                <button
                  onClick={() => setSearchQuery("")}
                  className="mt-2 text-teal-700 font-semibold hover:underline"
                >
                  Clear search
                </button>
              </div>
            ) : (
              filteredCategories.map((cat) => (
                <div key={cat.id} className="space-y-1">
                  <p className="px-2 text-[10px] font-extrabold uppercase tracking-wider text-slate-400">
                    {cat.title}
                  </p>
                  <div className="space-y-0.5">
                    {cat.items.map((item) => {
                      const isSelected = activeItem.id === item.id;
                      return (
                        <button
                          key={item.id}
                          onClick={() => handleSelectItem(item)}
                          className={cn(
                            "group flex w-full items-center justify-between rounded-xl px-2.5 py-2 text-left text-xs transition",
                            isSelected
                              ? "bg-teal-50 text-teal-950 font-bold shadow-2xs border border-teal-200/80"
                              : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                          )}
                        >
                          <div className="flex items-center gap-2 truncate">
                            {/* Method Badge */}
                            <span
                              className={cn(
                                "flex h-4 w-10 shrink-0 items-center justify-center rounded text-[9px] font-bold font-mono tracking-tight",
                                item.method === "POST"
                                  ? "bg-teal-100/90 text-teal-800"
                                  : item.method === "GET"
                                  ? "bg-sky-100 text-sky-800"
                                  : "bg-purple-100 text-purple-800"
                              )}
                            >
                              {item.method}
                            </span>
                            <span className="truncate">{item.title}</span>
                          </div>

                          {/* Credits Pill / Status */}
                          {item.credits > 0 ? (
                            <span
                              className={cn(
                                "shrink-0 rounded px-1.5 py-0.5 text-[9px] font-mono font-semibold",
                                isSelected
                                  ? "bg-teal-200/70 text-teal-900"
                                  : "bg-slate-100 text-slate-500 group-hover:bg-slate-200"
                              )}
                            >
                              {item.credits} cr
                            </span>
                          ) : (
                            <span className="shrink-0 text-[10px] text-slate-400 font-mono">
                              free
                            </span>
                          )}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Quick Sandbox Link in Sidebar Footer */}
          <div className="pt-3 border-t border-slate-100 text-xs">
            <Link
              href="/playground"
              className="flex items-center justify-between rounded-xl bg-slate-50 p-2.5 text-slate-700 hover:bg-slate-100 transition"
            >
              <span className="flex items-center gap-1.5 font-medium">
                <Sparkles size={13} className="text-teal-600" />
                <span>Interactive Playground</span>
              </span>
              <ArrowRight size={13} className="text-slate-400" />
            </Link>
          </div>
        </aside>

        {/* =======================================================================
            2. MAIN API DOCUMENTATION CONTENT (CENTER / RIGHT)
           ======================================================================= */}
        <main className="lg:col-span-8 xl:col-span-9 space-y-8">
          {/* SERVICE HERO & ENDPOINT BAR */}
          <section
            id="overview"
            className="rounded-2xl border border-slate-200 bg-white p-6 md:p-8 shadow-xs space-y-6"
          >
            {/* Header with Title and Actions */}
            <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
              <div className="space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={cn(
                      "rounded-md px-2 py-0.5 text-[11px] font-bold font-mono uppercase tracking-wide",
                      activeItem.method === "POST"
                        ? "bg-teal-100 text-teal-900 border border-teal-200"
                        : activeItem.method === "GET"
                        ? "bg-sky-100 text-sky-900 border border-sky-200"
                        : "bg-purple-100 text-purple-900 border border-purple-200"
                    )}
                  >
                    {activeItem.method}
                  </span>
                  <span className="rounded-md bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-700">
                    {activeItem.category}
                  </span>
                  {activeItem.bilingual && (
                    <span className="inline-flex items-center gap-1 rounded-md bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-800 border border-emerald-200">
                      <Languages size={12} /> Bilingual (AR / EN)
                    </span>
                  )}
                  {activeItem.credits > 0 && (
                    <span className="inline-flex items-center gap-1 rounded-md bg-amber-50 px-2 py-0.5 text-[11px] font-bold text-amber-900 border border-amber-200">
                      <Coins size={12} className="text-amber-700" /> {activeItem.credits} Credits / Call
                    </span>
                  )}
                  <span className="inline-flex items-center gap-1 rounded-md bg-teal-50 px-2 py-0.5 text-[11px] font-mono font-bold text-teal-900 border border-teal-200">
                    <Cpu size={12} className="text-teal-700" /> Model: {docModel}
                  </span>
                </div>

                <h2 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
                  {activeItem.title}
                </h2>
                <p className="text-sm text-slate-600 leading-relaxed max-w-3xl">
                  {activeItem.description}
                </p>
              </div>

              {/* Action Buttons: Try in Playground + Copy cURL */}
              <div className="flex flex-wrap items-center gap-2 shrink-0">
                {activeItem.type === "service" && activeItem.serviceKey && (
                  <Link
                    href={`/playground?service=${activeItem.serviceKey}`}
                    className="flex items-center gap-1.5 rounded-xl bg-[#087f74] px-3.5 py-2 text-xs font-semibold text-white shadow-sm hover:bg-[#06675e] transition"
                  >
                    <Sparkles size={14} />
                    <span>Test in Playground</span>
                    <ExternalLink size={12} className="opacity-80" />
                  </Link>
                )}
                <button
                  onClick={handleCopyCode}
                  className="flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition shadow-2xs"
                >
                  {copiedCode ? <Check size={14} className="text-emerald-600" /> : <Copy size={14} />}
                  <span>{copiedCode ? "Copied Snippet" : "Copy Code"}</span>
                </button>
              </div>
            </div>

            {/* HTTP ENDPOINT BAR WITH 1-CLICK COPY */}
            <div className="flex items-center justify-between rounded-xl border border-slate-200 bg-slate-900 p-3.5 text-xs font-mono text-emerald-400 shadow-inner overflow-x-auto">
              <div className="flex items-center gap-2.5">
                <span className="rounded bg-emerald-500/20 px-2 py-0.5 text-[10px] font-bold text-emerald-300 uppercase">
                  {activeItem.method}
                </span>
                <span className="font-semibold text-white">{activeItem.endpoint}</span>
              </div>
              <button
                onClick={handleCopyEndpoint}
                className="flex items-center gap-1 rounded bg-slate-800 px-2.5 py-1 text-[11px] text-slate-300 hover:bg-slate-700 hover:text-white transition ml-2 shrink-0"
              >
                {copiedEndpoint ? (
                  <>
                    <Check size={12} className="text-emerald-400" />
                    <span className="text-emerald-400">Copied!</span>
                  </>
                ) : (
                  <>
                    <Copy size={12} />
                    <span>Copy URL</span>
                  </>
                )}
              </button>
            </div>

            {/* KEY CAPABILITIES */}
            {activeItem.capabilities.length > 0 && (
              <div className="space-y-2 pt-2">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">
                  Key Capabilities &amp; Guarantees
                </h3>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {activeItem.capabilities.map((cap, i) => (
                    <div
                      key={i}
                      className="flex items-start gap-2 rounded-lg border border-slate-100 bg-slate-50/60 p-2.5 text-xs text-slate-700"
                    >
                      <CheckCircle2 size={15} className="text-teal-600 shrink-0 mt-0.5" />
                      <span>{cap}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </section>

          {/* 10-MINUTE SLIDING INACTIVITY TTL CALLOUT */}
          <section
            id="sliding-ttl-banner"
            className="rounded-2xl border border-teal-200 bg-gradient-to-r from-teal-50/80 via-white to-teal-50/50 p-5 shadow-xs space-y-3"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Timer size={18} className="text-teal-700" />
                <h3 className="text-sm font-bold text-slate-900">
                  Ephemeral Sliding Inactivity Window (10 Minutes)
                </h3>
              </div>
              <span className="rounded bg-teal-100 px-2 py-0.5 text-[10px] font-mono font-bold text-teal-800">
                DOC_TTL_MINUTES=10
              </span>
            </div>
            <p className="text-xs text-slate-600 leading-relaxed">
              When calling this service with a <code className="font-mono text-teal-800 font-bold">document_id</code>, DOC Tool automatically executes on the ephemeral in-memory document session and <strong>resets the 10-minute inactivity timer</strong> back to full 600 seconds. After 10 continuous minutes without any API requests, all temporary files, embeddings, and buffers are purged permanently.
            </p>
          </section>

          {/* AUTHENTICATION SPECIFICATION */}
          <section
            id="authentication"
            className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs space-y-4"
          >
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2">
                <ShieldCheck size={18} className="text-emerald-600" />
                <h3 className="text-sm font-bold text-slate-900">Authentication Header</h3>
              </div>
              <span className="rounded bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-800 border border-emerald-200">
                Atomic Credit Validation
              </span>
            </div>
            <p className="text-xs text-slate-600">
              Pass your company API key in the <code className="font-mono text-slate-800 font-semibold">X-API-Key</code> request header. DOC Tool checks your available credit balance and logs the audit event before invoking the model.
            </p>
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 font-mono text-xs flex items-center justify-between">
              <span className="text-slate-800">
                X-API-Key: <span className="text-teal-700 font-bold">{rawKey}</span>
              </span>
              <button
                onClick={handleCopyKey}
                className="text-xs text-teal-700 hover:underline flex items-center gap-1"
              >
                {copiedKey ? <Check size={12} className="text-emerald-600" /> : <Copy size={12} />}
                <span>{copiedKey ? "Copied" : "Copy"}</span>
              </button>
            </div>
          </section>

          {/* REQUEST PARAMETERS TABLE */}
          {activeItem.parameters.length > 0 && (
            <section
              id="parameters"
              className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs space-y-4"
            >
              <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                <div className="flex items-center gap-2">
                  <Terminal size={18} className="text-[#087f74]" />
                  <h3 className="text-sm font-bold text-slate-900">Request Parameters</h3>
                </div>
                <span className="text-[11px] font-mono text-slate-400">
                  Content-Type: {activeItem.id === "upload" ? "multipart/form-data" : "application/json"}
                </span>
              </div>

              <div className="overflow-x-auto rounded-xl border border-slate-200">
                <table className="w-full text-left text-xs">
                  <thead className="border-b border-slate-200 bg-slate-50 text-[11px] font-bold uppercase text-slate-500">
                    <tr>
                      <th className="px-4 py-2.5">Field</th>
                      <th className="px-4 py-2.5">Type &amp; In</th>
                      <th className="px-4 py-2.5">Required</th>
                      <th className="px-4 py-2.5">Description</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 bg-white">
                    {activeItem.parameters.map((p, i) => (
                      <tr key={i} className="hover:bg-slate-50/60">
                        <td className="px-4 py-3 font-mono font-bold text-slate-900">
                          {p.name}
                        </td>
                        <td className="px-4 py-3 font-mono text-[11px] text-slate-500">
                          {p.type} <span className="text-slate-400">({p.in})</span>
                        </td>
                        <td className="px-4 py-3">
                          {p.required ? (
                            <span className="rounded bg-rose-50 px-1.5 py-0.5 text-[10px] font-semibold text-rose-700 border border-rose-200">
                              Required
                            </span>
                          ) : (
                            <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-600">
                              Optional {p.default ? `(${p.default})` : ""}
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-slate-600 leading-snug">{p.description}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {/* INTERACTIVE MULTI-LANGUAGE CODE GENERATOR */}
          <section
            id="code-examples"
            className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs space-y-4"
          >
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-slate-100 pb-3">
              <div>
                <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                  <Code2 size={18} className="text-[#087f74]" />
                  <span>Code Examples &amp; SDK Integration</span>
                </h3>
                <p className="text-xs text-slate-500">
                  Ready to copy and execute directly in your backend pipeline, scripts, or terminal.
                </p>
              </div>

              {/* Language Switcher Tabs */}
              <div className="flex items-center gap-1 rounded-xl border border-slate-200 bg-slate-100 p-1 text-xs font-semibold">
                <button
                  onClick={() => setCodeLanguage("curl")}
                  className={cn(
                    "rounded-lg px-3 py-1.5 transition",
                    codeLanguage === "curl" ? "bg-white text-slate-900 shadow-2xs font-bold" : "text-slate-600 hover:text-slate-900"
                  )}
                >
                  cURL
                </button>
                <button
                  onClick={() => setCodeLanguage("python")}
                  className={cn(
                    "rounded-lg px-3 py-1.5 transition",
                    codeLanguage === "python" ? "bg-white text-slate-900 shadow-2xs font-bold" : "text-slate-600 hover:text-slate-900"
                  )}
                >
                  Python
                </button>
                <button
                  onClick={() => setCodeLanguage("typescript")}
                  className={cn(
                    "rounded-lg px-3 py-1.5 transition",
                    codeLanguage === "typescript" ? "bg-white text-slate-900 shadow-2xs font-bold" : "text-slate-600 hover:text-slate-900"
                  )}
                >
                  TypeScript
                </button>
                <button
                  onClick={() => setCodeLanguage("workflow")}
                  className={cn(
                    "rounded-lg px-3 py-1.5 transition",
                    codeLanguage === "workflow" ? "bg-white text-teal-800 shadow-2xs font-bold" : "text-slate-600 hover:text-slate-900"
                  )}
                >
                  Pipeline Script
                </button>
              </div>
            </div>

            {/* Interactive Model Selector & Cost Estimation Bar */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50/80 p-3 text-xs">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-slate-700">Model:</span>
                <select
                  value={docModel}
                  onChange={(e) => setDocModel(e.target.value)}
                  className="rounded-lg border border-slate-300 bg-white px-2.5 py-1 font-mono text-xs font-semibold text-slate-900 shadow-2xs focus:border-teal-600 focus:outline-none"
                >
                  {availableModels.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name} ({m.credit_cost} credits)
                    </option>
                  ))}
                </select>
                {docModel === selectedModel ? (
                  <span className="rounded bg-teal-100 px-2 py-0.5 text-[10px] font-bold text-teal-800">
                    Default
                  </span>
                ) : (
                  <button
                    type="button"
                    onClick={() => setSelectedModel(docModel)}
                    className="text-[11px] font-semibold text-teal-700 hover:underline"
                  >
                    Set as Default
                  </button>
                )}
              </div>
              <div className="flex items-center gap-2 text-slate-600 font-mono text-[11px]">
                <span>Cost:</span>
                <strong className="text-slate-900">{activeCost.totalCredits} credits</strong>
              </div>
            </div>

            {/* Dark Syntax Code Display */}
            <div className="relative rounded-2xl border border-slate-800 bg-[#080d19] p-4 text-xs font-mono text-emerald-300 shadow-xl overflow-hidden">
              <div className="flex items-center justify-between pb-3 mb-2 border-b border-slate-800 text-[10px] text-slate-400">
                <span className="flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                  <span>Production-ready payload</span>
                </span>
                <button
                  onClick={handleCopyCode}
                  className="flex items-center gap-1 rounded bg-slate-800 px-2.5 py-1 text-slate-300 hover:bg-slate-700 hover:text-white transition"
                >
                  {copiedCode ? (
                    <>
                      <Check size={12} className="text-emerald-400" />
                      <span className="text-emerald-400 font-bold">Copied!</span>
                    </>
                  ) : (
                    <>
                      <Copy size={12} />
                      <span>Copy Code</span>
                    </>
                  )}
                </button>
              </div>

              <pre className="max-h-[420px] overflow-auto leading-relaxed whitespace-pre font-mono text-[12px] text-emerald-300 pr-2">
                {activeCodeSnippet}
              </pre>
            </div>
          </section>

          {/* RESPONSE SPECIFICATION & LIVE SAMPLE JSON */}
          <section
            id="response-schema"
            className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs space-y-4"
          >
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2">
                <FileCode size={18} className="text-emerald-600" />
                <h3 className="text-sm font-bold text-slate-900">
                  Sample JSON Response Payload
                </h3>
              </div>
              <div className="flex items-center gap-2">
                <span className="rounded bg-emerald-100 px-2 py-0.5 text-[10px] font-bold font-mono text-emerald-900">
                  200 OK
                </span>
                <button
                  onClick={handleCopyJson}
                  className="flex items-center gap-1 rounded border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs text-slate-600 hover:bg-slate-100 transition"
                >
                  {copiedJson ? <Check size={12} className="text-emerald-600" /> : <Copy size={12} />}
                  <span>{copiedJson ? "Copied" : "Copy JSON"}</span>
                </button>
              </div>
            </div>

            <div className="rounded-xl border border-slate-800 bg-[#0c1222] p-4 font-mono text-[11px] leading-relaxed text-emerald-400 shadow-inner overflow-auto max-h-[360px]">
              <pre>{JSON.stringify(activeItem.sampleResponse, null, 2)}</pre>
            </div>
          </section>

          {/* HTTP ERROR CODES & LIFECYCLE */}
          <section
            id="status-codes"
            className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs space-y-4"
          >
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2">
                <AlertCircle size={18} className="text-slate-700" />
                <h3 className="text-sm font-bold text-slate-900">HTTP Status &amp; Error Lifecycle</h3>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 text-xs">
              <div className="rounded-xl border border-emerald-200 bg-emerald-50/50 p-3.5 space-y-1">
                <div className="flex items-center gap-2 font-mono font-bold text-emerald-900">
                  <span className="rounded bg-emerald-200 px-1.5 py-0.5 text-[10px]">200 OK</span>
                  <span>Success</span>
                </div>
                <p className="text-[11px] text-emerald-800 leading-relaxed">
                  Execution completed successfully. Sliding 10-minute countdown has been reset.
                </p>
              </div>

              <div className="rounded-xl border border-amber-200 bg-amber-50/50 p-3.5 space-y-1">
                <div className="flex items-center gap-2 font-mono font-bold text-amber-900">
                  <span className="rounded bg-amber-200 px-1.5 py-0.5 text-[10px]">410 GONE</span>
                  <span>Session Expired</span>
                </div>
                <p className="text-[11px] text-amber-800 leading-relaxed">
                  Document has been inactive for &gt;10 minutes and was wiped. Re-upload document.
                </p>
              </div>

              <div className="rounded-xl border border-rose-200 bg-rose-50/50 p-3.5 space-y-1">
                <div className="flex items-center gap-2 font-mono font-bold text-rose-900">
                  <span className="rounded bg-rose-200 px-1.5 py-0.5 text-[10px]">402 PAYMENT</span>
                  <span>Credits Exhausted</span>
                </div>
                <p className="text-[11px] text-rose-800 leading-relaxed">
                  Company credit balance is lower than service cost ({activeItem.credits} credits needed).
                </p>
              </div>

              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3.5 space-y-1">
                <div className="flex items-center gap-2 font-mono font-bold text-slate-800">
                  <span className="rounded bg-slate-200 px-1.5 py-0.5 text-[10px]">401 UNAUTHORIZED</span>
                  <span>Invalid Key</span>
                </div>
                <p className="text-[11px] text-slate-600 leading-relaxed">
                  Missing or invalid X-API-Key header. Provide your company key (docu_live_...).
                </p>
              </div>
            </div>
          </section>
        </main>
      </div>
    </div>
  );
}

