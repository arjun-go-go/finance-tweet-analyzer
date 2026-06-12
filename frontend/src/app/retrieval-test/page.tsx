"use client";

import { useState } from "react";
import {
  debugRetrieve,
  type RetrievalResult,
  type RetrievalDebugResponse,
} from "@/lib/api";
import { formatLatency } from "@/lib/datetime";

type MainTab = "intent" | "raw" | "fused" | "reranked" | "timing";
type PathTab = "documents" | "tweets" | "analyses" | "structured" | "bm25";

const MAIN_TABS: { key: MainTab; label: string }[] = [
  { key: "intent", label: "Intent解析" },
  { key: "raw", label: "原始召回" },
  { key: "fused", label: "RRF融合" },
  { key: "reranked", label: "Rerank结果" },
  { key: "timing", label: "耗时统计" },
];

const PATH_TABS: { key: PathTab; label: string }[] = [
  { key: "documents", label: "文档" },
  { key: "tweets", label: "推文" },
  { key: "analyses", label: "分析" },
  { key: "structured", label: "结构化" },
  { key: "bm25", label: "BM25" },
];

const SOURCE_BADGE_STYLES: Record<string, string> = {
  documents: "bg-blue-100 text-blue-700",
  tweets: "bg-green-100 text-green-700",
  analyses: "bg-purple-100 text-purple-700",
  structured: "bg-orange-100 text-orange-700",
  bm25: "bg-yellow-100 text-yellow-700",
  error: "bg-red-100 text-red-700",
};

const SOURCE_BADGE_LABELS: Record<string, string> = {
  documents: "文档",
  tweets: "推文",
  analyses: "分析",
  structured: "结构化",
  bm25: "BM25",
  error: "错误",
};

const TIMING_LABELS: Record<string, string> = {
  intent: "Intent解析",
  documents: "文档检索",
  tweets: "推文检索",
  analyses: "分析检索",
  structured: "结构化检索",
  bm25: "BM25检索",
  fusion: "RRF融合",
  rerank: "Rerank",
};

function ResultItem({
  item,
  rank,
  rankChange,
}: {
  item: RetrievalResult;
  rank?: number;
  rankChange?: number | null;
}) {
  const [expanded, setExpanded] = useState(false);
  const [showMeta, setShowMeta] = useState(false);

  const badgeStyle =
    SOURCE_BADGE_STYLES[item.source_type] || "bg-gray-100 text-gray-700";
  const badgeLabel =
    SOURCE_BADGE_LABELS[item.source_type] || item.source_type;

  const truncated =
    item.content.length > 200 ? item.content.slice(0, 200) : null;

  return (
    <div className="bg-white border rounded-lg p-3 mb-2">
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <span
            className={`text-xs px-2 py-0.5 rounded-full font-medium ${badgeStyle}`}
          >
            {badgeLabel}
          </span>
          {rank != null && (
            <span className="text-xs text-gray-500 font-mono">#{rank}</span>
          )}
          {rankChange != null && rankChange !== 0 && (
            <span
              className={`text-xs font-medium px-1.5 py-0.5 rounded ${
                rankChange > 0
                  ? "bg-green-100 text-green-700"
                  : "bg-red-100 text-red-700"
              }`}
            >
              {rankChange > 0 ? `↑${rankChange}` : `↓${Math.abs(rankChange)}`}
            </span>
          )}
          {rankChange === 0 && (
            <span className="text-xs font-medium px-1.5 py-0.5 rounded bg-gray-100 text-gray-500">
              —
            </span>
          )}
        </div>
        <span className="text-sm font-mono text-gray-600">
          {item.score.toFixed(4)}
        </span>
      </div>

      <p className="text-sm text-gray-800 whitespace-pre-wrap">
        {expanded || !truncated ? item.content : `${truncated}...`}
      </p>

      <div className="flex gap-3 mt-2">
        {truncated && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-xs text-blue-600 hover:underline"
          >
            {expanded ? "收起" : "展开"}
          </button>
        )}
        <button
          onClick={() => setShowMeta(!showMeta)}
          className="text-xs text-blue-600 hover:underline"
        >
          {showMeta ? "隐藏元数据" : "元数据"}
        </button>
      </div>

      {showMeta && (
        <pre className="bg-gray-50 rounded p-4 text-sm font-mono overflow-x-auto whitespace-pre-wrap mt-2">
          {JSON.stringify(item.metadata, null, 2)}
        </pre>
      )}
    </div>
  );
}

