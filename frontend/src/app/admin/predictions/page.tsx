"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import PredictionCard, { type PredictionItem } from "@/components/PredictionCard";
import { PageEmpty, PageError, PageLoading } from "@/components/PageState";
import { MetricStrip, SegmentedControl, WorkspacePageHeader } from "@/components/WorkspacePage";
import {
  fetchPredictionOperations,
  type PredictionLifecycleStatus,
  type PredictionOperationStats,
} from "@/lib/api";
import { formatDateTime } from "@/lib/datetime";

type LifecycleFilter = "action_required" | "all" | PredictionLifecycleStatus;

const LIFECYCLE_LABEL: Record<PredictionLifecycleStatus, string> = {
  tracking: "跟踪中",
  due: "已到验证时间",
  review: "需要复核",
  verified: "已验证",
  excluded: "已排除",
};

function verificationTiming(item: PredictionItem) {
  if (item.lifecycle_status === "verified" || item.lifecycle_status === "excluded") {
    return item.verified_at ? `完成于 ${formatDateTime(item.verified_at)}` : "流程已结束";
  }
  if (!item.verifiable_at) return "未设置验证时间";
  const remaining = new Date(item.verifiable_at).getTime() - Date.now();
  if (remaining <= 0) return `应于 ${formatDateTime(item.verifiable_at)} 验证`;
  const hours = Math.ceil(remaining / 3_600_000);
  return hours >= 24
    ? `预计 ${formatDateTime(item.verifiable_at)} · 还剩 ${Math.ceil(hours / 24)} 天`
    : `预计 ${formatDateTime(item.verifiable_at)} · 还剩 ${hours} 小时`;
}

function nextAction(item: PredictionItem) {
  if (item.lifecycle_status === "review") {
    return item.market_verification?.status === "market_data_unavailable"
      ? "下一步：重试行情；仍失败再人工处理"
      : "下一步：修正标的或排除无效预测";
  }
  if (item.lifecycle_status === "due") return "下一步：等待自动行情验证，也可人工判定";
  if (item.lifecycle_status === "tracking") return "无需操作：等待进入验证窗口";
  if (item.lifecycle_status === "verified") return "已完成：结果计入博主可信度";
  return "已结束：保留审计但不计入命中率";
}

export default function PredictionOperationsPage() {
  const [filter, setFilter] = useState<LifecycleFilter>("action_required");
  const [items, setItems] = useState<PredictionItem[]>([]);
  const [stats, setStats] = useState<PredictionOperationStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchPredictionOperations({ status: filter === "action_required" ? "all" : filter, limit: 200 });
      setItems(filter === "action_required"
        ? data.items.filter((item: PredictionItem) => item.lifecycle_status === "review" || item.lifecycle_status === "due")
        : data.items);
      setStats(data.stats);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "预测生命周期加载失败");
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { void load(); }, [load]);

  return (
    <div className="prediction-review-page">
      <WorkspacePageHeader
        eyebrow="Prediction Operations"
        title="预测复核"
        subtitle="系统自动跟踪并验证博主的可验证判断；你只需要处理行情异常、标的歧义和少量到期待办。"
        actions={(
          <div className="flex gap-2">
            <Link className="button-secondary" href="/admin/runtime">运行监控</Link>
            <button className="button-secondary" onClick={() => void load()}>刷新数据</button>
          </div>
        )}
      />

      <MetricStrip items={[
        { label: "跟踪中", value: stats?.tracking ?? "—", note: "尚未到验证窗口" },
        { label: "已到期", value: stats?.due ?? "—", note: "等待自动验证任务" },
        { label: "需要复核", value: stats?.review ?? "—", note: `${stats?.market_data_unavailable ?? 0} 条行情异常` },
        { label: "已验证", value: stats?.verified ?? "—", note: `${stats?.auto_verified ?? 0} 条由系统判定` },
        { label: "已排除", value: stats?.excluded ?? "—", note: "保留审计，不计命中率" },
      ]} />

      <div className="prediction-workflow" aria-label="预测验证流程">
        <div><b>01</b><span>严格规则创建</span><small>作者、方向、期限、标的、证据</small></div>
        <i />
        <div><b>02</b><span>等待验证窗口</span><small>短期 7 天 / 中期 30 天 / 长期 180 天</small></div>
        <i />
        <div><b>03</b><span>自动行情判定</span><small>A / 港 / 美股、原油、黄金、加密货币</small></div>
        <i />
        <div><b>04</b><span>仅异常转人工</span><small>修正、重试或排除，全程留痕</small></div>
      </div>

      <div className="prediction-review-toolbar">
        <div>
          <strong>{filter === "action_required" ? "当前待处理" : "全流程记录"}</strong>
          <span>优先处理异常复核，其次处理已到期记录；跟踪中的预测无需人工介入。</span>
        </div>
        <SegmentedControl
          value={filter}
          onChange={setFilter}
          options={[
            { value: "action_required", label: `待处理 ${(stats?.review ?? 0) + (stats?.due ?? 0)}` },
            { value: "all", label: `全部 ${stats?.total ?? ""}` },
            { value: "tracking", label: "跟踪中" },
            { value: "due", label: "已到期" },
            { value: "review", label: "需复核" },
            { value: "verified", label: "已验证" },
            { value: "excluded", label: "已排除" },
          ]}
        />
      </div>

      {loading ? (
        <PageLoading label="正在整理预测生命周期" />
      ) : error ? (
        <PageError detail={error} onRetry={() => void load()} />
      ) : items.length === 0 ? (
        <PageEmpty title="当前筛选下没有记录" detail="切换其他生命周期状态，或等待新的预测进入验证流程。" />
      ) : (
        <div className="prediction-review-list">
          {items.map((item) => {
            const lifecycle = item.lifecycle_status ?? "tracking";
            return (
              <article id={`prediction-${item.id}`} key={item.id} className={`prediction-lifecycle-item is-${lifecycle}`}>
                <div className="prediction-lifecycle-head">
                  <div>
                    <span className="prediction-lifecycle-state">{LIFECYCLE_LABEL[lifecycle]}</span>
                    <strong>@{item.blogger_handle?.replace(/^@/, "") || "unknown"}</strong>
                  </div>
                  <span>{verificationTiming(item)}</span>
                </div>
                <div className="prediction-next-action">{nextAction(item)}</div>
                <PredictionCard
                  prediction={item}
                  onChanged={() => void load()}
                  reviewMode={lifecycle === "review"}
                />
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
