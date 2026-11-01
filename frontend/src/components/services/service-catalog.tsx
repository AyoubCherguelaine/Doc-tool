"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight, Search, X, Sparkles } from "lucide-react";
import { useLanguage } from "@/components/providers/language-provider";
import { useModelSettings } from "@/components/providers/model-provider";
import { serviceCatalog, serviceCategories } from "@/lib/service-catalog";

export function ServiceCatalog({ preview = false }: { preview?: boolean }) {
  const { language, t } = useLanguage();
  const { calculateCost, selectedModelInfo } = useModelSettings();
  const [category, setCategory] = useState("all");
  const [query, setQuery] = useState("");
  const normalize = (value: string) =>
    value
      .toLocaleLowerCase()
      .normalize("NFKD")
      .replace(/[\u064B-\u065F\u0670\u0640]/g, "")
      .replace(/[أإآ]/g, "ا")
      .trim();
  const filtered = serviceCatalog.filter(
    (service) =>
      (category === "all" || service.category === category) &&
      normalize(
        [
          service.title.en,
          service.title.ar,
          service.description.en,
          service.description.ar,
          service.output.en,
          service.output.ar,
        ].join(" "),
      ).includes(normalize(query)),
  );
  const shown = preview
    ? serviceCatalog.filter((service) =>
        [
          "invoice",
          "contract",
          "extraction",
          "translation",
          "receipt",
          "summary",
        ].includes(service.id),
      )
    : filtered;
  return (
    <div className="space-y-5">
      {!preview && (
        <>
          <div className="relative max-w-xl">
            <label htmlFor="service-search" className="sr-only">
              {t("Search services", "ابحث عن خدمة")}
            </label>
            <Search
              size={18}
              className="pointer-events-none absolute start-3 top-3.5 text-slate-400"
            />
            <input
              id="service-search"
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={t(
                "Search by task, e.g. invoice or translation",
                "ابحث حسب المهمة، مثل الفواتير أو الترجمة",
              )}
              className="w-full rounded-xl border border-slate-300 bg-white py-3 ps-10 pe-4 text-sm dark:border-slate-700 dark:bg-slate-900"
            />
          </div>
          <div
            role="group"
            aria-label={t("Filter services", "تصفية الخدمات")}
            className="flex flex-wrap gap-2"
          >
            {serviceCategories.map((item) => (
              <button
                key={item.id}
                type="button"
                aria-pressed={category === item.id}
                onClick={() => setCategory(item.id)}
                className={`rounded-lg border px-3 py-2 text-sm transition ${category === item.id ? "border-emerald-700 bg-emerald-700 text-white dark:border-emerald-500 dark:bg-emerald-500 dark:text-slate-950" : "border-slate-200 bg-white text-slate-600 hover:border-emerald-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"}`}
              >
                {item.label[language]}
              </button>
            ))}
          </div>
          <p
            role="status"
            className="text-sm text-slate-500 dark:text-slate-400"
          >
            {t(
              `${filtered.length} services found`,
              `عدد الخدمات: ${filtered.length}`,
            )}
          </p>
        </>
      )}
      {shown.length === 0 ? (
        <div className="surface p-10 text-center dark:bg-slate-900">
          <h3 className="font-semibold">
            {t("No matching services", "لا توجد خدمات مطابقة")}
          </h3>
          <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
            {t(
              "Try another word or choose a different category.",
              "جرّب كلمة أخرى أو اختر فئة مختلفة.",
            )}
          </p>
          <button
            type="button"
            onClick={() => {
              setQuery("");
              setCategory("all");
            }}
            className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-emerald-700 dark:text-emerald-400"
          >
            <X size={16} />
            {t("Clear filters", "مسح عوامل التصفية")}
          </button>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {shown.map((service) => (
            <article
              key={service.id}
              className="surface flex flex-col p-5 transition hover:border-emerald-500/60"
            >
              <div className="mb-4 flex items-center justify-between gap-3">
                <span className="rounded-xl bg-emerald-50 p-2.5 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400">
                  <service.icon size={22} />
                </span>
                {!preview && (() => {
                  const pricing = calculateCost(service.credits);
                  return (
                    <div className="flex flex-col items-end">
                      <span className="text-xs font-bold text-slate-800 dark:text-slate-200 font-mono">
                        {pricing.totalCredits}{" "}
                        {t(
                          service.id === "chat"
                            ? "cr / question"
                            : "cr / run",
                          service.id === "chat" ? "رصيد / سؤال" : "رصيد / تشغيل",
                        )}
                      </span>
                      <span className="text-[10px] text-emerald-600 dark:text-emerald-400 font-mono">
                        ≈ {pricing.costUsdFormatted} USD
                      </span>
                    </div>
                  );
                })()}
              </div>
              <h3 className="text-base font-semibold">
                {service.title[language]}
              </h3>
              <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-400">
                {service.description[language]}
              </p>
              <div className="mb-5 mt-4 border-s-2 border-emerald-200 ps-3 text-sm dark:border-emerald-800">
                <p className="mb-1 text-xs font-semibold text-slate-500 dark:text-slate-400">
                  {t("What you get", "النتيجة")}
                </p>
                <p className="leading-6">{service.output[language]}</p>
              </div>
              <div className="mt-auto flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4 dark:border-slate-800">
                <Link
                  href={
                    preview
                      ? "/login?mode=signup"
                      : service.id === "chat"
                        ? "/conversations"
                        : `/playground?service=${service.id}`
                  }
                  className="inline-flex items-center gap-2 rounded-lg bg-emerald-700 px-3 py-2 text-sm font-semibold text-white hover:bg-emerald-800 dark:bg-emerald-500 dark:text-slate-950 dark:hover:bg-emerald-400"
                >
                  {t(
                    preview
                      ? "Get started"
                      : service.id === "chat"
                        ? "Open chat"
                        : "Try service",
                    preview
                      ? "ابدأ الآن"
                      : service.id === "chat"
                        ? "افتح المحادثة"
                        : "جرّب الخدمة",
                  )}
                  <ArrowRight size={15} className="rtl:rotate-180" />
                </Link>
                {!preview && (
                  <Link
                    href={`/docs?service=${service.id}`}
                    className="text-sm font-medium text-slate-600 hover:underline dark:text-slate-300"
                  >
                    {t("API docs", "توثيق API")}
                  </Link>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