export default function RetrievalTestPage() {
  const [query, setQuery] = useState("");
  const [ticker, setTicker] = useState("");
  const [bloggerFilter, setBloggerFilter] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<RetrievalDebugResponse | null>(null);

  const [mainTab, setMainTab] = useState<MainTab>("intent");
  const [pathTab, setPathTab] = useState<PathTab>("documents");

  const handleRetrieve = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const bloggers = bloggerFilter.trim()
        ? bloggerFilter.split(",").map((s) => s.trim()).filter(Boolean)
        : undefined;
      const result = await debugRetrieve(query.trim(), ticker.trim() || undefined, bloggers);
      setData(result);
    } catch (e: any) {
      if (e.message?.includes("404") || e.status === 404) {
        setError("调试模式未启用，请在后端配置 debug_mode=True");
      } else {
        setError(e.message || "检索失败，请稍后重试");
      }
    } finally {
      setLoading(false);
    }
  };

  const mainTabClass = (tab: MainTab) =>
    mainTab === tab
      ? "bg-blue-600 text-white px-4 py-2 rounded-lg text-sm"
      : "bg-gray-100 text-gray-600 px-4 py-2 rounded-lg text-sm hover:bg-gray-200";

  const pathTabClass = (tab: PathTab) =>
    pathTab === tab
      ? "bg-blue-600 text-white px-3 py-1.5 rounded-lg text-xs"
      : "bg-gray-100 text-gray-600 px-3 py-1.5 rounded-lg text-xs hover:bg-gray-200";

  // Build rank mapping for rerank comparison
  const fusedRankMap: Record<string, number> = {};
  if (data?.fused) {
    data.fused.forEach((item, idx) => {
      fusedRankMap[item.unique_id] = idx + 1;
    });
  }

  // Compute max latency for bar chart scaling
  const maxLatency = data?.latency_ms
    ? Math.max(...Object.values(data.latency_ms), 1)
    : 1;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">检索召回测试</h1>
        <p className="text-sm text-gray-500">开发调试工具 — 需启用 debug_mode</p>
      </div>

      {/* Input Area */}
      <div className="bg-white rounded-lg shadow p-4 space-y-3">
        <textarea
          rows={3}
          placeholder="输入检索查询..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="w-full border rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y"
          disabled={loading}
        />
        <div className="flex gap-3">
          <input
            type="text"
            placeholder="标的筛选（可选）"
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            className="border rounded-lg px-4 py-2 flex-1 focus:outline-none focus:ring-2 focus:ring-blue-500"
            disabled={loading}
          />
          <input
            type="text"
            placeholder="博主筛选（可选，逗号分隔）"
            value={bloggerFilter}
            onChange={(e) => setBloggerFilter(e.target.value)}
            className="border rounded-lg px-4 py-2 flex-1 focus:outline-none focus:ring-2 focus:ring-blue-500"
            disabled={loading}
          />
          <button
            onClick={handleRetrieve}
            disabled={loading || !query.trim()}
            className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 whitespace-nowrap"
          >
            {loading ? "检索中..." : "检索"}
          </button>
        </div>
      </div>

      {/* Error Display */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-red-700 text-sm">{error}</p>
        </div>
      )}

      {/* Results Area */}
      {data && (
        <div className="bg-white rounded-lg shadow p-4">
          {/* Main Tabs */}
          <div className="flex gap-2 mb-4 flex-wrap">
            {MAIN_TABS.map((tab) => (
              <button
                key={tab.key}
                className={mainTabClass(tab.key)}
                onClick={() => setMainTab(tab.key)}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Tab 1: Intent */}
          {mainTab === "intent" && (
            <pre className="bg-gray-50 rounded p-4 text-sm font-mono overflow-x-auto whitespace-pre-wrap">
              {JSON.stringify(data.intent, null, 2)}
            </pre>
          )}

          {/* Tab 2: Raw Paths */}
          {mainTab === "raw" && (
            <div>
              <div className="flex gap-2 mb-3 flex-wrap">
                {PATH_TABS.map((tab) => (
                  <button
                    key={tab.key}
                    className={pathTabClass(tab.key)}
                    onClick={() => setPathTab(tab.key)}
                  >
                    {tab.label} ({data.paths[tab.key]?.length || 0})
                  </button>
                ))}
              </div>
              <div>
                {(data.paths[pathTab] || []).length === 0 ? (
                  <p className="text-gray-500 text-sm py-4 text-center">
                    无召回结果
                  </p>
                ) : (
                  data.paths[pathTab].map((item, idx) => (
                    <ResultItem key={item.unique_id || idx} item={item} rank={idx + 1} />
                  ))
                )}
              </div>
            </div>
          )}

          {/* Tab 3: Fused */}
          {mainTab === "fused" && (
            <div>
              {data.fused.length === 0 ? (
                <p className="text-gray-500 text-sm py-4 text-center">
                  无融合结果
                </p>
              ) : (
                data.fused.map((item, idx) => (
                  <ResultItem key={item.unique_id || idx} item={item} rank={idx + 1} />
                ))
              )}
            </div>
          )}

          {/* Tab 4: Reranked */}
          {mainTab === "reranked" && (
            <div>
              {data.reranked.length === 0 ? (
                <p className="text-gray-500 text-sm py-4 text-center">
                  无Rerank结果
                </p>
              ) : (
                data.reranked.map((item, idx) => {
                  const fusedPos = fusedRankMap[item.unique_id];
                  const currentPos = idx + 1;
                  const rankChange =
                    fusedPos != null ? fusedPos - currentPos : null;
                  return (
                    <ResultItem
                      key={item.unique_id || idx}
                      item={item}
                      rank={currentPos}
                      rankChange={rankChange}
                    />
                  );
                })
              )}
            </div>
          )}

          {/* Tab 5: Timing */}
          {mainTab === "timing" && (
            <div className="space-y-2">
              {Object.entries(data.latency_ms).map(([stage, ms]) => (
                <div key={stage} className="flex items-center gap-3">
                  <span className="text-sm text-gray-700 w-28 shrink-0">
                    {TIMING_LABELS[stage] || stage}
                  </span>
                  <div className="flex-1 bg-gray-100 rounded h-6 relative">
                    <div
                      className="bg-blue-500 rounded h-6"
                      style={{ width: `${(ms / maxLatency) * 100}%` }}
                    />
                  </div>
                  <span className="text-sm font-mono text-gray-600 w-16 text-right shrink-0">
                    {formatLatency(ms)}
                  </span>
                </div>
              ))}
              <div className="border-t pt-3 mt-3 flex justify-between">
                <span className="text-sm font-medium text-gray-700">总耗时</span>
                <span className="text-sm font-mono font-medium text-gray-800">
                  {formatLatency(
                    Object.values(data.latency_ms).reduce((a, b) => a + b, 0)
                  )}
                </span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
