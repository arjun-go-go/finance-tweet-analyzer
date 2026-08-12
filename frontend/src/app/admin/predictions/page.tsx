"use client";

import { useCallback, useEffect, useState } from "react";
import PredictionCard, { type PredictionItem } from "@/components/PredictionCard";
import { PageEmpty, PageError, PageLoading } from "@/components/PageState";
import { MetricStrip, SegmentedControl, WorkspacePageHeader } from "@/components/WorkspacePage";
import {
  fetchPredictionReviewQueue,
  type PredictionReviewStats,
} from "@/lib/api";

type ReviewFilter = "all" | "manual_review" | "market_data_unavailable";

export default function PredictionReviewPage() {
  const [filter, setFilter] = useState<ReviewFilter>("all");
  const [items, setItems] = useState<PredictionItem[]>([]);
  const [stats, setStats] = useState<PredictionReviewStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchPredictionReviewQueue({ status: filter, limit: 100 });
      setItems(data.items);
      setStats(data.stats);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "人工复核队列加载失败");
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { void load(); }, [load]);

  const handleChanged = (next: PredictionItem) => {
    setItems((current) => current.filter((item) => item.id !== next.id));
    void load();
  };

  return (
    <div className="prediction-review-page">
      <WorkspacePageHeader
        eyebrow="Prediction Operations"
        title="预测复核"
        subtitle="集中处理无法自动判断的标的身份和行情异常。每一次自动验证都保留价格证据、数据源和规则版本。"
        actions={<button className="button-secondary" onClick={() => void load()}>刷新队列</button>}
      />

      <MetricStrip items={[
        { label: "需要人工复核", value: stats?.manual_review ?? "—", note: "标的或方向无法自动确认" },
        { label: "行情暂不可用", value: stats?.market_data_unavailable ?? "—", note: "等待数据源恢复后重试" },
        { label: "验证周期中", value: stats?.tracking ?? "—", note: "尚未到判定时间" },
        { label: "自动验证完成", value: stats?.auto_verified ?? "—", note: "market_auto_v1" },
      ]} />

      <div className="prediction-review-toolbar">
        <div>
          <strong>待处理记录</strong>
          <span>人工操作会写入 manual，并立即刷新博主可信度</span>
        </div>
        <SegmentedControl
          value={filter}
          onChange={setFilter}
          options={[
            { value: "all", label: "全部" },
            { value: "manual_review", label: "身份复核" },
            { value: "market_data_unavailable", label: "行情异常" },
          ]}
        />
      </div>

      {loading ? (
        <PageLoading label="正在整理复核证据" />
      ) : error ? (
        <PageError detail={error} onRetry={() => void load()} />
      ) : items.length === 0 ? (
        <PageEmpty title="当前没有待复核记录" detail="系统会在发现标的语义冲突、中性方向或行情失败时自动放入这里。" />
      ) : (
        <div className="prediction-review-list">
          {items.map((item) => (
            <article key={item.id}>
              <div className="prediction-review-source">
                <span>信息源</span>
                <strong>@{item.blogger_handle?.replace(/^@/, "") || "unknown"}</strong>
              </div>
              <PredictionCard prediction={item} onChanged={handleChanged} reviewMode />
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
