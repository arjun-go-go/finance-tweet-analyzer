"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import AppIcon from "@/components/AppIcon";
import PredictionCard, { PredictionItem } from "@/components/PredictionCard";
import { PageEmpty, PageError, PageLoading } from "@/components/PageState";
import { MetricStrip, SegmentedControl } from "@/components/WorkspacePage";
import {
  fetchBloggerDetail,
  fetchBloggerIngestionStatus,
  fetchBloggerPredictions,
  fetchTweets,
  toggleBloggerFetch,
  type BloggerIngestionStatus,
} from "@/lib/api";
import { formatDate } from "@/lib/datetime";

interface BloggerDetail {
  handle: string;
  name: string;
  bio: string | null;
  avatar_url: string | null;
  followers_count: number;
  market_focus: string[] | null;
  profile_updated_at: string | null;
  credibility_score: number;
  score_status: string;
  score_label: string;
  sample_confidence: number;
  verified_count: number;
  pending_count: number;
  hit_rate_overall: number | null;
  hit_rate_by_sentiment: { bullish: number | null; bearish: number | null; neutral: number | null };
  top_tickers: Array<{ ticker: string; verified: number; hit_rate: number }>;
  fetch_enabled: boolean;
  last_fetched_at: string | null;
  profile_url: string | null;
  verified: boolean;
}

interface BloggerTweet {
  id: string;
  tweet_id: string;
  content: string;
  published_at: string;
  status: string;
  tweet_type: string;
  analysis?: {
    analysis_schema_version?: string;
    is_investment_relevant?: boolean;
    statement_type?: string;
    overall_sentiment?: string;
    thesis?: string;
    key_points?: string[];
    tickers?: Array<{
      symbol?: string;
      verification?: { canonical_symbol?: string; downstream_eligible?: boolean };
    }>;
  } | null;
}

type PageTab = "insights" | "predictions";
type PredictionTab = "pending" | "verified" | "all";

const STATEMENT_LABELS: Record<string, string> = {
  recommendation: "投资建议",
  prediction: "方向预测",
  news_relay: "新闻转述",
  recap: "市场复盘",
  risk_warning: "风险提示",
  fact: "事实信息",
  opinion: "作者观点",
  non_investment: "非投资信息",
};
const SENTIMENT_LABELS: Record<string, string> = { bullish: "看好", bearish: "看空", neutral: "中性", mixed: "分化" };
const STATUS_LABELS: Record<string, string> = {
  analyzed: "已提取",
  pending: "待分析",
  analyzing: "分析中",
  retrying: "等待重试",
  failed: "分析失败",
};

function verifiedSymbols(tweet: BloggerTweet): string[] {
  return (tweet.analysis?.tickers ?? [])
    .filter((ticker) => ticker.verification?.downstream_eligible)
    .map((ticker) => ticker.verification?.canonical_symbol || ticker.symbol || "")
    .filter(Boolean);
}

