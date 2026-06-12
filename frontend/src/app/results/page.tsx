"use client";

import { useEffect, useState } from "react";
import { fetchAnalyses } from "@/lib/api";
import { formatDateTime } from "@/lib/datetime";

interface AnalysisItem {
  id: string;
  tweet_id: string;
  twitter_tweet_id: string;
  author_handle: string;
  content: string;
  analysis: {
    tickers?: string[];
    sentiment?: string;
    investment_horizon?: string;
    key_points?: string[];
    confidence?: number;
    is_investment_related?: boolean;
  };
  confidence: number;
  published_at: string;
}

const PAGE_SIZE = 20;

const SENTIMENT_MAP: Record<string, { label: string; color: string }> = {
  bullish: { label: "看好", color: "text-green-600 bg-green-50" },
  bearish: { label: "看空", color: "text-red-600 bg-red-50" },
  neutral: { label: "中性", color: "text-gray-600 bg-gray-100" },
  mixed: { label: "混合", color: "text-orange-600 bg-orange-50" },
};

export default function ResultsPage() {
  const [items, setItems] = useState<AnalysisItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [sentiment, setSentiment] = useState("");
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const totalPages = Math.ceil(total / PAGE_SIZE);

  const loadData = async (s: string, p: number) => {
    setLoading(true);
    try {
      const params: any = { limit: PAGE_SIZE, offset: p * PAGE_SIZE };
      if (s) params.sentiment = s;
      const res = await fetchAnalyses(params);
      setItems(res.items);
      setTotal(res.total);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData(sentiment, page);
  }, [sentiment, page]);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">分析结果</h1>

      <div className="flex gap-2">
        {[
          { label: "全部", value: "" },
          { label: "看好", value: "bullish" },
          { label: "看空", value: "bearish" },
          { label: "中性", value: "neutral" },
        ].map((tab) => (
          <button
            key={tab.value}
            onClick={() => {
              setSentiment(tab.value);
              setPage(0);
            }}
            className={`px-4 py-2 rounded-lg text-sm font-medium ${
              sentiment === tab.value
                ? "bg-blue-600 text-white"
                : "bg-gray-100 text-gray-700 hover:bg-gray-200"
            }`}
          >
            {tab.label}
          </button>
        ))}
        <span className="ml-auto text-sm text-gray-500 self-center">
          共 {total} 条
        </span>
      </div>

      {loading ? (
        <p className="text-center py-10 text-gray-500">加载中...</p>
      ) : items.length === 0 ? (
        <p className="text-center py-10 text-gray-500">暂无分析结果</p>
      ) : (
        <div className="space-y-3">
          {items.map((item) => {
            const s = SENTIMENT_MAP[item.analysis.overall_sentiment || item.analysis.sentiment || "neutral"] || SENTIMENT_MAP.neutral;
            return (
              <div
                key={item.id}
                className="bg-white rounded-lg shadow p-4 space-y-2"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-blue-600">
                      {item.author_handle}
                    </span>
                    <span className={`text-xs px-2 py-0.5 rounded ${s.color}`}>
                      {s.label}
                    </span>
                    {item.analysis.tickers && item.analysis.tickers.length > 0 && (
                      <div className="flex gap-1">
                        {item.analysis.tickers.map((t, idx) => (
                          <span
                            key={typeof t === "string" ? t : t.symbol || idx}
                            className="text-xs px-1.5 py-0.5 rounded bg-blue-50 text-blue-700"
                          >
                            {typeof t === "string" ? t : t.symbol}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <span className="text-xs text-gray-400">
                    置信度 {(item.confidence * 100).toFixed(0)}%
                  </span>
                </div>

                <p
                  className={`text-gray-800 text-sm whitespace-pre-wrap ${
                    expanded.has(item.id) ? "" : "line-clamp-3"
                  }`}
                >
                  {item.content}
                </p>
                {item.content.length > 150 && (
                  <button
                    onClick={() =>
                      setExpanded((prev) => {
                        const next = new Set(prev);
                        if (next.has(item.id)) next.delete(item.id);
                        else next.add(item.id);
                        return next;
                      })
                    }
                    className="text-xs text-blue-500 hover:underline"
                  >
                    {expanded.has(item.id) ? "收起" : "展开全部"}
                  </button>
                )}

                {item.analysis.key_points && item.analysis.key_points.length > 0 && (
                  <div className="text-xs text-gray-600 space-y-0.5">
                    {item.analysis.key_points.map((pt, i) => (
                      <p key={i}>- {pt}</p>
                    ))}
                  </div>
                )}

                <div className="flex items-center gap-4 text-xs text-gray-500">
                  <span>{formatDateTime(item.published_at)}</span>
                  {item.analysis.investment_horizon && (
                    <span>
                      周期: {item.analysis.investment_horizon === "short" ? "短期" : item.analysis.investment_horizon === "medium" ? "中期" : item.analysis.investment_horizon === "long" ? "长期" : "未知"}
                    </span>
                  )}
                  <a
                    href={`https://x.com/${item.author_handle.replace("@", "")}/status/${item.twitter_tweet_id}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-500 hover:underline ml-auto"
                  >
                    查看原文
                  </a>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 py-4">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            className="px-3 py-1 rounded border disabled:opacity-30"
          >
            上一页
          </button>
          <span className="text-sm text-gray-600">
            {page + 1} / {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            disabled={page >= totalPages - 1}
            className="px-3 py-1 rounded border disabled:opacity-30"
          >
            下一页
          </button>
        </div>
      )}
    </div>
  );
}
