"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard" },
  { href: "/tweets", label: "推文 & 分析" },
  { href: "/bloggers", label: "博主排行" },
  { href: "/documents", label: "文档" },
  { href: "/reports", label: "报告" },
  { href: "/tracking", label: "追踪" },
  { href: "/me", label: "我的工作台" },
  { href: "/retrieval-test", label: "检索测试" },
  { href: "/admin/es", label: "ES Admin" },
  { href: "/chat", label: "智能助手" },
];

export default function Navbar() {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  const isActive = (href: string) => {
    if (href === "/") return pathname === "/";
    return pathname === href || pathname.startsWith(href + "/");
  };

  return (
    <nav className="bg-gray-900 px-6 py-4 text-white">
      <div className="mx-auto flex max-w-7xl items-center justify-between">
        <Link href="/" className="text-xl font-bold">
          Finance Tweet Analyzer
        </Link>

        <div className="hidden items-center gap-6 md:flex">
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`text-sm transition-colors ${
                isActive(item.href)
                  ? "font-medium text-blue-400"
                  : "hover:text-blue-400"
              }`}
            >
              {item.label}
            </Link>
          ))}
        </div>

        <button
          className="flex flex-col gap-1 p-1 md:hidden"
          onClick={() => setMobileOpen((o) => !o)}
          aria-label="切换导航"
        >
          <span
            className={`block h-0.5 w-5 bg-white transition-transform ${
              mobileOpen ? "translate-y-1.5 rotate-45" : ""
            }`}
          />
          <span
            className={`block h-0.5 w-5 bg-white transition-opacity ${
              mobileOpen ? "opacity-0" : ""
            }`}
          />
          <span
            className={`block h-0.5 w-5 bg-white transition-transform ${
              mobileOpen ? "-translate-y-1.5 -rotate-45" : ""
            }`}
          />
        </button>
      </div>

      {mobileOpen && (
        <div className="mt-3 space-y-2 border-t border-gray-700 pt-3 pb-2 md:hidden">
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              onClick={() => setMobileOpen(false)}
              className={`block py-1 text-sm ${
                isActive(item.href)
                  ? "font-medium text-blue-400"
                  : "text-gray-300 hover:text-white"
              }`}
            >
              {item.label}
            </Link>
          ))}
        </div>
      )}
    </nav>
  );
}
