"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import AppIcon from "@/components/AppIcon";
import ConfirmDialog from "@/components/ConfirmDialog";
import { PageEmpty, PageError, PageLoading } from "@/components/PageState";
import {
  createTracking,
  deleteTracking,
  fetchTickerSummaries,
  listTracking,
  validateTracking,
  type TickerSummaryItem,
  type TrackingItem,
  type TrackingListResponse,
  type TrackingValidation,
} from "@/lib/api";

type AssetView = "all" | "tracked";

const MARKET_LABEL: Record<string, string> = {
  CN: "A股",
  HK: "港股",
  US: "美股",
  COMMODITY: "商品",
  CRYPTO: "加密货币",
};

const CONSENSUS_LABEL: Record<string, string> = {
  strong_buy: "多数看多",
  buy: "偏多",
  strong_sell: "多数看空",
  sell: "偏空",
  mixed: "观点分歧",
  neutral: "中性",
  none: "暂无方向",
};

const MONITOR_DIRECTION: Record<string, string> = {
  bullish: "偏多",
  bearish: "偏空",
  mixed: "观点分歧",
  neutral: "暂无方向",
};

const REFERENCE_REASON: Record<string, string> = {
  sponsor_related: "与推广方直接相关",
  sponsor_relation_unclear: "商业关联待确认",
  quoted_opinion: "引用观点",
  third_party_opinion: "第三方观点",
  opinion_source_unclear: "观点归属待确认",
  risk_warning: "风险提示",
  fact_mention: "事实提及",
  news_mention: "新闻信息",
  historical_recap: "历史复盘",
  reference_mention: "仅提及标的",
  opinion_not_author: "非博主本人观点",
  claim_type_not_stance: "事实或背景信息",
  direction_not_comparable: "尚未形成明确方向",
  instrument_not_verified: "标的身份待确认",
};

function referenceSummary(reasons: Record<string, number> = {}) {
  const keys = [
    "sponsor_related",
    "sponsor_relation_unclear",
    "quoted_opinion",
    "third_party_opinion",
    "opinion_source_unclear",
    "risk_warning",
    "fact_mention",
    "news_mention",
    "historical_recap",
    "reference_mention",
    "direction_not_comparable",
    "instrument_not_verified",
    "opinion_not_author",
    "claim_type_not_stance",
  ].filter((candidate) => reasons[candidate]);
  return keys.length
    ? keys.slice(0, 3).map((key) => REFERENCE_REASON[key]).join(" · ")
    : "暂无可计入统计的作者观点";
}

function TrackedAssetRow({ item, onRemove }: { item: TrackingItem; onRemove: () => void }) {
  const monitor = item.monitor || {};
  const instrument = item.instrument || {};
  return (
    <article className="asset-directory-row">
      <div className="asset-directory-symbol">
        <strong>{item.ticker}</strong>
        <span>{MARKET_LABEL[instrument.market || ""] || instrument.market || "已核验标的"}</span>
      </div>
      <div className="asset-directory-copy">
        <div><b>{MONITOR_DIRECTION[monitor.direction || "neutral"]}</b><span>{item.status === "paused" ? "已暂停" : "关注中"}</span></div>
        <p>{monitor.latest_title || "等待关注博主发布与该标的有关的新观点。"}</p>
        <small>{monitor.intelligence_24h || 0} 项 24h 新观点 · {monitor.bullish_count || 0} 多 / {monitor.bearish_count || 0} 空</small>
      </div>
      <div className="asset-directory-actions">
        <Link href={`/watch/${encodeURIComponent(item.ticker)}`}>查看</Link>
        <button type="button" onClick={onRemove}>取消关注</button>
      </div>
    </article>
  );
}

