"use client";

import React, { useState, useEffect } from "react";
import {
  X,
  Settings as SettingsIcon,
  Sparkles,
  ShieldCheck,
  ShieldAlert,
  Building,
  Key,
  Coins,
  Copy,
  Check,
  RefreshCw,
  ExternalLink,
  Save,
  CheckCircle2,
  DollarSign,
  AlertCircle,
  Cpu,
  Layers,
  Sliders,
  History,
} from "lucide-react";
import Link from "next/link";
import { useModelSettings } from "@/components/providers/model-provider";
import { useSession } from "@/components/providers/session-provider";
import { useLanguage } from "@/components/providers/language-provider";
import { getModelIcon } from "@/components/ui/model-selector";
import { FALLBACK_MODELS } from "@/lib/models-fallback";
import {
  fetchWorkspace,
  updateWorkspace,
  regenerateCompanyApiKey,
  type WorkspaceInfo,
} from "@/lib/api";
import { Spinner } from "@/components/ui/spinner";

interface SettingsModalProps {
  open?: boolean;
  onClose?: () => void;
  defaultTab?: "model" | "guardian" | "workspace" | "keys" | "quota";
}

export function SettingsModal({ open, onClose, defaultTab = "workspace" }: SettingsModalProps) {
  const { isSettingsOpen, closeSettings } = useModelSettings();
  const isOpen = open !== undefined ? open : isSettingsOpen;
  const handleClose = onClose || closeSettings;

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4 md:p-6 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="relative w-full max-w-6xl h-[90vh] max-h-[92vh] flex flex-col rounded-2xl bg-white dark:bg-[#0f172a] shadow-2xl border border-slate-200 dark:border-slate-800 overflow-hidden animate-in zoom-in-95 duration-150">
        <SettingsContent onClose={handleClose} defaultTab={defaultTab} />
      </div>
    </div>
  );
}

