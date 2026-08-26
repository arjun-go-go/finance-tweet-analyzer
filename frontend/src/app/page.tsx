"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import AppIcon from "@/components/AppIcon";
import IntelligenceCard from "@/components/IntelligenceCard";
import { PageEmpty, PageError, PageLoading } from "@/components/PageState";
import {
  fetchIntelligenceDigest,
  fetchIntelligenceFeed,
  type IntelligenceDigestResponse,
  type IntelligenceFeedItem,
  type IntelligenceFeedResponse,
} from "@/lib/api";

type FeedView = "related" | "latest" | "watch";
type WindowRange = "24h" | "3d" | "7d";

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

export default function IntelligenceDashboard() {
  const [feed, setFeed] = useState<IntelligenceFeedResponse | null>(null);
  const [digest, setDigest] = useState<IntelligenceDigestResponse | null>(null);
  const [selected, setSelected] = useState<IntelligenceFeedItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [windowRange, setWindowRange] = useState<WindowRange>("24h");
  const [view, setView] = useState<FeedView>("related");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [feedData, digestData] = await Promise.all([
        fetchIntelligenceFeed(30, windowRange, "all"),
        fetchIntelligenceDigest(),
      ]);
      setFeed(feedData);
      setDigest(digestData);
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
  }, [windowRange]);

  useEffect(() => {
    load();
  }, [load]);

  const visibleItems = useMemo(() => {
    if (!feed) return [];
    if (view === "latest") {
      return [...feed.items].sort(
        (left, right) =>
          new Date(right.published_at).getTime() - new Date(left.published_at).getTime(),
      );
    }
    if (view === "watch") {
      return feed.items.filter((item) =>
        item.match_reasons.some((reason) => reason.startsWith("关注标的")),
      );
    }
    if (!feed.context.personalized) return feed.items;
    return feed.items.filter((item) => item.feed_bucket === "personalized");
  }, [feed, view]);

  if (loading) return <PageLoading label="正在整理今天的重要观点" />;
  if (error || !feed) {
    return <PageError detail={error || "情报接口没有返回数据。"} onRetry={load} />;
  }

  const priority = digest?.highlights[0] || feed.items[0] || null;
  const scopeReady = feed.context.personalized;

  return (
    <div className="product-page today-page-v5">
      <header className="today-heading">
        <div>
          <p className="page-eyebrow">{formatToday()}</p>
          <h1>今天</h1>
          <p>
            {visibleItems.length
              ? `${visibleItems.length} 条值得看，按与你的关注范围和证据质量排序。`
              : "暂时没有匹配当前范围的新情报。"}
          </p>
        </div>
        <div className="today-heading-actions">
          <span className="today-freshness"><i />刚刚更新</span>
          <Link href="/assistant" className="button-primary">
            <AppIcon name="research" />向助手追问
          </Link>
        </div>
      </header>

      <section className={`today-scope ${scopeReady ? "is-live" : ""}`}>
        <span className="today-scope-state"><i /><strong>{scopeReady ? "你的研究范围正在生效" : "当前显示市场补充情报"}</strong></span>
        <p>{scopeReady ? "这里只保留与你关注的博主或标的相关的重要变化。" : "关注信息源或标的后，这里会自动切换为个性化情报。"}</p>
        <div>
          <Link href="/sources">{feed.context.followed_bloggers} 个信息源</Link>
          <Link href="/watch">{feed.context.tracked_tickers} 个标的</Link>
        </div>
      </section>

      {priority && (
        <button className="today-priority" onClick={() => setSelected(priority)}>
          <span>现在最重要</span>
          <div>
            <h2>{priority.title}</h2>
            <p>{priority.summary}</p>
          </div>
          <small>{priority.corroboration_count} 个来源 · 重要性 {priority.importance_score}</small>
          <AppIcon name="arrow" />
        </button>
      )}

      <div className="today-toolbar">
        <div className="today-view-tabs" aria-label="情报范围">
          {([
            ["related", "与你相关"],
            ["latest", "最新"],
            ["watch", "仅关注标的"],
          ] as Array<[FeedView, string]>).map(([value, label]) => (
            <button
              key={value}
              className={view === value ? "is-active" : ""}
              onClick={() => setView(value)}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="today-window-tabs" aria-label="时间范围">
          {([
            ["24h", "24 小时"],
            ["3d", "3 天"],
            ["7d", "7 天"],
          ] as Array<[WindowRange, string]>).map(([value, label]) => (
            <button
              key={value}
              className={windowRange === value ? "is-active" : ""}
              onClick={() => setWindowRange(value)}
            >
              {label}
            </button>
          ))}
        </div>
        <span>{visibleItems.length} 条</span>
      </div>

      {selected && <button className="today-preview-backdrop" aria-label="关闭证据预览" onClick={() => setSelected(null)} />}
      <div className={`today-workspace ${selected ? "has-preview" : ""}`}>
        <section className="today-feed" aria-label="今日情报列表">
          {visibleItems.length === 0 ? (
            <PageEmpty
              title={view === "watch" ? "关注标的暂时没有新观点" : "当前范围没有新情报"}
              detail="可以调整时间范围，或新增一个长期关注的信息源。"
              action={<Link className="button-primary mt-3" href="/sources?add=1">新增信息源</Link>}
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
                <b>{Math.round(selected.confidence * 100)}% 置信度</b>
              </div>
              <h2>{selected.title}</h2>
              <p className="today-preview-thesis">{selected.summary}</p>
              <section>
                <span>原文证据</span>
                <blockquote>{selected.evidence.excerpt}</blockquote>
              </section>
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
      </div>
    </div>
  );
}
