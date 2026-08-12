"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { fetchTweets, fetchAnalyses, triggerAnalysis, analyzeBlogger, analyzeSingleTweet } from "@/lib/api";
import TweetAnalysisCard from "@/components/TweetAnalysisCard";
import FilterBar from "@/components/FilterBar";
import SkeletonCard from "@/components/SkeletonCard";
import AppIcon from "@/components/AppIcon";
import { PageEmpty } from "@/components/PageState";
import { MetricStrip, Pagination, SectionTitle, WorkspacePageHeader } from "@/components/WorkspacePage";
import type { TweetMediaItem } from "@/components/TweetMediaGallery";

// ============================================================
// Types
// ============================================================

interface TweetMetrics {
  likes?: number;
  retweets?: number;
  views?: number;
}

interface AnalysisData {
  tickers: Array<{
    symbol: string;
    original_name: string;
    sentiment: string;
    horizon: string;
    market?: string;
    exchange?: string;
    asset_type?: string;
    listing_status?: string;
    tradable?: boolean;
    validation_status?: string;
    validation_sources?: string[];
    external_ids?: Record<string, string>;
    validated_at?: string;
    risks?: Array<{
      category: string;
      description: string;
      severity: string;
      urgency: string;
    }>;
    ticker_risk_level?: string;
  }>;
  overall_sentiment: string;
  key_points: string[];
  risk_factors: string[];
  risk_level?: string;
  risk_summary?: string;
  confidence: number;
  is_investment_related: boolean;
  reasoning?: string;
  media_summary?: string;
  media_evidence?: string[];
  text_image_consistency?: string;
  media_confidence?: number;
}

interface TweetItem {
  id: string;
  tweet_id: string;
  author_handle: string;
  author_name: string;
  content: string;
  published_at: string;
  status: string;
  metrics: TweetMetrics | null;
  analysis?: AnalysisData | null;
  media?: TweetMediaItem[];
}

interface AnalysisItem {
  id: string;
  tweet_id: string;
  twitter_tweet_id?: string;
  author_handle: string;
  content: string;
  published_at: string;
  created_at: string;
  analysis: AnalysisData;
  confidence: number;
  media?: TweetMediaItem[];
}

interface DisplayItem {
  id: string;
  tweetId: string;
  authorHandle: string;
  authorName?: string;
  content: string;
  publishedAt: string;
  status: string;
  metrics?: TweetMetrics | null;
  analysis?: AnalysisData | null;
  twitterTweetId?: string;
  media?: TweetMediaItem[];
}

// ============================================================
// Constants
// ============================================================

const PAGE_SIZE = 20;

const TWEET_TABS = [
  { label: "全部", value: "all", api: "tweets" as const },
  { label: "待分析", value: "pending", api: "tweets" as const },
  { label: "已分析", value: "analyzed", api: "tweets" as const },
];

const SENTIMENT_TABS = [
  { label: "看好", value: "bullish", api: "analyses" as const },
  { label: "看空", value: "bearish", api: "analyses" as const },
  { label: "中性", value: "neutral", api: "analyses" as const },
  { label: "分化", value: "mixed", api: "analyses" as const },
];

const ALL_TABS = [...TWEET_TABS, ...SENTIMENT_TABS];

function isSentimentTab(tab: string): boolean {
  return SENTIMENT_TABS.some((t) => t.value === tab);
}

// ============================================================
// Helpers
// ============================================================

function tweetToDisplay(item: TweetItem): DisplayItem {
  return {
    id: item.id,
    tweetId: item.tweet_id,
    authorHandle: item.author_handle,
    authorName: item.author_name || undefined,
    content: item.content,
    publishedAt: item.published_at,
    status: item.status,
    metrics: item.metrics,
    analysis: item.analysis || null,
    twitterTweetId: item.tweet_id,
    media: item.media || [],
  };
}

