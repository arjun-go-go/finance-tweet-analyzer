"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import ActivityTweetCard, { ActivityAnalysisPanel, type ActivityTweet } from "@/components/ActivityTweetCard";
import AppIcon from "@/components/AppIcon";
import OpinionChanges from "@/components/OpinionChanges";
import { PageEmpty, PageError, PageLoading } from "@/components/PageState";
import { fetchAnalysisStatus, fetchTweets, type AnalysisStatus } from "@/lib/api";

type TimelineFilter = "all" | "instrument" | "market";
type FeedFilter = TimelineFilter | "changes";
const PAGE_SIZE = 20;
const FILTERS: Array<{ value: FeedFilter; label: string }> = [
  { value: "all", label: "全部" },
  { value: "changes", label: "关注变化" },
  { value: "instrument", label: "标的观点" },
  { value: "market", label: "市场宏观" },
];

export default function ActivityPage() {
  const [filter, setFilter] = useState<FeedFilter>("all");
  const [analysisStatus, setAnalysisStatus] = useState<AnalysisStatus | null>(null);

  useEffect(() => {
    void fetchAnalysisStatus().then(setAnalysisStatus).catch(() => undefined);
  }, []);

  return (
    <div className="activity-page">
      <header className="activity-page-header">
        <div>
          <h1>动态</h1>
          <p>看全部推文，或追踪你关注的博主改了哪些判断。</p>
        </div>
        <Link href="/sources?add=1" className="button-secondary"><AppIcon name="plus" />添加博主</Link>
      </header>

      {analysisStatus && !analysisStatus.enabled && (
        <div className="analysis-pause-banner" role="status">
          <AppIcon name="alerts" />
          <div>
            <strong>{analysisStatus.message || "大模型分析当前已暂停"}</strong>
            <span>采集与归档继续。恢复时可以选择仅分析新增，或一起补跑历史。</span>
          </div>
        </div>
      )}

      <div className="activity-toolbar">
        <nav aria-label="动态筛选">
          {FILTERS.map((item) => (
            <button
              key={item.value}
              type="button"
              aria-pressed={filter === item.value}
              className={filter === item.value ? "is-active" : ""}
              onClick={() => setFilter(item.value)}
            >
              {item.label}
            </button>
          ))}
        </nav>
      </div>

      {filter === "changes" ? <OpinionChanges /> : <TweetTimeline key={filter} filter={filter} />}
    </div>
  );
}

function TweetTimeline({ filter }: { filter: TimelineFilter }) {
  const [tweets, setTweets] = useState<ActivityTweet[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");
  const [selectedTweetId, setSelectedTweetId] = useState<string | null>(null);
  const [analysisOpen, setAnalysisOpen] = useState(false);

  const load = useCallback(async (offset: number, signal?: AbortSignal) => {
    if (offset === 0) setLoading(true);
    else setLoadingMore(true);
    setError("");
    try {
      const result = await fetchTweets({
        analysis_kind: filter === "all" ? undefined : filter,
        include_analysis: true,
        limit: PAGE_SIZE,
        offset,
      }, signal) as { items: ActivityTweet[]; total: number };
      if (signal?.aborted) return;
      setTotal(result.total);
      setTweets((current) => offset === 0 ? result.items : [...current, ...result.items]);
    } catch {
      if (!signal?.aborted) setError("动态加载失败，请稍后重试。");
    } finally {
      if (!signal?.aborted) {
        setLoading(false);
        setLoadingMore(false);
      }
    }
  }, [filter]);

  useEffect(() => {
    const request = new AbortController();
    void load(0, request.signal);
    return () => request.abort();
  }, [load]);

  const selectedTweet = tweets.find((tweet) => tweet.id === selectedTweetId) || tweets[0] || null;
  const hasMore = tweets.length < total;
  if (loading) return <PageLoading label="正在加载最新推文" />;
  if (error && !tweets.length) {
    return <PageError detail={error} onRetry={() => void load(0)} />;
  }
  if (!tweets.length) {
    const filtered = filter !== "all";
    return (
      <PageEmpty
        title={filter === "instrument" ? "当前没有标的观点" : filter === "market" ? "当前没有市场宏观判断" : "还没有推文"}
        detail={filtered ? "新的相关推文完成分析后会显示在这里。" : "添加一个博主，首次采集完成后就能在这里查看原文和分析。"}
        action={filtered ? undefined : <Link className="button-primary mt-3" href="/sources?add=1">添加第一个博主</Link>}
      />
    );
  }

  return (
    <>
      <p className="activity-view-note">已显示 {tweets.length} / {total} 条推文</p>
      <div className="activity-workbench">
        <section className="activity-feed" aria-label="推文动态">
          {tweets.map((tweet) => (
            <ActivityTweetCard
              key={tweet.id}
              tweet={tweet}
              selectable
              selected={selectedTweet?.id === tweet.id}
              onOpenAnalysis={() => {
                setSelectedTweetId(tweet.id);
                setAnalysisOpen(true);
              }}
            />
          ))}
        </section>
        {selectedTweet && (
          <>
            <button
              className={`activity-inspector-backdrop ${analysisOpen ? "is-open" : ""}`}
              type="button"
              aria-label="关闭分析面板"
              onClick={() => setAnalysisOpen(false)}
            />
            <aside className={`activity-inspector ${analysisOpen ? "is-open" : ""}`} aria-label="选中推文分析">
              <ActivityAnalysisPanel key={selectedTweet.id} tweet={selectedTweet} onClose={() => setAnalysisOpen(false)} />
            </aside>
          </>
        )}
      </div>
      {error && <p className="activity-load-error">{error}</p>}
      {hasMore && (
        <button className="activity-load-more" type="button" disabled={loadingMore} onClick={() => void load(tweets.length)}>
          {loadingMore ? "正在加载…" : "加载更早的推文"}
        </button>
      )}
    </>
  );
}