export function SettingsContent({
  onClose,
  defaultTab = "workspace",
}: {
  onClose?: () => void;
  defaultTab?: "model" | "guardian" | "workspace" | "keys" | "quota";
}) {
  const { t } = useLanguage();
  const { user } = useSession();
  const {
    availableModels,
    selectedModel,
    selectedModelInfo,
    setSelectedModel,
    guardianMode,
    setGuardianMode,
    guardianCreditFee,
  } = useModelSettings();

  const displayModels = availableModels && availableModels.length > 0 ? availableModels : FALLBACK_MODELS;

  const [activeTab, setActiveTab] = useState<"model" | "guardian" | "workspace" | "keys" | "quota">(defaultTab);
  const [workspace, setWorkspace] = useState<WorkspaceInfo | null>(null);
  const [workspaceNameInput, setWorkspaceNameInput] = useState("");
  const [savingWorkspace, setSavingWorkspace] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [copiedKey, setCopiedKey] = useState(false);
  const [regenerating, setRegenerating] = useState(false);

  const cleanUserName =
    (user?.name || "").trim().startsWith("http") || (user?.name || "").includes("@") || !(user?.name || "").trim()
      ? "Ayoub"
      : user!.name!.trim();

  useEffect(() => {
    fetchWorkspace()
      .then((data) => {
        setWorkspace(data);
        const initialName = data.name && !data.name.startsWith("http")
          ? data.name
          : `${cleanUserName}'s Workspace`;
        setWorkspaceNameInput(initialName);
      })
      .catch(() => {
        setWorkspaceNameInput(`${cleanUserName}'s Workspace`);
      });
  }, [cleanUserName]);

  const handleSaveWorkspace = async () => {
    if (!workspaceNameInput.trim()) return;
    setSavingWorkspace(true);
    setSaveError("");
    setSaveSuccess(false);
    try {
      const res = await updateWorkspace(workspaceNameInput.trim());
      if (workspace) {
        setWorkspace({ ...workspace, name: res.name });
      }
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err: any) {
      setSaveError(err.message || "Failed to update workspace name");
    } finally {
      setSavingWorkspace(false);
    }
  };

  const handleCopyKey = () => {
    const key = workspace?.rawApiKey || workspace?.apiKey;
    if (!key) return;
    navigator.clipboard.writeText(key);
    setCopiedKey(true);
    setTimeout(() => setCopiedKey(false), 2000);
  };

  const handleRegenerateKey = async () => {
    if (!confirm("Are you sure you want to regenerate your Company API key? Any existing integrations will need to be updated.")) {
      return;
    }
    setRegenerating(true);
    try {
      const res = await regenerateCompanyApiKey();
      if (workspace) {
        setWorkspace({
          ...workspace,
          apiKey: res.apiKey,
          rawApiKey: res.apiKey,
          apiKeyPrefix: res.apiKeyPrefix,
          remainingCredits: res.remainingCredits,
        });
      }
    } catch {
      alert("Failed to regenerate API key");
    } finally {
      setRegenerating(false);
    }
  };

  const tabs = [
    { id: "workspace", label: t("Workspace & Account", "مساحة العمل والحساب"), icon: Building },
    { id: "model", label: t("AI Processing Model", "نموذج المعالجة الذكي"), icon: Cpu },
    { id: "guardian", label: t("Guardian Verification", "التحقق والضمان"), icon: ShieldCheck },
    { id: "keys", label: t("API Keys & Webhooks", "مفاتيح API والتكامل"), icon: Key },
    { id: "quota", label: t("Credits & Pricing", "الرصيد والتسعير"), icon: Coins },
  ] as const;

  return (
    <div className="flex flex-col h-full">
      {/* Modal Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-900/50">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-xl bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
            <SettingsIcon size={20} />
          </div>
          <div>
            <h2 className="text-base font-bold text-slate-900 dark:text-white">
              {t("System Settings", "إعدادات النظام")}
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400 font-mono">
              DOCTool Enterprise • {workspace?.name && !workspace.name.startsWith("http") ? workspace.name : `${cleanUserName}'s Workspace`}
            </p>
          </div>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition"
          >
            <X size={18} />
          </button>
        )}
      </div>

      {/* Main Body: Sidebar Tabs + Content */}
      <div className="flex flex-1 min-h-0 flex-col md:flex-row overflow-hidden">
        {/* Left Sub-nav Tabs */}
        <div className="w-full md:w-64 border-b md:border-b-0 md:border-e border-slate-200 dark:border-slate-800 bg-slate-50/40 dark:bg-[#0b1120] p-3 space-y-1 shrink-0 overflow-y-auto">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isCurrent = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`flex w-full items-center gap-2.5 px-3 py-2.5 rounded-xl text-xs font-semibold transition text-start ${
                  isCurrent
                    ? "bg-emerald-600 text-white shadow-sm shadow-emerald-600/20"
                    : "text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800/60 hover:text-slate-900 dark:hover:text-slate-200"
                }`}
              >
                <Icon size={16} />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>

        {/* Right Tab Content Viewport */}
        <div className="flex-1 p-6 overflow-y-auto space-y-6">
          {/* TAB 1: WORKSPACE */}
          {activeTab === "workspace" && (
            <div className="space-y-6 animate-in fade-in duration-150">
              <div>
                <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-1">
                  {t("User Dedicated Workspace", "مساحة العمل المخصصة للمستخدم")}
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
                  {t(
                    "Each user has their own isolated workspace with dedicated document index, API key, and audit logs.",
                    "لكل مستخدم مساحة عمل معزولة ومستقلة تشمل فهرس المستندات، مفتاح API الخاص، وسجلات الاستخدام.",
                  )}
                </p>
              </div>

              {/* Workspace Identity Card */}
              <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 p-4 space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1.5">
                    {t("Workspace Name", "اسم مساحة العمل")}
                  </label>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={workspaceNameInput}
                      onChange={(e) => setWorkspaceNameInput(e.target.value)}
                      placeholder="e.g. Ayoub's Workspace"
                      className="flex-1 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-xs font-medium text-slate-900 dark:text-white outline-none focus:border-emerald-500"
                    />
                    <button
                      onClick={handleSaveWorkspace}
                      disabled={savingWorkspace || !workspaceNameInput.trim()}
                      className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold shadow-xs disabled:opacity-50 transition"
                    >
                      {savingWorkspace ? <Spinner size={12} /> : <Save size={13} />}
                      <span>{t("Save", "حفظ")}</span>
                    </button>
                  </div>
                  {saveSuccess && (
                    <p className="text-emerald-600 dark:text-emerald-400 text-xs mt-1.5 flex items-center gap-1">
                      <CheckCircle2 size={13} /> {t("Workspace updated successfully!", "تم تحديث مساحة العمل بنجاح!")}
                    </p>
                  )}
                  {saveError && (
                    <p className="text-rose-600 text-xs mt-1.5 flex items-center gap-1">
                      <AlertCircle size={13} /> {saveError}
                    </p>
                  )}
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-3 border-t border-slate-200/60 dark:border-slate-800 font-mono text-xs">
                  <div>
                    <span className="block text-[10px] text-slate-400 uppercase font-sans">Owner Account</span>
                    <span className="font-semibold text-slate-800 dark:text-slate-200">
                      {cleanUserName} ({user?.email || "ayoub@example.com"})
                    </span>
                  </div>
                  <div>
                    <span className="block text-[10px] text-slate-400 uppercase font-sans">Workspace ID</span>
                    <span className="font-semibold text-slate-800 dark:text-slate-200 truncate block">
                      {workspace?.id || "ws_default"}
                    </span>
                  </div>
                  <div>
                    <span className="block text-[10px] text-slate-400 uppercase font-sans">Plan Tier</span>
                    <span className="inline-flex items-center gap-1 rounded bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300 px-2 py-0.5 text-[11px] font-bold">
                      {workspace?.planTier || "Free Trial (1,200 Credits)"}
                    </span>
                  </div>
                  <div>
                    <span className="block text-[10px] text-slate-400 uppercase font-sans">Workspace Status</span>
                    <span className="inline-flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400 font-bold">
                      <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                      Active Isolated Instance
                    </span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: AI PROCESSING MODEL */}
          {activeTab === "model" && (
            <div className="space-y-6 animate-in fade-in duration-150">
              <div>
                <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-1">
                  {t("Default AI Processing Model", "نموذج المعالجة الذكي الافتراضي")}
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
                  {t(
                    "Select the model used across all document extraction, chat inference, OCR, and API requests.",
                    "اختر النموذج المستخدم عبر جميع عمليات استخراج المستندات والمحادثة والاستدلال وطلبات API.",
                  )}
                </p>
              </div>

              {/* Direct Select List Dropdown */}
              <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-900/40 p-4 space-y-2">
                <label htmlFor="settings-model-select" className="block text-xs font-bold text-slate-800 dark:text-slate-200">
                  {t("Select Default AI Model", "اختر نموذج المعالجة الافتراضي")}
                </label>
                <select
                  id="settings-model-select"
                  value={selectedModel}
                  onChange={(e) => setSelectedModel(e.target.value)}
                  className="w-full rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3.5 py-2.5 text-xs font-mono font-bold text-slate-900 dark:text-white shadow-xs outline-none focus:border-emerald-500"
                >
                  {displayModels.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name} ({m.credit_cost} credits) {m.id === selectedModel ? "★ Current Default" : ""}
                    </option>
                  ))}
                </select>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">
                  {t(
                    "Choose your default model from the select list above or click any model card below to activate it.",
                    "اختر النموذج الافتراضي من القائمة المنسدلة أعلاه أو انقر على أي بطاقة أدناه لتفعيله مباشرة.",
                  )}
                </p>
              </div>

              {/* Models Grid */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {displayModels.map((m) => {
                  const Icon = getModelIcon(m.id);
                  const isSelected = selectedModel === m.id;
                  return (
                    <div
                      key={m.id}
                      onClick={() => setSelectedModel(m.id)}
                      className={`p-3.5 rounded-xl border transition cursor-pointer flex flex-col justify-between ${
                        isSelected
                          ? "border-emerald-500 bg-emerald-50/40 dark:bg-emerald-950/30 shadow-sm ring-1 ring-emerald-500"
                          : "border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 hover:border-slate-300 dark:hover:border-slate-700"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <span className={`p-1.5 rounded-lg ${isSelected ? "bg-emerald-500 text-white" : "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300"}`}>
                            <Icon size={15} />
                          </span>
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="font-mono text-xs font-bold text-slate-900 dark:text-white block">
                                {m.name}
                              </span>
                              {isSelected && (
                                <span className="rounded bg-emerald-100 dark:bg-emerald-900/60 text-emerald-800 dark:text-emerald-300 px-1.5 py-0.2 text-[10px] font-bold">
                                  Active
                                </span>
                              )}
                            </div>
                            <span className="text-[11px] text-slate-500 dark:text-slate-400">
                              {m.speed_tier} • {m.reasoning_tier}
                            </span>
                          </div>
                        </div>
                        {isSelected ? (
                          <span className="rounded-full bg-emerald-600 p-1 text-white">
                            <Check size={12} />
                          </span>
                        ) : (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              setSelectedModel(m.id);
                            }}
                            className="text-[10px] font-medium text-slate-400 hover:text-emerald-600 dark:hover:text-emerald-400"
                          >
                            Select
                          </button>
                        )}
                      </div>
                      <div className="mt-3 pt-2 border-t border-slate-100 dark:border-slate-800/80 flex items-center justify-between text-xs">
                        <span className="font-mono font-bold text-emerald-600 dark:text-emerald-400">
                          {m.credit_cost} credits / run
                        </span>
                        <span className="text-slate-400 text-[11px]">
                          {m.context_window ? `${Math.round(m.context_window / 1000)}k context` : "Standard context"}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* TAB 3: GUARDIAN VERIFICATION */}
          {activeTab === "guardian" && (
            <div className="space-y-6 animate-in fade-in duration-150">
              <div>
                <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-1">
                  {t("Guardian Verification vs. Direct Return Mode", "التحقق بواسطة الغارديان مقابل الإرجاع المباشر")}
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
                  {t(
                    "Choose whether to perform strict evidence citation validation and schema guardrails (takes credit), or return raw model values directly (guardian fee waived).",
                    "اختر ما إذا كنت ترغب في تشغيل التحقق الصارم من المطابقة والاقتباسات مع المخطط (يستهلك رصيداً)، أو استرجاع مخرجات النموذج مباشرة بدون اقتطاع رسوم الغارديان.",
                  )}
                </p>
              </div>

              {/* Guardian Big Toggle Card */}
              <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 space-y-4">
                <div className="flex items-center justify-between gap-4">
                  <div className="flex items-center gap-3">
                    <div
                      className={`p-2.5 rounded-xl ${
                        guardianMode
                          ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                          : "bg-amber-500/10 text-amber-600 dark:text-amber-400"
                      }`}
                    >
                      {guardianMode ? <ShieldCheck size={24} /> : <ShieldAlert size={24} />}
                    </div>
                    <div>
                      <h4 className="text-sm font-bold text-slate-900 dark:text-white">
                        {guardianMode ? t("Guardian Mode: Enabled", "وضع الغارديان: مفعّل") : t("Direct Return Mode: Enabled", "وضع الإرجاع المباشر: مفعّل")}
                      </h4>
                      <p className="text-xs text-slate-500 dark:text-slate-400">
                        {guardianMode
                          ? t("Full citation check against source pages & schema guardrails (+5 credits fee)", "تحقق صارم مع ربط الاقتباسات بصفحات المستند وفحص المخطط (رسوم 5 رصيد)")
                          : t("Bypasses evidence matching; raw model values returned directly (5 credits fee waived)", "تجاوز فحص الاقتباسات؛ استرجاع قيم النموذج مباشرة (إعفاء 5 رصيد)")}
                      </p>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setGuardianMode(!guardianMode)}
                    className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                      guardianMode ? "bg-emerald-600" : "bg-slate-300 dark:bg-slate-600"
                    }`}
                  >
                    <span
                      className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                        guardianMode ? "translate-x-5" : "translate-x-0"
                      }`}
                    />
                  </button>
                </div>

                {/* Comparison Details */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-3 border-t border-slate-200/60 dark:border-slate-800 text-xs">
                  <div className={`p-3 rounded-lg border ${guardianMode ? "border-emerald-300 bg-emerald-50/40 dark:border-emerald-800 dark:bg-emerald-950/20" : "border-slate-200 dark:border-slate-800"}`}>
                    <div className="font-bold text-slate-800 dark:text-slate-200 flex items-center gap-1.5 mb-1">
                      <ShieldCheck size={14} className="text-emerald-500" />
                      <span>Guardian Mode (+5 cr)</span>
                    </div>
                    <ul className="space-y-1 text-slate-600 dark:text-slate-400 text-[11px] list-disc list-inside">
                      <li>Evidence source page coordinates & citations</li>
                      <li>Nullifies fields that cannot be grounded in source text</li>
                      <li>Calculates arithmetic checks and tax validation</li>
                    </ul>
                  </div>

                  <div className={`p-3 rounded-lg border ${!guardianMode ? "border-amber-300 bg-amber-50/40 dark:border-amber-800 dark:bg-amber-950/20" : "border-slate-200 dark:border-slate-800"}`}>
                    <div className="font-bold text-slate-800 dark:text-slate-200 flex items-center gap-1.5 mb-1">
                      <ShieldAlert size={14} className="text-amber-500" />
                      <span>Direct Return Mode (Fee Waived)</span>
                    </div>
                    <ul className="space-y-1 text-slate-600 dark:text-slate-400 text-[11px] list-disc list-inside">
                      <li>Returns raw LLM response immediately</li>
                      <li>No citation nullification; retains all values</li>
                      <li>5 credits discount per run (cheaper execution)</li>
                    </ul>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 4: API KEYS */}
          {activeTab === "keys" && (
            <div className="space-y-6 animate-in fade-in duration-150">
              <div>
                <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-1">
                  {t("Company API Keys & Webhooks", "مفاتيح API والتكامل")}
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
                  {t(
                    "Authenticate REST API requests and external workers using your workspace API key.",
                    "استخدم مفتاح مساحة العمل للمصادقة على طلبات REST API وتكامل الأنظمة الخارجية.",
                  )}
                </p>
              </div>

              {/* Key Box */}
              <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 p-4 space-y-3">
                <div className="flex items-center justify-between text-xs font-semibold text-slate-700 dark:text-slate-300">
                  <span>{t("Active Secret API Key", "مفتاح API السري النشط")}</span>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={handleCopyKey}
                      className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400 hover:underline text-xs"
                    >
                      {copiedKey ? <Check size={12} /> : <Copy size={12} />}
                      <span>{copiedKey ? t("Copied", "تم النسخ") : t("Copy Key", "نسخ المفتاح")}</span>
                    </button>
                    <button
                      onClick={handleRegenerateKey}
                      disabled={regenerating}
                      className="inline-flex items-center gap-1 text-rose-600 hover:underline text-xs disabled:opacity-50"
                    >
                      <RefreshCw size={12} className={regenerating ? "animate-spin" : ""} />
                      <span>{t("Roll Key", "تجديد المفتاح")}</span>
                    </button>
                  </div>
                </div>
                <div className="p-2.5 rounded-lg bg-slate-900 font-mono text-xs text-emerald-400 border border-slate-800 break-all select-all">
                  {workspace?.rawApiKey || `${workspace?.apiKeyPrefix || "docu_live_"}••••••••••••••••••••••••••••••••`}
                </div>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">
                  Pass this in the header: <code className="bg-slate-200 dark:bg-slate-800 px-1 py-0.5 rounded font-mono">X-API-Key: docu_live_...</code>
                </p>
              </div>
            </div>
          )}

          {/* TAB 5: CREDITS & PRICING */}
          {activeTab === "quota" && (
            <div className="space-y-6 animate-in fade-in duration-150">
              <div>
                <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-1">
                  {t("Credit Balance & Usage Quota", "رصيد الاستهلاك والمتبقي")}
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
                  {t("Monitor your workspace credit allocation, consumption, and audit history.", "تابع رصيد مساحة عملك، ونسبة الاستهلاك، وسجل العمليات.")}
                </p>
              </div>

              {/* Credit Metric Cards */}
              <div className="grid grid-cols-3 gap-3">
                <div className="p-3.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 text-center">
                  <span className="block text-[10px] text-slate-400 uppercase font-sans font-semibold">Total Quota</span>
                  <span className="font-mono text-lg font-black text-slate-800 dark:text-slate-200">
                    {(workspace?.totalCredits ?? 1200).toLocaleString()} cr
                  </span>
                </div>
                <div className="p-3.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 text-center">
                  <span className="block text-[10px] text-slate-400 uppercase font-sans font-semibold">Used Credits</span>
                  <span className="font-mono text-lg font-black text-amber-600 dark:text-amber-400">
                    {(workspace?.usedCredits ?? 0).toLocaleString()} cr
                  </span>
                </div>
                <div className="p-3.5 rounded-xl border border-emerald-300 dark:border-emerald-800 bg-emerald-50/40 dark:bg-emerald-950/30 text-center">
                  <span className="block text-[10px] text-emerald-700 dark:text-emerald-400 uppercase font-sans font-semibold">Remaining</span>
                  <span className="font-mono text-lg font-black text-emerald-600 dark:text-emerald-400">
                    {(workspace?.remainingCredits ?? 1200).toLocaleString()} cr
                  </span>
                </div>
              </div>

              <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 flex items-center justify-between">
                <div>
                  <h4 className="text-xs font-bold text-slate-900 dark:text-white">Audit Logs</h4>
                  <p className="text-[11px] text-slate-500">View detailed history of all credit deductions and services run.</p>
                </div>
                <Link
                  href="/usage"
                  onClick={onClose}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-xs font-semibold text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 transition"
                >
                  <History size={13} />
                  <span>{t("Open Credit Logs", "عرض سجل الرصيد")}</span>
                </Link>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