function analysisToDisplay(item: AnalysisItem): DisplayItem {
  return {
    id: item.tweet_id,
    tweetId: item.twitter_tweet_id || item.id,
    authorHandle: item.author_handle,
    content: item.content,
    publishedAt: item.published_at,
    status: "analyzed",
    metrics: null,
    analysis: item.analysis,
    twitterTweetId: item.twitter_tweet_id,
    media: item.media || [],
  };
}

// ============================================================
// Inner component (uses useSearchParams)
// ============================================================

function TweetsPageInner() {
  const searchParams = useSearchParams();
  const router = useRouter();

  const initialTab = searchParams.get("tab") || "all";
  const initialBlogger = searchParams.get("blogger") || "";
  const initialSearch = searchParams.get("q") || "";
  const initialPage = Math.max(0, parseInt(searchParams.get("page") || "0", 10));

  const [activeTab, setActiveTab] = useState(initialTab);
  const [blogger, setBlogger] = useState(initialBlogger);
  const [search, setSearch] = useState(initialSearch);
  const [page, setPage] = useState(initialPage);
  const [items, setItems] = useState<DisplayItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);

  const totalPages = Math.ceil(total / PAGE_SIZE);

  // Keep URL in sync with state
  const updateUrl = (updates: {
    tab?: string;
    blogger?: string;
    q?: string;
    page?: number;
  }) => {
    const params = new URLSearchParams();
    const t = updates.tab ?? activeTab;
    const b = updates.blogger ?? blogger;
    const q = updates.q ?? search;
    const p = updates.page ?? page;

    if (t && t !== "all") params.set("tab", t);
    if (b) params.set("blogger", b);
    if (q) params.set("q", q);
    if (p > 0) params.set("page", String(p));

    const qs = params.toString();
    router.replace(`/tweets${qs ? `?${qs}` : ""}`);
  };

  const loadData = async (
    tab: string,
    bloggerFilter: string,
    searchFilter: string,
    pageNum: number,
  ) => {
    setLoading(true);
    try {
      if (isSentimentTab(tab) || tab === "analyzed") {
        const res = await fetchAnalyses({
          sentiment: isSentimentTab(tab) ? tab : undefined,
          blogger: bloggerFilter || undefined,
          limit: PAGE_SIZE,
          offset: pageNum * PAGE_SIZE,
        });
        let data: DisplayItem[] = (res.items || []).map(analysisToDisplay);
        if (searchFilter) {
          const q = searchFilter.toLowerCase();
          data = data.filter(
            (i) =>
              i.content.toLowerCase().includes(q) ||
              i.authorHandle.toLowerCase().includes(q) ||
              i.analysis?.tickers.some((t) =>
                t.symbol.toLowerCase().includes(q),
              ),
          );
        }
        setItems(data);
        setTotal(res.total || 0);
      } else {
        const params: any = {
          limit: PAGE_SIZE,
          offset: pageNum * PAGE_SIZE,
          include_analysis: tab === "all", // only for 'all' tab to enrich analyzed tweets
        };
        if (tab !== "all") params.status = tab;
        if (bloggerFilter) params.blogger = bloggerFilter;
        const res = await fetchTweets(params);
        let data: DisplayItem[] = (res.items || []).map(tweetToDisplay);
        if (searchFilter) {
          const q = searchFilter.toLowerCase();
          data = data.filter(
            (i) =>
              i.content.toLowerCase().includes(q) ||
              i.authorHandle.toLowerCase().includes(q),
          );
        }
        setItems(data);
        setTotal(res.total || 0);
      }
    } catch (e) {
      console.error(e);
      setItems([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData(activeTab, blogger, search, page);
  }, [activeTab, blogger, search, page]);

  const handleTabChange = (val: string) => {
    setActiveTab(val);
    setPage(0);
    updateUrl({ tab: val, page: 0 });
  };

  const handleApplyFilters = () => {
    setPage(0);
    updateUrl({ page: 0 });
    loadData(activeTab, blogger, search, 0);
  };

  const handleClearFilters = () => {
    setBlogger("");
    setSearch("");
    setPage(0);
    updateUrl({ blogger: "", q: "", page: 0 });
    loadData(activeTab, "", "", 0);
  };

  const handlePageChange = (newPage: number) => {
    setPage(newPage);
    updateUrl({ page: newPage });
  };

  // UUID v4 regex pattern for detecting tweetId vs handle
  const isTweetId = (s: string) => /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(s);

  const handleTriggerAnalysis = async (tweetId: string, handle: string) => {
    setAnalyzing(true);
    try {
      if (tweetId && isTweetId(tweetId)) {
        await analyzeSingleTweet(tweetId);
        alert("已触发单条推文分析，请稍后刷新查看结果");
      } else if (handle) {
        await analyzeBlogger(handle);
        alert(`已触发博主 ${handle} 的分析任务，请稍后刷新查看结果`);
      } else {
        await triggerAnalysis();
        alert("已触发批量分析任务，请稍后刷新查看结果");
      }
    } catch (e) {
      alert("触发分析失败");
    } finally {
      setAnalyzing(false);
    }
  };

  return (
    <div className="product-page">
      <WorkspacePageHeader eyebrow="Raw Intelligence" title="推文情报" subtitle="保留原始观点、分析状态和模型判断，让每条市场信号都可以回到来源。" actions={<button
            onClick={() => handleTriggerAnalysis("", "")}
            disabled={analyzing}
            className="button-primary"
          >
            <AppIcon name="research" className="h-4 w-4" />{analyzing ? "分析中..." : "分析待处理推文"}
          </button>} />
      <MetricStrip items={[{ label: "当前结果", value: total, note: "符合当前筛选" }, { label: "视图", value: ALL_TABS.find((tab) => tab.value === activeTab)?.label ?? "全部", note: "分析状态与观点" }, { label: "每页展示", value: PAGE_SIZE, note: "按发布时间排序" }]} />

      {/* Filter bar */}
      <FilterBar
        blogger={blogger}
        search={search}
        onBloggerChange={setBlogger}
        onSearchChange={setSearch}
        onApply={handleApplyFilters}
        onClear={handleClearFilters}
      />

      {/* Tabs */}
      <div className="content-toolbar"><SectionTitle icon="tweets" title="情报流" meta={`${total} 条结果`} /><div className="signal-tabs">
        {ALL_TABS.map((tab) => (
          <button
            key={tab.value}
            onClick={() => handleTabChange(tab.value)}
            className={activeTab === tab.value ? "is-active" : ""}
          >
            {tab.label}
          </button>
        ))}
      </div></div>

      {/* Content */}
      {loading ? (
        <div className="space-y-3">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : items.length === 0 ? (
        <PageEmpty title={isSentimentTab(activeTab)
              ? `暂无${SENTIMENT_TABS.find((t) => t.value === activeTab)?.label || ""}态度的分析结果`
              : activeTab === "pending"
                ? "暂无待分析推文"
                : activeTab === "analyzed"
                  ? "暂无已分析推文"
                  : "暂无推文数据"} detail={activeTab === "pending" ? "所有推文已分析完毕，或尚未采集到新推文。" : "调整筛选范围，或者等待新的数据进入。"} />
      ) : (
        <div className="space-y-3">
          {items.map((item) => (
            <TweetAnalysisCard
              key={item.id}
              id={item.id}
              tweetId={item.tweetId}
              authorHandle={item.authorHandle}
              authorName={item.authorName}
              content={item.content}
              publishedAt={item.publishedAt}
              status={item.status}
              metrics={item.metrics}
              analysis={item.analysis}
              twitterTweetId={item.twitterTweetId}
              media={item.media}
              onTriggerAnalysis={
                item.status !== "analyzed"
                  ? handleTriggerAnalysis
                  : undefined
              }
            />
          ))}
        </div>
      )}

      {/* Pagination */}
      <Pagination page={page} pages={totalPages} onChange={handlePageChange} zeroBased />
    </div>
  );
}

// ============================================================
// Page export with Suspense boundary
// ============================================================

export default function TweetsPage() {
  return (
    <Suspense fallback={<p className="text-center py-10 text-gray-500">加载中...</p>}>
      <TweetsPageInner />
    </Suspense>
  );
}
