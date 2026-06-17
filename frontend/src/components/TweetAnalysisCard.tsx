"use client";

import { useState } from "react";
import { formatDateTime } from "@/lib/datetime";
import AnalysisInline from "./AnalysisInline";

interface TweetMetrics {
  likes?: number;
  retweets?: number;
  views?: number;
}

interface AnalysisData {
  tickers: Array<{
    symbol: string;
    original_name: string;
    sentiment: string;
    horizon: string;
    risks?: Array<{
      category: string;
      description: string;
      severity: string;
      urgency: string;
    }>;
    ticker_risk_level?: string;
  }>;
  overall_sentiment: string;
  key_points: string[];
  risk_factors: string[];
  risk_level?: string;
  risk_summary?: string;
  confidence: number;
  is_investment_related: boolean;
  reasoning?: string;
}

interface TweetAnalysisCardProps {
  id: string;
  tweetId: string;
  authorHandle: string;
  authorName?: string;
  content: string;
  publishedAt: string;
  status: string;
  metrics?: TweetMetrics | null;
  analysis?: AnalysisData | null;
  twitterTweetId?: string;
  onTriggerAnalysis?: (tweetId: string, handle: string) => void;
}

const STATUS_CONFIG: Record<string, { label: string; color: string }> = {
  analyzed: { label: "已分析", color: "bg-green-100 text-green-700" },
  pending: { label: "待分析", color: "bg-yellow-100 text-yellow-700" },
};

const SENTIMENT_BADGE: Record<string, string> = {
  bullish: "bg-green-200 text-green-900",
  bearish: "bg-red-200 text-red-900",
  neutral: "bg-gray-200 text-gray-900",
  mixed: "bg-yellow-200 text-yellow-900",
};

const SENTIMENT_LABEL: Record<string, string> = {
  bullish: "看好",
  bearish: "看空",
  neutral: "中性",
  mixed: "分化",
};

export default function TweetAnalysisCard({
  id,
  authorHandle,
  authorName,
  content,
  publishedAt,
  status,
  metrics,
  analysis,
  twitterTweetId,
  onTriggerAnalysis,
}: TweetAnalysisCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [analysisExpanded, setAnalysisExpanded] = useState(false);

  const statusCfg = STATUS_CONFIG[status] || STATUS_CONFIG.pending;
  const isAnalyzed = status === "analyzed";

  // Extract quick summary from analysis for card header
  const quickSummary = analysis?.is_investment_related
    ? {
        sentiment: analysis.overall_sentiment,
        tickers: analysis.tickers.slice(0, 3).map((t) => t.symbol),
        horizon: analysis.tickers[0]?.horizon,
      }
    : null;

  return (
    <div className="bg-white rounded-lg shadow p-4 space-y-2">
      {/* Header row */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-medium text-blue-600">{authorHandle}</span>
          {authorName && (
            <span className="text-sm text-gray-500">({authorName})</span>
          )}
          <span className={`text-xs px-2 py-0.5 rounded ${statusCfg.color}`}>
            {statusCfg.label}
          </span>
          {isAnalyzed && quickSummary && (
            <>
              <span className={`text-xs px-2 py-0.5 rounded font-semibold ${SENTIMENT_BADGE[quickSummary.sentiment] || SENTIMENT_BADGE.neutral}`}>
                {SENTIMENT_LABEL[quickSummary.sentiment] || quickSummary.sentiment}
              </span>
              {quickSummary.tickers.length > 0 && (
                <span className="text-xs text-gray-500">
                  {quickSummary.tickers.join(", ")}
                </span>
              )}
            </>
          )}
        </div>
      </div>

      {/* Tweet content */}
      <p className={`text-gray-800 whitespace-pre-wrap ${expanded ? "" : "line-clamp-3"}`}>
        {content}
      </p>
      {content.length > 200 && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-xs text-blue-500 hover:underline"
        >
          {expanded ? "收起" : "展开全部"}
        </button>
      )}

      {/* Inline analysis (expandable) */}
      {isAnalyzed && analysis && (
        <div>
          <button
            onClick={() => setAnalysisExpanded(!analysisExpanded)}
            className="text-xs text-blue-600 hover:underline flex items-center gap-1"
          >
            <span>{analysisExpanded ? "▲" : "▼"}</span>
            {analysisExpanded ? "收起分析详情" : "展开分析详情"}
          </button>
          {analysisExpanded && <AnalysisInline analysis={analysis} />}
        </div>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between flex-wrap gap-2 pt-2 border-t border-gray-100">
        <div className="flex items-center gap-3 text-xs text-gray-500">
          <span>{formatDateTime(publishedAt)}</span>
          {metrics && (
            <>
              {metrics.likes != null && <span>赞 {metrics.likes}</span>}
              {metrics.retweets != null && <span>转发 {metrics.retweets}</span>}
              {metrics.views != null && <span>浏览 {metrics.views}</span>}
            </>
          )}
        </div>
        <div className="flex items-center gap-3">
          {twitterTweetId && (
            <a
              href={`https://x.com/${authorHandle.replace("@", "")}/status/${twitterTweetId}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-blue-500 hover:underline"
            >
              查看原文
            </a>
          )}
          {!isAnalyzed && onTriggerAnalysis && (
            <button
              onClick={() => onTriggerAnalysis(id, authorHandle)}
              className="text-xs text-blue-600 hover:text-blue-800 font-medium"
            >
              触发分析
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
