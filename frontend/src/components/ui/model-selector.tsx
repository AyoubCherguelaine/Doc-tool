"use client";

import React, { useState, useMemo } from "react";
import {
  Sparkles,
  Zap,
  Brain,
  Cpu,
  Check,
  ChevronDown,
  Coins,
  Search,
  SlidersHorizontal,
  X,
  Layers,
  ArrowRight,
  TrendingDown,
  Info,
  DollarSign,
  BarChart3,
  Table,
} from "lucide-react";
import { useModelSettings } from "@/components/providers/model-provider";
import { useLanguage } from "@/components/providers/language-provider";
import type { AvailableModelItem } from "@/lib/api";

export function getModelIcon(modelId: string) {
  if (modelId.startsWith("o1") || modelId.startsWith("o3")) {
    return Brain;
  }
  if (modelId.includes("nano") || modelId.includes("luna")) {
    return Zap;
  }
  if (modelId.includes("turbo") || modelId === "gpt-4o") {
    return Sparkles;
  }
  return Cpu;
}

export function getModelCategory(model: AvailableModelItem): "reasoning" | "fast" | "flagship" {
  const id = model.id;
  if (id.startsWith("o1") || id.startsWith("o3")) return "reasoning";
  if (id.includes("nano") || id.includes("luna") || id === "gpt-4o-mini") return "fast";
  return "flagship";
}

interface ModelSelectorButtonProps {
  size?: "sm" | "md" | "lg";
  className?: string;
  showDetails?: boolean;
}

export function ModelSelectorButton({
  size = "md",
  className = "",
  showDetails = true,
}: ModelSelectorButtonProps) {
  const { selectedModelInfo, openModelModal } = useModelSettings();
  const { t } = useLanguage();

  if (!selectedModelInfo) return null;

  const Icon = getModelIcon(selectedModelInfo.id);
  const cost = selectedModelInfo.credit_cost;
  const costUsd = (cost * 0.002).toFixed(3);

  const sizeClasses = {
    sm: "px-2.5 py-1 text-xs gap-1.5",
    md: "px-3 py-1.5 text-xs gap-2",
    lg: "px-4 py-2 text-sm gap-2.5",
  }[size];

  return (
    <button
      type="button"
      onClick={openModelModal}
      className={`group inline-flex items-center rounded-xl border border-slate-200 bg-white/90 backdrop-blur-md shadow-sm transition hover:border-emerald-500/80 hover:bg-emerald-50/30 dark:border-slate-800 dark:bg-slate-900/90 dark:hover:border-emerald-500/60 dark:hover:bg-emerald-950/20 ${sizeClasses} ${className}`}
      title={t("Choose AI processing model", "اختر نموذج المعالجة الذكي")}
    >
      <span className="flex items-center justify-center rounded-lg bg-emerald-500/10 p-1 text-emerald-600 dark:bg-emerald-400/10 dark:text-emerald-400">
        <Icon size={size === "sm" ? 13 : 15} />
      </span>
      <div className="flex flex-col text-start">
        <span className="font-semibold text-slate-800 dark:text-slate-200 font-mono text-[11px] leading-tight">
          {selectedModelInfo.name}
        </span>
        {showDetails && (
          <span className="text-[10px] text-slate-500 dark:text-slate-400 font-mono">
            {cost} credits
          </span>
        )}
      </div>
      <ChevronDown
        size={13}
        className="text-slate-400 transition group-hover:text-emerald-600 dark:group-hover:text-emerald-400 ms-0.5"
      />
    </button>
  );
}

