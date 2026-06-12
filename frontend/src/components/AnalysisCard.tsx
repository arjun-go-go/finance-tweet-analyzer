"use client";

import { useState } from "react";
import { formatDateTime } from "@/lib/datetime";

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

interface AnalysisCardProps {
  authorHandle: string;
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
  createdAt: string;
  twitterTweetId?: string;
}

const SENTIMENT_CONFIG: Record<string, { label: string; color: string; badge: string }> = {
  bullish: { label: "看好", color: "border-green-400 bg-green-50", badge: "bg-green-200 text-green-900" },
  bearish: { label: "看空", color: "border-red-400 bg-red-50", badge: "bg-red-200 text-red-900" },
  neutral: { label: "中性", color: "border-gray-300 bg-gray-50", badge: "bg-gray-200 text-gray-900" },
  mixed: { label: "分化", color: "border-yellow-400 bg-yellow-50", badge: "bg-yellow-200 text-yellow-900" },
};

const HORIZON_LABEL: Record<string, string> = {
  short: "短期",
  medium: "中期",
  long: "长期",
  unknown: "",
};

const RISK_LEVEL_CONFIG: Record<string, { label: string; color: string }> = {
  critical: { label: "紧急", color: "bg-red-600 text-white" },
  high: { label: "高", color: "bg-red-200 text-red-800" },
  medium: { label: "中", color: "bg-orange-200 text-orange-800" },
  low: { label: "低", color: "bg-gray-200 text-gray-700" },
};

const RISK_CATEGORY_LABEL: Record<string, string> = {
  market: "市场",
  liquidity: "流动性",
  regulatory: "监管",
  technical: "技术",
  event: "事件",
  credit: "信用",
};

export default function AnalysisCard({
  authorHandle,
  content,
  analysis,
  createdAt,
  twitterTweetId,
}: AnalysisCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [showReasoning, setShowReasoning] = useState(false);

  if (!analysis.is_investment_related) {
    return (
      <div className="border-l-4 border-gray-200 bg-gray-50 rounded-lg shadow p-4 opacity-60">
        <div className="flex justify-between items-start mb-2">
          <span className="text-xs text-gray-400">非投资内容</span>
          <span className="text-xs text-gray-400">{authorHandle}</span>
        </div>
        <p className={`text-sm text-gray-500 whitespace-pre-wrap ${expanded ? "" : "line-clamp-3"}`}>{content}</p>
        {content.length > 150 && (
          <button onClick={() => setExpanded(!expanded)} className="text-xs text-blue-500 hover:underline mt-1">
            {expanded ? "收起" : "展开全部"}
          </button>
        )}
      </div>
    );
  }

  const overallSentiment = SENTIMENT_CONFIG[analysis.overall_sentiment] || SENTIMENT_CONFIG.neutral;

  return (
    <div className={`border-l-4 rounded-lg shadow p-4 ${overallSentiment.color}`}>
      {/* Header: overall sentiment + confidence + risk level */}
      <div className="flex justify-between items-start mb-3">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`px-2 py-0.5 rounded text-xs font-semibold ${overallSentiment.badge}`}>
            {overallSentiment.label}
          </span>
          {analysis.risk_level && analysis.risk_level !== "low" && (
            <span className={`px-2 py-0.5 rounded text-xs font-semibold ${RISK_LEVEL_CONFIG[analysis.risk_level]?.color || ""}`}>
              风险: {RISK_LEVEL_CONFIG[analysis.risk_level]?.label || analysis.risk_level}
            </span>
          )}
        </div>
        <span className="text-sm text-gray-500">
          置信度 {(analysis.confidence * 100).toFixed(0)}%
        </span>
      </div>

      {/* Tweet content */}
      <p className={`text-sm text-gray-700 mb-3 whitespace-pre-wrap ${expanded ? "" : "line-clamp-3"}`}>{content}</p>
      {content.length > 150 && (
        <button onClick={() => setExpanded(!expanded)} className="text-xs text-blue-500 hover:underline mb-3">
          {expanded ? "收起" : "展开全部"}
        </button>
      )}

      {/* Per-ticker detail cards */}
      {analysis.tickers.length > 0 && (
        <div className="space-y-2 mb-3">
          <p className="text-xs font-semibold text-gray-600">标的分析:</p>
          {analysis.tickers.map((ticker) => {
            const tickerSentiment = SENTIMENT_CONFIG[ticker.sentiment] || SENTIMENT_CONFIG.neutral;
            const riskLevel = ticker.ticker_risk_level || "low";
            return (
              <div key={ticker.symbol} className="bg-white/70 border rounded-md p-2.5">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="bg-blue-100 text-blue-800 px-2 py-0.5 rounded text-xs font-bold">
                    {ticker.symbol}
                  </span>
                  {ticker.original_name && ticker.original_name !== ticker.symbol && (
                    <span className="text-xs text-gray-400">({ticker.original_name})</span>
                  )}
                  <span className={`px-1.5 py-0.5 rounded text-xs ${tickerSentiment.badge}`}>
                    {tickerSentiment.label}
                  </span>
                  {HORIZON_LABEL[ticker.horizon] && (
                    <span className="text-xs text-gray-500">{HORIZON_LABEL[ticker.horizon]}</span>
                  )}
                  {riskLevel !== "low" && (
                    <span className={`px-1.5 py-0.5 rounded text-xs ${RISK_LEVEL_CONFIG[riskLevel]?.color || ""}`}>
                      {RISK_LEVEL_CONFIG[riskLevel]?.label || riskLevel}
                    </span>
                  )}
                </div>
                {/* Per-ticker risks */}
                {ticker.risks && ticker.risks.length > 0 && (
                  <div className="mt-1.5 pl-2 border-l-2 border-orange-200">
                    {ticker.risks.map((risk, idx) => (
                      <div key={idx} className="text-xs text-orange-700 flex items-start gap-1">
                        <span className="text-orange-400 shrink-0">[{RISK_CATEGORY_LABEL[risk.category] || risk.category}]</span>
                        <span>{risk.description}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Key points */}
      {analysis.key_points.length > 0 && (
        <div className="mb-2">
          <p className="text-xs font-semibold text-gray-600 mb-1">关键观点:</p>
          <ul className="text-xs text-gray-600 space-y-0.5">
            {analysis.key_points.map((point, i) => (
              <li key={i}>• {point}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Risk summary (tweet-level) */}
      {analysis.risk_summary && (
        <div className="mb-2">
          <p className="text-xs font-semibold text-orange-600">风险概述: <span className="font-normal">{analysis.risk_summary}</span></p>
        </div>
      )}

      {/* Reasoning toggle */}
      {analysis.reasoning && (
        <div className="mb-2">
          <button
            onClick={() => setShowReasoning(!showReasoning)}
            className="text-xs text-purple-500 hover:underline"
          >
            {showReasoning ? "隐藏分析逻辑" : "查看分析逻辑"}
          </button>
          {showReasoning && (
            <p className="mt-1 text-xs text-purple-700 bg-purple-50 rounded p-2 whitespace-pre-wrap">
              {analysis.reasoning}
            </p>
          )}
        </div>
      )}

      {/* Footer */}
      <div className="flex justify-between items-center mt-2 pt-2 border-t">
        <span className="text-xs text-gray-500">{authorHandle}</span>
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
          <span className="text-xs text-gray-400">
            {formatDateTime(createdAt)}
          </span>
        </div>
      </div>
    </div>
  );
}
