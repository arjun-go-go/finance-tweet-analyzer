"use client";

import { useMemo, useState } from "react";
import {
  debugRetrieve,
  type RetrievalDebugResponse,
  type RetrievalResult,
} from "@/lib/api";

type Tab = "overview" | "es" | "paths" | "fusion" | "rerank";

const PATHS = ["documents", "tweets", "analyses", "structured", "bm25"] as const;

const SOURCE_COLORS: Record<string, string> = {
  tweet: "border-emerald-400/40 bg-emerald-400/10 text-emerald-200",
  analysis: "border-fuchsia-400/40 bg-fuchsia-400/10 text-fuchsia-200",
  document: "border-sky-400/40 bg-sky-400/10 text-sky-200",
  structured: "border-amber-400/40 bg-amber-400/10 text-amber-200",
  error: "border-rose-400/40 bg-rose-400/10 text-rose-200",
};

function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="max-h-[520px] overflow-auto rounded-2xl border border-slate-700/70 bg-[#08111f] p-4 font-mono text-xs leading-relaxed text-slate-200 shadow-inner">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

function ResultCard({ item, index }: { item: RetrievalResult; index: number }) {
  const [open, setOpen] = useState(false);
  const sourceClass =
    SOURCE_COLORS[item.source_type] || "border-slate-500/50 bg-slate-500/10 text-slate-200";
  const highlight = item.metadata?.highlight as Record<string, string[]> | undefined;
  const snippet = highlight?.content?.[0] || item.content.slice(0, 260);

  return (
    <div className="rounded-2xl border border-slate-700/70 bg-slate-900/70 p-4 shadow-lg shadow-black/20">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="rounded-full border border-slate-600 bg-slate-950 px-2 py-1 font-mono text-xs text-slate-400">
            #{index + 1}
          </span>
          <span className={`rounded-full border px-2 py-1 text-xs ${sourceClass}`}>
            {item.source_type}
          </span>
        </div>
        <span className="font-mono text-xs text-cyan-300">{item.score.toFixed(4)}</span>
      </div>
      <div
        className="text-sm leading-6 text-slate-200 [&_em]:rounded [&_em]:bg-cyan-300/20 [&_em]:px-1 [&_em]:not-italic [&_em]:text-cyan-200"
        dangerouslySetInnerHTML={{ __html: snippet }}
      />
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="mt-3 text-xs text-cyan-300 hover:text-cyan-100"
      >
        {open ? "收起 metadata" : "展开 metadata"}
      </button>
      {open && <div className="mt-3"><JsonBlock value={item.metadata} /></div>}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-2xl border border-slate-700 bg-slate-900/80 p-4">
      <div className="text-xs uppercase tracking-[0.2em] text-slate-500">{label}</div>
      <div className="mt-2 font-mono text-2xl text-slate-100">{value}</div>
    </div>
  );
}

