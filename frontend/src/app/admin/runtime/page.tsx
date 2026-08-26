"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { fetchRuntimeStats, type RuntimeStats } from "@/lib/api";
import { formatDateTime } from "@/lib/datetime";

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

function timeLabel(value: string | null) {
  return value ? formatDateTime(value) : "尚无记录";
}

function statusStyle(status: string) {
  if (status === "healthy" || status === "success") return "border-emerald-400/30 bg-emerald-400/10 text-emerald-300";
  if (status === "degraded" || status === "running") return "border-amber-400/30 bg-amber-400/10 text-amber-300";
  if (status === "failed") return "border-rose-400/30 bg-rose-400/10 text-rose-300";
  return "border-slate-700 bg-slate-800 text-slate-400";
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

  useEffect(() => { void load(); }, [load]);

  const vision = stats?.vision;
  const verification = stats?.prediction_verification;
  const result = verification?.task.last_result ?? {};
  return (
    <div className="min-h-screen rounded-3xl bg-[#070b12] p-6 text-slate-100">
      <header className="mb-6 flex flex-col gap-4 rounded-3xl border border-cyan-400/20 bg-gradient-to-br from-slate-950 via-slate-900 to-cyan-950/30 p-6 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="mb-3 text-xs uppercase tracking-[0.35em] text-cyan-300">Runtime Control Plane</div>
          <h1 className="text-3xl font-semibold">系统运行监控</h1>
          <p className="mt-2 text-sm text-slate-400">监控预测自动验证、行情数据源、任务队列、索引任务与图片识别消耗。</p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Link href="/admin/predictions" className="rounded-2xl border border-slate-700 px-5 py-3 text-sm text-slate-200 hover:border-cyan-300">预测生命周期</Link>
          <Link href="/admin/es" className="rounded-2xl border border-slate-700 px-5 py-3 text-sm text-slate-200 hover:border-cyan-300">ES / Milvus 管理</Link>
          <button onClick={() => void load()} className="rounded-2xl bg-cyan-300 px-5 py-3 text-sm font-semibold text-slate-950 hover:bg-cyan-200">刷新</button>
        </div>
      </header>

      {loading && <div className="rounded-2xl bg-slate-900 p-4 text-slate-400">加载中...</div>}
      {error && <div className="mb-4 rounded-2xl border border-rose-400/30 bg-rose-950/30 p-4 text-rose-200">{error}</div>}

      {verification && verification.alerts.length > 0 && (
        <section className="mb-5 rounded-3xl border border-rose-400/30 bg-rose-950/25 p-5">
          <div className="text-xs uppercase tracking-[0.22em] text-rose-300">Action required</div>
          {verification.alerts.map((alert) => <p className="mt-2 text-sm text-rose-100" key={`${alert.source}-${alert.message}`}>{alert.message}</p>)}
        </section>
      )}

      {stats && vision && verification && (
        <div className="space-y-5">
          <section className="rounded-3xl border border-cyan-400/20 bg-slate-950 p-5">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <div className="text-xs uppercase tracking-[0.24em] text-cyan-300">Prediction verification</div>
                <h2 className="mt-2 text-xl font-semibold">自动行情验证</h2>
                <p className="mt-1 text-sm text-slate-400">
                  {verification.enabled ? `每 ${verification.interval_minutes} 分钟运行，单批最多 ${verification.batch_size} 条` : "自动验证当前未启用"}
                </p>
              </div>
              <span className={`w-fit rounded-full border px-3 py-1 text-xs font-semibold ${statusStyle(verification.task.status)}`}>
                {verification.task.status === "success" ? "最近执行成功" : verification.task.status === "running" ? "正在执行" : verification.task.status === "failed" ? "最近执行失败" : "尚未执行"}
              </span>
            </div>
            <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-5">
              <Stat label="Last run" value={timeLabel(verification.task.last_finished_at)} />
              <Stat label="Next expected" value={timeLabel(verification.task.next_scheduled_at)} />
              <Stat label="Processed" value={Number(result.processed ?? 0)} />
              <Stat label="Applied" value={Number(result.applied ?? 0)} />
              <Stat label="Failed" value={Number(result.failed ?? result.market_data_unavailable ?? result.errors ?? 0)} />
            </div>
            {verification.task.last_error && <p className="mt-4 rounded-2xl border border-rose-400/20 bg-rose-950/25 p-3 font-mono text-xs text-rose-200">{verification.task.last_error}</p>}
          </section>

          <section className="rounded-3xl border border-slate-800 bg-slate-950 p-5">
            <div className="mb-4">
              <div className="text-xs uppercase tracking-[0.24em] text-slate-500">Market sources</div>
              <h2 className="mt-2 text-xl font-semibold">行情数据源状态</h2>
            </div>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
              {Object.entries(verification.sources).map(([key, source]) => (
                <article key={key} className="rounded-2xl border border-slate-800 bg-slate-900 p-4">
                  <div className="flex items-start justify-between gap-2">
                    <strong>{source.label}</strong>
                    <span className={`rounded-full border px-2 py-0.5 text-[10px] ${statusStyle(source.status)}`}>
                      {source.status === "healthy" ? "正常" : source.status === "degraded" ? "已降级" : source.status === "failed" ? "失败" : "待采样"}
                    </span>
                  </div>
                  <div className="mt-3 font-mono text-xs text-cyan-200">{source.provider || "—"}</div>
                  <dl className="mt-4 space-y-2 text-xs text-slate-400">
                    <div className="flex justify-between"><dt>最近检查</dt><dd className="text-right text-slate-300">{timeLabel(source.last_checked_at)}</dd></div>
                    <div className="flex justify-between"><dt>成功 / 失败</dt><dd className="font-mono text-slate-300">{source.total_successes} / {source.total_failures}</dd></div>
                    <div className="flex justify-between"><dt>降级次数</dt><dd className="font-mono text-slate-300">{source.fallback_count}</dd></div>
                    <div className="flex justify-between"><dt>连续失败</dt><dd className="font-mono text-slate-300">{source.consecutive_failures}</dd></div>
                  </dl>
                </article>
              ))}
            </div>
          </section>

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