export default function BloggerDetailPage({ params }: { params: Promise<{ handle: string }> }) {
  const { handle } = use(params);
  const decodedHandle = decodeURIComponent(handle);
  const cleanHandle = decodedHandle.replace(/^@/, "");
  const [detail, setDetail] = useState<BloggerDetail | null>(null);
  const [tweets, setTweets] = useState<BloggerTweet[]>([]);
  const [tweetTotal, setTweetTotal] = useState(0);
  const [pageTab, setPageTab] = useState<PageTab>("insights");
  const [predictionTab, setPredictionTab] = useState<PredictionTab>("pending");
  const [predictions, setPredictions] = useState<PredictionItem[]>([]);
  const [predictionTotal, setPredictionTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [predictionsLoading, setPredictionsLoading] = useState(false);
  const [fetchToggling, setFetchToggling] = useState(false);
  const [fetchNotice, setFetchNotice] = useState("");
  const [ingestion, setIngestion] = useState<BloggerIngestionStatus | null>(null);

  const loadOverview = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [detailData, tweetData, ingestionData] = await Promise.all([
        fetchBloggerDetail(decodedHandle),
        fetchTweets({ blogger: decodedHandle, include_analysis: true, limit: 20 }),
        fetchBloggerIngestionStatus(decodedHandle).catch(() => null),
      ]);
      setDetail(detailData as BloggerDetail);
      setTweets((tweetData.items ?? []) as BloggerTweet[]);
      setTweetTotal(tweetData.total ?? 0);
      setIngestion(ingestionData);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "信息源加载失败");
    } finally {
      setLoading(false);
    }
  }, [decodedHandle]);

  const loadPredictions = useCallback(async (status: PredictionTab) => {
    setPredictionsLoading(true);
    try {
      const data = await fetchBloggerPredictions(decodedHandle, { status, limit: 50 });
      setPredictions(data.items);
      setPredictionTotal(data.total);
    } finally {
      setPredictionsLoading(false);
    }
  }, [decodedHandle]);

  useEffect(() => { loadOverview(); }, [loadOverview]);
  useEffect(() => {
    if (!ingestion || !["syncing", "analyzing"].includes(ingestion.stage)) return;
    const timer = window.setTimeout(async () => {
      const next = await fetchBloggerIngestionStatus(decodedHandle).catch(() => null);
      if (next) {
        setIngestion(next);
        if (next.stage === "ready" || next.stage === "attention") loadOverview();
      }
    }, 3000);
    return () => window.clearTimeout(timer);
  }, [decodedHandle, ingestion, loadOverview]);
  useEffect(() => {
    if (pageTab === "predictions") loadPredictions(predictionTab);
  }, [loadPredictions, pageTab, predictionTab]);

  const handleVerified = (next: PredictionItem) => {
    if (predictionTab === "pending" && next.verdict !== null) {
      setPredictions((current) => current.filter((item) => item.id !== next.id));
      setPredictionTotal((current) => Math.max(0, current - 1));
    } else {
      setPredictions((current) => current.map((item) => item.id === next.id ? next : item));
    }
    loadOverview();
  };

  const handleToggleFetch = async () => {
    if (!detail) return;
    setFetchToggling(true);
    setFetchNotice("");
    try {
      const nextEnabled = !detail.fetch_enabled;
      await toggleBloggerFetch(decodedHandle, nextEnabled);
      setDetail((current) => current ? { ...current, fetch_enabled: nextEnabled } : current);
      setIngestion((current) => current ? { ...current, fetch_enabled: nextEnabled, stage: nextEnabled ? "syncing" : "paused", message: nextEnabled ? "定时采集已恢复，等待下一次同步。" : "定时采集已暂停，已经保存的内容仍会保留。" } : current);
      setFetchNotice(nextEnabled ? "已开启定时抓取" : "已暂停定时抓取");
    } catch (toggleError) {
      setFetchNotice(toggleError instanceof Error ? toggleError.message : "更新失败，请稍后重试");
    } finally {
      setFetchToggling(false);
    }
  };

  if (loading) return <PageLoading label="正在整理信息源档案" />;
  if (error || !detail) return <PageError detail={error || "博主不存在或加载失败"} onRetry={loadOverview} />;

  const analyzedCount = tweets.filter((tweet) => Boolean(tweet.analysis)).length;
  const hitRate = detail.hit_rate_overall == null ? "—" : `${Math.round(detail.hit_rate_overall * 100)}%`;

  return <div className="product-page source-detail-page">
    <section className="source-detail-hero">
      <div className="source-detail-identity">
        {detail.avatar_url
          ? <img src={detail.avatar_url} alt="" />
          : <span className="source-detail-avatar">{cleanHandle.slice(0, 2).toUpperCase()}</span>}
        <div>
          <p className="page-eyebrow">Twitter intelligence source</p>
          <h1>{detail.name || `@${cleanHandle}`}{detail.verified && <span className="source-verified">✓</span>}</h1>
          <strong>@{cleanHandle}</strong>
          {detail.bio && <p>{detail.bio}</p>}
          <div className="source-detail-tags">{(detail.market_focus ?? []).map((market) => <span key={market}>{market}</span>)}</div>
        </div>
      </div>
      <div className="source-detail-actions">
        <button className={`source-fetch-toggle ${detail.fetch_enabled ? "is-active" : ""}`} onClick={handleToggleFetch} disabled={fetchToggling}>
          <i />{fetchToggling ? "更新中…" : detail.fetch_enabled ? "定时抓取中" : "定时抓取已暂停"}
        </button>
        <a className="button-secondary" href={detail.profile_url || `https://x.com/${cleanHandle}`} target="_blank" rel="noreferrer">查看 Twitter <AppIcon name="external" /></a>
        {fetchNotice && <span className="source-fetch-notice">{fetchNotice}</span>}
      </div>
    </section>

    <div className="source-freshness">
      <span>最近抓取：{detail.last_fetched_at ? formatDate(detail.last_fetched_at) : "尚未完成首次抓取"}</span>
      <span>资料更新：{detail.profile_updated_at ? formatDate(detail.profile_updated_at) : "暂无记录"}</span>
      <span>{detail.followers_count.toLocaleString()} 位关注者</span>
    </div>

    {ingestion && ingestion.stage !== "ready" && <section className={`source-ingestion-banner state-${ingestion.stage}`}>
      <div>
        <span className="source-ingestion-mark">{ingestion.stage === "attention" ? "!" : ingestion.stage === "paused" ? "Ⅱ" : <i />}</span>
        <div><strong>{ingestion.stage === "syncing" ? "首次同步中" : ingestion.stage === "analyzing" ? "正在提取投资信息" : ingestion.stage === "attention" ? "部分内容处理失败" : "定时采集已暂停"}</strong><p>{ingestion.message}</p></div>
      </div>
      <span>{ingestion.analyzed_tweets} / {ingestion.collected_tweets} 条已提取</span>
    </section>}

    <MetricStrip items={[
      { label: "预测评分", value: detail.verified_count ? Math.round(detail.credibility_score) : "—", note: detail.score_label },
      { label: "已采集推文", value: tweetTotal, note: `最近 ${analyzedCount} 条已提取` },
      { label: "预测命中率", value: hitRate, note: `${detail.pending_count} 条等待验证` },
    ]} />
    <div className="source-score-disclosure"><strong>评分说明</strong><span>预测评分使用贝叶斯平滑，避免少量样本产生极端排名；当前样本充分度 {Math.round(detail.sample_confidence * 100)}%，原始命中率与评分分开展示。</span></div>

    <div className="source-detail-nav">
      <SegmentedControl value={pageTab} options={[{ value: "insights", label: "最新推文与提取" }, { value: "predictions", label: `预测记录 ${detail.pending_count ? `(${detail.pending_count})` : ""}` }]} onChange={setPageTab} />
      {pageTab === "insights" && <Link href={`/tweets?blogger=${encodeURIComponent(decodedHandle)}`}>查看全部推文 <AppIcon name="arrow" /></Link>}
    </div>

    {pageTab === "insights" ? (
      tweets.length === 0 ? <PageEmpty title="尚未采集到推文" detail="首次抓取任务完成后，原推文和投资信息提取结果会显示在这里。" />
        : <div className="source-tweet-stream">{tweets.map((tweet) => {
          const analysis = tweet.analysis;
          const tickers = verifiedSymbols(tweet);
          const summary = analysis?.thesis || analysis?.key_points?.[0];
          return <article className="source-tweet-item" key={tweet.id}>
            <div className="source-tweet-meta">
              <span>{formatDate(tweet.published_at)}</span>
              <span>{tweet.tweet_type === "original" ? "原创" : tweet.tweet_type === "quote" ? "引用推文" : tweet.tweet_type === "reply" ? "回复" : "转推"}</span>
              <span className={`source-analysis-state state-${tweet.status}`}>{STATUS_LABELS[tweet.status] || tweet.status}</span>
            </div>
            <p className="source-tweet-content">{tweet.content}</p>
            {analysis && <div className="source-extraction">
              <div>
                <span>{STATEMENT_LABELS[analysis.statement_type || ""] || "投资信息"}</span>
                {analysis.overall_sentiment && <span className={`direction direction-${analysis.overall_sentiment}`}>{SENTIMENT_LABELS[analysis.overall_sentiment] || analysis.overall_sentiment}</span>}
                {tickers.map((ticker) => <span className="ticker-chip" key={ticker}>{ticker}</span>)}
              </div>
              <p>{summary || "已完成结构化提取，暂无独立论点摘要。"}</p>
            </div>}
            <footer>
              <a href={`https://x.com/${cleanHandle}/status/${tweet.tweet_id}`} target="_blank" rel="noreferrer">查看原推文 <AppIcon name="external" /></a>
            </footer>
          </article>;
        })}</div>
    ) : <section className="source-predictions">
      <div className="source-prediction-toolbar">
        <div><h2>预测记录</h2><p>这里只保留满足严格预测创建规则的可验证判断。</p></div>
        <SegmentedControl value={predictionTab} options={[{ value: "pending", label: `待验证 ${detail.pending_count}` }, { value: "verified", label: `已验证 ${detail.verified_count}` }, { value: "all", label: "全部" }]} onChange={setPredictionTab} />
      </div>
      {predictionsLoading ? <PageLoading label="正在加载预测记录" />
        : predictions.length === 0 ? <PageEmpty title="当前没有预测记录" detail="只有具备作者归因、方向、期限和已验证标的的判断才会进入这里。" />
          : <div className="grid gap-4">{predictions.map((prediction) => <PredictionCard key={prediction.id} prediction={prediction} onChanged={handleVerified} />)}</div>}
      {predictionTotal > 0 && <p className="source-result-count">共 {predictionTotal} 条</p>}
    </section>}
  </div>;
}
