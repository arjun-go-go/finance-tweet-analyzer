"use client";

import { useEffect, useState } from "react";
import DashboardStats from "@/components/DashboardStats";
import TickerCard from "@/components/TickerCard";
import { fetchDashboard, triggerAnalysis } from "@/lib/api";

interface DashboardData {
  total_tweets: number;
  pending_tweets: number;
  analyzed_tweets: number;
  total_analyses: number;
  total_bloggers: number;
  pending_predictions?: number;
  top_tickers: Array<{
    id: string;
    result: Record<string, any>;
    confidence: number;
  }>;
}

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);

  const loadData = async () => {
    try {
      const result = await fetchDashboard();
      setData(result);
    } catch (e) {
      console.error("Failed to load dashboard:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleTrigger = async () => {
    setAnalyzing(true);
    try {
      const result = await triggerAnalysis();
      alert(`分析完成！处理了 ${result.analyzed} 条推文，发现 ${result.ticker_summaries.length} 个标的`);
      loadData();
    } catch (e) {
      alert("分析触发失败");
    } finally {
      setAnalyzing(false);
    }
  };

  if (loading) return <p className="text-center py-10">加载中...</p>;
  if (!data) return <p className="text-center py-10 text-red-500">加载失败</p>;

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <button
          onClick={handleTrigger}
          disabled={analyzing}
          className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50"
        >
          {analyzing ? "分析中..." : "分析待处理推文"}
        </button>
      </div>

      <DashboardStats
        totalTweets={data.total_tweets}
        pendingTweets={data.pending_tweets}
        analyzedTweets={data.analyzed_tweets}
        totalAnalyses={data.total_analyses}
        totalBloggers={data.total_bloggers}
        pendingPredictions={data.pending_predictions ?? 0}
      />

      <div>
        <h2 className="text-lg font-semibold mb-4">标的推荐排行</h2>
        {data.top_tickers.length === 0 ? (
          <p className="text-gray-500">暂无分析数据，请先导入推文并触发分析</p>
        ) : (
          <div className="grid md:grid-cols-2 gap-4">
            {data.top_tickers.map((item) => (
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
    </div>
  );
}
