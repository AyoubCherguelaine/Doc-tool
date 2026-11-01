"use client";

import React, { useEffect, useState } from "react";
import {
  Sparkles,
  Coins,
  DollarSign,
  Layers,
  BarChart3,
  SlidersHorizontal,
  ChevronRight,
  TrendingUp,
  ShieldCheck,
  ShieldAlert,
} from "lucide-react";
import { useModelSettings } from "@/components/providers/model-provider";
import { useLanguage } from "@/components/providers/language-provider";
import { ModelSelectorButton, ModelSelectionModal, getModelIcon } from "@/components/ui/model-selector";
import { fetchCompanyAccount, type CompanyAccountInfo } from "@/lib/api";

export function ModelKpiBanner() {
  const { selectedModelInfo, openModelModal, availableModels, guardianMode, setGuardianMode } = useModelSettings();
  const { t } = useLanguage();
  const [account, setAccount] = useState<CompanyAccountInfo | null>(null);

  useEffect(() => {
    fetchCompanyAccount()
      .then(setAccount)
      .catch(() => {});
  }, []);

  if (!selectedModelInfo) return null;

  const Icon = getModelIcon(selectedModelInfo.id);
  const creditCost = selectedModelInfo.credit_cost;
  const costUsd = (creditCost * 0.002).toFixed(3);
  const remainingCredits = account?.remainingCredits ?? 1200;
  const remainingUsd = (remainingCredits * 0.002).toFixed(2);

  return (
    <div className="space-y-3">
      {/* Superset-style Analytics Metric Strip */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {/* Metric 1: Selected Model */}
        <div className="surface flex flex-col justify-between p-4 rounded-xl border border-slate-200/80 dark:border-slate-800 shadow-sm relative overflow-hidden group">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              {t("Processing Model", "نموذج المعالجة")}
            </span>
            <span className="p-1 rounded-md bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
              <Icon size={14} />
            </span>
          </div>
          <div>
            <div className="text-base font-bold text-slate-900 dark:text-white truncate font-mono">
              {selectedModelInfo.name}
            </div>
            <div className="flex items-center gap-1.5 mt-1">
              <span className="inline-block h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
              <span className="text-xs text-slate-500 dark:text-slate-400">
                {selectedModelInfo.speed_tier} • {selectedModelInfo.reasoning_tier}
              </span>
            </div>
          </div>
          <div className="mt-3 pt-2 border-t border-slate-100 dark:border-slate-800/80 flex items-center justify-between gap-1.5">
            <ModelSelectorButton size="sm" showDetails={false} />
            <button
              type="button"
              onClick={() => setGuardianMode(!guardianMode)}
              title={
                guardianMode
                  ? "Guardian active: +5 credits fee for full evidence citation and rule validation"
                  : "Direct mode active: raw model values returned directly, 5 credits fee waived"
              }
              className={`text-[10px] font-mono px-2 py-0.5 rounded-full border transition flex items-center gap-1 cursor-pointer font-medium ${
                guardianMode
                  ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300"
                  : "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/60 dark:text-amber-300"
              }`}
            >
              {guardianMode ? (
                <ShieldCheck size={11} className="text-emerald-600 dark:text-emerald-400" />
              ) : (
                <ShieldAlert size={11} className="text-amber-600 dark:text-amber-400" />
              )}
              <span>{guardianMode ? "Guardian ON (+5cr)" : "Direct Mode"}</span>
            </button>
          </div>
        </div>

        {/* Metric 2: Per-Run Cost */}
        <div className="surface flex flex-col justify-between p-4 rounded-xl border border-slate-200/80 dark:border-slate-800 shadow-sm">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              {t("Model Inference Rate", "معدل استهلاك النموذج")}
            </span>
            <span className="p-1 rounded-md bg-amber-500/10 text-amber-600 dark:text-amber-400">
              <Coins size={14} />
            </span>
          </div>
          <div>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-black text-slate-900 dark:text-white font-mono">
                {creditCost}
              </span>
              <span className="text-xs font-semibold text-slate-500">
                {t("credits / run", "رصيد / تشغيل")}
              </span>
            </div>
            <div className="text-xs text-emerald-600 dark:text-emerald-400 font-mono mt-0.5">
              ≈ ${costUsd} USD
            </div>
          </div>
          <div className="mt-3 pt-2 border-t border-slate-100 dark:border-slate-800/80 text-[11px] text-slate-500">
            {t("Calculated at $2.00 / 1,000 cr", "محسوبة بسعر 2.00$ لكل 1,000 رصيد")}
          </div>
        </div>

        {/* Metric 3: Credit Balance */}
        <div className="surface flex flex-col justify-between p-4 rounded-xl border border-slate-200/80 dark:border-slate-800 shadow-sm">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              {t("Available Balance", "الرصيد المتاح")}
            </span>
            <span className="p-1 rounded-md bg-blue-500/10 text-blue-600 dark:text-blue-400">
              <DollarSign size={14} />
            </span>
          </div>
          <div>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-black text-emerald-600 dark:text-emerald-400 font-mono">
                {remainingCredits.toLocaleString()}
              </span>
              <span className="text-xs font-semibold text-slate-500">
                {t("credits", "رصيد")}
              </span>
            </div>
            <div className="text-xs text-slate-500 dark:text-slate-400 font-mono mt-0.5">
              ≈ ${remainingUsd} USD value
            </div>
          </div>
          <div className="mt-3 pt-2 border-t border-slate-100 dark:border-slate-800/80 text-[11px] text-slate-500">
            {account?.planTier ? `${account.planTier} tier` : "Enterprise Trial"}
          </div>
        </div>

        {/* Metric 4: Superset Model Matrix Trigger */}
        <div
          onClick={openModelModal}
          className="surface flex flex-col justify-between p-4 rounded-xl border border-emerald-500/40 bg-emerald-50/10 hover:bg-emerald-50/30 dark:bg-emerald-950/10 dark:hover:bg-emerald-950/20 shadow-sm cursor-pointer transition group"
        >
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-emerald-700 dark:text-emerald-400">
              {t("Model Matrix", "مصفوفة النماذج")}
            </span>
            <span className="p-1 rounded-md bg-emerald-500/20 text-emerald-700 dark:text-emerald-300">
              <BarChart3 size={14} />
            </span>
          </div>
          <div>
            <div className="text-base font-bold text-slate-900 dark:text-white">
              {availableModels.length} {t("Models Configured", "نماذج مهيأة")}
            </div>
            <p className="text-xs text-slate-600 dark:text-slate-400 mt-1 line-clamp-2">
              {t(
                "Compare token pricing, speed, and intelligence across models.json.",
                "قارن أسعار التوكنات، السرعة ومستوى الذكاء في models.json.",
              )}
            </p>
          </div>
          <div className="mt-3 pt-2 border-t border-emerald-200/50 dark:border-emerald-800/50 flex items-center justify-between text-xs font-semibold text-emerald-700 dark:text-emerald-400 group-hover:translate-x-0.5 rtl:group-hover:-translate-x-0.5 transition-transform">
            <span>{t("Open Model Matrix", "فتح مصفوفة المقارنة")}</span>
            <ChevronRight size={14} className="rtl:rotate-180" />
          </div>
        </div>
      </div>

      {/* Global Model Modal instance */}
      <ModelSelectionModal />
    </div>
  );
}

