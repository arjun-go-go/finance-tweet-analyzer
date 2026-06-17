"use client";

import { useEffect, useState } from "react";
import DashboardStats from "@/components/DashboardStats";
import TickerCard from "@/components/TickerCard";
import SkeletonCard from "@/components/SkeletonCard";
import { fetchDashboard, fetchTickerSummaries } from "@/lib/api";

interface DashboardData {
  total_tweets: number;
  pending_tweets: number;
  analyzed_tweets: number;
  total_analyses: number;
  total_bloggers: number;
  pending_predictions?: number;
}

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

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [tickers, setTickers] = useState<TickerItem[]>([]);
  const [tickerTotal, setTickerTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  const loadData = async () => {
    setLoading(true);
    try {
      const [dashRes, tickersRes] = await Promise.all([
        fetchDashboard(),
        fetchTickerSummaries(),
      ]);
      setData(dashRes);
      setTickers(tickersRes.items || []);
      setTickerTotal(tickersRes.total || 0);
    } catch (e) {
      console.error("Failed to load dashboard:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="h-8 w-32 bg-gray-200 rounded animate-pulse" />
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="bg-white rounded-lg shadow p-4 animate-pulse">
              <div className="h-4 w-16 bg-gray-200 rounded mb-2" />
              <div className="h-8 w-12 bg-gray-200 rounded" />
            </div>
          ))}
        </div>
        <div className="grid md:grid-cols-2 gap-4">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      </div>
    );
  }

  if (!data) {
    return <p className="text-center py-10 text-red-500">加载失败</p>;
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <h1 className="text-2xl font-bold">Dashboard</h1>

      {/* Stats */}
      <DashboardStats
        totalTweets={data.total_tweets}
        pendingTweets={data.pending_tweets}
        analyzedTweets={data.analyzed_tweets}
        totalAnalyses={data.total_analyses}
        totalBloggers={data.total_bloggers}
        pendingPredictions={data.pending_predictions ?? 0}
      />

      {/* Ticker recommendations */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">标的推荐排行</h2>
          <span className="text-sm text-gray-500">共 {tickerTotal} 个</span>
        </div>

        {tickers.length === 0 ? (
          <div className="text-center py-14 bg-white rounded-lg shadow">
            <div className="text-5xl mb-3">📊</div>
            <p className="text-gray-500 text-lg font-medium mb-1">暂无分析数据</p>
            <p className="text-gray-400 text-sm">
              请先导入推文并在「推文 & 分析」页面触发分析以生成标的推荐
            </p>
          </div>
        ) : (
          <div className="grid md:grid-cols-2 gap-4">
            {tickers.map((item) => (
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
