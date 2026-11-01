"use client";

import React from "react";
import { SettingsContent } from "@/components/ui/settings-modal";
import { useLanguage } from "@/components/providers/language-provider";
import { Settings as SettingsIcon } from "lucide-react";

export default function SettingsPage() {
  const { t } = useLanguage();

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      <div className="flex items-center justify-between pb-4 border-b border-slate-200 dark:border-slate-800">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
            <SettingsIcon size={24} />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight text-slate-900 dark:text-white">
              {t("Platform Settings", "إعدادات المنصة")}
            </h1>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {t(
                "Configure your personal workspace, AI processing model, guardian mode, and API keys.",
                "قم بتهيئة مساحة عملك المخصصة، نموذج المعالجة، وضع الغارديان، ومفاتيح API.",
              )}
            </p>
          </div>
        </div>
      </div>

      <div className="surface rounded-2xl border border-slate-200 dark:border-slate-800 overflow-hidden shadow-sm">
        <SettingsContent defaultTab="workspace" />
      </div>
    </div>
  );
}

