"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { fetchTweets, fetchAnalyses, triggerAnalysis, analyzeBlogger, analyzeSingleTweet } from "@/lib/api";
import TweetAnalysisCard from "@/components/TweetAnalysisCard";
import FilterBar from "@/components/FilterBar";
import SkeletonCard from "@/components/SkeletonCard";

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
}

interface AnalysisItem {
  id: string;
  twitter_tweet_id?: string;
  author_handle: string;
  content: string;
  published_at: string;
  created_at: string;
  analysis: AnalysisData;
  confidence: number;
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
  };
}

function analysisToDisplay(item: AnalysisItem): DisplayItem {
  return {
    id: item.id,
    tweetId: item.twitter_tweet_id || item.id,
    authorHandle: item.author_handle,
    content: item.content,
    publishedAt: item.published_at,
    status: "analyzed",
    metrics: null,
    analysis: item.analysis,
    twitterTweetId: item.twitter_tweet_id,
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
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h1 className="text-2xl font-bold">推文 & 分析</h1>
        <div className="flex items-center gap-3">
          <span className="text-sm text-gray-500">共 {total} 条</span>
          <button
            onClick={() => handleTriggerAnalysis("", "")}
            disabled={analyzing}
            className="px-3 py-1.5 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {analyzing ? "分析中..." : "批量分析待分析推文"}
          </button>
        </div>
      </div>

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
      <div className="flex flex-wrap gap-2">
        {ALL_TABS.map((tab) => (
          <button
            key={tab.value}
            onClick={() => handleTabChange(tab.value)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              activeTab === tab.value
                ? "bg-blue-600 text-white"
                : "bg-gray-100 text-gray-700 hover:bg-gray-200"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      {loading ? (
        <div className="space-y-3">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : items.length === 0 ? (
        <div className="text-center py-14 bg-white rounded-lg shadow">
          <div className="text-5xl mb-3">
            {isSentimentTab(activeTab) ? "📊" : activeTab === "pending" ? "📭" : activeTab === "analyzed" ? "✅" : "📝"}
          </div>
          <p className="text-gray-500 text-lg font-medium mb-1">
            {isSentimentTab(activeTab)
              ? `暂无${SENTIMENT_TABS.find((t) => t.value === activeTab)?.label || ""}态度的分析结果`
              : activeTab === "pending"
                ? "暂无待分析推文"
                : activeTab === "analyzed"
                  ? "暂无已分析推文"
                  : "暂无推文数据"}
          </p>
          {activeTab === "pending" && (
            <p className="text-gray-400 text-sm">
              所有推文已分析完毕，或尚未抓取新推文
            </p>
          )}
        </div>
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
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-4 py-4">
          <button
            onClick={() => handlePageChange(Math.max(0, page - 1))}
            disabled={page === 0}
            className="px-4 py-2 rounded-lg text-sm bg-gray-100 text-gray-600 hover:bg-gray-200 disabled:opacity-50 transition-colors"
          >
            上一页
          </button>
          <span className="text-sm text-gray-600">
            第 {page + 1} 页 / 共 {totalPages} 页
          </span>
          <button
            onClick={() =>
              handlePageChange(Math.min(totalPages - 1, page + 1))
            }
            disabled={page >= totalPages - 1}
            className="px-4 py-2 rounded-lg text-sm bg-gray-100 text-gray-600 hover:bg-gray-200 disabled:opacity-50 transition-colors"
          >
            下一页
          </button>
        </div>
      )}
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
