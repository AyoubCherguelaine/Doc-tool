import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { SessionProvider } from "@/components/providers/session-provider";
import { LanguageProvider } from "@/components/providers/language-provider";
import { ThemeProvider } from "@/components/providers/theme-provider";
import { ModelProvider } from "@/components/providers/model-provider";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});
const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "DOCTool — Document chat, OCR and data extraction",
  description:
    "Upload documents, ask questions with source references, extract data, and translate between Arabic and English.",
};

const themeInitScript = `
  (function() {
    try {
      var stored = localStorage.getItem('doctool-theme');
      var root = document.documentElement;
      var language = localStorage.getItem('doctool-language') === 'ar' ? 'ar' : 'en';
      root.lang = language;
      root.dir = language === 'ar' ? 'rtl' : 'ltr';
      if (stored === 'dark' || (!stored && window.matchMedia('(prefers-color-scheme: dark)').matches && stored !== 'light')) {
        root.classList.add('dark');
        root.setAttribute('data-theme', 'dark');
        root.style.colorScheme = 'dark';
      } else {
        root.classList.remove('dark');
        root.setAttribute('data-theme', 'light');
        root.style.colorScheme = 'light';
      }
    } catch (e) {}
  })();
`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body
        className={`${geistSans.variable} ${geistMono.variable} h-full antialiased bg-white text-slate-900 dark:bg-[#090d12] dark:text-slate-100 transition-colors duration-150`}
      >
        <ThemeProvider>
          <LanguageProvider>
            <SessionProvider>
              <ModelProvider>{children}</ModelProvider>
            </SessionProvider>
          </LanguageProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
