import type { Metadata } from "next";
import "@fontsource-variable/noto-sans-sc";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "@fontsource/ibm-plex-mono/600.css";
import "@fontsource/ibm-plex-mono/700.css";
import "./globals.css";
import AuthGuard from "@/components/AuthGuard";

export const metadata: Metadata = {
  title: "Signal Desk · AI 投资情报工作台",
  description: "把分散的市场观点，变成有证据的投资情报。",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body>
        <AuthGuard>{children}</AuthGuard>
      </body>
    </html>
  );
}
