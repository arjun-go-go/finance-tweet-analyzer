"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import AppIcon from "@/components/AppIcon";
import IntelligenceCard from "@/components/IntelligenceCard";
import { PageEmpty, PageError, PageLoading } from "@/components/PageState";
import {
  fetchIntelligenceFeed,
  type IntelligenceFeedItem,
  type IntelligenceFeedResponse,
} from "@/lib/api";

type FeedView = "all" | "watch";
const PRIORITY_THRESHOLD = 65;

function formatToday() {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "long",
    day: "numeric",
    weekday: "long",
  }).format(new Date());
}

function formatEvidenceTime(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatRefreshTime(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function evidenceStrength(item: IntelligenceFeedItem) {
  if (item.corroboration_count > 1) return "多源印证";
  if (item.confidence >= 0.75) return "证据较充分";
  return "单一来源";
}

export default function IntelligenceDashboard() {
  const [feed, setFeed] = useState<IntelligenceFeedResponse | null>(null);
  const [selected, setSelected] = useState<IntelligenceFeedItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [view, setView] = useState<FeedView>("all");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const feedData = await fetchIntelligenceFeed(30, "24h", "all");
      setFeed(feedData);
      setSelected((current) =>
        current
          ? feedData.items.find((item) => item.id === current.id) || null
          : null,
      );
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "无法加载今日情报。");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const personalItems = useMemo(() => {
    if (!feed) return [];
    return feed.items.filter((item) =>
      item.feed_bucket === "personalized"
      && item.match_reasons.includes("关注博主"),
    );
  }, [feed]);

  const visibleItems = useMemo(() => {
    if (view === "watch") {
      return personalItems.filter((item) =>
        item.match_reasons.some((reason) => reason.startsWith("关注标的")),
      );
    }
    return personalItems;
  }, [personalItems, view]);

  if (loading) return <PageLoading label="正在整理今天的重要观点" />;
  if (error || !feed) {
    return <PageError detail={error || "情报接口没有返回数据。"} onRetry={load} />;
  }

  const priority = visibleItems.find((item) => item.importance_score >= PRIORITY_THRESHOLD) || null;
  const scopeReady = feed.context.followed_bloggers > 0;

  return (
    <div className="product-page today-page-v5">
      <header className="today-heading">
        <div>
          <p className="page-eyebrow">{formatToday()}</p>
          <h1>今天</h1>
          <p>
            {scopeReady
              ? personalItems.length
                ? `过去 24 小时，从 ${feed.context.followed_bloggers} 位关注博主中整理出 ${personalItems.length} 条重要更新。`
                : `过去 24 小时，${feed.context.followed_bloggers} 位关注博主没有出现重要变化。`
              : "添加信息源后，这里只展示与你研究范围相关的 Twitter 情报。"}
          </p>
        </div>
        <div className="today-heading-actions">
          <span className="today-freshness"><i />更新于 {formatRefreshTime(feed.context.generated_at)}</span>
          <Link href={`/assistant?prompt=${encodeURIComponent("总结过去24小时我关注的 Twitter 博主的重要观点变化和证据")}`} className="button-primary">
            <AppIcon name="research" />向助手追问
          </Link>
        </div>
      </header>

      {!scopeReady ? <section className="today-first-source">
        <span><AppIcon name="sources" /></span>
        <div><h2>建立你的第一条情报流</h2><p>添加一个长期关注的 Twitter 博主，首批推文完成整理后会自动出现在这里。</p></div>
        <Link href="/sources?add=1" className="button-primary">新增信息源</Link>
      </section> : <section className="today-scope is-live is-compact">
        <span className="today-scope-state"><i /><strong>基于 {feed.context.followed_bloggers} 位关注博主</strong></span>
        <p>{feed.context.tracked_tickers ? `同时聚焦 ${feed.context.tracked_tickers} 个关注标的。` : "这里只保留有证据的重要观点变化。"}</p>
        <div><Link href="/sources">管理信息源</Link>{feed.context.tracked_tickers > 0 && <Link href="/watch">查看关注标的</Link>}</div>
      </section>}

      {scopeReady && priority && (
        <button className="today-priority" onClick={() => setSelected(priority)}>
          <span>现在最重要</span>
          <div>
            <h2>{priority.title}</h2>
            <p>{priority.summary}</p>
          </div>
          <small>{priority.corroboration_count} 个来源 · {priority.tickers.slice(0, 2).join(" / ") || "关注博主"}</small>
          <AppIcon name="arrow" />
        </button>
      )}

      {scopeReady && <div className="today-toolbar">
        <div className="today-view-tabs" aria-label="情报范围">
          {([
            ["all", "全部更新"],
            ...(feed.context.tracked_tickers > 0 ? [["watch", "仅关注标的"]] : []),
          ] as Array<[FeedView, string]>).map(([value, label]) => (
            <button
              key={value}
              className={view === value ? "is-active" : ""}
              onClick={() => { setView(value); setSelected(null); }}
            >
              {label}
            </button>
          ))}
        </div>
        <span>{visibleItems.length} 条</span>
      </div>}

      {selected && <button className="today-preview-backdrop" aria-label="关闭证据预览" onClick={() => setSelected(null)} />}
      {scopeReady && <div className={`today-workspace ${selected ? "has-preview" : ""}`}>
        <section className="today-feed" aria-label="今日情报列表">
          {visibleItems.length === 0 ? (
            <PageEmpty
              title={view === "watch" ? "关注标的暂时没有新观点" : "过去 24 小时没有重要变化"}
              detail={view === "watch" ? "过去 24 小时没有出现需要特别关注的标的观点变化。" : "过去 24 小时没有重要变化；新信息完成分析后会自动更新。"}
              action={view === "watch" ? <Link className="button-secondary mt-3" href="/watch">管理关注标的</Link> : undefined}
            />
          ) : (
            visibleItems.map((item) => (
              <IntelligenceCard
                key={item.id}
                item={item}
                selected={selected?.id === item.id}
                onSelect={() => setSelected(item)}
              />
            ))
          )}
        </section>

        {selected && (
          <aside className="today-preview" id="today-evidence-preview" aria-live="polite">
            <header>
              <div><span>Evidence preview</span><strong>判断依据</strong></div>
              <button onClick={() => setSelected(null)} aria-label="关闭证据预览"><AppIcon name="close" /></button>
            </header>
            <div className="today-preview-body">
              <div className="today-preview-meta">
                <span>@{selected.evidence.author}</span>
                <span>{formatEvidenceTime(selected.evidence.published_at)}</span>
                <b>{evidenceStrength(selected)}</b>
              </div>
              <h2>{selected.title}</h2>
              <p className="today-preview-thesis">{selected.summary}</p>
              <section>
                <span>原文证据</span>
                <blockquote>{selected.evidence.excerpt}</blockquote>
              </section>
              {selected.tickers.length > 0 && <section className="today-preview-identity">
                <span>标的身份</span>
                <div><b><AppIcon name="check" /></b><strong>{selected.tickers.slice(0, 4).join(" · ")}</strong><small>已通过正式标的校验</small></div>
              </section>}
              {(selected.key_points.length > 0 || selected.risk_factors.length > 0) && (
                <section>
                  <span>{selected.kind === "risk" ? "风险边界" : "关键依据"}</span>
                  <ul>
                    {(selected.kind === "risk" ? selected.risk_factors : selected.key_points)
                      .slice(0, 4)
                      .map((point) => <li key={point}>{point}</li>)}
                  </ul>
                </section>
              )}
              <section className="today-preview-ranking">
                <span>为什么显示</span>
                <div>{selected.score_explanation.map((reason) => <b key={reason}>✓ {reason}</b>)}</div>
              </section>
              {selected.supporting_evidence.length > 1 && (
                <section className="today-preview-sources">
                  <span>{selected.corroboration_count} 个独立来源</span>
                  {selected.supporting_evidence.slice(0, 4).map((evidence) => (
                    <a key={evidence.source_id} href={evidence.source_url} target="_blank" rel="noreferrer">
                      <b>@{evidence.author}</b><small>{formatEvidenceTime(evidence.published_at)}</small>
                    </a>
                  ))}
                </section>
              )}
            </div>
            <footer>
              <a href={selected.evidence.source_url} target="_blank" rel="noreferrer" className="button-secondary">查看原推文</a>
              <Link href={`/insights/${encodeURIComponent(selected.id)}`} className="button-primary">完整证据<AppIcon name="arrow" /></Link>
            </footer>
          </aside>
        )}
      </div>}
    </div>
  );
}
