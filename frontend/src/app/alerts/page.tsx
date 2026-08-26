"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import AppIcon from "@/components/AppIcon";
import { PageEmpty, PageError, PageLoading } from "@/components/PageState";
import { MetricStrip, SegmentedControl, WorkspacePageHeader } from "@/components/WorkspacePage";
import { fetchAlerts, readAllAlerts, updateAlert, type UserAlertItem, type UserAlertListResponse } from "@/lib/api";
import { formatDateTime } from "@/lib/datetime";

type AlertFilter = "unread" | "all" | "read" | "dismissed";

const KIND_LABELS: Record<string, string> = {
  high_risk: "高风险线索",
  direction_reversal: "观点反转",
  new_prediction: "新预测",
};

export default function AlertsPage() {
  const [filter, setFilter] = useState<AlertFilter>("unread");
  const [data, setData] = useState<UserAlertListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try { setData(await fetchAlerts(filter)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "提醒加载失败"); }
    finally { setLoading(false); }
  }, [filter]);

  useEffect(() => { void load(); }, [load]);

  const changeStatus = async (item: UserAlertItem, action: "read" | "dismiss") => {
    setBusy(item.id);
    try { await updateAlert(item.id, action); await load(); }
    finally { setBusy(null); }
  };

  const markAll = async () => {
    setBusy("all");
    try { await readAllAlerts(); await load(); }
    finally { setBusy(null); }
  };

  return <div className="product-page alerts-page">
    <WorkspacePageHeader
      eyebrow="Twitter Intelligence Alerts"
      title="研究提醒"
      subtitle="只提醒与你关注的 Twitter 博主或标的直接相关的高风险、观点反转和新预测。"
      actions={data?.unread ? <button className="button-secondary" onClick={() => void markAll()} disabled={busy === "all"}>全部标记已读</button> : undefined}
    />
    <MetricStrip items={[
      { label: "未读提醒", value: data?.unread ?? "—", note: "等待处理" },
      { label: "高优先级", value: data?.high_priority ?? "—", note: "高风险或观点反转" },
      { label: "当前列表", value: data?.total ?? "—", note: "按当前状态筛选" },
    ]} />
    <div className="alerts-toolbar">
      <div><strong>提醒队列</strong><span>提醒由正式关注关系触发，不使用记忆偏好推断。</span></div>
      <SegmentedControl value={filter} onChange={setFilter} options={[
        { value: "unread", label: "未读" },
        { value: "all", label: "全部" },
        { value: "read", label: "已读" },
        { value: "dismissed", label: "已忽略" },
      ]} />
    </div>
    {loading ? <PageLoading label="正在整理研究提醒" />
      : error ? <PageError detail={error} onRetry={load} />
        : !data?.items.length ? <PageEmpty title="当前没有提醒" detail="关注 Twitter 博主或标的后，相关的重要变化会出现在这里。" />
          : <div className="alerts-list">{data.items.map((item) => <article className={`alert-item is-${item.severity} is-${item.status}`} key={item.id}>
            <span className="alert-marker"><AppIcon name="alerts" /></span>
            <div className="alert-copy">
              <div className="alert-meta"><span>{KIND_LABELS[item.kind] || item.kind}</span>{item.ticker && <b>{item.ticker}</b>}{item.blogger_handle && <span>@{item.blogger_handle.replace(/^@/, "")}</span>}<time>{formatDateTime(item.occurred_at)}</time></div>
              <h2>{item.title}</h2>
              <p>{item.message}</p>
              <footer><Link href={item.target_url}>查看证据 <AppIcon name="arrow" /></Link>{item.status === "unread" && <button disabled={busy === item.id} onClick={() => void changeStatus(item, "read")}>标记已读</button>}{item.status !== "dismissed" && <button disabled={busy === item.id} onClick={() => void changeStatus(item, "dismiss")}>忽略</button>}</footer>
            </div>
          </article>)}</div>}
  </div>;
}
