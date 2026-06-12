"use client";

import { useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { fetchTweets } from "@/lib/api";
import { formatDateTime } from "@/lib/datetime";

interface TweetItem {
  id: string;
  tweet_id: string;
  author_handle: string;
  author_name: string;
  content: string;
  published_at: string;
  status: string;
  metrics: { likes?: number; retweets?: number; views?: number } | null;
}

const PAGE_SIZE = 20;

const TABS = [
  { label: "全部", value: "" },
  { label: "待分析", value: "pending" },
  { label: "已分析", value: "analyzed" },
];

export default function TweetsPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const initialStatus = searchParams.get("status") || "";

  const [status, setStatus] = useState(initialStatus);
  const [tweets, setTweets] = useState<TweetItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const totalPages = Math.ceil(total / PAGE_SIZE);

  const loadData = async (s: string, p: number) => {
    setLoading(true);
    try {
      const params: any = { limit: PAGE_SIZE, offset: p * PAGE_SIZE };
      if (s) params.status = s;
      const res = await fetchTweets(params);
      setTweets(res.items);
      setTotal(res.total);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData(status, page);
  }, [status, page]);

  const handleTabChange = (val: string) => {
    setStatus(val);
    setPage(0);
    const params = new URLSearchParams();
    if (val) params.set("status", val);
    router.replace(`/tweets?${params.toString()}`);
  };

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">推文列表</h1>

      <div className="flex gap-2">
        {TABS.map((tab) => (
          <button
            key={tab.value}
            onClick={() => handleTabChange(tab.value)}
            className={`px-4 py-2 rounded-lg text-sm font-medium ${
              status === tab.value
                ? "bg-blue-600 text-white"
                : "bg-gray-100 text-gray-700 hover:bg-gray-200"
            }`}
          >
            {tab.label}
          </button>
        ))}
        <span className="ml-auto text-sm text-gray-500 self-center">
          共 {total} 条
        </span>
      </div>

      {loading ? (
        <p className="text-center py-10 text-gray-500">加载中...</p>
      ) : tweets.length === 0 ? (
        <p className="text-center py-10 text-gray-500">暂无数据</p>
      ) : (
        <div className="space-y-3">
          {tweets.map((tweet) => (
            <div
              key={tweet.id}
              className="bg-white rounded-lg shadow p-4 space-y-2"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-blue-600">
                    {tweet.author_handle}
                  </span>
                  {tweet.author_name && (
                    <span className="text-sm text-gray-500">
                      ({tweet.author_name})
                    </span>
                  )}
                </div>
                <span
                  className={`text-xs px-2 py-0.5 rounded ${
                    tweet.status === "analyzed"
                      ? "bg-green-100 text-green-700"
                      : "bg-yellow-100 text-yellow-700"
                  }`}
                >
                  {tweet.status === "analyzed" ? "已分析" : "待分析"}
                </span>
              </div>
              <p
                className={`text-gray-800 whitespace-pre-wrap ${
                  expanded.has(tweet.id) ? "" : "line-clamp-4"
                }`}
              >
                {tweet.content}
              </p>
              {tweet.content.length > 200 && (
                <button
                  onClick={() =>
                    setExpanded((prev) => {
                      const next = new Set(prev);
                      if (next.has(tweet.id)) next.delete(tweet.id);
                      else next.add(tweet.id);
                      return next;
                    })
                  }
                  className="text-xs text-blue-500 hover:underline"
                >
                  {expanded.has(tweet.id) ? "收起" : "展开全部"}
                </button>
              )}
              <div className="flex items-center gap-4 text-xs text-gray-500">
                <span>{formatDateTime(tweet.published_at)}</span>
                {tweet.metrics && (
                  <>
                    {tweet.metrics.likes != null && (
                      <span>赞 {tweet.metrics.likes}</span>
                    )}
                    {tweet.metrics.retweets != null && (
                      <span>转发 {tweet.metrics.retweets}</span>
                    )}
                    {tweet.metrics.views != null && (
                      <span>浏览 {tweet.metrics.views}</span>
                    )}
                  </>
                )}
                <a
                  href={`https://x.com/${tweet.author_handle.replace("@", "")}/status/${tweet.tweet_id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-500 hover:underline ml-auto"
                >
                  查看原文
                </a>
              </div>
            </div>
          ))}
        </div>
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 py-4">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            className="px-3 py-1 rounded border disabled:opacity-30"
          >
            上一页
          </button>
          <span className="text-sm text-gray-600">
            {page + 1} / {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            disabled={page >= totalPages - 1}
            className="px-3 py-1 rounded border disabled:opacity-30"
          >
            下一页
          </button>
        </div>
      )}
    </div>
  );
}
