"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import ActivityTweetCard, { ActivityAnalysisPanel, type ActivityTweet } from "@/components/ActivityTweetCard";
import AppIcon from "@/components/AppIcon";
import { PageEmpty, PageError, PageLoading } from "@/components/PageState";
import { fetchTweets } from "@/lib/api";

type FeedFilter = "all" | "instrument" | "market";

interface TweetFeedResponse {
  items: ActivityTweet[];
  total: number;
}

const PAGE_SIZE = 20;

const FILTERS: Array<{ value: FeedFilter; label: string }> = [
  { value: "all", label: "全部" },
  { value: "instrument", label: "标的观点" },
  { value: "market", label: "市场宏观" },
];

function matchesFilter(tweet: ActivityTweet, filter: FeedFilter) {
  if (filter === "instrument") return Boolean(tweet.analysis?.claims?.length);
  if (filter === "market") return Boolean(tweet.analysis?.market_views?.length);
  return true;
}

export default function ActivityPage() {
  const [tweets, setTweets] = useState<ActivityTweet[]>([]);
  const [total, setTotal] = useState(0);
  const [filter, setFilter] = useState<FeedFilter>("all");
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");
  const [selectedTweetId, setSelectedTweetId] = useState<string | null>(null);
  const [analysisOpen, setAnalysisOpen] = useState(false);

  const load = useCallback(async (reset = false) => {
    if (reset) setLoading(true);
    else setLoadingMore(true);
    setError("");
    try {
      const offset = reset ? 0 : tweets.length;
      const result = await fetchTweets({
        include_analysis: true,
        limit: PAGE_SIZE,
        offset,
      }) as TweetFeedResponse;
      setTotal(result.total);
      setTweets((current) => reset ? result.items : [...current, ...result.items]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "动态加载失败，请稍后重试。");
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, [tweets.length]);

  useEffect(() => {
    void load(true);
    // Initial fetch only; later offsets are driven by the explicit load-more action.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const visibleTweets = useMemo(
    () => tweets.filter((tweet) => matchesFilter(tweet, filter)),
    [filter, tweets],
  );
  const selectedTweet = useMemo(
    () => visibleTweets.find((tweet) => tweet.id === selectedTweetId) || visibleTweets[0] || null,
    [selectedTweetId, visibleTweets],
  );
  const hasMore = tweets.length < total;

  if (loading) return <PageLoading label="正在加载最新推文" />;
  if (error && tweets.length === 0) {
    return <PageError detail="动态加载失败，请检查服务连接后重试。" onRetry={() => void load(true)} />;
  }

  return (
    <div className="activity-page">
      <header className="activity-page-header">
        <div>
          <h1>动态</h1>
          <p>按时间查看已获取的推文，以及其中逐标的观点和市场判断。</p>
        </div>
        <Link href="/sources?add=1" className="button-secondary"><AppIcon name="plus" />添加博主</Link>
      </header>

      <div className="activity-toolbar">
        <nav aria-label="动态筛选">
          {FILTERS.map((item) => (
            <button
              key={item.value}
              type="button"
              className={filter === item.value ? "is-active" : ""}
              onClick={() => {
                setFilter(item.value);
                setSelectedTweetId(null);
                setAnalysisOpen(false);
              }}
            >
              {item.label}
            </button>
          ))}
        </nav>
        <span>{tweets.length ? `已载入 ${tweets.length} / ${total}` : "暂无推文"}</span>
      </div>

      {tweets.length === 0 ? (
        <PageEmpty
          title="还没有推文"
          detail="添加一个 Twitter 博主，首次采集完成后，原文与分析会按时间出现在这里。"
          action={<Link className="button-primary mt-3" href="/sources?add=1">添加第一个博主</Link>}
        />
      ) : visibleTweets.length === 0 ? (
        <PageEmpty
          title={filter === "instrument" ? "当前没有标的观点" : "当前没有市场宏观判断"}
          detail={hasMore ? "当前已载入的推文中没有匹配内容，可以继续加载更早的推文。" : "新的相关推文完成分析后会显示在这里。"}
        />
      ) : (
        <div className="activity-workbench">
          <section className="activity-feed" aria-label="推文动态">
            {visibleTweets.map((tweet) => (
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
      )}

      {error && tweets.length > 0 && <p className="activity-load-error">加载更多失败，请稍后重试。</p>}
      {hasMore && (
        <button className="activity-load-more" type="button" disabled={loadingMore} onClick={() => void load(false)}>
          {loadingMore ? "正在加载…" : "加载更早的推文"}
        </button>
      )}
    </div>
  );
}
