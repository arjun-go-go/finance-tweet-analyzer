"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import ActivityTweetCard, { type ActivityTweet } from "@/components/ActivityTweetCard";
import AppIcon from "@/components/AppIcon";
import ConfirmDialog from "@/components/ConfirmDialog";
import { PageEmpty, PageError, PageLoading } from "@/components/PageState";
import {
  fetchBloggerDetail,
  fetchBloggerIngestionStatus,
  fetchTweets,
  listMyBloggers,
  toggleBloggerFetch,
  unfollowBlogger,
  type BloggerIngestionStatus,
} from "@/lib/api";
import { formatDate } from "@/lib/datetime";

interface BloggerDetail {
  id: string;
  handle: string;
  name: string;
  bio: string | null;
  avatar_url: string | null;
  followers_count: number;
  market_focus: string[] | null;
  profile_updated_at: string | null;
  fetch_enabled: boolean;
  last_fetched_at: string | null;
  profile_url: string | null;
  verified: boolean;
}

const STAGE_LABEL: Record<string, string> = {
  syncing: "正在同步",
  analyzing: "正在分析",
  ready: "采集中",
  attention: "采集需重试",
  paused: "已暂停",
};

export default function BloggerDetailPage({ params }: { params: Promise<{ handle: string }> }) {
  const { handle } = use(params);
  const decodedHandle = decodeURIComponent(handle);
  const cleanHandle = decodedHandle.replace(/^@/, "");
  const [detail, setDetail] = useState<BloggerDetail | null>(null);
  const [tweets, setTweets] = useState<ActivityTweet[]>([]);
  const [tweetTotal, setTweetTotal] = useState(0);
  const [ingestion, setIngestion] = useState<BloggerIngestionStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [fetchToggling, setFetchToggling] = useState(false);
  const [isFollowed, setIsFollowed] = useState(false);
  const [notice, setNotice] = useState("");
  const [showUnfollowConfirm, setShowUnfollowConfirm] = useState(false);
  const [unfollowing, setUnfollowing] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [detailData, tweetData, ingestionData, followedData] = await Promise.all([
        fetchBloggerDetail(decodedHandle),
        fetchTweets({ blogger: decodedHandle, include_analysis: true, limit: 50 }),
        fetchBloggerIngestionStatus(decodedHandle).catch(() => null),
        listMyBloggers().catch(() => ({ items: [] })),
      ]);
      const bloggerDetail = detailData as BloggerDetail;
      setDetail(bloggerDetail);
      setTweets((tweetData.items || []) as ActivityTweet[]);
      setTweetTotal(tweetData.total || 0);
      setIngestion(ingestionData);
      setIsFollowed(followedData.items.some((item) => item.id === bloggerDetail.id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "博主页面加载失败");
    } finally {
      setLoading(false);
    }
  }, [decodedHandle]);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    if (!ingestion || !["syncing", "analyzing"].includes(ingestion.stage)) return;
    const timer = window.setTimeout(async () => {
      const next = await fetchBloggerIngestionStatus(decodedHandle).catch(() => null);
      if (!next) return;
      setIngestion(next);
      if (["ready", "attention"].includes(next.stage)) void load();
    }, 3000);
    return () => window.clearTimeout(timer);
  }, [decodedHandle, ingestion, load]);

  const handleToggleFetch = async () => {
    if (!detail) return;
    setFetchToggling(true);
    setNotice("");
    try {
      const nextEnabled = !detail.fetch_enabled;
      await toggleBloggerFetch(decodedHandle, nextEnabled);
      setDetail((current) => current ? { ...current, fetch_enabled: nextEnabled } : current);
      setIngestion((current) => current ? {
        ...current,
        fetch_enabled: nextEnabled,
        stage: nextEnabled ? "syncing" : "paused",
        message: nextEnabled ? "定时采集已恢复，等待下一次同步。" : "定时采集已暂停。",
      } : current);
      setNotice(nextEnabled ? "已恢复定时采集" : "已暂停定时采集");
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : "更新失败，请稍后重试");
    } finally {
      setFetchToggling(false);
    }
  };

  const handleUnfollow = async () => {
    if (!detail) return;
    setShowUnfollowConfirm(false);
    setUnfollowing(true);
    setNotice("");
    try {
      await unfollowBlogger(detail.id);
      setIsFollowed(false);
      setNotice("已取消关注；历史推文仍会保留。");
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : "取消关注失败，请稍后重试。");
    } finally {
      setUnfollowing(false);
    }
  };

  if (loading) return <PageLoading label="正在加载博主页" />;
  if (error || !detail) return <PageError detail={error || "博主不存在或加载失败"} onRetry={load} />;

  const stage = ingestion?.stage || (detail.fetch_enabled ? "ready" : "paused");

  return (
    <div className="blogger-core-page">
      <Link className="insight-back" href="/sources"><AppIcon name="arrow" />返回博主</Link>

      <header className="blogger-core-hero">
        <div className="blogger-core-profile">
          {detail.avatar_url
            ? <img src={detail.avatar_url} alt="" />
            : <span>{cleanHandle.slice(0, 2).toUpperCase()}</span>}
          <div>
            <h1>{detail.name || `@${cleanHandle}`}{detail.verified && <i>✓</i>}</h1>
            <strong>@{cleanHandle}</strong>
            {detail.bio && <p>{detail.bio}</p>}
            {(detail.market_focus || []).length > 0 && <div>{(detail.market_focus || []).map((market) => <span key={market}>{market}</span>)}</div>}
          </div>
        </div>
        <div className="blogger-core-actions">
          {isFollowed ? <button className={detail.fetch_enabled ? "is-active" : ""} type="button" onClick={() => void handleToggleFetch()} disabled={fetchToggling}>
            <i />{fetchToggling ? "更新中…" : detail.fetch_enabled ? "定时采集中" : "已暂停采集"}
          </button> : <Link href="/sources?add=1">关注博主</Link>}
          <a href={`https://x.com/${cleanHandle}`} target="_blank" rel="noreferrer">查看 Twitter <AppIcon name="external" /></a>
          {isFollowed && <button type="button" className="is-danger" onClick={() => setShowUnfollowConfirm(true)} disabled={unfollowing}>{unfollowing ? "处理中…" : "取消关注"}</button>}
        </div>
      </header>

      <div className="blogger-core-meta">
        <span className={`state-${stage}`}><i />{STAGE_LABEL[stage] || "采集中"}</span>
        <span>最近采集 {detail.last_fetched_at ? formatDate(detail.last_fetched_at) : "尚未完成"}</span>
        <span>{tweetTotal} 条推文</span>
        <span>{detail.followers_count.toLocaleString()} 位关注者</span>
      </div>

      {notice && <p className="blogger-core-notice" role="status">{notice}</p>}
      {ingestion && ["syncing", "analyzing", "attention"].includes(ingestion.stage) && (
        <p className="blogger-core-progress">{ingestion.message} · {ingestion.analyzed_tweets} / {ingestion.collected_tweets} 条已分析</p>
      )}

      <div className="blogger-core-section-heading"><h2>推文</h2><span>{tweets.length < tweetTotal ? `最近 ${tweets.length} 条` : `${tweetTotal} 条`}</span></div>
      {tweets.length ? (
        <section className="activity-feed blogger-activity-feed" aria-label={`${detail.name || cleanHandle} 的推文`}>
          {tweets.map((tweet) => <ActivityTweetCard key={tweet.id} tweet={tweet} />)}
        </section>
      ) : <PageEmpty title="尚未采集到推文" detail="首次采集完成后，原文、逐标的观点和市场判断会显示在这里。" />}

      <ConfirmDialog
        open={showUnfollowConfirm}
        title="取消关注博主"
        message={`取消关注 @${cleanHandle} 后，它将不再进入你的动态和标的观点聚合。历史推文会保留，定时抓取设置不会改变。`}
        confirmText="取消关注"
        variant="danger"
        onConfirm={handleUnfollow}
        onCancel={() => setShowUnfollowConfirm(false)}
      />
    </div>
  );
}
