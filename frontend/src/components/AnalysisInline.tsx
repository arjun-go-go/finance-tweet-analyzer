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
  market?: string;
  exchange?: string;
  asset_type?: string;
  listing_status?: string;
  tradable?: boolean;
  validation_status?: string;
  validation_sources?: string[];
  external_ids?: Record<string, string>;
  validated_at?: string;
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
  media_summary?: string;
  media_evidence?: string[];
  text_image_consistency?: string;
  media_confidence?: number;
}

const MEDIA_CONSISTENCY_LABEL: Record<string, string> = {
  consistent: "图文一致",
  complementary: "图片补充正文",
  conflict: "图文存在冲突",
  image_only: "关键信息仅在图片中",
  unclear: "图文关系不明确",
};

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

const MARKET_LABEL: Record<string, string> = {
  CN: "A股",
  HK: "港股",
  US: "美股",
  CRYPTO: "加密市场",
  COMMODITY: "原油 / 黄金",
  GLOBAL: "全球市场",
  UNKNOWN: "市场待确认",
};

const ASSET_TYPE_LABEL: Record<string, string> = {
  equity: "股票",
  crypto: "加密资产",
  crypto_asset: "加密资产",
  crypto_pair: "交易对",
  index: "指数",
  commodity: "商品",
  forex: "外汇",
  unknown: "类型待确认",
};

const VALIDATION_SOURCE_LABEL: Record<string, string> = {
  akshare: "AKShare",
  sec_edgar: "SEC EDGAR",
  openfigi: "OpenFIGI",
  binance: "Binance",
  eia_pet_rwtc_d: "EIA WTI",
  binance_paxg_proxy: "Binance PAXG 黄金代理",
};

interface AnalysisInlineProps {
  analysis: AnalysisData;
}

