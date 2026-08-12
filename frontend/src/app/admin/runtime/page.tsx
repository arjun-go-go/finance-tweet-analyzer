"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { fetchRuntimeStats, type RuntimeStats } from "@/lib/api";

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900 p-4">
      <div className="text-xs uppercase tracking-[0.16em] text-slate-500">{label}</div>
      <div className="mt-2 font-mono text-2xl text-cyan-300">{value}</div>
    </div>
  );
}

function JsonPanel({ title, value }: { title: string; value: unknown }) {
  return (
    <section className="rounded-3xl border border-slate-800 bg-slate-950 p-5">
      <h2 className="mb-3 text-base font-semibold text-slate-100">{title}</h2>
      <pre className="overflow-auto rounded-2xl bg-slate-900 p-4 font-mono text-xs leading-5 text-slate-300">
        {JSON.stringify(value, null, 2)}
      </pre>
    </section>
  );
}

export default function RuntimeAdminPage() {
  const [stats, setStats] = useState<RuntimeStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setStats(await fetchRuntimeStats());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "运行状态加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const vision = stats?.vision;
  return (
    <div className="min-h-screen rounded-3xl bg-[#070b12] p-6 text-slate-100">
      <header className="mb-6 flex flex-col gap-4 rounded-3xl border border-cyan-400/20 bg-gradient-to-br from-slate-950 via-slate-900 to-cyan-950/30 p-6 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="mb-3 text-xs uppercase tracking-[0.35em] text-cyan-300">Runtime Control Plane</div>
          <h1 className="text-3xl font-semibold">系统运行监控</h1>
          <p className="mt-2 text-sm text-slate-400">查看队列、Outbox、分析任务，以及图片识别的调用量与 Token 用量。</p>
        </div>
        <div className="flex gap-3">
          <Link href="/admin/es" className="rounded-2xl border border-slate-700 px-5 py-3 text-sm text-slate-200 hover:border-cyan-300">ES / Milvus 管理</Link>
          <button onClick={() => void load()} className="rounded-2xl bg-cyan-300 px-5 py-3 text-sm font-semibold text-slate-950 hover:bg-cyan-200">刷新</button>
        </div>
      </header>

      {loading && <div className="rounded-2xl bg-slate-900 p-4 text-slate-400">加载中...</div>}
      {error && <div className="mb-4 rounded-2xl border border-rose-400/30 bg-rose-950/30 p-4 text-rose-200">{error}</div>}

      {stats && vision && (
        <div className="space-y-5">
          <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
            <Stat label="Vision completed" value={vision.statuses.completed || 0} />
            <Stat label="Vision failed" value={vision.statuses.failed || 0} />
            <Stat label="Images archived" value={vision.assets.downloaded || 0} />
            <Stat label="Avg confidence" value={`${(vision.average_confidence * 100).toFixed(1)}%`} />
            <Stat label="Vision tokens" value={vision.usage.total_tokens.toLocaleString()} />
            <Stat label="Provider cost" value={vision.usage.provider_cost_usd ? `$${vision.usage.provider_cost_usd.toFixed(4)}` : "未返回"} />
          </div>
          <div className="grid gap-5 lg:grid-cols-3">
            <JsonPanel title="Celery 队列" value={stats.queues} />
            <JsonPanel title="Outbox" value={stats.outbox} />
            <JsonPanel title="图片分析" value={vision} />
          </div>
          <div className="grid gap-5 lg:grid-cols-2">
            <JsonPanel title="推文分析状态" value={stats.tweet_analysis} />
            <JsonPanel title="索引任务" value={stats.index_jobs} />
          </div>
        </div>
      )}
    </div>
  );
}
