"use client";

import { useEffect, useState } from "react";
import {
  fetchEsAdminStats,
  fetchEsIndexJobs,
  rebuildEsAlias,
  type EsAdminStats,
  type IndexJobItem,
} from "@/lib/api";

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-3xl border border-slate-800 bg-slate-950 p-5 shadow-xl shadow-black/20">
      <h2 className="mb-4 text-lg font-semibold text-slate-100">{title}</h2>
      {children}
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900 p-4">
      <div className="text-xs uppercase tracking-[0.18em] text-slate-500">{label}</div>
      <div className="mt-2 font-mono text-2xl text-cyan-300">{value}</div>
    </div>
  );
}

export default function EsAdminPage() {
  const [stats, setStats] = useState<EsAdminStats | null>(null);
  const [jobs, setJobs] = useState<IndexJobItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [statsResult, failedJobs] = await Promise.all([
        fetchEsAdminStats(),
        fetchEsIndexJobs({ status: "failed", limit: 50 }),
      ]);
      setStats(statsResult);
      setJobs(failedJobs.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载 ES 管理数据失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const triggerRebuild = async () => {
    setMessage(null);
    setError(null);
    try {
      const result = await rebuildEsAlias({ batchSize: 500, switchAlias: true });
      setMessage(`Rebuild 已入队：${result.task_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "触发 rebuild 失败");
    }
  };

  return (
    <div className="min-h-screen rounded-3xl bg-[#070b12] p-6 text-slate-100">
      <div className="mb-6 flex flex-col gap-4 rounded-3xl border border-cyan-400/20 bg-gradient-to-br from-slate-950 via-slate-900 to-cyan-950/30 p-6 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="mb-3 text-xs uppercase tracking-[0.35em] text-cyan-300">
            Elasticsearch Control Plane
          </div>
          <h1 className="text-3xl font-semibold">ES 管理后台</h1>
          <p className="mt-2 text-sm text-slate-400">
            监控 alias、文档数量、索引账本失败项，并一键重建新版本索引后切换 alias。
          </p>
        </div>
        <div className="flex gap-3">
          <button onClick={load} className="rounded-2xl border border-slate-700 px-5 py-3 text-sm text-slate-200 hover:border-cyan-300">
            刷新
          </button>
          <button onClick={triggerRebuild} className="rounded-2xl bg-cyan-300 px-5 py-3 text-sm font-semibold text-slate-950 hover:bg-cyan-200">
            一键重建并切换 alias
          </button>
        </div>
      </div>

      {loading && <div className="rounded-2xl bg-slate-900 p-4 text-slate-400">加载中...</div>}
      {message && <div className="mb-4 rounded-2xl border border-emerald-400/30 bg-emerald-950/30 p-4 text-emerald-200">{message}</div>}
      {error && <div className="mb-4 rounded-2xl border border-rose-400/30 bg-rose-950/30 p-4 text-rose-200">{error}</div>}

      {stats && (
        <div className="space-y-5">
          <div className="grid gap-3 md:grid-cols-4">
            <Stat label="Alias" value={stats.elasticsearch.alias} />
            <Stat label="Write Index" value={stats.elasticsearch.current_write_index || "-"} />
            <Stat label="ES Docs" value={stats.elasticsearch.total} />
            <Stat label="PG Chunks" value={stats.doc_chunks} />
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            <Panel title="Source Counts">
              <div className="space-y-3">
                {Object.entries(stats.elasticsearch.source_counts).map(([source, count]) => (
                  <div key={source}>
                    <div className="mb-1 flex justify-between text-sm">
                      <span className="text-slate-300">{source}</span>
                      <span className="font-mono text-cyan-300">{count}</span>
                    </div>
                    <div className="h-2 rounded-full bg-slate-800">
                      <div className="h-2 rounded-full bg-cyan-300" style={{ width: `${Math.min(100, count * 8)}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            </Panel>
            <Panel title="Index Jobs">
              <pre className="overflow-auto rounded-2xl bg-slate-900 p-4 font-mono text-xs text-slate-200">
                {JSON.stringify(stats.index_jobs, null, 2)}
              </pre>
            </Panel>
          </div>

          <Panel title="Failed Jobs">
            <div className="overflow-auto">
              <table className="w-full min-w-[820px] text-left text-sm">
                <thead className="text-xs uppercase tracking-wider text-slate-500">
                  <tr>
                    <th className="py-2">target</th>
                    <th>status</th>
                    <th>attempts</th>
                    <th>doc_chunk_id</th>
                    <th>error</th>
                    <th>updated</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {jobs.map((job) => (
                    <tr key={`${job.target}-${job.doc_chunk_id}`} className="text-slate-300">
                      <td className="py-3 font-mono text-cyan-300">{job.target}</td>
                      <td>{job.status}</td>
                      <td>{job.attempts}</td>
                      <td className="font-mono text-xs">{job.doc_chunk_id}</td>
                      <td className="max-w-[280px] truncate text-rose-200">{job.error_message || "-"}</td>
                      <td className="font-mono text-xs">{job.updated_at || "-"}</td>
                    </tr>
                  ))}
                  {!jobs.length && (
                    <tr>
                      <td colSpan={6} className="py-6 text-center text-slate-500">
                        暂无失败索引任务
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>
      )}
    </div>
  );
}
