"use client";

import { useState, useEffect, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  getReport,
  streamReport,
  type ReportCitation,
  type ReportDetail,
  type ReportSection,
} from "@/lib/api";
import { formatDateTime, formatLatency } from "@/lib/datetime";
import StatusBadge from "@/components/StatusBadge";

// ============================================================
// Consensus Color Mapping
// ============================================================

const CONSENSUS_CONFIG: Record<string, { color: string; label: string }> = {
  strong_buy: { color: "bg-green-700 text-white", label: "强烈看多" },
  buy: { color: "bg-green-500 text-white", label: "看多" },
  neutral: { color: "bg-gray-400 text-white", label: "中性" },
  sell: { color: "bg-red-500 text-white", label: "看空" },
  strong_sell: { color: "bg-red-700 text-white", label: "强烈看空" },
};

// ============================================================
// Trigger Type Config
// ============================================================

const TRIGGER_CONFIG: Record<string, { color: string; label: string }> = {
  manual: { color: "bg-blue-100 text-blue-700", label: "手动" },
  chat: { color: "bg-green-100 text-green-700", label: "对话" },
  scheduled: { color: "bg-purple-100 text-purple-700", label: "定时" },
};

// ============================================================
// Source Type Badge Styles
// ============================================================

const SOURCE_BADGE_STYLES: Record<string, string> = {
  documents: "bg-blue-100 text-blue-700",
  tweets: "bg-green-100 text-green-700",
  analyses: "bg-purple-100 text-purple-700",
  structured: "bg-orange-100 text-orange-700",
  kol: "bg-green-100 text-green-700",
  research: "bg-blue-100 text-blue-700",
  news: "bg-yellow-100 text-yellow-700",
  risk: "bg-red-100 text-red-700",
  history: "bg-gray-100 text-gray-700",
};

const SOURCE_BADGE_LABELS: Record<string, string> = {
  documents: "文档",
  tweets: "推文",
  analyses: "分析",
  structured: "结构化",
  kol: "KOL",
  research: "研报",
  news: "新闻",
  risk: "风险",
  history: "历史",
};

// ============================================================
// Citation Rendering Helper
// ============================================================

function renderContentWithCitations(
  content: string,
  onCitationClick: (index: number) => void
) {
  const parts = content.split(/(\[\d+\])/g);
  return parts.map((part, i) => {
    const match = part.match(/^\[(\d+)\]$/);
    if (match) {
      const citIndex = parseInt(match[1], 10);
      return (
        <span
          key={i}
          onClick={() => onCitationClick(citIndex)}
          className="inline-flex items-center px-1 text-xs font-medium text-blue-600 bg-blue-100 rounded cursor-pointer hover:bg-blue-200"
          title={`引用 [${citIndex}]`}
        >
          [{citIndex}]
        </span>
      );
    }
    return <span key={i}>{part}</span>;
  });
}

// ============================================================
// Collapsible Section Component
// ============================================================