export default function AnalysisInline({ analysis }: AnalysisInlineProps) {
  const [showReasoning, setShowReasoning] = useState(false);
  const [showCandidates, setShowCandidates] = useState(false);
  const [expandedValidation, setExpandedValidation] = useState<string | null>(null);

  if (!analysis.is_investment_related) {
    return (
      <div className="text-xs text-gray-400 mt-2 pl-2 border-l-2 border-gray-200">
        非投资内容
      </div>
    );
  }

  const overallSentiment = SENTIMENT_CONFIG[analysis.overall_sentiment] || SENTIMENT_CONFIG.neutral;
  const verifiedTickers = analysis.tickers.filter(
    (ticker) => ticker.validation_status === "verified" && ticker.tradable === true,
  );
  const unverifiedTickers = analysis.tickers.filter(
    (ticker) => ticker.validation_status !== "verified" || ticker.tradable !== true,
  );

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
        <span className="text-xs text-gray-500" title="模型对推文观点和情绪判断的把握，不代表标的核验状态">
          分析置信度 {(analysis.confidence * 100).toFixed(0)}%
        </span>
      </div>

      {/* Verified instruments */}
      {verifiedTickers.length > 0 ? (
        <div className="space-y-1.5">
          <div className="flex items-center justify-between gap-3">
            <p className="text-xs font-semibold text-gray-700">已核验标的</p>
            <span className="text-[11px] text-emerald-700">仅这些标的参与预测与排行</span>
          </div>
          {verifiedTickers.map((ticker, index) => {
            const tickerSentiment = SENTIMENT_CONFIG[ticker.sentiment] || SENTIMENT_CONFIG.neutral;
            const riskLevel = ticker.ticker_risk_level || "low";
            const validationKey = `${ticker.symbol}-${index}`;
            const sources = (ticker.validation_sources || []).map(
              (source) => VALIDATION_SOURCE_LABEL[source] || source,
            );
            return (
              <div key={validationKey} className="rounded-md border border-emerald-200 bg-white p-2.5">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="rounded bg-slate-900 px-2 py-0.5 font-mono text-xs font-bold text-white">
                        {ticker.symbol}
                      </span>
                      <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-[11px] font-semibold text-emerald-700">
                        ✓ 已核验
                      </span>
                      <span className="text-[11px] text-gray-500">
                        {[MARKET_LABEL[ticker.market || ""] || ticker.market, ASSET_TYPE_LABEL[ticker.asset_type || ""] || ticker.asset_type].filter(Boolean).join(" · ")}
                      </span>
                    </div>
                    {ticker.original_name && ticker.original_name !== ticker.symbol && (
                      <p className="mt-1 text-xs text-gray-500">原文称呼 / 名称：{ticker.original_name}</p>
                    )}
                  </div>
                  {sources.length > 0 && (
                    <button
                      type="button"
                      className="shrink-0 text-[11px] font-medium text-cyan-700 hover:underline"
                      onClick={() => setExpandedValidation(expandedValidation === validationKey ? null : validationKey)}
                    >
                      {expandedValidation === validationKey ? "收起核验信息" : "查看核验信息"}
                    </button>
                  )}
                </div>
                <div className="mt-2 flex items-center gap-2 flex-wrap border-t border-slate-100 pt-2">
                  <span className={`px-1.5 py-0.5 rounded text-xs ${tickerSentiment.badge}`}>
                    观点：{tickerSentiment.label}
                  </span>
                  {HORIZON_LABEL[ticker.horizon] && (
                    <span className="text-xs text-gray-500">周期：{HORIZON_LABEL[ticker.horizon]}</span>
                  )}
                  {riskLevel !== "low" && (
                    <span className={`px-1.5 py-0.5 rounded text-xs ${RISK_LEVEL_CONFIG[riskLevel]?.color || ""}`}>
                      风险：{RISK_LEVEL_CONFIG[riskLevel]?.label || riskLevel}
                    </span>
                  )}
                </div>
                {expandedValidation === validationKey && (
                  <div className="mt-2 rounded bg-slate-50 p-2 text-[11px] leading-5 text-slate-600">
                    <p>核验来源：{sources.join("、")}</p>
                    {ticker.exchange && <p>交易场所：{ticker.exchange}</p>}
                    {ticker.validated_at && <p>核验时间：{new Date(ticker.validated_at).toLocaleString("zh-CN")}</p>}
                    {ticker.external_ids && Object.keys(ticker.external_ids).length > 0 && (
                      <p>外部标识：{Object.entries(ticker.external_ids).map(([key, value]) => `${key.toUpperCase()} ${value}`).join(" · ")}</p>
                    )}
                  </div>
                )}
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
      ) : (
        <div className="rounded-md border border-slate-200 bg-slate-50 p-2.5 text-xs text-slate-600">
          暂未识别到可用于预测和排行的已核验标的。
        </div>
      )}

      {/* Unverified candidates stay visible for audit but never look actionable. */}
      {unverifiedTickers.length > 0 && (
        <div className="rounded-md border border-amber-200 bg-amber-50/60">
          <button
            type="button"
            onClick={() => setShowCandidates(!showCandidates)}
            className="flex w-full items-center justify-between gap-3 p-2.5 text-left"
          >
            <span>
              <strong className="block text-xs text-amber-900">待核验候选（{unverifiedTickers.length}）</strong>
              <small className="text-[11px] text-amber-700">不会参与预测、标的排行或 Watchlist 匹配</small>
            </span>
            <span className="text-xs text-amber-700">{showCandidates ? "收起" : "展开"}</span>
          </button>
          {showCandidates && (
            <div className="space-y-1.5 border-t border-amber-200 p-2.5">
              {unverifiedTickers.map((ticker, index) => (
                <div key={`${ticker.symbol}-${index}`} className="rounded border border-amber-100 bg-white/80 p-2">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-bold text-slate-700">{ticker.symbol}</span>
                    <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[11px] text-amber-800">暂未核验</span>
                    <span className="text-[11px] text-slate-500">
                      {ASSET_TYPE_LABEL[ticker.asset_type || ""] || ticker.asset_type || "类型待确认"}
                    </span>
                  </div>
                  <p className="mt-1 text-[11px] leading-4 text-slate-500">
                    系统从原文中识别到该候选，但当前公开数据源未能确认其标准身份或交易状态。
                  </p>
                </div>
              ))}
            </div>
          )}
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

      {(analysis.media_summary || (analysis.media_evidence?.length ?? 0) > 0) && (
        <div className="rounded-md border border-cyan-200 bg-cyan-50/70 p-2.5">
          <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs font-semibold text-cyan-800">图片证据</p>
            <div className="flex items-center gap-2 text-[11px] text-cyan-700">
              {analysis.text_image_consistency && (
                <span>{MEDIA_CONSISTENCY_LABEL[analysis.text_image_consistency] || analysis.text_image_consistency}</span>
              )}
              {analysis.media_confidence != null && (
                <span>识别置信度 {(analysis.media_confidence * 100).toFixed(0)}%</span>
              )}
            </div>
          </div>
          {analysis.media_summary && (
            <p className="text-xs leading-5 text-slate-700">{analysis.media_summary}</p>
          )}
          {(analysis.media_evidence?.length ?? 0) > 0 && (
            <ul className="mt-1.5 space-y-1 text-xs text-slate-600">
              {analysis.media_evidence!.map((evidence, index) => (
                <li key={`${evidence}-${index}`} className="flex gap-1.5">
                  <span className="text-cyan-600">•</span>
                  <span>{evidence}</span>
                </li>
              ))}
            </ul>
          )}
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
