"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import AppIcon from "@/components/AppIcon";
import ConfirmDialog from "@/components/ConfirmDialog";
import { PageError, PageLoading } from "@/components/PageState";
import { deleteTracking, listTracking, updateTracking, type TrackingItem } from "@/lib/api";
import { formatDateTime } from "@/lib/datetime";

const MARKET_LABEL: Record<string, string> = { CN: "A股", HK: "港股", US: "美股", COMMODITY: "商品", CRYPTO: "加密货币" };
const DIRECTION_LABEL: Record<string, string> = { bullish: "偏多", bearish: "偏空", mixed: "分歧", neutral: "观察" };

export default function WatchAssetDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [item, setItem] = useState<TrackingItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const result = await listTracking();
      const match = result.items.find((entry) => entry.id === decodeURIComponent(params.id));
      if (!match) throw new Error("这个标的不在你的关注范围中。");
      setItem(match);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "标的详情加载失败"); }
    finally { setLoading(false); }
  }, [params.id]);

  useEffect(() => { void load(); }, [load]);

  const toggle = async () => {
    if (!item) return;
    setBusy(true);
    try { setItem(await updateTracking(item.id, { status: item.status === "active" ? "paused" : "active" })); }
    finally { setBusy(false); }
  };

  const remove = async () => {
    if (!item) return;
    await deleteTracking(item.id);
    router.push("/watch");
  };

  if (loading) return <PageLoading label="正在读取标的观点" />;
  if (error || !item) return <PageError detail={error || "标的不存在"} onRetry={load} />;

  const monitor = item.monitor || {};
  const instrument = item.instrument || {};
  const bullish = monitor.bullish_count || 0;
  const bearish = monitor.bearish_count || 0;
  const neutral = Math.max((monitor.intelligence_24h || 0) - bullish - bearish, 0);
  const total = Math.max(bullish + bearish + neutral, 1);

  return <div className="product-page asset-prototype-page">
    <Link className="insight-back" href="/watch"><AppIcon name="arrow" />返回关注</Link>
    <header className="asset-prototype-hero"><div><h1>{item.ticker}</h1><span>{MARKET_LABEL[instrument.market || ""] || instrument.market || "已核验标的"} · 身份已核验</span></div><div><strong>{monitor.direction_trend === "up" ? "观点升温" : monitor.direction_trend === "down" ? "观点转弱" : monitor.intelligence_24h ? "方向稳定" : "等待新观点"}</strong><span>最近更新：{monitor.latest_seen_at ? formatDateTime(monitor.latest_seen_at) : "暂无"}</span></div></header>

    <div className="asset-prototype-layout">
      <main>
        <section className="asset-consensus-card"><span>当前博主共识</span><h2>{monitor.latest_title || `${item.ticker} 暂无新的明确观点`}</h2><p>{monitor.intelligence_24h ? `过去 24 小时收录 ${monitor.intelligence_24h} 条相关 Twitter 情报；这里总结的是关注博主观点，不是实时行情建议。` : "系统会继续等待关注博主发布带有可追溯证据的相关观点。"}</p><div><div><strong>{Math.round(bullish / total * 100)}%</strong><span>偏多</span></div><div><strong>{Math.round(neutral / total * 100)}%</strong><span>观察</span></div><div><strong>{Math.round(bearish / total * 100)}%</strong><span>偏空 / 风险</span></div></div></section>

        <section className="asset-opinion-section"><header><h2>观点变化</h2><span>{monitor.intelligence_24h || 0} 条 24h 情报</span></header>{monitor.latest_title ? <article><time>{monitor.latest_seen_at ? formatDateTime(monitor.latest_seen_at) : "最近"}</time><div><h3>{monitor.latest_title}</h3><p>来自关注博主的已采集内容；打开相关推文可以查看完整证据和原文。</p><footer><span>{DIRECTION_LABEL[monitor.direction || "neutral"]}</span><span>标的已核验</span></footer></div></article> : <div className="asset-opinion-empty"><strong>暂无观点变化</strong><p>关注关系已经建立，新的相关推文完成分析后会出现在这里。</p></div>}{monitor.alerts?.map((alert) => <article key={`${alert.type}-${alert.message}`}><time>系统提醒</time><div><h3>{alert.message}</h3><footer><span>{alert.level === "high" ? "需要关注" : "新变化"}</span></footer></div></article>)}</section>
      </main>

      <aside className="asset-prototype-aside">
        <section><span>标的身份</span><div className="asset-identity-proof"><b><AppIcon name="check" /></b><div><strong>{item.ticker} · {MARKET_LABEL[instrument.market || ""] || instrument.market || "已验证"}</strong><small>{instrument.resolved_name || instrument.name || "通过正式标的校验"}</small></div></div></section>
        <section><span>信息覆盖</span><dl><div><dt>24h 情报</dt><dd>{monitor.intelligence_24h || 0} 条</dd></div><div><dt>有效预测</dt><dd>{monitor.active_predictions || 0} 条</dd></div><div><dt>高风险</dt><dd>{monitor.risk_count || 0} 条</dd></div><div><dt>当前状态</dt><dd>{item.status === "active" ? "采集中" : "已暂停"}</dd></div></dl></section>
        <section><span>使用说明</span><h3>这里只解释博主观点</h3><p>价格行情只用于验证预测结果，不提供实时交易信号。</p>{instrument.price_proxy_disclosure && <small>{instrument.price_proxy_disclosure}</small>}</section>
        <div><Link className="button-secondary" href={`/tweets?q=${encodeURIComponent(item.ticker)}`}>查看相关推文</Link><Link className="button-primary" href={`/assistant?prompt=${encodeURIComponent(`总结关注博主最近对 ${item.ticker} 的观点、风险和证据`)}`}>向助手追问</Link><button className="button-secondary" disabled={busy} onClick={() => void toggle()}>{item.status === "active" ? "暂停采集" : "恢复采集"}</button><button className="text-danger" onClick={() => setConfirming(true)}>取消关注</button></div>
      </aside>
    </div>
    <ConfirmDialog open={confirming} title={`取消关注 ${item.ticker}？`} message="取消后不再进入你的个性化研究范围；历史推文和分析记录不会删除。" confirmText="确认取消" variant="danger" onConfirm={remove} onCancel={() => setConfirming(false)} />
  </div>;
}
