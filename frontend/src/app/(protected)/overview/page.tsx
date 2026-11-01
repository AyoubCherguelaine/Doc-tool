"use client";

import Link from "next/link";
import {
  ArrowRight,
  MessageSquare,
  ScanText,
  Grid2X2,
  BookOpen,
  Building,
} from "lucide-react";
import { useLanguage } from "@/components/providers/language-provider";
import { useSession } from "@/components/providers/session-provider";

export default function OverviewPage() {
  const { t } = useLanguage();
  const { user } = useSession();
  const tools = [
    {
      href: "/conversations",
      icon: MessageSquare,
      title: t("Chat with a document", "تحدث مع مستند"),
      body: t(
        "Upload a file and ask questions about its contents. Review answers alongside their source references.",
        "ارفع ملفًا واطرح أسئلة عن محتواه. راجع الإجابات والمراجع المصدرية المرتبطة بها.",
      ),
      action: t("Open document chat", "افتح محادثة المستندات"),
    },
    {
      href: "/advanced-ocr",
      icon: ScanText,
      title: t("Extract text from a scan", "استخرج النص من صورة ممسوحة"),
      body: t(
        "Read scanned pages with OCR. Check the extracted text and tables before exporting them.",
        "اقرأ الصفحات الممسوحة باستخدام التعرف الضوئي على الحروف. راجع النص والجداول المستخرجة قبل تصديرها.",
      ),
      action: t("Open OCR", "افتح أداة استخراج النص"),
    },
    {
      href: "/services",
      icon: Grid2X2,
      title: t("Process a document", "عالج مستندًا"),
      body: t(
        "Extract invoice fields, review a contract, summarize a report or translate between Arabic and English.",
        "استخرج حقول فاتورة، أو راجع عقدًا، أو لخص تقريرًا، أو ترجم بين العربية والإنجليزية.",
      ),
      action: t("Browse services", "تصفح الخدمات"),
    },
  ];
  return (
    <div className="mx-auto max-w-6xl space-y-9 animate-enter">
      <header className="max-w-2xl">
        <div className="flex flex-wrap items-center gap-2 mb-2">
          <p className="eyebrow">{t("Your workspace", "مساحة عملك")}</p>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-200/80 bg-emerald-50 px-2.5 py-0.5 text-xs font-mono font-semibold text-emerald-800 dark:border-emerald-800/60 dark:bg-emerald-950/40 dark:text-emerald-300">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
            <Building size={11} className="text-emerald-600 dark:text-emerald-400" />
            <span>
              {user?.name && !user.name.startsWith("http") && !user.name.includes("@")
                ? `${user.name.trim()}'s Workspace`
                : "Ayoub's Workspace"}
            </span>
          </span>
        </div>
        <h1 className="text-3xl font-bold tracking-tight">
          {t("What do you need to do?", "ما الذي تريد إنجازه؟")}
        </h1>
        <p className="mt-3 text-base leading-7 text-slate-600 dark:text-slate-400">
          {t(
            "Choose a tool based on your task. You can ask about a document, read a scanned file, or extract specific information.",
            "اختر الأداة حسب مهمتك. يمكنك السؤال عن مستند أو قراءة ملف ممسوح ضوئيًا أو استخراج معلومات محددة.",
          )}
        </p>
      </header>
      <div className="grid gap-5 md:grid-cols-3">
        {tools.map((tool) => (
          <article key={tool.href} className="surface flex flex-col p-6">
            <span className="mb-5 w-fit rounded-xl bg-emerald-50 p-3 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400">
              <tool.icon size={26} />
            </span>
            <h2 className="text-lg font-semibold">{tool.title}</h2>
            <p className="mb-7 mt-3 text-sm leading-7 text-slate-600 dark:text-slate-400">
              {tool.body}
            </p>
            <Link
              href={tool.href}
              className="mt-auto inline-flex items-center justify-between gap-2 rounded-xl bg-emerald-700 px-4 py-3 text-sm font-semibold text-white hover:bg-emerald-800 dark:bg-emerald-500 dark:text-slate-950 dark:hover:bg-emerald-400"
            >
              {tool.action}
              <ArrowRight size={16} className="shrink-0 rtl:rotate-180" />
            </Link>
          </article>
        ))}
      </div>
      <section className="rounded-2xl border border-slate-200 p-6 dark:border-slate-800">
        <h2 className="text-lg font-semibold">
          {t(
            "Using the platform for the first time?",
            "هل تستخدم المنصة لأول مرة؟",
          )}
        </h2>
        <ol className="mt-5 grid gap-5 text-sm md:grid-cols-3">
          {[
            [
              t("Choose a tool", "اختر أداة"),
              t(
                "Open chat, OCR or a service from the menu.",
                "افتح المحادثة أو أداة استخراج النص أو إحدى الخدمات من القائمة.",
              ),
            ],
            [
              t("Select a file", "حدد ملفًا"),
              t(
                "Check the supported formats and file size on the upload screen.",
                "راجع الصيغ المدعومة وحجم الملف في شاشة الرفع.",
              ),
            ],
            [
              t("Check the output", "تحقق من النتيجة"),
              t(
                "Compare important details with the original before using the result.",
                "قارن التفاصيل المهمة بالمستند الأصلي قبل استخدام النتيجة.",
              ),
            ],
          ].map(([title, body], i) => (
            <li key={title}>
              <p className="font-semibold">
                <span className="me-2 text-emerald-700 dark:text-emerald-400">
                  {i + 1}.
                </span>
                {title}
              </p>
              <p className="mt-2 leading-6 text-slate-600 dark:text-slate-400">
                {body}
              </p>
            </li>
          ))}
        </ol>
      </section>
      <section className="flex flex-wrap items-center justify-between gap-4 rounded-2xl bg-slate-100 p-6 dark:bg-slate-900">
        <div>
          <h2 className="font-semibold">
            {t(
              "Connect document tools to your application",
              "اربط أدوات المستندات بتطبيقك",
            )}
          </h2>
          <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-400">
            {t(
              "Read the API guide for requests and response examples, or try a request in the playground.",
              "راجع دليل API لأمثلة الطلبات والاستجابات، أو جرّب طلبًا في بيئة التجربة.",
            )}
          </p>
        </div>
        <div className="flex flex-wrap gap-4">
          <Link
            href="/docs"
            className="inline-flex items-center gap-2 text-sm font-semibold text-emerald-700 hover:underline dark:text-emerald-400"
          >
            <BookOpen size={16} />
            {t("API guide", "دليل API")}
          </Link>
          <Link
            href="/playground"
            className="text-sm font-semibold text-emerald-700 hover:underline dark:text-emerald-400"
          >
            {t("Open playground", "افتح بيئة التجربة")}
          </Link>
        </div>
      </section>
    </div>
  );
}
