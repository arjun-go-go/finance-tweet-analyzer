"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  createTracking,
  deleteTracking,
  listTracking,
  updateTracking,
  validateTracking,
  type TrackingItem,
  type TrackingListResponse,
  type TrackingValidation,
} from "@/lib/api";
import { formatDateTime } from "@/lib/datetime";
import ConfirmDialog from "@/components/ConfirmDialog";
import AppIcon from "@/components/AppIcon";
import { PageEmpty, PageError, PageLoading } from "@/components/PageState";
import { MetricStrip, SegmentedControl, WorkspacePageHeader } from "@/components/WorkspacePage";

const FILTERS = [{ value: "all", label: "全部" }, { value: "attention", label: "需要关注" }, { value: "prediction", label: "新预测" }, { value: "quiet", label: "暂无更新" }, { value: "paused", label: "已暂停" }] as const;
const MARKET_LABEL: Record<string, string> = { CN: "A 股", HK: "港股", US: "美股", COMMODITY: "商品", CRYPTO: "加密货币" };
const DIRECTION_LABEL: Record<string, string> = { bullish: "偏多", bearish: "偏空", mixed: "分歧", neutral: "暂无方向" };

export default function TrackingPage() {
  const [data, setData] = useState<TrackingListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [ticker, setTicker] = useState("");
  const [validation, setValidation] = useState<TrackingValidation | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [notice, setNotice] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<TrackingItem | null>(null);
  const [filter, setFilter] = useState<(typeof FILTERS)[number]["value"]>("all");

  const load = async () => {
    setLoading(true); setError("");
    try { setData(await listTracking()); }
    catch { setError("无法读取标的监控，请检查服务连接后重试。"); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, []);

  const validate = async () => {
    if (!ticker.trim()) { setNotice("请输入标的代码。"); return; }
    setSubmitting(true); setNotice(""); setValidation(null);
    try { setValidation(await validateTracking(ticker.trim().toUpperCase())); }
    catch (reason) { setNotice(reason instanceof Error ? reason.message : "标的校验失败"); }
    finally { setSubmitting(false); }
  };
  const create = async () => {
    if (!validation?.accepted || !validation.instrument?.symbol) { setNotice("请先完成标的校验。"); return; }
    setSubmitting(true); setNotice("");
    try {
      await createTracking(validation.instrument.symbol);
      setTicker(""); setValidation(null); setShowForm(false); await load();
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : "添加标的失败"); }
    finally { setSubmitting(false); }
  };
  const toggle = async (item: TrackingItem) => {
    setBusyId(item.id);
    try { await updateTracking(item.id, { status: item.status === "active" ? "paused" : "active" }); await load(); }
    finally { setBusyId(null); }
  };
  const remove = async () => { if (!deleteTarget) return; await deleteTracking(deleteTarget.id); setDeleteTarget(null); await load(); };

  const items = data?.items ?? [];
  const activeCount = items.filter((item) => item.status === "active").length;
  const filtered = items.filter((item) => {
    const alerts = item.monitor.alerts ?? [];
    if (filter === "attention") return alerts.some((alert) => alert.level === "high");
    if (filter === "prediction") return alerts.some((alert) => alert.type === "new_prediction");
    if (filter === "quiet") return (item.monitor.intelligence_24h ?? 0) === 0 && alerts.length === 0;
    if (filter === "paused") return item.status === "paused";
    return true;
  });

  return <div className="product-page watchlist-monitor-page">
    <WorkspacePageHeader
      eyebrow="Research Scope"
      title="关注标的"
      subtitle="用标的定义你的 Twitter 研究范围：系统会优先筛出相关博主观点、风险和预测；这里不是实时行情盯盘工具。"
      actions={<button className="button-primary" onClick={() => setShowForm((value) => !value)}><AppIcon name="watchlist" className="h-4 w-4" />添加标的</button>}
    />
    <MetricStrip items={[
      { label: "监控标的", value: items.length, note: `${activeCount} 个持续运行` },
      { label: "24h 博主情报", value: data?.summary.intelligence_24h ?? 0, note: "命中关注标的" },
      { label: "需要关注", value: data?.summary.attention ?? 0, note: "风险、反转或新预测" },
      { label: "已暂停", value: items.length - activeCount, note: "不参与首页个性化" },
    ]} />

    {showForm && <section className="watchlist-composer">
      <div><p className="page-eyebrow">Add verified instrument</p><h2>添加关注标的</h2><p>标的通过公开数据源确认后，会立即成为今日情报和研究助手的个性化过滤条件。</p></div>
      <div className="watchlist-composer-fields">
        <label>标的代码<input value={ticker} onChange={(event) => { setTicker(event.target.value); setValidation(null); }} placeholder="NVDA / 600519 / BTC / XAU" /></label>
        <button className="button-secondary" onClick={() => void validate()} disabled={submitting || !ticker.trim()}>校验标的</button>
      </div>
      {validation && <div className={`watchlist-validation ${validation.accepted ? "is-valid" : "is-invalid"}`}>
        <div><span>{validation.accepted ? "身份已确认" : "无法确认"}</span><strong>{validation.instrument?.symbol || ticker}</strong><small>{validation.instrument?.resolved_name || validation.instrument?.name || validation.reason}</small></div>
        {validation.accepted && <dl><div><dt>市场</dt><dd>{MARKET_LABEL[validation.instrument?.market || ""] || validation.instrument?.market}</dd></div><div><dt>校验来源</dt><dd>{validation.instrument?.validation_sources?.join(" / ")}</dd></div>{validation.instrument?.price_proxy_symbol && <div><dt>行情代理</dt><dd>{validation.instrument.price_proxy_symbol}</dd></div>}</dl>}
        <button className="button-primary" disabled={!validation.accepted || submitting} onClick={() => void create()}>{submitting ? "正在添加" : "加入研究范围"}</button>
      </div>}
    </section>}

    {notice && <div className="inline-notice">{notice}</div>}
    <div className="watchlist-scope-note"><AppIcon name="evidence" /><div><strong>它如何影响系统</strong><span>启用的标的会提高相关 Twitter 情报在首页的优先级，并作为研究助手检索和回答的个人范围。</span></div></div>
    <div className="watchlist-monitor-toolbar"><div><strong>我的研究范围</strong><span>{filtered.length} / {items.length} 个标的</span></div><SegmentedControl value={filter} options={[...FILTERS]} onChange={setFilter} /></div>

    {loading ? <PageLoading label="正在整理关注标的" /> : error ? <PageError detail={error} onRetry={load} /> : items.length === 0 ? <PageEmpty title="尚未建立研究范围" detail="添加第一个标的后，系统会优先整理 Twitter 博主对它的观点、风险和预测。" action={<button className="button-primary" onClick={() => setShowForm(true)}>添加标的</button>} /> : filtered.length === 0 ? <PageEmpty title="当前筛选下没有标的" detail="这些标的目前没有需要处理的变化。" /> : <div className="watchlist-monitor-grid">{filtered.map((item) => {
      const instrument = item.instrument ?? {};
      const monitor = item.monitor ?? {};
      return <article className={`watchlist-monitor-card is-${item.status}`} key={item.id}>
        <div className="watchlist-monitor-head"><div><span>{MARKET_LABEL[instrument.market || ""] || instrument.market || "已验证标的"}</span><h3>{item.ticker}</h3><p>{instrument.resolved_name || instrument.name || item.ticker}</p></div><span className={`status-pill ${item.status}`}>{item.status === "active" ? "监控中" : "已暂停"}</span></div>
        <div className={`watchlist-direction is-${monitor.direction || "neutral"}`}><div><small>24h 博主观点方向</small><strong>{DIRECTION_LABEL[monitor.direction || "neutral"]}</strong></div><b>{monitor.direction_trend === "up" ? "↗" : monitor.direction_trend === "down" ? "↘" : "→"}</b></div>
        <div className="watchlist-signal-grid"><div><span>相关情报</span><strong>{monitor.intelligence_24h ?? 0}</strong></div><div><span>看多 / 看空</span><strong>{monitor.bullish_count ?? 0} / {monitor.bearish_count ?? 0}</strong></div><div><span>有效预测</span><strong>{monitor.active_predictions ?? 0}</strong></div><div><span>高风险</span><strong>{monitor.risk_count ?? 0}</strong></div></div>
        <div className="watchlist-latest"><span>最新博主情报</span><p>{monitor.latest_title || "过去 7 天暂无匹配的 Twitter 情报"}</p>{monitor.latest_seen_at && <small>{formatDateTime(monitor.latest_seen_at)}</small>}</div>
        {(monitor.alerts?.length ?? 0) > 0 && <div className="watchlist-alerts">{monitor.alerts?.map((alert) => <span className={`is-${alert.level}`} key={`${alert.type}-${alert.message}`}><AppIcon name="alerts" />{alert.message}</span>)}</div>}
        {instrument.price_proxy_disclosure && <p className="watchlist-proxy">{instrument.price_proxy_disclosure}</p>}
        <div className="card-actions"><Link className="button-primary" href={`/tweets?q=${encodeURIComponent(item.ticker)}`}>查看相关推文</Link><Link className="button-secondary" href={`/assistant?prompt=${encodeURIComponent(`总结博主们最近对 ${item.ticker} 的观点、预测和风险`)}`}>询问助手</Link><button className="button-secondary" disabled={busyId === item.id} onClick={() => void toggle(item)}>{item.status === "active" ? "暂停过滤" : "恢复过滤"}</button><button className="text-danger" onClick={() => setDeleteTarget(item)}>移除</button></div>
      </article>;
    })}</div>}
    <ConfirmDialog open={!!deleteTarget} title="移出标的监控" message={`确定移除「${deleteTarget?.ticker ?? ""}」吗？历史推文和分析记录不会被删除。`} confirmText="移除" variant="danger" onConfirm={remove} onCancel={() => setDeleteTarget(null)} />
  </div>;
}