export function ModelSelectionModal() {
  const {
    availableModels,
    selectedModel,
    setSelectedModel,
    isModelModalOpen,
    closeModelModal,
  } = useModelSettings();
  const { t, language } = useLanguage();

  const [searchQuery, setSearchQuery] = useState("");
  const [activeTab, setActiveTab] = useState<"all" | "fast" | "flagship" | "reasoning">("all");
  const [viewMode, setViewMode] = useState<"cards" | "matrix">("cards");

  const filteredModels = useMemo(() => {
    return availableModels.filter((model) => {
      const matchesSearch =
        model.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        model.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (model.description && model.description.toLowerCase().includes(searchQuery.toLowerCase()));

      if (!matchesSearch) return false;
      if (activeTab === "all") return true;
      return getModelCategory(model) === activeTab;
    });
  }, [availableModels, searchQuery, activeTab]);

  if (!isModelModalOpen) return null;

  const currentModel = availableModels.find((m) => m.id === selectedModel) || availableModels[0];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-5 bg-slate-950/70 backdrop-blur-md animate-enter">
      <div className="relative flex flex-col w-full max-w-4xl max-h-[90vh] rounded-2xl border border-slate-200 bg-white shadow-2xl dark:border-slate-800 dark:bg-[#0c121c] overflow-hidden">
        {/* Header - OpenAI Minimalist & Clean */}
        <div className="flex items-center justify-between border-b border-slate-100 p-5 dark:border-slate-800/80">
          <div>
            <div className="flex items-center gap-2">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-600 dark:bg-emerald-400/10 dark:text-emerald-400">
                <SlidersHorizontal size={16} />
              </span>
              <h2 className="text-lg font-bold text-slate-900 dark:text-white">
                {t("AI Service Model Setting", "إعداد نموذج معالجة الذكاء الاصطناعي")}
              </h2>
              <span className="rounded-full bg-emerald-100 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-800 dark:bg-emerald-950/70 dark:text-emerald-300">
                Verified Models
              </span>
            </div>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              {t(
                "Select which AI model processes your documents, chats, and services.",
                "اختر النموذج الذي يعالج مستنداتك ومحادثاتك وخدماتك.",
              )}
            </p>
          </div>
          <button
            type="button"
            onClick={closeModelModal}
            className="rounded-xl p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-200 transition"
          >
            <X size={18} />
          </button>
        </div>

        {/* Superset-style Analytical KPI Bar */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-slate-50/80 p-4 border-b border-slate-100 dark:bg-slate-900/40 dark:border-slate-800/80 text-xs">
          <div className="rounded-xl bg-white p-3 border border-slate-200/80 dark:bg-slate-900/90 dark:border-slate-800 shadow-sm">
            <div className="flex items-center justify-between text-slate-400 mb-1">
              <span className="text-[10px] font-medium uppercase tracking-wider">
                {t("Active Model", "النموذج النشط")}
              </span>
              <Sparkles size={13} className="text-emerald-500" />
            </div>
            <div className="font-bold text-slate-900 dark:text-white truncate font-mono text-sm">
              {currentModel?.id}
            </div>
            <div className="text-[10px] text-emerald-600 dark:text-emerald-400 font-medium mt-0.5">
              {currentModel?.speed_tier} • {currentModel?.reasoning_tier}
            </div>
          </div>

          <div className="rounded-xl bg-white p-3 border border-slate-200/80 dark:bg-slate-900/90 dark:border-slate-800 shadow-sm">
            <div className="flex items-center justify-between text-slate-400 mb-1">
              <span className="text-[10px] font-medium uppercase tracking-wider">
                {t("Model Inference Fee", "تكلفة الاستدلال")}
              </span>
              <Coins size={13} className="text-amber-500" />
            </div>
            <div className="font-bold text-slate-900 dark:text-white text-sm">
              {currentModel?.credit_cost} {t("Credits", "رصيد")}
            </div>
            <div className="text-[10px] text-slate-500 dark:text-slate-400 mt-0.5">
              {t("Per service invocation", "لكل عملية معالجة")}
            </div>
          </div>

          <div className="rounded-xl bg-white p-3 border border-slate-200/80 dark:bg-slate-900/90 dark:border-slate-800 shadow-sm">
            <div className="flex items-center justify-between text-slate-400 mb-1">
              <span className="text-[10px] font-medium uppercase tracking-wider">
                {t("Execution Mode", "وضع المعالجة")}
              </span>
              <Cpu size={13} className="text-blue-500" />
            </div>
            <div className="font-bold text-slate-900 dark:text-white text-sm">
              {t("Direct AI Service", "خدمة الذكاء المباشرة")}
            </div>
            <div className="text-[10px] text-slate-500 dark:text-slate-400 mt-0.5">
              {t("Instant deduction", "خصم فوري للرصيد")}
            </div>
          </div>

          <div className="rounded-xl bg-white p-3 border border-slate-200/80 dark:bg-slate-900/90 dark:border-slate-800 shadow-sm">
            <div className="flex items-center justify-between text-slate-400 mb-1">
              <span className="text-[10px] font-medium uppercase tracking-wider">
                {t("Catalog Scope", "نطاق النماذج")}
              </span>
              <Layers size={13} className="text-indigo-500" />
            </div>
            <div className="font-bold text-slate-900 dark:text-white text-sm">
              {availableModels.length} {t("Allowed Models", "نماذج معتمدة")}
            </div>
            <div className="text-[10px] text-emerald-600 dark:text-emerald-400 mt-0.5">
              Enterprise Catalog
            </div>
          </div>
        </div>

        {/* Toolbar: Search, Filters, and View Toggle */}
        <div className="flex flex-wrap items-center justify-between gap-3 p-4 border-b border-slate-100 dark:border-slate-800/80">
          <div className="flex items-center gap-2 flex-1 min-w-[200px] max-w-sm">
            <div className="relative w-full">
              <Search
                size={14}
                className="absolute start-3 top-3 text-slate-400 pointer-events-none"
              />
              <input
                type="search"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder={t("Filter by name, ID or tier...", "ابحث بالاسم أو المعرف...")}
                className="w-full rounded-xl border border-slate-200 bg-white py-1.5 ps-9 pe-3 text-xs outline-none focus:border-emerald-500 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-100"
              />
            </div>
          </div>

          <div className="flex items-center gap-2">
            <div className="flex rounded-xl bg-slate-100 p-0.5 dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
              <button
                type="button"
                onClick={() => setActiveTab("all")}
                className={`rounded-lg px-2.5 py-1 text-xs font-medium transition ${
                  activeTab === "all"
                    ? "bg-white text-slate-900 shadow-sm dark:bg-slate-800 dark:text-white"
                    : "text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
                }`}
              >
                {t("All", "الكل")} ({availableModels.length})
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("fast")}
                className={`rounded-lg px-2.5 py-1 text-xs font-medium transition ${
                  activeTab === "fast"
                    ? "bg-white text-slate-900 shadow-sm dark:bg-slate-800 dark:text-white"
                    : "text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
                }`}
              >
                ⚡ {t("Fast & Compact", "سريعة واقتصادية")}
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("flagship")}
                className={`rounded-lg px-2.5 py-1 text-xs font-medium transition ${
                  activeTab === "flagship"
                    ? "bg-white text-slate-900 shadow-sm dark:bg-slate-800 dark:text-white"
                    : "text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
                }`}
              >
                💎 {t("Flagship", "الرائدة")}
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("reasoning")}
                className={`rounded-lg px-2.5 py-1 text-xs font-medium transition ${
                  activeTab === "reasoning"
                    ? "bg-white text-slate-900 shadow-sm dark:bg-slate-800 dark:text-white"
                    : "text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
                }`}
              >
                🧠 {t("Reasoning", "الاستدلال المتقدم")}
              </button>
            </div>

            <div className="flex rounded-xl bg-slate-100 p-0.5 dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
              <button
                type="button"
                onClick={() => setViewMode("cards")}
                className={`p-1.5 rounded-lg text-xs transition ${
                  viewMode === "cards"
                    ? "bg-white text-slate-900 shadow-sm dark:bg-slate-800 dark:text-white"
                    : "text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
                }`}
                title={t("Cards View", "عرض البطاقات")}
              >
                <Layers size={14} />
              </button>
              <button
                type="button"
                onClick={() => setViewMode("matrix")}
                className={`p-1.5 rounded-lg text-xs transition ${
                  viewMode === "matrix"
                    ? "bg-white text-slate-900 shadow-sm dark:bg-slate-800 dark:text-white"
                    : "text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
                }`}
                title={t("Superset Matrix Table View", "عرض جدول المقارنة التحليلي")}
              >
                <Table size={14} />
              </button>
            </div>
          </div>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {viewMode === "cards" ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {filteredModels.map((model) => {
                const Icon = getModelIcon(model.id);
                const isSelected = selectedModel === model.id;
                const costUsd = (model.credit_cost * 0.002).toFixed(3);

                return (
                  <div
                    key={model.id}
                    onClick={() => setSelectedModel(model.id)}
                    className={`relative flex flex-col justify-between p-4 rounded-xl border cursor-pointer transition ${
                      isSelected
                        ? "border-emerald-500 bg-emerald-50/20 shadow-md dark:border-emerald-500/80 dark:bg-emerald-950/20"
                        : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50/50 dark:border-slate-800 dark:bg-slate-900/60 dark:hover:border-slate-700"
                    }`}
                  >
                    <div>
                      <div className="flex items-start justify-between gap-2 mb-2">
                        <div className="flex items-center gap-2">
                          <span
                            className={`flex h-8 w-8 items-center justify-center rounded-lg ${
                              isSelected
                                ? "bg-emerald-500 text-white"
                                : "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300"
                            }`}
                          >
                            <Icon size={16} />
                          </span>
                          <div>
                            <div className="flex items-center gap-1.5">
                              <h3 className="font-bold text-sm text-slate-900 dark:text-white font-mono">
                                {model.name}
                              </h3>
                              {model.is_default && (
                                <span className="rounded bg-slate-100 px-1.5 py-0.2 text-[9px] font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                                  Default
                                </span>
                              )}
                            </div>
                            <span className="text-[11px] text-slate-400 font-mono">
                              ID: {model.id}
                            </span>
                          </div>
                        </div>

                        <div className="flex flex-col items-end">
                          <span
                            className={`rounded-lg px-2 py-0.5 text-xs font-bold font-mono ${
                              isSelected
                                ? "bg-emerald-600 text-white"
                                : "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/80 dark:text-emerald-300 border border-emerald-200/50 dark:border-emerald-800/50"
                            }`}
                          >
                            {model.credit_cost} cr
                          </span>
                        </div>
                      </div>

                      <p className="text-xs text-slate-600 dark:text-slate-400 line-clamp-2 mb-3">
                        {model.description}
                      </p>
                    </div>

                    <div className="pt-2 border-t border-slate-100 dark:border-slate-800/80 flex items-center justify-between text-[11px]">
                      <div className="flex items-center gap-2 text-slate-500 dark:text-slate-400">
                        <span className="rounded bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 text-[10px]">
                          In: ${model.pricing?.input_per_million}/M
                        </span>
                        <span className="rounded bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 text-[10px]">
                          Out: ${model.pricing?.output_per_million}/M
                        </span>
                      </div>

                      {isSelected ? (
                        <span className="inline-flex items-center gap-1 font-semibold text-emerald-600 dark:text-emerald-400 text-xs">
                          <Check size={14} />
                          {t("Active Model", "النموذج المختار")}
                        </span>
                      ) : (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedModel(model.id);
                          }}
                          className="font-medium text-slate-500 hover:text-emerald-600 dark:text-slate-400 dark:hover:text-emerald-400 transition"
                        >
                          {t("Select", "اختيار")}
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            /* Superset-style Analytical Matrix Table */
            <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
              <table className="w-full text-start text-xs border-collapse">
                <thead className="bg-slate-50 dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-400 font-semibold uppercase text-[10px] tracking-wider">
                  <tr>
                    <th className="py-2.5 px-3 text-start">{t("Model Name & ID", "اسم النموذج")}</th>
                    <th className="py-2.5 px-3 text-start">{t("Category / Tier", "الفئة والسرعة")}</th>
                    <th className="py-2.5 px-3 text-end">{t("Credit Cost", "تكلفة الرصيد")}</th>
                    <th className="py-2.5 px-3 text-end">{t("USD / Run", "السعر بالدولار")}</th>
                    <th className="py-2.5 px-3 text-end">{t("Input / 1M Tokens", "سعر الإدخال/مليون")}</th>
                    <th className="py-2.5 px-3 text-end">{t("Output / 1M Tokens", "سعر الإخراج/مليون")}</th>
                    <th className="py-2.5 px-3 text-center">{t("Action", "الإجراء")}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800 font-mono text-[11px]">
                  {filteredModels.map((model) => {
                    const isSelected = selectedModel === model.id;
                    const costUsd = (model.credit_cost * 0.002).toFixed(3);

                    return (
                      <tr
                        key={model.id}
                        onClick={() => setSelectedModel(model.id)}
                        className={`cursor-pointer transition ${
                          isSelected
                            ? "bg-emerald-50/40 dark:bg-emerald-950/20 font-bold"
                            : "hover:bg-slate-50/80 dark:hover:bg-slate-900/50"
                        }`}
                      >
                        <td className="py-2.5 px-3">
                          <div className="font-semibold text-slate-900 dark:text-white">
                            {model.name}
                          </div>
                          <div className="text-[10px] text-slate-400 font-normal">
                            {model.id}
                          </div>
                        </td>
                        <td className="py-2.5 px-3">
                          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] text-slate-700 dark:bg-slate-800 dark:text-slate-300 font-sans">
                            {model.speed_tier} • {model.reasoning_tier}
                          </span>
                        </td>
                        <td className="py-2.5 px-3 text-end font-bold text-emerald-600 dark:text-emerald-400">
                          {model.credit_cost} cr
                        </td>
                        <td className="py-2.5 px-3 text-end text-slate-700 dark:text-slate-300">
                          ${costUsd}
                        </td>
                        <td className="py-2.5 px-3 text-end text-slate-500">
                          ${model.pricing?.input_per_million}/M
                        </td>
                        <td className="py-2.5 px-3 text-end text-slate-500">
                          ${model.pricing?.output_per_million}/M
                        </td>
                        <td className="py-2.5 px-3 text-center">
                          {isSelected ? (
                            <span className="inline-flex items-center gap-1 rounded-lg bg-emerald-600 px-2 py-0.5 text-[10px] font-semibold text-white">
                              <Check size={11} /> {t("Active", "نشط")}
                            </span>
                          ) : (
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                setSelectedModel(model.id);
                              }}
                              className="rounded-lg border border-slate-300 px-2 py-0.5 text-[10px] font-medium text-slate-700 hover:border-emerald-500 hover:text-emerald-600 dark:border-slate-700 dark:text-slate-300 dark:hover:border-emerald-400"
                            >
                              {t("Use", "اختيار")}
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-slate-100 p-4 bg-slate-50/50 dark:bg-slate-900/40 dark:border-slate-800">
          <div className="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
            <Info size={14} className="text-slate-400" />
            <span>
              {t(
                "Selected model applies across Document AI workflows, Playground, and API calls.",
                "ينطبق النموذج المختار على كافة خدمات المستندات ومساحة التجربة وواجهات API.",
              )}
            </span>
          </div>
          <button
            type="button"
            onClick={closeModelModal}
            className="rounded-xl bg-emerald-700 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-800 dark:bg-emerald-500 dark:text-slate-950 dark:hover:bg-emerald-400 transition"
          >
            {t("Done", "تم")}
          </button>
        </div>
      </div>
    </div>
  );
}

