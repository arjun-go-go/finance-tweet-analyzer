"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const PATH_LABELS: Record<string, string> = {
  tweets: "推文 & 分析",
  bloggers: "博主排行",
  documents: "文档",
  reports: "报告",
  tracking: "追踪",
  "retrieval-test": "检索测试",
  chat: "智能助手",
};

export default function Breadcrumb() {
  const pathname = usePathname();
  if (pathname === "/") return null;

  const segments = pathname.split("/").filter(Boolean);

  return (
    <div className="bg-white border-b border-gray-200">
      <div className="max-w-7xl mx-auto px-6 py-2 flex items-center gap-2 text-sm text-gray-500">
        <Link
          href="/"
          className="hover:text-blue-600 transition-colors"
        >
          Dashboard
        </Link>
        {segments.map((seg, idx) => {
          const isLast = idx === segments.length - 1;
          const label = PATH_LABELS[seg] || (isLast ? "详情" : seg);
          return (
            <span key={idx} className="flex items-center gap-2">
              <span className="text-gray-300">/</span>
              {isLast ? (
                <span className="text-gray-800 font-medium">{label}</span>
              ) : (
                <Link
                  href={`/${segments.slice(0, idx + 1).join("/")}`}
                  className="hover:text-blue-600 transition-colors"
                >
                  {label}
                </Link>
              )}
            </span>
          );
        })}
      </div>
    </div>
  );
}
