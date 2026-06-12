"use client";

import { useState } from "react";
import { verifyPrediction } from "@/lib/api";
import { formatDate, formatDateTime } from "@/lib/datetime";

export interface PredictionItem {
  id: string;
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
}: {
  prediction: PredictionItem;
  onChanged?: (next: PredictionItem) => void;
}) {
  const now = Date.now();
  const verifiableMs = prediction.verifiable_at
    ? new Date(prediction.verifiable_at).getTime()
    : 0;
  // TODO: restore time lock after testing
  const isLocked = false;
  const isVerifiable = prediction.verdict === null;
  const isVerified = prediction.verdict !== null;

  const [editing, setEditing] = useState(false);
  const [note, setNote] = useState(prediction.note ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  const showVerifyForm = isVerifiable || (isVerified && editing);
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
                  : "bg-red-200 text-red-900"
              }`}
            >
              {VERDICT_LABEL[prediction.verdict ?? ""] ?? prediction.verdict}
            </span>
            <button
              onClick={() => setEditing(true)}
              className="text-xs text-blue-600 hover:underline"
            >
              重新标注
            </button>
          </div>
        )}
      </div>

      <p className="text-sm text-gray-700 mb-2 line-clamp-3">
        {prediction.tweet.content}
      </p>

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
