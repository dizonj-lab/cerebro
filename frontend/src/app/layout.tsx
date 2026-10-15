import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import "./globals.css";
import { THEME_BOOTSTRAP_SCRIPT } from "@/lib/theme";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: {
    default: "CEREBRO — Adaptive Knowledge and Reasoning Digital Twin",
    template: "%s — CEREBRO",
  },
  description:
    "CEREBRO turns your knowledge and experiences into a connected digital twin: learn, connect, reason, recall.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <head>
        {/* Applies the remembered theme before the first paint. Without this
            the page renders light and then flips, which is worse than being
            light-only was. */}
        <script
          dangerouslySetInnerHTML={{ __html: THEME_BOOTSTRAP_SCRIPT }}
        />
      </head>
      <body className="min-h-full">{children}</body>
    </html>
  );
}