export default function RetrievalTestPage() {
  const [query, setQuery] = useState("");
  const [ticker, setTicker] = useState("");
  const [bloggerFilter, setBloggerFilter] = useState("");
  const [tab, setTab] = useState<Tab>("overview");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<RetrievalDebugResponse | null>(null);

  const sourceCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const item of data?.fused || []) {
      counts[item.source_type] = (counts[item.source_type] || 0) + 1;
    }
    return counts;
  }, [data]);

  const run = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const bloggers = bloggerFilter.trim()
        ? bloggerFilter.split(",").map((v) => v.trim()).filter(Boolean)
        : undefined;
      setData(await debugRetrieve(query.trim(), ticker.trim() || undefined, bloggers));
      setTab("overview");
    } catch (err) {
      setError(err instanceof Error ? err.message : "检索调试失败");
    } finally {
      setLoading(false);
    }
  };

  const tabs: { key: Tab; label: string }[] = [
    { key: "overview", label: "Overview" },
    { key: "es", label: "ES DSL / Raw" },
    { key: "paths", label: "Source Paths" },
    { key: "fusion", label: "RRF Fusion" },
    { key: "rerank", label: "Rerank" },
  ];

  return (
    <div className="min-h-screen rounded-3xl bg-[#050914] p-6 text-slate-100">
      <div className="mb-6 overflow-hidden rounded-3xl border border-cyan-400/20 bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.18),transparent_35%),linear-gradient(135deg,#0f172a,#020617)] p-6 shadow-2xl shadow-cyan-950/40">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="mb-3 text-xs uppercase tracking-[0.35em] text-cyan-300">
              Retrieval Observatory
            </div>
            <h1 className="text-3xl font-semibold tracking-tight text-white">
              RAG 检索质量调试台
            </h1>
            <p className="mt-2 max-w-2xl text-sm text-slate-400">
              同屏查看 ES DSL、原始召回、RRF 融合和 rerank 结果，用于定位“召回不足 / 排序偏差 / 上下文污染”。
            </p>
          </div>
          <button
            onClick={run}
            disabled={loading || !query.trim()}
            className="rounded-2xl bg-cyan-300 px-6 py-3 text-sm font-semibold text-slate-950 shadow-lg shadow-cyan-400/20 transition hover:bg-cyan-200 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {loading ? "检索中..." : "运行调试"}
          </button>
        </div>

        <div className="mt-6 grid gap-3 lg:grid-cols-[2fr_1fr_1.5fr]">
          <textarea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="输入检索问题，例如：最近 NVDA 的主要风险是什么？"
            className="min-h-28 rounded-2xl border border-slate-700 bg-slate-950/80 p-4 text-sm text-slate-100 outline-none ring-cyan-400/30 placeholder:text-slate-600 focus:ring-4"
          />
          <input
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            placeholder="Ticker 可选"
            className="rounded-2xl border border-slate-700 bg-slate-950/80 p-4 text-sm outline-none ring-cyan-400/30 placeholder:text-slate-600 focus:ring-4"
          />
          <input
            value={bloggerFilter}
            onChange={(e) => setBloggerFilter(e.target.value)}
            placeholder="博主过滤，可逗号分隔"
            className="rounded-2xl border border-slate-700 bg-slate-950/80 p-4 text-sm outline-none ring-cyan-400/30 placeholder:text-slate-600 focus:ring-4"
          />
        </div>
      </div>

      {error && (
        <div className="mb-6 rounded-2xl border border-rose-400/30 bg-rose-950/40 p-4 text-rose-200">
          {error}
        </div>
      )}

      {data && (
        <>
          <div className="mb-6 grid gap-3 md:grid-cols-4">
            <Metric label="ES raw hits" value={data.es_debug?.raw_hits?.length ?? 0} />
            <Metric label="Fused" value={data.fused.length} />
            <Metric label="Reranked" value={data.reranked.length} />
            <Metric label="Latency" value={`${Math.round(Object.values(data.latency_ms).reduce((a, b) => a + b, 0))}ms`} />
          </div>

          <div className="mb-5 flex flex-wrap gap-2">
            {tabs.map((item) => (
              <button
                key={item.key}
                onClick={() => setTab(item.key)}
                className={`rounded-full border px-4 py-2 text-sm transition ${
                  tab === item.key
                    ? "border-cyan-300 bg-cyan-300 text-slate-950"
                    : "border-slate-700 bg-slate-900 text-slate-300 hover:border-cyan-400"
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>

          {tab === "overview" && (
            <div className="grid gap-5 lg:grid-cols-2">
              <div className="rounded-3xl border border-slate-700 bg-slate-900/60 p-5">
                <h2 className="mb-4 text-lg font-semibold">Intent</h2>
                <JsonBlock value={data.intent} />
              </div>
              <div className="rounded-3xl border border-slate-700 bg-slate-900/60 p-5">
                <h2 className="mb-4 text-lg font-semibold">Source Mix</h2>
                <div className="space-y-3">
                  {Object.entries(sourceCounts).map(([source, count]) => (
                    <div key={source}>
                      <div className="mb-1 flex justify-between text-sm">
                        <span>{source}</span>
                        <span className="font-mono text-cyan-300">{count}</span>
                      </div>
                      <div className="h-2 rounded-full bg-slate-800">
                        <div
                          className="h-2 rounded-full bg-cyan-300"
                          style={{ width: `${Math.min(100, count * 12)}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {tab === "es" && (
            <div className="grid gap-5 lg:grid-cols-2">
              <div>
                <h2 className="mb-3 text-lg font-semibold">ES Query DSL</h2>
                <JsonBlock value={data.es_debug?.query || data.es_debug?.error} />
              </div>
              <div>
                <h2 className="mb-3 text-lg font-semibold">Raw Hits</h2>
                <JsonBlock value={data.es_debug?.raw_hits || []} />
              </div>
            </div>
          )}

          {tab === "paths" && (
            <div className="space-y-6">
              {PATHS.map((path) => (
                <section key={path}>
                  <h2 className="mb-3 text-lg font-semibold">{path}</h2>
                  <div className="grid gap-3 lg:grid-cols-2">
                    {(data.paths[path] || []).map((item, index) => (
                      <ResultCard key={`${path}-${item.unique_id}-${index}`} item={item} index={index} />
                    ))}
                  </div>
                </section>
              ))}
            </div>
          )}

          {tab === "fusion" && (
            <div className="grid gap-3 lg:grid-cols-2">
              {data.fused.map((item, index) => (
                <ResultCard key={`${item.unique_id}-${index}`} item={item} index={index} />
              ))}
            </div>
          )}

          {tab === "rerank" && (
            <div className="grid gap-5 lg:grid-cols-[360px_1fr]">
              <JsonBlock value={data.rerank_debug || {}} />
              <div className="grid gap-3">
                {data.reranked.map((item, index) => (
                  <ResultCard key={`${item.unique_id}-${index}`} item={item} index={index} />
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
