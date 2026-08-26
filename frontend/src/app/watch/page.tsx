"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import AppIcon from "@/components/AppIcon";
import ConfirmDialog from "@/components/ConfirmDialog";
import { PageEmpty, PageError, PageLoading } from "@/components/PageState";
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

const MARKET_LABEL: Record<string, string> = { CN: "A股", HK: "港股", US: "美股", COMMODITY: "商品", CRYPTO: "加密货币" };
const DIRECTION_LABEL: Record<string, string> = { bullish: "偏多", bearish: "偏空", mixed: "分歧", neutral: "观察" };
const FILTERS = [{ value: "all", label: "全部" }, { value: "active", label: "采集中" }, { value: "attention", label: "有变化" }, { value: "paused", label: "已暂停" }] as const;

function distribution(item: TrackingItem) {
  const bullish = item.monitor.bullish_count || 0;
  const bearish = item.monitor.bearish_count || 0;
  const neutral = Math.max((item.monitor.intelligence_24h || 0) - bullish - bearish, 0);
  const total = Math.max(bullish + bearish + neutral, 1);
  return {
    bullish: Math.round(bullish / total * 100),
    neutral: Math.round(neutral / total * 100),
    bearish: Math.round(bearish / total * 100),
  };
}

export default function WatchPage() {
  const [data, setData] = useState<TrackingListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<(typeof FILTERS)[number]["value"]>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [ticker, setTicker] = useState("");
  const [validation, setValidation] = useState<TrackingValidation | null>(null);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<TrackingItem | null>(null);

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const result = await listTracking();
      setData(result);
      setSelectedId((current) => current && result.items.some((item) => item.id === current) ? current : result.items[0]?.id || null);
    } catch {
      setError("无法读取关注标的，请检查服务连接后重试。");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, []);

  const items = useMemo(() => data?.items || [], [data]);
  const visibleItems = useMemo(() => items.filter((item) => {
    if (filter === "active") return item.status === "active";
    if (filter === "paused") return item.status === "paused";
    if (filter === "attention") return (item.monitor.alerts?.length || 0) > 0 || item.monitor.direction_trend === "up" || item.monitor.direction_trend === "down";
    return true;
  }), [filter, items]);
  const selected = items.find((item) => item.id === selectedId) || null;
  const changedCount = items.filter((item) => (item.monitor.alerts?.length || 0) > 0 || item.monitor.direction_trend === "up" || item.monitor.direction_trend === "down").length;

  const validate = async () => {
    if (!ticker.trim()) return;
    setBusy(true); setNotice(""); setValidation(null);
    try { setValidation(await validateTracking(ticker.trim().toUpperCase())); }
    catch (reason) { setNotice(reason instanceof Error ? reason.message : "标的校验失败"); }
    finally { setBusy(false); }
  };

  const add = async () => {
    const symbol = validation?.instrument?.symbol;
    if (!validation?.accepted || !symbol) return;
    setBusy(true); setNotice("");
    try {
      await createTracking(symbol);
      setShowAdd(false); setTicker(""); setValidation(null);
      await load();
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : "添加标的失败"); }
    finally { setBusy(false); }
  };

  const toggle = async (item: TrackingItem) => {
    setBusy(true);
    try { await updateTracking(item.id, { status: item.status === "active" ? "paused" : "active" }); await load(); }
    finally { setBusy(false); }
  };

  const remove = async () => {
    if (!deleteTarget) return;
    await deleteTracking(deleteTarget.id);
    setDeleteTarget(null);
    await load();
  };

  return <div className="product-page watch-prototype-page">
    <header className="watch-prototype-heading">
      <div><p className="page-eyebrow">Watchlist</p><h1>关注</h1><p>不重复做行情软件，只看你关注博主的观点发生了什么变化。</p></div>
      <button className="button-secondary" type="button" onClick={() => setShowAdd(true)}><AppIcon name="plus" />添加标的</button>
    </header>

    <section className="watch-change-summary">
      <span><AppIcon name="watchlist" /></span>
      <div><strong>过去 24 小时，{changedCount} 个标的的观点发生明显变化</strong><p>{data?.summary.intelligence_24h || 0} 条相关 Twitter 情报进入你的研究范围。</p></div>
      <small>基于 {items.length} 个关注标的</small>
    </section>

    <div className="watch-prototype-toolbar">
      <div>{FILTERS.map((item) => <button key={item.value} className={filter === item.value ? "is-active" : ""} onClick={() => setFilter(item.value)}>{item.label}</button>)}</div>
      <span>{visibleItems.length} 个标的</span>
    </div>

    {loading ? <PageLoading label="正在整理关注标的" /> : error ? <PageError detail={error} onRetry={load} /> : items.length === 0 ? <PageEmpty title="还没有关注标的" detail="添加股票、原油、黄金或加密货币后，这里只聚合已关注博主的相关观点变化。" action={<button className="button-primary" onClick={() => setShowAdd(true)}>添加第一个标的</button>} /> : visibleItems.length === 0 ? <PageEmpty title="当前筛选下没有标的" detail="切换其他状态，或添加一个新的关注标的。" /> : <div className={`watch-prototype-layout ${selected ? "has-detail" : ""}`}>
      <section className="watch-prototype-list">
        {visibleItems.map((item) => {
          const instrument = item.instrument || {};
          const monitor = item.monitor || {};
          const direction = monitor.direction || "neutral";
          const change = monitor.direction_trend === "up" ? "观点升温" : monitor.direction_trend === "down" ? "观点转弱" : monitor.active_predictions ? "出现新预测" : monitor.intelligence_24h ? "方向稳定" : "暂无更新";
          return <button className={`watch-prototype-row ${selectedId === item.id ? "is-selected" : ""}`} key={item.id} onClick={() => setSelectedId(item.id)}>
            <div><strong>{item.ticker}</strong><span>{MARKET_LABEL[instrument.market || ""] || instrument.market || "已核验"} · {DIRECTION_LABEL[direction]}</span></div>
            <div><strong>{monitor.latest_title || `${item.ticker} 暂无新的重要观点`}</strong><p>{monitor.intelligence_24h ? `${monitor.intelligence_24h} 条情报，${monitor.bullish_count || 0} 条偏多，${monitor.bearish_count || 0} 条偏空。` : "已纳入研究范围，等待关注博主发布相关观点。"}</p><i><span style={{ width: `${Math.min(100, Math.max(12, (monitor.bullish_count || 0) * 18))}%` }} /><span className="is-risk" style={{ width: `${Math.min(100, (monitor.bearish_count || 0) * 18)}%` }} /></i></div>
            <div><strong>{change}</strong><small>{monitor.latest_seen_at ? formatDateTime(monitor.latest_seen_at) : item.status === "paused" ? "已暂停" : "等待更新"}</small></div>
            <AppIcon name="arrow" />
          </button>;
        })}
      </section>

      {selected && <aside className="watch-prototype-detail">
        <header><div><AppIcon name="watchlist" />观点变化</div><button type="button" onClick={() => setSelectedId(null)} aria-label="关闭详情">×</button></header>
        <div className="watch-prototype-detail-body">
          <div className="watch-detail-title"><div><h2>{selected.ticker}</h2><p>{MARKET_LABEL[selected.instrument?.market || ""] || selected.instrument?.market || "已核验标的"} · {selected.monitor.intelligence_24h || 0} 条更新</p></div><span className={`is-${selected.monitor.direction || "neutral"}`}>{DIRECTION_LABEL[selected.monitor.direction || "neutral"]}</span></div>
          <p className="watch-detail-thesis">{selected.monitor.latest_title || "关注博主暂未形成新的明确观点；系统会继续等待可追溯证据。"}</p>
          <section><span>关注博主观点分布</span>{(() => { const value = distribution(selected); return <div className="watch-distribution"><div><strong>{value.bullish}%</strong><small>偏多</small></div><div><strong>{value.neutral}%</strong><small>观察</small></div><div><strong>{value.bearish}%</strong><small>偏空 / 风险</small></div></div>; })()}</section>
          <section><span>最近变化</span><div className="watch-change-list">{selected.monitor.latest_title ? <article><i /><div><small>{selected.monitor.latest_seen_at ? formatDateTime(selected.monitor.latest_seen_at) : "最近"}</small><strong>{selected.monitor.latest_title}</strong><p>来自已关注博主的结构化 Twitter 情报。</p></div></article> : <p>暂无可展示的观点变化。</p>}{selected.monitor.alerts?.map((alert) => <article key={`${alert.type}-${alert.message}`} className={`is-${alert.level}`}><i /><div><small>系统提醒</small><strong>{alert.message}</strong></div></article>)}</div></section>
          {selected.instrument?.price_proxy_disclosure && <p className="watch-detail-disclosure">{selected.instrument.price_proxy_disclosure}</p>}
          <div className="watch-detail-actions"><Link className="button-secondary" href={`/assistant?prompt=${encodeURIComponent(`总结关注博主最近对 ${selected.ticker} 的观点变化和证据`)}`}>向助手追问</Link><Link className="button-primary" href={`/watch/${encodeURIComponent(selected.id)}`}>完整标的</Link><button className="watch-detail-toggle" disabled={busy} onClick={() => void toggle(selected)}>{selected.status === "active" ? "暂停采集" : "恢复采集"}</button><button className="text-danger" onClick={() => setDeleteTarget(selected)}>取消关注</button></div>
        </div>
      </aside>}
    </div>}

    {showAdd && <div className="workspace-overlay" onMouseDown={(event) => { if (event.target === event.currentTarget) setShowAdd(false); }}><section className="watch-add-dialog" role="dialog" aria-modal="true" aria-label="添加关注标的">
      <header><div><p className="page-eyebrow">Watchlist</p><h2>添加关注标的</h2><span>只用于聚合博主观点，不创建行情面板。</span></div><button onClick={() => setShowAdd(false)} aria-label="关闭">×</button></header>
      <label><AppIcon name="search" /><input autoFocus value={ticker} onChange={(event) => { setTicker(event.target.value); setValidation(null); setNotice(""); }} onKeyDown={(event) => { if (event.key === "Enter") void validate(); }} placeholder="搜索股票、原油、黄金或加密货币" /></label>
      {notice && <p className="form-message is-error">{notice}</p>}
      {validation && <div className={`watch-add-result ${validation.accepted ? "is-valid" : "is-invalid"}`}><b>{validation.instrument?.symbol || ticker.toUpperCase()}</b><div><strong>{validation.instrument?.resolved_name || validation.instrument?.name || "未找到正式标的"}</strong><small>{validation.accepted ? `${MARKET_LABEL[validation.instrument?.market || ""] || validation.instrument?.market || "已核验"} · ${(validation.instrument?.validation_sources || []).join(" / ")}` : validation.reason}</small></div><span>{validation.accepted ? "身份已核验" : "无法添加"}</span></div>}
      <footer><span>{validation?.accepted ? `将聚合与 ${validation.instrument?.symbol} 相关的博主观点` : "先完成正式标的校验"}</span>{validation?.accepted ? <button className="button-primary" disabled={busy} onClick={() => void add()}>{busy ? "正在添加" : "加入关注"}</button> : <button className="button-primary" disabled={busy || !ticker.trim()} onClick={() => void validate()}>{busy ? "正在校验" : "校验标的"}</button>}</footer>
    </section></div>}

    <ConfirmDialog open={!!deleteTarget} title={`取消关注 ${deleteTarget?.ticker || "标的"}？`} message="取消后不再进入你的个性化研究范围；历史推文和分析记录不会删除。" confirmText="确认取消" variant="danger" onConfirm={remove} onCancel={() => setDeleteTarget(null)} />
  </div>;
}
