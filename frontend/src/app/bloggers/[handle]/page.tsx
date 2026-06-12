"use client";

import { use, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import BloggerStatsHeader from "@/components/BloggerStatsHeader";
import PredictionCard, { PredictionItem } from "@/components/PredictionCard";
import {
  fetchBloggerDetail,
  fetchBloggerPredictions,
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
  verified_count: number;
  pending_count: number;
  hit_rate_overall: number | null;
  hit_rate_by_sentiment: {
    bullish: number | null;
    bearish: number | null;
    neutral: number | null;
  };
  top_tickers: Array<{ ticker: string; verified: number; hit_rate: number }>;
  recent_verified: PredictionItem[];
}

type TabKey = "pending" | "verified" | "all";

export default function BloggerDetailPage({
  params,
}: {
  params: Promise<{ handle: string }>;
}) {
  const { handle } = use(params);
  const decodedHandle = decodeURIComponent(handle);
  const search = useSearchParams();
  const initialTab = (search.get("status") as TabKey) || "pending";

  const [detail, setDetail] = useState<BloggerDetail | null>(null);
  const [tab, setTab] = useState<TabKey>(initialTab);
  const [predictions, setPredictions] = useState<PredictionItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [predictionsLoading, setPredictionsLoading] = useState(false);

  const loadDetail = async () => {
    try {
      const data = await fetchBloggerDetail(decodedHandle);
      setDetail(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const loadPredictions = async (currentTab: TabKey) => {
    setPredictionsLoading(true);
    try {
      const data = await fetchBloggerPredictions(decodedHandle, {
        status: currentTab,
        limit: 50,
      });
      setPredictions(data.items);
      setTotal(data.total);
    } catch (e) {
      console.error(e);
    } finally {
      setPredictionsLoading(false);
    }
  };

  useEffect(() => {
    loadDetail();
  }, [decodedHandle]);

  useEffect(() => {
    loadPredictions(tab);
  }, [decodedHandle, tab]);

  const handleVerified = (next: PredictionItem) => {
    if (tab === "pending" && next.verdict !== null) {
      setPredictions((prev) => prev.filter((p) => p.id !== next.id));
      setTotal((t) => Math.max(0, t - 1));
    } else {
      setPredictions((prev) =>
        prev.map((p) => (p.id === next.id ? next : p)),
      );
    }
    loadDetail();
  };

  if (loading) return <p className="text-center py-10">加载中...</p>;
  if (!detail)
    return (
      <p className="text-center py-10 text-red-500">博主不存在或加载失败</p>
    );

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-lg shadow p-5 flex items-start gap-4">
        {detail.avatar_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={detail.avatar_url}
            alt={detail.handle}
            className="w-16 h-16 rounded-full bg-gray-200 object-cover"
          />
        ) : (
          <div className="w-16 h-16 rounded-full bg-gray-200 flex items-center justify-center text-gray-500 font-bold">
            {detail.handle.slice(1, 3).toUpperCase()}
          </div>
        )}
        <div className="flex-1">
          <h1 className="text-2xl font-bold">{detail.handle}</h1>
          <p className="text-sm text-gray-600">{detail.name}</p>
          {detail.bio && (
            <p className="text-sm text-gray-500 mt-1">{detail.bio}</p>
          )}
          <div className="flex flex-wrap gap-2 mt-2 text-xs text-gray-500">
            <span>粉丝 {detail.followers_count.toLocaleString()}</span>
            {(detail.market_focus ?? []).map((m) => (
              <span
                key={m}
                className="bg-gray-100 text-gray-600 px-2 py-0.5 rounded"
              >
                {m}
              </span>
            ))}
            {detail.profile_updated_at && (
              <span>
                资料更新于 {formatDate(detail.profile_updated_at)}
              </span>
            )}
          </div>
        </div>
      </div>

      <BloggerStatsHeader
        credibilityScore={detail.credibility_score}
        verifiedCount={detail.verified_count}
        pendingCount={detail.pending_count}
        hitRateOverall={detail.hit_rate_overall}
        hitRateBySentiment={detail.hit_rate_by_sentiment}
        topTickers={detail.top_tickers}
      />

      <div>
        <div className="flex items-center gap-2 border-b mb-4">
          {(
            [
              ["pending", `待标注 (${detail.pending_count})`],
              ["verified", `已标注 (${detail.verified_count})`],
              ["all", "全部"],
            ] as Array<[TabKey, string]>
          ).map(([key, label]) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`px-4 py-2 text-sm border-b-2 -mb-px ${
                tab === key
                  ? "border-blue-600 text-blue-600 font-semibold"
                  : "border-transparent text-gray-500 hover:text-gray-700"
              }`}
            >
              {label}
            </button>
          ))}
          <span className="ml-auto text-xs text-gray-400">共 {total} 条</span>
        </div>

        {predictionsLoading ? (
          <p className="text-center py-10">加载中...</p>
        ) : predictions.length === 0 ? (
          <p className="text-center py-10 text-gray-500">暂无数据</p>
        ) : (
          <div className="grid gap-4">
            {predictions.map((p) => (
              <PredictionCard
                key={p.id}
                prediction={p}
                onChanged={handleVerified}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
