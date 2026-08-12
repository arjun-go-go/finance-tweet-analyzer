"use client";

import { useState } from "react";
import {
  correctPredictionInstrument,
  excludePrediction,
  validatePredictionInstrument,
  verifyPrediction,
} from "@/lib/api";
import type { InstrumentCorrection } from "@/lib/api";
import type { MarketVerificationEvidence } from "@/lib/api";
import { formatDate, formatDateTime } from "@/lib/datetime";

export interface PredictionItem {
  id: string;
  blogger_handle?: string | null;
  ticker: string;
  sentiment: string;
  investment_horizon: string;
  published_at: string | null;
  verifiable_at: string | null;
  verdict: string | null;
  score: number | null;
  verified_at: string | null;
  verified_by: string | null;
  note: string | null;
  instrument_snapshot?: Record<string, unknown> | null;
  market_verification?: MarketVerificationEvidence | null;
  tweet: {
    id: string;
    content: string;
    published_at: string | null;
  };
}

const SENTIMENT_LABEL: Record<string, string> = {
  bullish: "看好",
  bearish: "看空",
  neutral: "中性",
};

const HORIZON_LABEL: Record<string, string> = {
  short: "短期",
  medium: "中期",
  long: "长期",
  unknown: "",
};

const VERDICT_LABEL: Record<string, string> = {
  correct: "看对了",
  partial: "部分对",
  incorrect: "看错了",
  excluded: "已排除",
};

const MARKET_LABEL: Record<string, string> = {
  CN: "A 股",
  HK: "港股",
  US: "美股",
  COMMODITY: "原油 / 黄金",
  CRYPTO: "加密货币",
};

function sentimentBorder(sentiment: string) {
  return sentiment === "bullish"
    ? "border-green-400 bg-green-50"
    : sentiment === "bearish"
    ? "border-red-400 bg-red-50"
    : "border-gray-300 bg-gray-50";
}

function daysUntil(iso: string | null): number {
  if (!iso) return 0;
  const t = new Date(iso).getTime();
  return Math.max(0, Math.ceil((t - Date.now()) / (1000 * 60 * 60 * 24)));
}

