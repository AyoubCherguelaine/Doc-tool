"use client";
import { useLanguage } from "@/components/providers/language-provider";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  MessageSquare,
  LogOut,
  PanelLeftClose,
  Menu,
  ChevronDown,
  Zap,
  Code2,
  Copy,
  Check,
  ShieldCheck,
  History,
  Users,
  Building,
  LayoutDashboard,
  ScanText,
  Bot,
  BookOpen,
  Settings as SettingsIcon,
} from "lucide-react";
import { useState, useEffect, useRef } from "react";
import { Brand } from "@/components/brand";
import { useSession } from "@/components/providers/session-provider";
import { fetchCompanyAccount, type CompanyAccountInfo } from "@/lib/api";
import { cn } from "@/lib/utils";
import { LanguageToggle } from "@/components/ui/language-toggle";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { ModelSelectorButton, ModelSelectionModal } from "@/components/ui/model-selector";
import { SettingsModal } from "@/components/ui/settings-modal";
import { useModelSettings } from "@/components/providers/model-provider";

function getPageTitle(pathname: string, t: (value: string) => string): string {
  if (pathname.startsWith("/overview")) return t("Platform Overview");
  if (pathname.startsWith("/advanced-ocr")) return t("Advanced OCR");
  if (pathname.startsWith("/services")) return t("AI Services");
  if (pathname.startsWith("/docs")) return t("Platform Documentation");
  if (pathname.startsWith("/playground")) return t("Playground Sandbox");
  if (pathname.startsWith("/usage")) return t("Credits & Usage Logs");
  if (pathname.startsWith("/conversations")) return t("Chats");
  if (pathname.startsWith("/chat")) return t("Document Chat");
  if (pathname.startsWith("/settings")) return t("Settings & Workspace");
  return t("Document AI");
}

