"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import BloggerCard, { BloggerListItem } from "@/components/BloggerCard";
import { fetchBloggers } from "@/lib/api";

type SortKey = "credibility" | "verified_count" | "followers" | "pending_count";

export default function BloggersListPage() {
  const params = useSearchParams();
  const initialSort = (params.get("sort") as SortKey) || "credibility";
  const [sort, setSort] = useState<SortKey>(initialSort);
  const [items, setItems] = useState<BloggerListItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchBloggers({ sort })
      .then((data: BloggerListItem[]) => {
        if (!cancelled) setItems(data);
      })
      .catch((e) => console.error("Failed to load bloggers:", e))
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [sort]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">博主排行</h1>
        <div className="flex gap-2">
          {(
            [
              ["credibility", "可信度"],
              ["verified_count", "已标注数"],
              ["pending_count", "待标注数"],
              ["followers", "粉丝数"],
            ] as Array<[SortKey, string]>
          ).map(([key, label]) => (
            <button
              key={key}
              onClick={() => setSort(key)}
              className={`px-3 py-1 rounded-lg text-sm transition-colors ${
                sort === key
                  ? "bg-blue-600 text-white"
                  : "bg-gray-100 text-gray-700 hover:bg-gray-200"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="grid md:grid-cols-2 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="bg-white rounded-lg shadow p-4 animate-pulse">
              <div className="flex items-center gap-3 mb-3">
                <div className="w-10 h-10 rounded-full bg-gray-200" />
                <div className="flex-1 space-y-1.5">
                  <div className="h-4 w-24 bg-gray-200 rounded" />
                  <div className="h-3 w-16 bg-gray-200 rounded" />
                </div>
              </div>
              <div className="h-3 w-full bg-gray-200 rounded mb-2" />
              <div className="h-8 w-16 bg-gray-200 rounded mb-2" />
              <div className="flex gap-1.5 mb-2">
                <div className="h-5 w-14 bg-gray-200 rounded" />
                <div className="h-5 w-14 bg-gray-200 rounded" />
              </div>
              <div className="flex justify-between">
                <div className="h-3 w-20 bg-gray-200 rounded" />
                <div className="h-3 w-12 bg-gray-200 rounded" />
              </div>
            </div>
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="text-center py-14 bg-white rounded-lg shadow">
          <div className="text-5xl mb-3">👤</div>
          <p className="text-gray-500 text-lg font-medium mb-1">暂无博主数据</p>
          <p className="text-gray-400 text-sm">先导入推文，系统将自动识别并汇总博主信息</p>
        </div>
      ) : (
        <div className="grid md:grid-cols-2 gap-4">
          {items.map((b) => (
            <BloggerCard key={b.handle} blogger={b} />
          ))}
        </div>
      )}
    </div>
  );
}