export default function PredictionCard({
  prediction,
  onChanged,
  reviewMode = false,
}: {
  prediction: PredictionItem;
  onChanged?: (next: PredictionItem) => void;
  reviewMode?: boolean;
}) {
  const now = Date.now();
  const verifiableMs = prediction.verifiable_at
    ? new Date(prediction.verifiable_at).getTime()
    : 0;
  const isLocked = prediction.verdict === null && verifiableMs > now;
  const isVerifiable = prediction.verdict === null && !isLocked;
  const isVerified = prediction.verdict !== null;

  const [editing, setEditing] = useState(false);
  const [note, setNote] = useState(prediction.note ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [correcting, setCorrecting] = useState(false);
  const defaultCorrection: InstrumentCorrection = prediction.ticker === "CL"
    ? {
        symbol: "WTI",
        name: "WTI 原油",
        asset_type: "commodity",
        market: "COMMODITY",
        reason: "原文讨论 WTI 原油，原标的被误映射为同名美股 CL",
      }
    : ["XAU", "XAUUSD", "GOLD"].includes(prediction.ticker)
      ? {
          symbol: "XAU",
          name: "黄金",
          asset_type: "commodity",
          market: "COMMODITY",
          reason: "黄金统一映射为 XAU，使用 PAXGUSDT 作为行情代理",
        }
      : {
        symbol: prediction.ticker,
        name: "",
        asset_type: "equity",
        market: "US",
        reason: prediction.market_verification?.reason || "修正原预测的标的映射",
      };
  const [correction, setCorrection] = useState<InstrumentCorrection>(defaultCorrection);
  const [instrumentValidation, setInstrumentValidation] = useState<{
    accepted: boolean;
    reason: string;
  } | null>(null);

  const updateCorrection = (next: InstrumentCorrection) => {
    setCorrection(next);
    setInstrumentValidation(null);
  };

  const validateInstrument = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const result = await validatePredictionInstrument({
        symbol: correction.symbol,
        name: correction.name,
        asset_type: correction.asset_type,
        market: correction.market,
      });
      setInstrumentValidation({ accepted: result.accepted, reason: result.reason });
    } catch (reason) {
      setInstrumentValidation(null);
      setError(reason instanceof Error ? reason.message : "标的校验失败");
    } finally {
      setSubmitting(false);
    }
  };

  const exclude = async () => {
    const reason = note.trim() || prediction.market_verification?.reason || "标的或观点无法形成有效行情验证";
    if (!window.confirm("确认排除这条预测？该操作会保留审计记录，但不计入命中率。")) return;
    setSubmitting(true);
    setError(null);
    try {
      const updated = await excludePrediction(prediction.id, reason);
      onChanged?.(updated);
    } catch {
      setError("排除失败");
    } finally {
      setSubmitting(false);
    }
  };

  const correctInstrument = async () => {
    if (!instrumentValidation?.accepted) {
      setError("请先完成标的校验");
      return;
    }
    if (!window.confirm(`确认将 ${prediction.ticker} 修正为 ${correction.symbol}？分析结果和检索索引会同步更新。`)) return;
    setSubmitting(true);
    setError(null);
    try {
      const updated = await correctPredictionInstrument(prediction.id, correction);
      onChanged?.(updated);
      setCorrecting(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "修正标的失败");
    } finally {
      setSubmitting(false);
    }
  };

  const submit = async (verdict: "correct" | "partial" | "incorrect") => {
    setSubmitting(true);
    setError(null);
    try {
      const updated = await verifyPrediction(prediction.id, {
        verdict,
        note: note || undefined,
      });
      onChanged?.(updated);
      setEditing(false);
    } catch (e: any) {
      if (e?.status === 400 && e?.payload?.detail?.error === "not_yet_verifiable") {
        setError(
          `还未到验证时间：${e.payload.detail.verifiable_at ?? ""}`,
        );
      } else {
        setError("提交失败");
      }
    } finally {
      setSubmitting(false);
    }
  };

  const showVerifyForm = isVerifiable || (isVerified && prediction.verdict !== "excluded" && editing);
  const containerClass = isLocked
    ? "border-gray-300 bg-gray-50 opacity-80"
    : sentimentBorder(prediction.sentiment);

  return (
    <div className={`border-l-4 rounded-lg shadow p-4 ${containerClass}`}>
      <div className="flex justify-between items-start mb-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="bg-blue-100 text-blue-800 px-2 py-0.5 rounded text-xs font-bold">
            {prediction.ticker}
          </span>
          <span
            className={`px-2 py-0.5 rounded text-xs font-semibold ${
              prediction.sentiment === "bullish"
                ? "bg-green-200 text-green-900"
                : prediction.sentiment === "bearish"
                ? "bg-red-200 text-red-900"
                : "bg-gray-200 text-gray-900"
            }`}
          >
            {SENTIMENT_LABEL[prediction.sentiment] ?? prediction.sentiment}
          </span>
          {HORIZON_LABEL[prediction.investment_horizon] && (
            <span className="text-xs text-gray-500">
              {HORIZON_LABEL[prediction.investment_horizon]}
            </span>
          )}
          {prediction.published_at && (
            <span className="text-xs text-gray-400">
              发布 {formatDate(prediction.published_at)}
            </span>
          )}
        </div>
        {isLocked && (
          <span
            className="text-xs text-gray-500"
            title={`可在 ${prediction.verifiable_at} 后验证`}
          >
            🔒 还剩 {daysUntil(prediction.verifiable_at)} 天可验证
          </span>
        )}
        {isVerified && !editing && (
          <div className="flex items-center gap-2">
            <span
              className={`px-2 py-0.5 rounded text-xs font-semibold ${
                prediction.verdict === "correct"
                  ? "bg-green-200 text-green-900"
                  : prediction.verdict === "partial"
                  ? "bg-yellow-200 text-yellow-900"
                  : prediction.verdict === "excluded"
                  ? "bg-gray-200 text-gray-700"
                  : "bg-red-200 text-red-900"
              }`}
            >
              {VERDICT_LABEL[prediction.verdict ?? ""] ?? prediction.verdict}
            </span>
            {prediction.verdict !== "excluded" && (
              <button
                onClick={() => setEditing(true)}
                className="text-xs text-blue-600 hover:underline"
              >
                重新标注
              </button>
            )}
          </div>
        )}
      </div>

      <p className="text-sm text-gray-700 mb-2 line-clamp-3">
        {prediction.tweet.content}
      </p>

      {prediction.market_verification && (
        <MarketEvidence
          evidence={prediction.market_verification}
          predictionTicker={prediction.ticker}
          manuallyResolved={isVerified && prediction.verified_by === "manual"}
        />
      )}

      {reviewMode && prediction.verdict === null && (
        <div className="prediction-review-actions">
          <textarea
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="复核说明（默认使用系统识别原因）"
            rows={2}
          />
          <div className="prediction-review-buttons">
            {prediction.sentiment !== "neutral" && (
              <button className="is-correct" disabled={submitting} onClick={() => setCorrecting((value) => !value)}>
                修正标的
              </button>
            )}
            <button disabled={submitting} onClick={() => void exclude()}>
            排除无效预测
            </button>
          </div>
          <span>排除后保留审计记录，但不计入博主命中率。</span>
          {error && <p>{error}</p>}
        </div>
      )}

      {reviewMode && correcting && prediction.verdict === null && (
        <div className="instrument-correction-form">
          <header><strong>修正标的</strong><span>原标的 {prediction.ticker}</span></header>
          <label>标准代码<input value={correction.symbol} onChange={(event) => updateCorrection({ ...correction, symbol: event.target.value.toUpperCase() })} /></label>
          <label>资产名称<input value={correction.name} onChange={(event) => updateCorrection({ ...correction, name: event.target.value })} placeholder="例如 WTI 原油" /></label>
          <label>资产类型<select value={correction.asset_type} onChange={(event) => updateCorrection({ ...correction, asset_type: event.target.value as InstrumentCorrection["asset_type"] })}><option value="equity">股票</option><option value="commodity">原油 / 黄金</option><option value="crypto">加密货币</option></select></label>
          <label>市场<select value={correction.market} onChange={(event) => updateCorrection({ ...correction, market: event.target.value as InstrumentCorrection["market"] })}><option value="CN">A 股</option><option value="HK">港股</option><option value="US">美股</option><option value="COMMODITY">原油 / 黄金</option><option value="CRYPTO">加密市场</option></select></label>
          <label className="is-wide">修正原因<textarea rows={2} value={correction.reason} onChange={(event) => setCorrection({ ...correction, reason: event.target.value })} /></label>
          {instrumentValidation && <p className={`instrument-validation ${instrumentValidation.accepted ? "is-valid" : "is-invalid"}`}>{instrumentValidation.accepted ? "校验通过" : "校验未通过"} · {instrumentValidation.reason}</p>}
          <div className="instrument-correction-submit"><button className="button-secondary" onClick={() => setCorrecting(false)}>取消</button><button className="button-secondary" disabled={submitting || !correction.symbol.trim() || !correction.name.trim()} onClick={() => void validateInstrument()}>校验标的</button><button className="button-primary" disabled={submitting || !instrumentValidation?.accepted || !correction.reason.trim()} onClick={() => void correctInstrument()}>确认修正</button></div>
        </div>
      )}

      {isVerified && !editing && (
        <div className="text-xs text-gray-500">
          {prediction.verified_at &&
            `${formatDateTime(prediction.verified_at)} · `}
          {prediction.verified_by ?? "manual"}
          {prediction.note && (
            <p className="text-xs text-gray-600 italic mt-1">
              备注：{prediction.note}
            </p>
          )}
        </div>
      )}

      {showVerifyForm && (
        <div className="mt-2 space-y-2">
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="备注（可选）"
            className="w-full text-sm border rounded p-2"
            rows={2}
          />
          <div className="flex gap-2">
            <button
              disabled={submitting}
              onClick={() => submit("correct")}
              className="bg-green-600 text-white text-sm px-3 py-1 rounded hover:bg-green-700 disabled:opacity-50"
            >
              看对了
            </button>
            <button
              disabled={submitting}
              onClick={() => submit("partial")}
              className="bg-yellow-500 text-white text-sm px-3 py-1 rounded hover:bg-yellow-600 disabled:opacity-50"
            >
              部分对
            </button>
            <button
              disabled={submitting}
              onClick={() => submit("incorrect")}
              className="bg-red-600 text-white text-sm px-3 py-1 rounded hover:bg-red-700 disabled:opacity-50"
            >
              看错了
            </button>
            {editing && (
              <button
                onClick={() => {
                  setEditing(false);
                  setError(null);
                }}
                className="text-sm text-gray-500 hover:underline ml-auto"
              >
                取消
              </button>
            )}
          </div>
          {error && <p className="text-xs text-red-500">{error}</p>}
        </div>
      )}
    </div>
  );
}