export default function AssetsPage() {
  const [view, setView] = useState<AssetView>("all");
  const [summaries, setSummaries] = useState<TickerSummaryItem[]>([]);
  const [tracking, setTracking] = useState<TrackingListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busyTicker, setBusyTicker] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<TrackingItem | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [ticker, setTicker] = useState("");
  const [validation, setValidation] = useState<TrackingValidation | null>(null);
  const [validating, setValidating] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [summaryData, trackingData] = await Promise.all([
        fetchTickerSummaries({ limit: 100 }),
        listTracking(),
      ]);
      setSummaries(summaryData.items);
      setTracking(trackingData);
    } catch {
      setError("标的数据加载失败，请检查服务连接后重试。");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const trackedByTicker = useMemo(
    () => new Map((tracking?.items || []).map((item) => [item.ticker.toUpperCase(), item])),
    [tracking],
  );

  const follow = async (symbol: string) => {
    setBusyTicker(symbol);
    setNotice("");
    try {
      await createTracking(symbol);
      setNotice(`已关注 ${symbol}`);
      await load();
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : "关注标的失败");
    } finally {
      setBusyTicker("");
    }
  };

  const remove = async () => {
    if (!deleteTarget) return;
    const target = deleteTarget;
    setDeleteTarget(null);
    setBusyTicker(target.ticker);
    try {
      await deleteTracking(target.id);
      setNotice(`已取消关注 ${target.ticker}`);
      await load();
    } catch {
      setNotice("取消关注失败，请稍后重试。");
    } finally {
      setBusyTicker("");
    }
  };

  const validate = async () => {
    if (!ticker.trim()) return;
    setValidating(true);
    setNotice("");
    setValidation(null);
    try {
      setValidation(await validateTracking(ticker.trim().toUpperCase()));
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : "标的校验失败");
    } finally {
      setValidating(false);
    }
  };

  const add = async () => {
    const symbol = validation?.instrument?.symbol;
    if (!validation?.accepted || !symbol) return;
    await follow(symbol);
    setShowAdd(false);
    setTicker("");
    setValidation(null);
  };

  if (loading) return <PageLoading label="正在加载标的" />;
  if (error) return <PageError detail={error} onRetry={load} />;

  const trackedItems = tracking?.items || [];

  return (
    <div className="asset-directory-page">
      <header className="asset-directory-header">
        <div><h1>标的</h1><p>汇总博主对股票、原油、黄金和加密货币的逐标的观点。</p></div>
        <button className="button-secondary" type="button" onClick={() => setShowAdd(true)}><AppIcon name="plus" />关注标的</button>
      </header>

      <div className="asset-directory-toolbar">
        <nav aria-label="标的范围">
          <button type="button" className={view === "all" ? "is-active" : ""} onClick={() => setView("all")}>全部标的</button>
          <button type="button" className={view === "tracked" ? "is-active" : ""} onClick={() => setView("tracked")}>我的关注</button>
        </nav>
        <span>{view === "all" ? `${summaries.length} 个已核验标的` : `${trackedItems.length} 个关注标的`}</span>
      </div>

      {notice && <p className="asset-directory-notice" role="status">{notice}</p>}

      {view === "all" ? (
        summaries.length ? <section className="asset-directory-list" aria-label="全部标的">
          {summaries.map((item) => {
            const summary = item.result;
            const tracked = trackedByTicker.get(summary.ticker.toUpperCase());
            const hasEffectiveViews = summary.has_effective_views ?? summary.mention_count > 0;
            const relatedCount = summary.related_claim_count ?? summary.mention_count;
            const bloggerCount = hasEffectiveViews
              ? summary.bloggers.length
              : (summary.related_bloggers || []).length;
            return (
              <article className="asset-directory-row" key={item.id}>
                <div className="asset-directory-symbol"><strong>{summary.ticker}</strong><span>{bloggerCount} 位博主</span></div>
                <div className="asset-directory-copy">
                  <div><b>{hasEffectiveViews ? CONSENSUS_LABEL[summary.consensus] || "暂无方向" : "仅供参考"}</b><span>{hasEffectiveViews ? `${summary.mention_count} 项有效观点${summary.consensus_sample_status === "limited" ? " · 样本较少" : ""}` : `${relatedCount} 项相关信息`}</span></div>
                  <p>{summary.summary || "已有结构化观点，暂无可展示的简要说明。"}</p>
                  <small>{hasEffectiveViews
                    ? `${summary.bullish_count} 多 / ${summary.bearish_count} 空${summary.neutral_count ? ` / ${summary.neutral_count} 中性` : ""}`
                    : `${referenceSummary(summary.exclusion_reasons)} · 不参与多空统计`}</small>
                </div>
                <div className="asset-directory-actions">
                  <Link href={`/watch/${encodeURIComponent(summary.ticker)}`}>查看</Link>
                  {tracked
                    ? <span className="is-tracked">已关注</span>
                    : <button type="button" disabled={busyTicker === summary.ticker} onClick={() => void follow(summary.ticker)}>{busyTicker === summary.ticker ? "处理中…" : "关注"}</button>}
                </div>
              </article>
            );
          })}
        </section> : <PageEmpty title="还没有标的信息" detail="博主推文完成逐标的分析后，已核验标的及其观点、引用和事实信息会显示在这里。" />
      ) : (
        trackedItems.length ? <section className="asset-directory-list" aria-label="关注标的">
          {trackedItems.map((item) => <TrackedAssetRow key={item.id} item={item} onRemove={() => setDeleteTarget(item)} />)}
        </section> : <PageEmpty title="还没有关注标的" detail="从全部标的中选择关注，或直接输入股票、原油、黄金及加密货币代码。" action={<button className="button-primary mt-3" onClick={() => setShowAdd(true)}>关注第一个标的</button>} />
      )}

      {showAdd && <div className="workspace-overlay" onMouseDown={(event) => { if (event.target === event.currentTarget) setShowAdd(false); }}>
        <section className="watch-add-dialog" role="dialog" aria-modal="true" aria-label="关注标的">
          <header><div><h2>关注标的</h2><span>用于持续聚合你关注博主的相关观点。</span></div><button onClick={() => setShowAdd(false)} aria-label="关闭">×</button></header>
          <label><AppIcon name="search" /><input autoFocus value={ticker} onChange={(event) => { setTicker(event.target.value); setValidation(null); setNotice(""); }} onKeyDown={(event) => { if (event.key === "Enter") void validate(); }} placeholder="输入股票、WTI、XAU 或加密货币代码" /></label>
          {validation && <div className={`watch-add-result ${validation.accepted ? "is-valid" : "is-invalid"}`}><b>{validation.instrument?.symbol || ticker.toUpperCase()}</b><div><strong>{validation.instrument?.resolved_name || validation.instrument?.name || "未找到正式标的"}</strong><small>{validation.accepted ? `${MARKET_LABEL[validation.instrument?.market || ""] || validation.instrument?.market || "已核验"} · ${(validation.instrument?.validation_sources || []).join(" / ")}` : validation.reason}</small></div><span>{validation.accepted ? "身份已核验" : "无法关注"}</span></div>}
          <footer><span>{validation?.accepted ? `将聚合 ${validation.instrument?.symbol} 的博主观点` : "先完成正式标的校验"}</span>{validation?.accepted ? <button className="button-primary" disabled={Boolean(busyTicker)} onClick={() => void add()}>{busyTicker ? "正在关注" : "确认关注"}</button> : <button className="button-primary" disabled={validating || !ticker.trim()} onClick={() => void validate()}>{validating ? "正在校验" : "校验标的"}</button>}</footer>
        </section>
      </div>}

      <ConfirmDialog open={Boolean(deleteTarget)} title={`取消关注 ${deleteTarget?.ticker || "标的"}？`} message="取消后不再进入你的关注列表，历史推文和分析记录不会删除。" confirmText="确认取消" variant="danger" onConfirm={remove} onCancel={() => setDeleteTarget(null)} />
    </div>
  );
}
