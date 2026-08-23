import { Suspense } from "react";
import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import "@xterm/xterm/css/xterm.css";
import { Header } from "@/components/layout/Header";
import { ThemeProvider } from "@/components/theme-provider";
import { AuthProvider } from "@/context/AuthContext";
import { BackendHealthStatus } from "@/components/common/BackendHealthStatus";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "GitOnboard - Repository Intelligence",
  description: "Repository Intelligence Platform",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full" suppressHydrationWarning>
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased h-full flex flex-col overflow-hidden bg-white text-slate-900 dark:bg-slate-950 dark:text-slate-100 transition-colors duration-200`}>
        <ThemeProvider attribute="class" defaultTheme="system" disableTransitionOnChange enableSystem>
          <AuthProvider>
            <Suspense fallback={<div className="h-16 border-b border-slate-200 dark:border-slate-800" />}><Header /></Suspense>
            <div className="flex-1 flex overflow-hidden">
              {children}
            </div>
            <BackendHealthStatus />
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