function formatPercent(value: number | null) {
  if (value === null) return "—";
  return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(2)}%`;
}

function formatPrice(value: number | null) {
  if (value === null) return "—";
  return value.toLocaleString("zh-CN", { maximumFractionDigits: 4 });
}

function MarketEvidence({
  evidence,
  predictionTicker,
  manuallyResolved,
}: {
  evidence: MarketVerificationEvidence;
  predictionTicker: string;
  manuallyResolved: boolean;
}) {
  const isReview = evidence.status === "manual_review";
  const isUnavailable = evidence.status === "market_data_unavailable";
  const isNonDirectional = evidence.review_type === "non_directional" || evidence.status === "excluded_non_directional";
  const isDuplicate = evidence.review_type === "duplicate_prediction" || evidence.status === "excluded_duplicate";
  const symbol = evidence.provider_symbol || evidence.identity?.symbol || predictionTicker;
  const market = evidence.market || evidence.identity?.market;
  const identityLabel = market ? `${symbol} · ${MARKET_LABEL[market] || market}（${market}）` : symbol;
  const statusLabel = manuallyResolved
    ? "人工复核已完成"
    : isDuplicate
    ? "修正后已合并去重"
    : isNonDirectional
    ? "不构成可验证预测"
    : evidence.applied
    ? "自动验证已应用"
    : isReview
      ? "需要人工复核"
      : isUnavailable
        ? "行情暂不可用"
        : "行情验证证据";
  return (
    <section className={`prediction-evidence ${isReview ? "is-review" : isUnavailable ? "is-unavailable" : ""}`}>
      <header>
        <div>
          <span className="prediction-evidence-kicker">{statusLabel}</span>
          <strong>{identityLabel}</strong>
        </div>
        {evidence.directional_return !== null && (
          <b className={evidence.directional_return >= 0 ? "is-positive" : "is-negative"}>
            {formatPercent(evidence.directional_return)}
          </b>
        )}
      </header>
      {evidence.start_price !== null && evidence.end_price !== null && (
        <div className="prediction-price-path">
          <div><small>起始价格</small><strong>{formatPrice(evidence.start_price)}</strong><span>{evidence.start_observed_at}</span></div>
          <i aria-hidden="true" />
          <div><small>期末价格</small><strong>{formatPrice(evidence.end_price)}</strong><span>{evidence.end_observed_at}</span></div>
          <div><small>判定阈值</small><strong>{formatPercent(evidence.threshold)}</strong><span>{evidence.rule_version}</span></div>
        </div>
      )}

      {(evidence.reason || evidence.identity_reason) && (
        <p>{evidence.reason || evidence.identity_reason}</p>
      )}
      {evidence.price_proxy && (
        <p className="prediction-proxy-disclosure">
          行情代理：{evidence.price_proxy.business_symbol} → {evidence.price_proxy.provider_symbol}。{evidence.price_proxy.disclosure}
        </p>
      )}
      <footer>
        <span>{evidence.provider || "身份核验规则"}</span>
        <span>{manuallyResolved ? "管理员人工判定" : isDuplicate ? "保留较早预测" : evidence.applied ? "系统自动判定" : "等待管理员处理"}</span>
      </footer>
    </section>
  );
}
