"use client";

import { useState } from "react";

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

interface AnalysisData {
  tickers: TickerDetail[];
  overall_sentiment: string;
  key_points: string[];
  risk_factors: string[];
  risk_level?: string;
  risk_summary?: string;
  confidence: number;
  is_investment_related: boolean;
  reasoning?: string;
}

const SENTIMENT_CONFIG: Record<string, { label: string; badge: string }> = {
  bullish: { label: "看好", badge: "bg-green-200 text-green-900" },
  bearish: { label: "看空", badge: "bg-red-200 text-red-900" },
  neutral: { label: "中性", badge: "bg-gray-200 text-gray-900" },
  mixed: { label: "分化", badge: "bg-yellow-200 text-yellow-900" },
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

interface AnalysisInlineProps {
  analysis: AnalysisData;
}

export default function AnalysisInline({ analysis }: AnalysisInlineProps) {
  const [showReasoning, setShowReasoning] = useState(false);

  if (!analysis.is_investment_related) {
    return (
      <div className="text-xs text-gray-400 mt-2 pl-2 border-l-2 border-gray-200">
        非投资内容
      </div>
    );
  }

  const overallSentiment = SENTIMENT_CONFIG[analysis.overall_sentiment] || SENTIMENT_CONFIG.neutral;

  return (
    <div className="mt-3 bg-white/60 rounded-lg p-3 space-y-2">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
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
        <span className="text-xs text-gray-500">
          置信度 {(analysis.confidence * 100).toFixed(0)}%
        </span>
      </div>

      {/* Per-ticker cards */}
      {analysis.tickers.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-xs font-semibold text-gray-600">标的分析:</p>
          {analysis.tickers.map((ticker) => {
            const tickerSentiment = SENTIMENT_CONFIG[ticker.sentiment] || SENTIMENT_CONFIG.neutral;
            const riskLevel = ticker.ticker_risk_level || "low";
            return (
              <div key={ticker.symbol} className="bg-white border rounded-md p-2">
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
                {ticker.risks && ticker.risks.length > 0 && (
                  <div className="mt-1 pl-2 border-l-2 border-orange-200">
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
        <div>
          <p className="text-xs font-semibold text-gray-600 mb-1">关键观点:</p>
          <ul className="text-xs text-gray-600 space-y-0.5">
            {analysis.key_points.map((point, i) => (
              <li key={i}>• {point}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Risk summary */}
      {analysis.risk_summary && (
        <div>
          <p className="text-xs font-semibold text-orange-600">风险概述: <span className="font-normal">{analysis.risk_summary}</span></p>
        </div>
      )}

      {/* Reasoning */}
      {analysis.reasoning && (
        <div>
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
    </div>
  );
}