export function Navbar() {
  const { t } = useLanguage();
  const { user, logout } = useSession();
  const { selectedModelInfo, openModelModal, openSettings } = useModelSettings();
  const pathname = usePathname();

  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [profileDropdownOpen, setProfileDropdownOpen] = useState(false);
  const [selectedGroup, setSelectedGroup] = useState<string>("main");
  const [account, setAccount] = useState<CompanyAccountInfo | null>(null);
  const [copiedKey, setCopiedKey] = useState(false);

  const profileMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let active = true;
    const updateAccount = () => {
      fetchCompanyAccount()
        .then((data) => {
          if (active) setAccount(data);
        })
        .catch(() => {});
    };

    updateAccount();

    const handleCreditUpdate = () => updateAccount();
    window.addEventListener("doctool:credit-updated", handleCreditUpdate);
    window.addEventListener("focus", handleCreditUpdate);

    return () => {
      active = false;
      window.removeEventListener("doctool:credit-updated", handleCreditUpdate);
      window.removeEventListener("focus", handleCreditUpdate);
    };
  }, [pathname]);

  // Close profile dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        profileMenuRef.current &&
        !profileMenuRef.current.contains(event.target as Node)
      ) {
        setProfileDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const mainNavLinks = [
    {
      href: "/overview",
      label: t("Overview"),
      icon: LayoutDashboard,
      isActive: (p: string) => p.startsWith("/overview"),
    },
    {
      href: "/conversations",
      label: t("Chats"),
      icon: MessageSquare,
      isActive: (p: string) =>
        p.startsWith("/conversations") || p.startsWith("/chat"),
    },
    {
      href: "/advanced-ocr",
      label: t("Advanced OCR"),
      icon: ScanText,
      isActive: (p: string) => p.startsWith("/advanced-ocr"),
    },
    {
      href: "/services",
      label: t("AI Services"),
      icon: Bot,
      isActive: (p: string) => p.startsWith("/services"),
    },
    {
      href: "/settings",
      label: t("Settings"),
      icon: SettingsIcon,
      isActive: (p: string) => p.startsWith("/settings"),
    },
  ];

  const copyApiKey = async () => {
    if (!account?.apiKeyPrefix) return;
    try {
      await navigator.clipboard.writeText(
        `${account.apiKeyPrefix}********************`,
      );
      setCopiedKey(true);
      setTimeout(() => setCopiedKey(false), 2000);
    } catch {}
  };

  const remaining = account?.remainingCredits ?? 300;
  const cleanName = (user?.name || "").trim().startsWith("http") || (user?.name || "").includes("@") || !(user?.name || "").trim()
    ? "Ayoub"
    : user!.name!.trim();
  const initial = cleanName[0]?.toUpperCase() || "A";
  const pageTitle = getPageTitle(pathname, t);

  return (
    <>
      {/* =========================================================================
          1. TOP HORIZONTAL NAVIGATION BAR (NAVBAR)
          Contains: small credit pill, theme toggle, profile with select group, logout
         ========================================================================= */}
      <header className="sticky top-0 z-30 flex h-14 w-full items-center justify-between border-b border-slate-200 bg-white/95 px-4 backdrop-blur-md sm:px-6 lg:px-10 dark:border-slate-800 dark:bg-[#0c1017]/95 transition-colors">
        {/* Left: Mobile Toggle + Breadcrumb / Operation Title */}
        <div className="flex items-center gap-3">
          <button
            aria-label={t("Toggle operations sidebar")}
            aria-expanded={sidebarOpen}
            aria-controls="workspace-navigation"
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800 lg:hidden"
          >
            <Menu size={20} />
          </button>

          <div className="hidden sm:flex items-center gap-2 text-xs">
            <span className="font-semibold text-slate-400 dark:text-slate-500">
              DOCTool
            </span>
            <span className="text-slate-300 dark:text-slate-700">/</span>
            <span className="font-bold text-slate-800 dark:text-slate-200">
              {pageTitle}
            </span>
          </div>

          <div className="hidden min-[480px]:block sm:hidden">
            <Brand href="/overview" />
          </div>
        </div>

        {/* Right: Theme Toggle + Small Credit Pill + Profile */}
        <div className="flex items-center gap-2 sm:gap-2.5">
          {/* OpenAI-style Model Selector Button */}
          <ModelSelectorButton size="sm" />

          {/* DEDICATED SETTINGS BUTTON */}
          <button
            onClick={openSettings}
            title={t("Settings: AI Model, Guardian & Workspace", "الإعدادات ومساحة العمل")}
            className="flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition shadow-2xs dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 cursor-pointer"
          >
            <SettingsIcon size={14} className="text-emerald-600 dark:text-emerald-400" />
            <span className="hidden sm:inline">{t("Settings")}</span>
          </button>

          {/* THEME TOGGLE (WHITE/GREEN <-> MODERN DARK) */}
          <LanguageToggle />
          <ThemeToggle />

          {/* SMALL CREDIT PILL */}
          <Link
            href="/usage"
            title={t("View remaining credit quota and usage logs")}
            className="hidden sm:inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-800 hover:bg-emerald-100 transition shadow-2xs dark:border-emerald-800/50 dark:bg-emerald-950/40 dark:text-emerald-300 dark:hover:bg-emerald-900/50"
          >
            <Zap
              size={12}
              className="text-emerald-600 fill-emerald-600 dark:text-emerald-400 dark:fill-emerald-400"
            />
            <span>{remaining.toLocaleString()}</span>
            <span className="hidden sm:inline text-[11px] font-normal text-emerald-700 dark:text-emerald-400">
              {t("Credits")}
            </span>
          </Link>

          {/* PROFILE WITH SELECT GROUP (DROPDOWN) */}
          <div className="relative" ref={profileMenuRef}>
            <button
              onClick={() => setProfileDropdownOpen(!profileDropdownOpen)}
              className="flex items-center gap-2 rounded-full border border-slate-200 bg-white p-1 pe-2.5 text-start transition hover:border-emerald-500 hover:shadow-2xs dark:border-slate-800 dark:bg-slate-900 dark:hover:border-emerald-500"
              aria-label={t("Profile and select group")}
            >
              <span className="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-tr from-teal-700 to-emerald-600 text-xs font-bold text-white shadow-2xs">
                {initial}
              </span>
              <span className="hidden md:inline max-w-[110px] truncate text-xs font-semibold text-slate-800 dark:text-slate-200">
                {user?.name || t("Account")}
              </span>
              <ChevronDown
                size={13}
                className="text-slate-400 dark:text-slate-500"
              />
            </button>

            {/* Profile Dropdown */}
            {profileDropdownOpen && (
              <div className="absolute end-0 top-11 z-50 w-[min(20rem,calc(100vw-2rem))] overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl animate-in fade-in zoom-in-95 duration-150 dark:border-slate-800 dark:bg-[#121820]">
                {/* Profile Header */}
                <div className="border-b border-slate-100 bg-slate-50/70 p-4 dark:border-slate-800 dark:bg-slate-900/50">
                  <div className="flex items-center gap-3">
                    <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-tr from-teal-700 to-emerald-600 text-base font-bold text-white shadow-sm">
                      {initial}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-bold text-slate-900 dark:text-slate-100">
                        {cleanName}
                      </p>
                      <p className="truncate text-xs text-slate-500 dark:text-slate-400">
                        {user?.email}
                      </p>
                    </div>
                  </div>
                </div>

                {/* Dedicated Workspace Card for this user */}
                <div className="border-b border-slate-100 p-3 dark:border-slate-800">
                  <div className="flex items-center justify-between mb-2 px-1">
                    <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500">
                      {t("Dedicated Workspace", "مساحة العمل")}
                    </p>
                    <span className="inline-flex items-center gap-1 text-[10px] text-emerald-600 dark:text-emerald-400 font-bold">
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
                      {t("Isolated Instance", "مثيل معزول")}
                    </span>
                  </div>

                  <div className="rounded-xl border border-emerald-200/60 bg-emerald-50/40 p-2.5 dark:border-emerald-800/40 dark:bg-emerald-950/20">
                    <div className="flex items-center gap-2">
                      <Building
                        size={15}
                        className="text-emerald-600 dark:text-emerald-400 shrink-0"
                      />
                      <span className="text-xs font-bold text-slate-800 dark:text-slate-200 truncate">
                        {account?.companyName && !account.companyName.startsWith("http") && !account.companyName.includes("daall")
                          ? account.companyName
                          : `${cleanName}'s Workspace`}
                      </span>
                    </div>
                    <div className="mt-2 flex items-center justify-between pt-2 border-t border-emerald-100 dark:border-emerald-900/40 text-[11px]">
                      <span className="text-slate-500 dark:text-slate-400 font-mono text-[10px]">
                        {account?.planTier ? `${account.planTier}` : "Free Trial"}
                      </span>
                      <button
                        type="button"
                        onClick={() => {
                          setProfileDropdownOpen(false);
                          openSettings();
                        }}
                        className="font-semibold text-emerald-700 dark:text-emerald-400 hover:underline inline-flex items-center gap-1 text-[11px]"
                      >
                        <SettingsIcon size={11} />
                        <span>{t("Settings", "الإعدادات")}</span>
                      </button>
                    </div>
                  </div>
                </div>

                {/* Credit Balance & Logs Link */}
                <div className="border-b border-slate-100 p-3 bg-emerald-50/40 dark:border-slate-800 dark:bg-emerald-950/20">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[11px] font-semibold text-slate-700 dark:text-slate-300 flex items-center gap-1">
                      <Zap
                        size={13}
                        className="text-emerald-600 fill-emerald-600 dark:text-emerald-400 dark:fill-emerald-400"
                      />
                      {t("Available Balance")}
                    </span>
                    <span className="text-[10px] font-bold uppercase rounded bg-emerald-100 px-1.5 py-0.5 text-emerald-800 dark:bg-emerald-900/60 dark:text-emerald-300">
                      {account?.planTier || t("Free Trial")}
                    </span>
                  </div>
                  <div className="text-xl font-extrabold text-slate-900 dark:text-white">
                    {remaining.toLocaleString()}{" "}
                    <span className="text-xs font-normal text-slate-500 dark:text-slate-400">
                      {t("credits")}
                    </span>
                  </div>
                  <Link
                    href="/usage"
                    onClick={() => setProfileDropdownOpen(false)}
                    className="mt-2 flex items-center justify-between rounded-lg bg-white border border-emerald-200 p-2 text-[11px] font-semibold text-emerald-800 hover:bg-emerald-50 transition dark:bg-slate-900 dark:border-emerald-800/50 dark:text-emerald-300 dark:hover:bg-emerald-950/30"
                  >
                    <span className="flex items-center gap-1">
                      <History size={13} /> {t("View Credit Usage Logs")}
                    </span>
                    <span>→</span>
                  </Link>
                </div>

                {/* API Key */}
                <div className="border-b border-slate-100 p-3 space-y-2 dark:border-slate-800">
                  <div className="flex items-center justify-between text-xs font-semibold text-slate-700 dark:text-slate-300">
                    <span>{t("Company API Key")}</span>
                    <button
                      onClick={copyApiKey}
                      className="text-[11px] text-emerald-700 dark:text-emerald-400 hover:underline flex items-center gap-1"
                    >
                      {copiedKey ? (
                        <>
                          <Check
                            size={11}
                            className="text-emerald-600 dark:text-emerald-400"
                          />
                          <span className="text-emerald-600 dark:text-emerald-400">
                            {t("Copied")}
                          </span>
                        </>
                      ) : (
                        <>
                          <Copy size={11} />
                          <span>{t("Copy")}</span>
                        </>
                      )}
                    </button>
                  </div>
                  <div className="rounded bg-slate-900 dark:bg-slate-950 p-1.5 font-mono text-[11px] text-emerald-400 truncate border border-slate-800">
                    {account?.apiKeyPrefix || "docu_live_"}••••••••••••••••
                  </div>
                  <div className="flex items-center justify-between text-[10px] text-slate-400 dark:text-slate-500 pt-1">
                    <span>
                      {t("Model:")}{" "}
                      <span className="font-semibold text-slate-700 dark:text-slate-200 font-mono">
                        {selectedModelInfo?.name || "gpt-4o-mini"}
                      </span>
                    </span>
                    <button
                      type="button"
                      onClick={() => {
                        setProfileDropdownOpen(false);
                        openModelModal();
                      }}
                      className="text-emerald-600 dark:text-emerald-400 hover:underline font-semibold"
                    >
                      {t("Change")}
                    </button>
                  </div>
                </div>

                {/* Settings & Preferences Link */}
                <div className="border-b border-slate-100 p-2 dark:border-slate-800">
                  <button
                    type="button"
                    onClick={() => {
                      setProfileDropdownOpen(false);
                      openSettings();
                    }}
                    className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 dark:text-slate-300 dark:hover:bg-slate-800/60 transition cursor-pointer"
                  >
                    <SettingsIcon size={14} className="text-emerald-600 dark:text-emerald-400" />
                    <span>{t("Settings & Workspace", "الإعدادات ومساحة العمل")}</span>
                  </button>
                </div>

                {/* Logout Button */}
                <div className="p-2 bg-slate-50/50 dark:bg-slate-900/40">
                  <button
                    type="button"
                    onClick={() => {
                      setProfileDropdownOpen(false);
                      logout();
                    }}
                    className="flex w-full items-center justify-center gap-2 rounded-xl py-2 text-xs font-semibold text-rose-700 hover:bg-rose-50 dark:text-rose-400 dark:hover:bg-rose-950/30 transition"
                  >
                    <LogOut size={14} />
                    <span>{t("Log Out")}</span>
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* =========================================================================
          2. SIDEBAR FOR OPERATIONS (LEFT)
         ========================================================================= */}
      {/* Mobile Backdrop */}
      {sidebarOpen && (
        <button
          aria-label={t("Close navigation")}
          className="fixed inset-0 z-40 bg-slate-950/40 backdrop-blur-xs lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <aside
        id="workspace-navigation"
        className={cn(
          "fixed inset-y-0 start-0 z-50 w-[244px] flex-col overflow-y-auto border-e border-slate-200 bg-white px-4 py-6 dark:border-slate-800 dark:bg-[#0c1017]",
          sidebarOpen ? "flex" : "hidden lg:flex",
        )}
      >
        {/* Brand Header */}
        <div className="mb-8 flex items-center justify-between px-2">
          <Brand href="/overview" />
          <button
            className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 lg:hidden"
            aria-label={t("Close navigation")}
            onClick={() => setSidebarOpen(false)}
          >
            <PanelLeftClose size={17} />
          </button>
        </div>

        {/* Operations / Workspace Label */}
        <p className="eyebrow mb-2 px-3 text-[11px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider">
          {t("Workspace")}
        </p>

        {/* Primary Navigation Links */}
        <nav aria-label={t("Main operations navigation")} className="space-y-1">
          {mainNavLinks.map(({ href, label, icon: Icon, isActive }) => {
            const active = isActive(pathname);
            return (
              <Link
                key={href}
                href={href}
                onClick={() => setSidebarOpen(false)}
                className={cn(
                  "flex items-center gap-3 rounded-xl px-3 py-2.5 text-[13px] font-medium text-slate-600 transition-colors hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800/60 dark:hover:text-slate-200",
                  active &&
                    "bg-emerald-50 text-[#087f74] dark:bg-emerald-950/50 dark:text-emerald-400 font-semibold",
                )}
              >
                <Icon
                  size={17}
                  className={
                    active
                      ? "text-[#087f74] dark:text-emerald-400"
                      : "text-slate-400 dark:text-slate-500"
                  }
                />
                <span>{label}</span>
              </Link>
            );
          })}
        </nav>

        {/* Secondary Developer & Quota Tools */}
        <div className="mt-5 pt-4 border-t border-slate-100 dark:border-slate-800">
          <p className="eyebrow mb-2 px-3 text-[10px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider">
            {t("Developer & Quota")}
          </p>
          <nav aria-label={t("Developer navigation")} className="space-y-1">
            <Link
              href="/docs"
              onClick={() => setSidebarOpen(false)}
              className={cn(
                "flex items-center gap-3 rounded-xl px-3 py-2 text-[12px] font-medium text-slate-600 transition-colors hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800/60 dark:hover:text-slate-200",
                pathname.startsWith("/docs") &&
                  "bg-emerald-50 text-[#087f74] dark:bg-emerald-950/50 dark:text-emerald-400 font-semibold",
              )}
            >
              <BookOpen size={16} />
              <span>{t("Platform Docs")}</span>
              <span className="ms-auto rounded border border-emerald-200 bg-emerald-50 px-1.5 py-0.5 text-[9px] font-mono font-semibold text-emerald-800 dark:border-emerald-800/50 dark:bg-emerald-950/40 dark:text-emerald-300">
                DOCS
              </span>
            </Link>
            <Link
              href="/playground"
              onClick={() => setSidebarOpen(false)}
              className={cn(
                "flex items-center gap-3 rounded-xl px-3 py-2 text-[12px] font-medium text-slate-600 transition-colors hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800/60 dark:hover:text-slate-200",
                pathname.startsWith("/playground") &&
                  "bg-emerald-50 text-[#087f74] dark:bg-emerald-950/50 dark:text-emerald-400 font-semibold",
              )}
            >
              <Code2 size={16} />
              <span>{t("Sandbox Demo")}</span>
              <span className="ms-auto rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[9px] font-mono font-semibold text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                RUN
              </span>
            </Link>
            <Link
              href="/usage"
              onClick={() => setSidebarOpen(false)}
              className={cn(
                "flex items-center gap-3 rounded-xl px-3 py-2 text-[12px] font-medium text-slate-600 transition-colors hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800/60 dark:hover:text-slate-200",
                pathname.startsWith("/usage") &&
                  "bg-emerald-50 text-[#087f74] dark:bg-emerald-950/50 dark:text-emerald-400 font-semibold",
              )}
            >
              <Zap size={16} />
              <span>Credits & Usage</span>
              <span className="ms-auto rounded bg-emerald-100 px-1.5 py-0.5 text-[9px] font-bold text-emerald-800 dark:bg-emerald-900/60 dark:text-emerald-300">
                LOGS
              </span>
            </Link>
          </nav>
        </div>

        {/* Sidebar Footer Info */}
        <div className="mt-auto rounded-xl border border-slate-200 bg-slate-50/70 p-3.5 space-y-1 text-xs text-slate-500 dark:border-slate-800 dark:bg-slate-900/50 dark:text-slate-400">
          <div className="flex items-center gap-1.5 font-semibold text-slate-800 dark:text-slate-200">
            <ShieldCheck
              size={14}
              className="text-emerald-600 dark:text-emerald-400"
            />
            <span>{t("Document tools")}</span>
          </div>
          <p className="text-[11px] text-slate-500 dark:text-slate-400 leading-relaxed">
            {t(
              "Upload a file, choose a task, and review the result.",
              "ارفع ملفًا، واختر مهمة، ثم راجع النتيجة.",
            )}
          </p>
        </div>
      </aside>

      {/* Global Modals for Navbar & Entire App */}
      <ModelSelectionModal />
      <SettingsModal />
    </>
  );
}
