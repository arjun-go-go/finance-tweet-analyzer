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
              className={`px-3 py-1 rounded text-sm ${
                sort === key
                  ? "bg-blue-600 text-white"
                  : "bg-gray-200 text-gray-700 hover:bg-gray-300"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <p className="text-center py-10">加载中...</p>
      ) : items.length === 0 ? (
        <p className="text-center py-10 text-gray-500">
          暂无博主，先导入推文
        </p>
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
