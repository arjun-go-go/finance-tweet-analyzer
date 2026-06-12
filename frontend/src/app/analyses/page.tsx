"use client";

import { useEffect, useState } from "react";
import AnalysisCard from "@/components/AnalysisCard";
import { fetchAnalyses, analyzeBlogger, analyzeBloggers } from "@/lib/api";

interface TickerRisk {
  category: string;
  description: string;
  severity: string;
  urgency: string;
}

interface TickerDetail {
  symbol: string;
  original_name: string;
  sentiment: string;
  horizon: string;
  risks?: TickerRisk[];
  ticker_risk_level?: string;
}

interface AnalysisItem {
  id: string;
  tweet_id: string;
  twitter_tweet_id: string;
  author_handle: string;
  content: string;
  analysis: {
    tickers: TickerDetail[];
    overall_sentiment: string;
    key_points: string[];
    risk_factors: string[];
    risk_level?: string;
    risk_summary?: string;
    confidence: number;
    is_investment_related: boolean;
    reasoning?: string;
  };
  confidence: number;
  created_at: string;
  published_at: string;
}

export default function AnalysesPage() {
  const [items, setItems] = useState<AnalysisItem[]>([]);
  const [total, setTotal] = useState(0);
  const [filter, setFilter] = useState("");
  const [bloggerInput, setBloggerInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);

  const loadAnalyses = async (sentiment?: string) => {
    setLoading(true);
    try {
      const result = await fetchAnalyses({
        sentiment: sentiment || undefined,
        limit: 30,
      });
      setItems(result.items);
      setTotal(result.total);
    } catch (e) {
      console.error("Failed to load analyses:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAnalyses(filter);
  }, [filter]);

  const handleAnalyze = async () => {
    if (!bloggerInput.trim()) return;
    setAnalyzing(true);
    try {
      const handles = bloggerInput.split(",").map((s) => s.trim()).filter(Boolean);
      let result;
      if (handles.length === 1) {
        result = await analyzeBlogger(handles[0]);
      } else {
        result = await analyzeBloggers(handles);
      }
      alert(
        `分析完成！处理 ${result.analyzed} 条推文，发现 ${result.ticker_summaries.length} 个标的`
      );
      loadAnalyses(filter);
    } catch (e) {
      alert("分析失败");
    } finally {
      setAnalyzing(false);
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">推文投资分析</h1>

      <div className="bg-white rounded-lg shadow p-4">
        <p className="text-sm text-gray-600 mb-2">
          输入博主账号进行分析（多个博主用逗号分隔，进行综合对比分析）
        </p>
        <div className="flex gap-2">
          <input
            type="text"
            value={bloggerInput}
            onChange={(e) => setBloggerInput(e.target.value)}
            placeholder="如: @btc_master 或 @btc_master, @eth_whale"
            className="flex-1 border rounded-lg px-3 py-2 text-sm"
          />
          <button
            onClick={handleAnalyze}
            disabled={analyzing || !bloggerInput.trim()}
            className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm"
          >
            {analyzing ? "分析中..." : "开始分析"}
          </button>
        </div>
      </div>

      <div className="flex items-center justify-between">
        <span className="text-sm text-gray-500">共 {total} 条分析结果</span>
        <div className="flex gap-2">
          {["", "bullish", "bearish", "neutral", "mixed"].map((s) => (
            <button
              key={s}
              onClick={() => setFilter(s)}
              className={`px-3 py-1 rounded text-sm ${
                filter === s
                  ? "bg-blue-600 text-white"
                  : "bg-gray-200 text-gray-700 hover:bg-gray-300"
              }`}
            >
              {s === ""
                ? "全部"
                : s === "bullish"
                ? "看好"
                : s === "bearish"
                ? "看空"
                : s === "mixed"
                ? "分化"
                : "中性"}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <p className="text-center py-10">加载中...</p>
      ) : items.length === 0 ? (
        <p className="text-center py-10 text-gray-500">暂无分析数据</p>
      ) : (
        <div className="grid gap-4">
          {items.map((item) => (
            <AnalysisCard
              key={item.id}
              authorHandle={item.author_handle}
              content={item.content}
              analysis={item.analysis}
              createdAt={item.published_at}
              twitterTweetId={item.twitter_tweet_id}
            />
          ))}
        </div>
      )}
    </div>
  );
}
