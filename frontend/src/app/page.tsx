"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import AppIcon from "@/components/AppIcon";
import IntelligenceCard from "@/components/IntelligenceCard";
import { PageEmpty, PageError, PageLoading } from "@/components/PageState";
import { fetchDashboard, fetchIntelligenceFeed, type IntelligenceFeedItem, type IntelligenceFeedResponse } from "@/lib/api";

interface DashboardData {
  analyzed_tweets: number;
  total_analyses: number;
  total_bloggers: number;
  pending_tweets: number;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "long", day: "numeric", weekday: "long" }).format(new Date(value));
}

const SCORE_LABELS: Record<string, string> = { relevance: "与你相关", freshness: "新鲜度", confidence: "模型置信", credibility: "来源可信", risk: "风险强度", corroboration: "交叉印证" };

export default function IntelligenceDashboard() {
  const [feed, setFeed] = useState<IntelligenceFeedResponse | null>(null);
  const [stats, setStats] = useState<DashboardData | null>(null);
  const [selected, setSelected] = useState<IntelligenceFeedItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [windowRange, setWindowRange] = useState<"24h" | "3d" | "7d">("24h");
  const [feedKind, setFeedKind] = useState<"all" | "risk" | "opinion">("all");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [feedData, statsData] = await Promise.all([fetchIntelligenceFeed(20, windowRange, feedKind), fetchDashboard()]);
      setFeed(feedData);
      setStats(statsData);
      setSelected(feedData.items[0] || null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "无法加载今日情报。");
    } finally {
      setLoading(false);
    }
  }, [windowRange, feedKind]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <PageLoading label="正在整理今天的市场观点" />;
  if (error || !feed) return <PageError detail={error || "情报接口没有返回数据。"} onRetry={load} />;

  return (
    <div>
      <header className="page-header">
        <div>
          <p className="page-eyebrow">Daily intelligence</p>
          <h1 className="page-title">今日情报</h1>
          <p className="page-subtitle">{formatDate(new Date().toISOString())} · 按重要性整理你关注的博主、标的与市场风险，每条结论都能回到原始证据。</p>
        </div>
        <div className="page-header-actions flex gap-2">
          <Link href="/tracking" className="button-secondary"><AppIcon name="watchlist" />管理 Watchlist</Link>
          <Link href="/chat" className="button-primary"><AppIcon name="research" />深入研究</Link>
        </div>
      </header>

      <div className="research-scope-bar">
        <div className="research-scope-state">
          <span className={`scope-live-dot ${feed.context.personalized ? "is-live" : ""}`} />
          <div><strong>{feed.context.personalized ? "个性化情报已开启" : "市场情报模式"}</strong><span>首页会根据你的关注范围自动筛选重要变化</span></div>
        </div>
        <div className="research-scope-links">
          <Link href="/bloggers"><span>关注博主</span><b>{feed.context.followed_bloggers}</b></Link>
          <Link href="/tracking"><span>Watchlist</span><b>{feed.context.tracked_tickers}</b></Link>
          <Link href="/tweets?tab=analyzed"><span>已分析</span><b>{stats?.analyzed_tweets ?? 0}</b></Link>
        </div>
      </div>

      <div className="dashboard-grid">
        <section className="dashboard-main">
          <div className="feed-toolbar">
            <div className="section-heading"><h2>与你相关的重要变化</h2><span>显示 {feed.items.length} / {feed.total} 条候选</span></div>
            <div className="feed-filters">
              <div className="feed-filter-group" aria-label="时间范围">
                {([['24h', '24 小时'], ['3d', '近 3 日'], ['7d', '近 7 日']] as const).map(([value, label]) => <button key={value} className={windowRange === value ? "is-active" : ""} onClick={() => setWindowRange(value)}>{label}</button>)}
              </div>
              <div className="feed-filter-group" aria-label="情报类型">
                {([['all', '全部'], ['risk', '风险'], ['opinion', '观点']] as const).map(([value, label]) => <button key={value} className={feedKind === value ? "is-active" : ""} onClick={() => setFeedKind(value)}>{label}</button>)}
              </div>
            </div>
          </div>
          {(!feed.context.personalized || feed.context.fallback_to_market) && (
            <div className="feed-mode-notice">
              <AppIcon name="alerts" />
              <span>{feed.context.fallback_to_market ? "暂时没有匹配关注范围的新内容，以下补充展示市场最新情报。" : "当前展示市场最新情报。关注博主或添加 Watchlist 标的后，首页会切换为个性化情报。"}</span>
              <Link href={feed.context.followed_bloggers === 0 ? "/bloggers" : "/tracking"}>完善研究范围</Link>
            </div>
          )}
          {feed.items.length === 0 ? (
            <PageEmpty title="还没有与你相关的情报" detail="先关注一个博主或添加一个标的，系统会持续整理相关观点。" action={<Link className="button-primary mt-3" href="/bloggers">选择信息源</Link>} />
          ) : (
            <div className="intelligence-list">
              {feed.items.map((item) => <IntelligenceCard key={item.id} item={item} selected={selected?.id === item.id} onSelect={() => setSelected(item)} />)}
            </div>
          )}
        </section>

        <aside className="dashboard-side">
          {selected ? (
            <div className="evidence-panel">
              <div className="evidence-panel-header"><span><AppIcon name="evidence" />Evidence trail</span><strong>{selected.title}</strong></div>
              <div className="evidence-panel-body">
                <div className="evidence-source"><span>@{selected.evidence.author}</span><span>{selected.time_bucket} · 置信度 {Math.round(selected.confidence * 100)}%</span></div>
                <p className="evidence-excerpt">{selected.evidence.excerpt}</p>
                {(selected.risk_factors.length > 0 || selected.key_points.length > 0) && (
                  <ul className="evidence-points">{(selected.kind === "risk" ? selected.risk_factors : selected.key_points).map((point) => <li key={point}>{point}</li>)}</ul>
                )}
                <div className="score-explain">
                  <div className="score-explain-head"><strong>为什么排在这里</strong><b>{selected.importance_score}</b></div>
                  <div className="score-bars">{Object.entries(selected.score_breakdown).filter(([key, value]) => key in SCORE_LABELS && value > 0).map(([key, value]) => <div key={key}><span>{SCORE_LABELS[key]}</span><i><i style={{ width: `${Math.min(100, Number(value) / 30 * 100)}%` }} /></i><b>+{value}</b></div>)}</div>
                  <p>{selected.score_explanation.join(" · ")}</p>
                </div>
                {selected.supporting_evidence.length > 1 && <div className="supporting-sources"><strong>{selected.corroboration_count} 个独立来源交叉印证</strong>{selected.supporting_evidence.map((evidence, index) => <a key={evidence.source_id} href={evidence.source_url} target="_blank" rel="noreferrer"><span>{index + 1}</span><div><b>@{evidence.author}</b><small>{formatDate(evidence.published_at)}</small></div><AppIcon name="external" /></a>)}</div>}
                <a href={selected.evidence.source_url} target="_blank" rel="noreferrer" className="evidence-link">查看原始推文 <AppIcon name="external" /></a>
              </div>
            </div>
          ) : (
            <div className="dashboard-panel"><h3>选择一条情报</h3><p className="text-xs text-slate-500">查看它的原始来源和分析依据。</p></div>
          )}

        </aside>
      </div>
    </div>
  );
}