function CollapsibleSection({
  sectionKey,
  title,
  sourceType,
  content,
  error,
  onCitationClick,
}: {
  sectionKey: string;
  title: string;
  sourceType: string;
  content: string;
  error?: string | null;
  onCitationClick: (index: number) => void;
}) {
  const [expanded, setExpanded] = useState(true);

  const badgeStyle =
    SOURCE_BADGE_STYLES[sourceType] || "bg-gray-100 text-gray-700";
  const badgeLabel =
    SOURCE_BADGE_LABELS[sourceType] || sourceType;

  const hasError = !!error;

  return (
    <div
      className={`border rounded-lg overflow-hidden ${
        hasError ? "border-red-300 bg-red-50/30" : ""
      }`}
    >
      <div
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 cursor-pointer py-3 px-4 hover:bg-gray-50 rounded"
      >
        <span className="text-sm text-gray-500">
          {expanded ? "▼" : "▶"}
        </span>
        <span className="font-medium text-gray-800">{title}</span>
        <span
          className={`text-xs px-2 py-0.5 rounded-full font-medium ${badgeStyle}`}
        >
          {badgeLabel}
        </span>
        {hasError && (
          <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-red-100 text-red-700">
            ⚠ 失败
          </span>
        )}
      </div>
      {expanded && (
        <div className="px-4 pb-4">
          {hasError ? (
            <div className="text-sm text-red-600 leading-relaxed">
              {error}
            </div>
          ) : (
            <div className="whitespace-pre-wrap text-sm text-gray-700 leading-relaxed">
              {renderContentWithCitations(content, onCitationClick)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ============================================================
// Main Page Component
// ============================================================

export default function ReportDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const [report, setReport] = useState<ReportDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const streamRef = useRef<(() => void) | null>(null);
  const citationsRef = useRef<HTMLDivElement>(null);

  // Initial fetch + SSE subscription
  useEffect(() => {
    if (!id) return;
    let cancelled = false;

    const init = async () => {
      try {
        const data = await getReport(id);
        if (cancelled) return;
        setReport(data);
        setError(null);
        setLoading(false);

        if (data.status !== "generating") return;

        // Subscribe to SSE for incremental updates
        streamRef.current = streamReport(id, {
          onSnapshot: (snap) => {
            if (cancelled) return;
            setReport((prev) => ({ ...(prev as ReportDetail), ...snap }));
          },
          onReranked: (citations: ReportCitation[]) => {
            if (cancelled) return;
            setReport((prev) =>
              prev ? { ...prev, citations } : prev,
            );
          },
          onSectionDone: (section: ReportSection) => {
            if (cancelled || !section.name) return;
            setReport((prev) => {
              if (!prev) return prev;
              return {
                ...prev,
                sections: { ...prev.sections, [section.name!]: section },
              };
            });
          },
          onSynthesized: (s) => {
            if (cancelled) return;
            setReport((prev) =>
              prev
                ? {
                    ...prev,
                    summary: s.summary ?? prev.summary,
                    consensus: s.consensus ?? prev.consensus,
                    latency_ms: s.latency_ms ?? prev.latency_ms,
                  }
                : prev,
            );
          },
          onDone: async () => {
            if (cancelled) return;
            try {
              const fresh = await getReport(id);
              if (!cancelled) setReport(fresh);
            } catch (e) {
              console.error("Refresh after done failed:", e);
            }
          },
          onError: (msg) => {
            console.error("SSE error:", msg);
            if (!cancelled) {
              setReport((prev) =>
                prev
                  ? { ...prev, status: "failed", error_detail: msg }
                  : prev,
              );
            }
          },
        });
      } catch (e: unknown) {
        if (cancelled) return;
        const err = e as { message?: string; status?: number };
        if (err.message?.includes("404") || err.status === 404) {
          setError("报告不存在");
        } else {
          setError("加载失败");
        }
        setLoading(false);
      }
    };

    init();

    return () => {
      cancelled = true;
      if (streamRef.current) {
        streamRef.current();
        streamRef.current = null;
      }
    };
  }, [id]);

  const [flashCitation, setFlashCitation] = useState<number | null>(null);

  // Handle citation click - scroll to specific citation row and flash it
  const handleCitationClick = (index: number) => {
    const el = document.getElementById(`citation-${index}`);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      setFlashCitation(index);
      setTimeout(() => setFlashCitation(null), 1500);
    } else {
      citationsRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  };

  // Loading state
  if (loading) {
    return <p className="text-center py-10">加载中...</p>;
  }

  // Error state
  if (error) {
    return (
      <div className="text-center py-10">
        <p className="text-red-600 text-lg">{error}</p>
        <button
          onClick={() => router.push("/reports")}
          className="mt-4 text-blue-600 hover:underline text-sm"
        >
          ← 返回报告列表
        </button>
      </div>
    );
  }

  if (!report) return null;

  // Generating skeleton
  if (report.status === "generating") {
    const hasPartial =
      (report.sections && Object.keys(report.sections).length > 0) ||
      (report.citations && report.citations.length > 0);

    if (!hasPartial) {
      return (
        <div className="space-y-6">
          {/* Header */}
          <div className="flex items-center justify-between">
            <button
              onClick={() => router.push("/reports")}
              className="text-blue-600 hover:underline text-sm"
            >
              ← 返回报告列表
            </button>
            <StatusBadge status="generating" />
          </div>

          {/* Skeleton blocks */}
          <div className="bg-white rounded-lg shadow p-6 space-y-4">
            <div className="h-6 bg-gray-200 rounded animate-pulse w-1/3"></div>
            <div className="h-4 bg-gray-200 rounded animate-pulse w-full"></div>
            <div className="h-4 bg-gray-200 rounded animate-pulse w-2/3"></div>
            <div className="h-20 bg-gray-200 rounded animate-pulse w-full"></div>
            <div className="h-4 bg-gray-200 rounded animate-pulse w-1/2"></div>
            <div className="h-32 bg-gray-200 rounded animate-pulse w-full"></div>
            <div className="h-4 bg-gray-200 rounded animate-pulse w-3/4"></div>
            <div className="h-32 bg-gray-200 rounded animate-pulse w-full"></div>
          </div>
        </div>
      );
    }
    // else: fall through to the regular render so partial sections show progressively
  }

  // Failed state
  if (report.status === "failed") {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <button
            onClick={() => router.push("/reports")}
            className="text-blue-600 hover:underline text-sm"
          >
            ← 返回报告列表
          </button>
          <StatusBadge status="failed" />
        </div>

        <div className="bg-white rounded-lg shadow p-6">
          <h1 className="text-xl font-bold mb-4">
            {report.title || `${report.ticker} 分析报告`}
          </h1>
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <p className="text-red-700 font-medium mb-1">生成失败</p>
            <p className="text-red-600 text-sm">
              {report.error_detail || "未知错误"}
            </p>
          </div>
        </div>
      </div>
    );
  }

  // Normal "done" state
  const consensusConfig = report.consensus
    ? CONSENSUS_CONFIG[report.consensus]
    : null;
  const triggerConfig = TRIGGER_CONFIG[report.trigger_type] || null;

  return (
    <div className="space-y-6">
      {/* ========== Header ========== */}
      <div className="bg-white rounded-lg shadow p-4">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <button
            onClick={() => router.push("/reports")}
            className="text-blue-600 hover:underline text-sm"
          >
            ← 返回报告列表
          </button>
          <h1 className="text-lg font-bold text-gray-800">
            {report.title || `${report.ticker} 分析报告`}
          </h1>
          <span className="text-sm text-gray-500">
            {formatDateTime(report.created_at)}
          </span>
        </div>
        {report.status !== "done" && (
          <div className="mt-2">
            <StatusBadge status={report.status} />
          </div>
        )}
      </div>

      {/* ========== Summary + Consensus ========== */}
      <div className="bg-white rounded-lg shadow p-6 space-y-4">
        {report.summary && (
          <div className="bg-blue-50 border-l-4 border-blue-500 p-4">
            <p className="text-sm text-gray-800 leading-relaxed">
              {report.summary}
            </p>
          </div>
        )}

        {consensusConfig && (
          <div className="flex items-center gap-3">
            <span className="text-sm text-gray-600 font-medium">共识评级:</span>
            <span
              className={`text-sm px-3 py-1 rounded-full font-medium ${consensusConfig.color}`}
            >
              {consensusConfig.label}
            </span>
          </div>
        )}
      </div>

      {/* ========== Sections (collapsible) ========== */}
      {report.sections && Object.keys(report.sections).length > 0 && (
        <div className="bg-white rounded-lg shadow p-6 space-y-3">
          {Object.entries(report.sections).map(([key, section]) => (
            <CollapsibleSection
              key={key}
              sectionKey={key}
              title={section.title}
              sourceType={section.source_type}
              content={section.content}
              error={section.error}
              onCitationClick={handleCitationClick}
            />
          ))}
        </div>
      )}

      {/* ========== Citations ========== */}
      {report.citations && report.citations.length > 0 && (
        <div
          ref={citationsRef}
          className="bg-white rounded-lg shadow p-6"
        >
          <h2 className="text-base font-semibold text-gray-800 mb-4">
            引用来源
          </h2>
          <div className="divide-y divide-gray-100">
            {report.citations.map((citation) => {
              const badgeStyle =
                SOURCE_BADGE_STYLES[citation.source_type] ||
                "bg-gray-100 text-gray-700";
              const badgeLabel =
                SOURCE_BADGE_LABELS[citation.source_type] ||
                citation.source_type;
              const truncatedSnippet =
                (citation.snippet || "").length > 100
                  ? (citation.snippet || "").slice(0, 100) + "..."
                  : citation.snippet || "";

              return (
                <div
                  key={citation.index}
                  id={`citation-${citation.index}`}
                  className={`py-2 flex items-start gap-2 transition-colors duration-500 ${
                    flashCitation === citation.index
                      ? "bg-yellow-100 ring-2 ring-yellow-300 rounded"
                      : ""
                  }`}
                >
                  <span className="text-xs font-mono text-blue-600 font-medium mt-0.5">
                    [{citation.index}]
                  </span>
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full font-medium whitespace-nowrap ${badgeStyle}`}
                  >
                    {badgeLabel}
                  </span>
                  <span className="text-sm text-gray-700">
                    {citation.title && (
                      <span className="font-medium">{citation.title}: </span>
                    )}
                    <span className="text-gray-500">
                      &ldquo;{truncatedSnippet}&rdquo;
                    </span>
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ========== Footer (metadata) ========== */}
      <div className="bg-gray-50 rounded-lg p-4 text-sm text-gray-600">
        <div className="flex items-center gap-6 flex-wrap">
          {report.token_usage && (
            <span>
              Token 用量: input{" "}
              {report.token_usage.input ?? report.token_usage.prompt_tokens ?? 0}{" "}
              / output{" "}
              {report.token_usage.output ??
                report.token_usage.completion_tokens ??
                0}
            </span>
          )}
          {report.latency_ms != null && (
            <span>生成耗时: {formatLatency(report.latency_ms)}</span>
          )}
          {triggerConfig && (
            <span
              className={`text-xs px-2 py-0.5 rounded-full font-medium ${triggerConfig.color}`}
            >
              {triggerConfig.label}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
