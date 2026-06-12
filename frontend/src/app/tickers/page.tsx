"use client";

import { useEffect, useState } from "react";
import TickerCard from "@/components/TickerCard";
import { fetchTickerSummaries } from "@/lib/api";

interface TickerItem {
  id: string;
  result: {
    ticker: string;
    mention_count: number;
    bloggers: string[];
    consensus: string;
    bullish_count: number;
    bearish_count: number;
    recommendation_score: number;
    summary: string;
  };
  created_at: string;
}

export default function TickersPage() {
  const [items, setItems] = useState<TickerItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const result = await fetchTickerSummaries();
        setItems(result.items);
        setTotal(result.total);
      } catch (e) {
        console.error("Failed to load ticker summaries:", e);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  if (loading) return <p className="text-center py-10">加载中...</p>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">标的推荐排行 ({total})</h1>
      </div>

      {items.length === 0 ? (
        <p className="text-center py-10 text-gray-500">
          暂无数据，请先在「推文分析」页面触发分析
        </p>
      ) : (
        <div className="grid md:grid-cols-2 gap-4">
          {items.map((item) => (
            <TickerCard
              key={item.id}
              ticker={item.result.ticker}
              mentionCount={item.result.mention_count}
              bloggers={item.result.bloggers}
              consensus={item.result.consensus}
              bullishCount={item.result.bullish_count}
              bearishCount={item.result.bearish_count}
              recommendationScore={item.result.recommendation_score}
              summary={item.result.summary}
            />
          ))}
        </div>
      )}
    </div>
  );
}
