"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { createTracking, deleteTracking, listTracking, triggerTracking, updateTracking, type TrackingItem } from "@/lib/api";
import { formatDateTime } from "@/lib/datetime";
import ConfirmDialog from "@/components/ConfirmDialog";
import AppIcon from "@/components/AppIcon";
import { PageEmpty, PageError, PageLoading } from "@/components/PageState";
import { MetricStrip, SectionTitle, SegmentedControl, WorkspacePageHeader } from "@/components/WorkspacePage";

const FREQUENCIES = [{ value: "daily", label: "每日" }, { value: "weekly", label: "每周" }, { value: "manual", label: "手动" }] as const;
const frequencyLabel = (value: string) => FREQUENCIES.find((item) => item.value === value)?.label ?? value;

export default function TrackingPage() {
  const router = useRouter();
  const [items, setItems] = useState<TrackingItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [ticker, setTicker] = useState("");
  const [frequency, setFrequency] = useState<"daily" | "weekly" | "manual">("daily");
  const [submitting, setSubmitting] = useState(false);
  const [notice, setNotice] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<TrackingItem | null>(null);

  const load = async () => {
    setLoading(true); setError("");
    try { setItems((await listTracking()).items); }
    catch { setError("无法读取 Watchlist，请检查服务连接后重试。"); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const create = async () => {
    if (!ticker.trim()) { setNotice("请输入标的代码。"); return; }
    setSubmitting(true); setNotice("");
    try { await createTracking(ticker.trim().toUpperCase(), frequency); setTicker(""); setShowForm(false); await load(); }
    catch { setNotice("添加失败，可能已存在相同标的。"); }
    finally { setSubmitting(false); }
  };
  const toggle = async (item: TrackingItem) => {
    setBusyId(item.id);
    try { const status = item.status === "active" ? "paused" : "active"; await updateTracking(item.id, { status }); setItems((prev) => prev.map((value) => value.id === item.id ? { ...value, status } : value)); }
    finally { setBusyId(null); }
  };
  const trigger = async (item: TrackingItem) => {
    setBusyId(item.id); setNotice("");
    try { const result = await triggerTracking(item.id); setNotice(`${item.ticker} 研究简报已进入生成队列。`); router.push(`/reports/${result.report_id}`); }
    catch { setNotice(`${item.ticker} 简报触发失败，请稍后重试。`); }
    finally { setBusyId(null); }
  };
  const remove = async () => { if (!deleteTarget) return; await deleteTracking(deleteTarget.id); setDeleteTarget(null); await load(); };
  const activeCount = items.filter((item) => item.status === "active").length;
  const scheduledCount = items.filter((item) => item.frequency !== "manual" && item.status === "active").length;

  return <div className="product-page">
    <WorkspacePageHeader eyebrow="Research Scope" title="Watchlist" subtitle="把需要持续判断的标的放进研究范围，系统按频率生成可回溯的投资简报。" actions={<button className="button-primary" onClick={() => setShowForm((value) => !value)}><AppIcon name="watchlist" className="h-4 w-4" />添加标的</button>} />
    <MetricStrip items={[{ label: "跟踪标的", value: items.length, note: "当前研究范围" }, { label: "持续监控", value: activeCount, note: "状态正常" }, { label: "自动简报", value: scheduledCount, note: "每日或每周" }]} />
    {showForm && <section className="composer-panel"><div><p className="page-eyebrow">Add to scope</p><h2>添加跟踪标的</h2><p>输入标准 ticker，选择系统生成研究简报的节奏。</p></div><div className="composer-fields"><label>标的代码<input value={ticker} onChange={(event) => setTicker(event.target.value)} placeholder="例如 NVDA / BTC" /></label><label>研究频率<SegmentedControl value={frequency} options={[...FREQUENCIES]} onChange={setFrequency} /></label><button className="button-primary" onClick={create} disabled={submitting}>{submitting ? "正在添加" : "确认添加"}</button></div></section>}
    {notice && <div className="inline-notice">{notice}</div>}
    <SectionTitle icon="watchlist" title="研究范围" meta={`${items.length} 个标的`} />
    {loading ? <PageLoading label="正在读取 Watchlist" /> : error ? <PageError detail={error} onRetry={load} /> : items.length === 0 ? <PageEmpty title="尚未建立研究范围" detail="添加第一个标的后，系统会持续整理相关观点并生成简报。" action={<button className="button-primary" onClick={() => setShowForm(true)}>添加标的</button>} /> : <div className="watchlist-grid">{items.map((item) => <article className="watchlist-card" key={item.id}><div className={`watchlist-status ${item.status}`} /><div className="watchlist-card-head"><div><span>TRACKING ASSET</span><h3>{item.ticker}</h3></div><span className={`status-pill ${item.status}`}>{item.status === "active" ? "监控中" : "已暂停"}</span></div><dl><div><dt>研究频率</dt><dd>{frequencyLabel(item.frequency)}</dd></div><div><dt>最近简报</dt><dd>{formatDateTime(item.last_report_at) || "尚未生成"}</dd></div><div><dt>下次执行</dt><dd>{item.frequency === "manual" ? "按需触发" : formatDateTime(item.next_run_at) || "等待调度"}</dd></div></dl><div className="card-actions"><button className="button-primary" disabled={busyId === item.id} onClick={() => trigger(item)}>生成简报</button><button className="button-secondary" disabled={busyId === item.id} onClick={() => toggle(item)}>{item.status === "active" ? "暂停" : "恢复"}</button><button className="text-danger" onClick={() => setDeleteTarget(item)}>移除</button></div></article>)}</div>}
    <ConfirmDialog open={!!deleteTarget} title="移出 Watchlist" message={`确定移除「${deleteTarget?.ticker ?? ""}」吗？已有简报不会被删除。`} confirmText="移除" variant="danger" onConfirm={remove} onCancel={() => setDeleteTarget(null)} />
  </div>;
}
