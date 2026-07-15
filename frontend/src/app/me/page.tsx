"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  AnalysisJobItem,
  BookmarkedTweetListResponse,
  FollowedBloggerListResponse,
  confirmAnalysisJobs,
  createAnalysisJob,
  listMyAnalysisJobs,
  listMyBloggers,
  listMyTweets,
} from "@/lib/api";

function statusTone(status: string) {
  if (status === "completed") return "bg-green-100 text-green-800";
  if (status === "failed") return "bg-red-100 text-red-800";
  if (status === "running") return "bg-blue-100 text-blue-800";
  if (status === "awaiting_confirmation") return "bg-amber-100 text-amber-800";
  return "bg-gray-100 text-gray-700";
}

export default function MePage() {
  const [bloggers, setBloggers] = useState<FollowedBloggerListResponse>({
    items: [],
    total: 0,
  });
  const [tweets, setTweets] = useState<BookmarkedTweetListResponse>({
    items: [],
    total: 0,
  });
  const [jobs, setJobs] = useState<AnalysisJobItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [submittingId, setSubmittingId] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [selectedJobIds, setSelectedJobIds] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  const runningCount = useMemo(
    () => jobs.filter((job) => ["queued", "running"].includes(job.status)).length,
    [jobs],
  );
  const confirmableJobIds = useMemo(
    () =>
      jobs
        .filter((job) => job.status === "awaiting_confirmation")
        .map((job) => job.id),
    [jobs],
  );
  const selectedConfirmableCount = selectedJobIds.filter((id) =>
    confirmableJobIds.includes(id),
  ).length;

  async function refresh() {
    setError(null);
    const [bloggerData, tweetData, jobData] = await Promise.all([
      listMyBloggers(),
      listMyTweets(),
      listMyAnalysisJobs(),
    ]);
    setBloggers(bloggerData);
    setTweets(tweetData);
    setJobs(jobData.items);
    setSelectedJobIds((current) =>
      current.filter((id) => jobData.items.some((job) => job.id === id)),
    );
  }

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    refresh()
      .catch((err) => {
        if (!cancelled) setError(err.message || "加载失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function submitBloggerJob(bloggerId: string) {
    setSubmittingId(bloggerId);
    setError(null);
    try {
      await createAnalysisJob({
        kind: "blogger_analysis",
        target_id: bloggerId,
      });
      await refresh();
    } catch (err) {
      setError((err as Error).message || "提交失败");
    } finally {
      setSubmittingId(null);
    }
  }

  function toggleJobSelection(jobId: string) {
    setSelectedJobIds((current) =>
      current.includes(jobId)
        ? current.filter((id) => id !== jobId)
        : [...current, jobId],
    );
  }

  function selectAllConfirmableJobs() {
    setSelectedJobIds(confirmableJobIds);
  }

  async function confirmSelectedJobs() {
    const jobIds = selectedJobIds.filter((id) => confirmableJobIds.includes(id));
    if (jobIds.length === 0) return;

    setConfirming(true);
    setError(null);
    try {
      await confirmAnalysisJobs(jobIds);
      setSelectedJobIds([]);
      await refresh();
    } catch (err) {
      setError((err as Error).message || "确认失败");
    } finally {
      setConfirming(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-sm font-medium text-blue-600">Personal workspace</p>
          <h1 className="text-2xl font-bold text-gray-900">我的工作台</h1>
          <p className="mt-1 text-sm text-gray-500">
            管理关注、收藏和个人分析任务，所有昂贵分析都会进入可追踪队列。
          </p>
        </div>
        <button
          onClick={() => refresh().catch((err) => setError(err.message))}
          className="w-fit rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
        >
          刷新状态
        </button>
      </div>

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-4">
        <div className="rounded-lg bg-white p-4 shadow">
          <p className="text-xs text-gray-500">关注博主</p>
          <p className="mt-1 text-2xl font-bold">{bloggers.total}</p>
        </div>
        <div className="rounded-lg bg-white p-4 shadow">
          <p className="text-xs text-gray-500">收藏推文</p>
          <p className="mt-1 text-2xl font-bold">{tweets.total}</p>
        </div>
        <div className="rounded-lg bg-white p-4 shadow">
          <p className="text-xs text-gray-500">分析任务</p>
          <p className="mt-1 text-2xl font-bold">{jobs.length}</p>
        </div>
        <div className="rounded-lg bg-white p-4 shadow">
          <p className="text-xs text-gray-500">队列中</p>
          <p className="mt-1 text-2xl font-bold">{runningCount}</p>
        </div>
      </div>

      {loading ? (
        <div className="rounded-lg bg-white p-8 text-center text-sm text-gray-500 shadow">
          正在加载个人资源...
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-3">
          <section className="rounded-lg bg-white shadow">
            <div className="border-b border-gray-100 px-4 py-3">
              <h2 className="font-semibold text-gray-900">关注博主</h2>
            </div>
            <div className="divide-y divide-gray-100">
              {bloggers.items.slice(0, 8).map((blogger) => (
                <div key={blogger.id} className="p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <Link
                        href={`/bloggers/${encodeURIComponent(blogger.handle)}`}
                        className="font-medium text-gray-900 hover:text-blue-600"
                      >
                        @{blogger.handle}
                      </Link>
                      <p className="truncate text-xs text-gray-500">{blogger.name}</p>
                      <p className="mt-2 text-xs text-gray-500">
                        待验证 {blogger.pending_count} · 可信度{" "}
                        {blogger.credibility_score.toFixed(1)}
                      </p>
                    </div>
                    <button
                      onClick={() => submitBloggerJob(blogger.id)}
                      disabled={submittingId === blogger.id}
                      className="shrink-0 rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {submittingId === blogger.id ? "提交中" : "分析"}
                    </button>
                  </div>
                </div>
              ))}
              {bloggers.items.length === 0 && (
                <div className="p-6 text-sm text-gray-500">还没有关注博主。</div>
              )}
            </div>
          </section>

          <section className="rounded-lg bg-white shadow">
            <div className="border-b border-gray-100 px-4 py-3">
              <h2 className="font-semibold text-gray-900">收藏推文</h2>
            </div>
            <div className="divide-y divide-gray-100">
              {tweets.items.slice(0, 8).map((tweet) => (
                <div key={tweet.id} className="p-4">
                  <p className="text-xs font-medium text-gray-500">
                    @{tweet.author_handle}
                  </p>
                  <p className="mt-1 line-clamp-3 text-sm text-gray-800">
                    {tweet.content}
                  </p>
                  <p className="mt-2 text-xs text-gray-400">{tweet.status}</p>
                </div>
              ))}
              {tweets.items.length === 0 && (
                <div className="p-6 text-sm text-gray-500">还没有收藏推文。</div>
              )}
            </div>
          </section>

          <section className="rounded-lg bg-white shadow">
            <div className="border-b border-gray-100 px-4 py-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <h2 className="font-semibold text-gray-900">分析任务</h2>
                  <p className="mt-1 text-xs text-gray-500">
                    待确认 {confirmableJobIds.length} · 已选 {selectedConfirmableCount}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <button
                    onClick={selectAllConfirmableJobs}
                    disabled={confirmableJobIds.length === 0 || confirming}
                    className="rounded-md border border-gray-300 bg-white px-2 py-1 text-xs text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    全选待确认
                  </button>
                  <button
                    onClick={confirmSelectedJobs}
                    disabled={selectedConfirmableCount === 0 || confirming}
                    className="rounded-md bg-amber-600 px-2 py-1 text-xs font-medium text-white hover:bg-amber-700 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {confirming ? "确认中" : "确认选中"}
                  </button>
                </div>
              </div>
            </div>
            <div className="divide-y divide-gray-100">
              {jobs.slice(0, 10).map((job) => (
                <div key={job.id} className="p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex min-w-0 items-center gap-2">
                      {job.status === "awaiting_confirmation" && (
                        <input
                          type="checkbox"
                          checked={selectedJobIds.includes(job.id)}
                          onChange={() => toggleJobSelection(job.id)}
                          className="h-4 w-4 rounded border-gray-300 text-amber-600 focus:ring-amber-500"
                          aria-label={`选择分析任务 ${job.id}`}
                        />
                      )}
                      <p className="text-sm font-medium text-gray-900">
                        {job.kind === "blogger_analysis" ? "博主分析" : "推文分析"}
                      </p>
                    </div>
                    <span
                      className={`rounded px-2 py-0.5 text-xs ${statusTone(job.status)}`}
                    >
                      {job.status}
                    </span>
                  </div>
                  <p className="mt-1 break-all text-xs text-gray-500">
                    {job.id}
                  </p>
                  {job.reused_result && (
                    <p className="mt-2 text-xs text-green-700">已复用共享缓存</p>
                  )}
                  {job.error_summary && (
                    <p className="mt-2 text-xs text-red-600">{job.error_summary}</p>
                  )}
                </div>
              ))}
              {jobs.length === 0 && (
                <div className="p-6 text-sm text-gray-500">暂无分析任务。</div>
              )}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
