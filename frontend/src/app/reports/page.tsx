"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState, useEffect, useCallback, useRef, Suspense } from "react";
import {
  listReports,
  generateReport,
  getReport,
  deleteReport,
  type ReportListItem,
} from "@/lib/api";
import { formatDateTime, formatLatency } from "@/lib/datetime";
import StatusBadge from "@/components/StatusBadge";
import ConfirmDialog from "@/components/ConfirmDialog";

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
// Trigger Type Tag Config
// ============================================================

const TRIGGER_CONFIG: Record<string, { color: string; label: string }> = {
  manual: { color: "bg-blue-100 text-blue-700", label: "手动" },
  chat: { color: "bg-green-100 text-green-700", label: "对话" },
  scheduled: { color: "bg-purple-100 text-purple-700", label: "定时" },
};

// ============================================================
// Time Range Options
// ============================================================

const TIME_RANGE_OPTIONS = [
  { value: "1w", label: "近1周" },
  { value: "2w", label: "近2周" },
  { value: "1m", label: "近1月" },
  { value: "3m", label: "近3月" },
];

// ============================================================
// Main Page Component (inner, uses useSearchParams)
// ============================================================

function ReportsPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();

  // Read ticker from URL query params
  const urlTicker = searchParams.get("ticker") || "";

  // Report list state
  const [reports, setReports] = useState<ReportListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const pageSize = 9;

  // Filter state
  const [tickerFilter, setTickerFilter] = useState(urlTicker);

  // Generate form state
  const [showForm, setShowForm] = useState(false);
  const [formTicker, setFormTicker] = useState("");
  const [formTimeRange, setFormTimeRange] = useState("1w");
  const [formFocusAspects, setFormFocusAspects] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // Delete dialog
  const [deleteTarget, setDeleteTarget] = useState<ReportListItem | null>(null);

  // Polling for generating reports
  const pollingRef = useRef<Map<string, ReturnType<typeof setInterval>>>(new Map());

  // Load reports
  const loadReports = useCallback(async () => {
    try {
      const result = await listReports({
        ticker: tickerFilter || undefined,
        page,
        size: pageSize,
      });
      setReports(result.items);
      setTotal(result.total);
    } catch (e) {
      console.error("Failed to load reports:", e);
    } finally {
      setLoading(false);
    }
  }, [page, tickerFilter]);

  useEffect(() => {
    loadReports();
  }, [loadReports]);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      pollingRef.current.forEach((interval) => clearInterval(interval));
      pollingRef.current.clear();
    };
  }, []);

  // Start polling for a specific report
  const startPolling = useCallback((reportId: string) => {
    if (pollingRef.current.has(reportId)) return;

    const interval = setInterval(async () => {
      try {
        const detail = await getReport(reportId);
        if (detail.status === "done" || detail.status === "failed") {
          // Stop polling
          clearInterval(pollingRef.current.get(reportId)!);
          pollingRef.current.delete(reportId);
          // Update the report in the list
          setReports((prev) =>
            prev.map((r) =>
              r.id === reportId
                ? {
                    ...r,
                    status: detail.status as ReportListItem["status"],
                    title: detail.title,
                    consensus: detail.consensus,
                    latency_ms: detail.latency_ms,
                  }
                : r
            )
          );
        }
      } catch (e) {
        console.error(`Failed to poll report ${reportId}:`, e);
      }
    }, 3000);

    pollingRef.current.set(reportId, interval);
  }, []);

  // Start polling for any existing generating reports on load
  useEffect(() => {
    reports
      .filter((r) => r.status === "generating")
      .forEach((r) => startPolling(r.id));
  }, [reports, startPolling]);

  // Generate report handler
  const handleGenerate = async () => {
    if (!formTicker.trim()) {
      setFormError("请输入标的代码");
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      const focusAspects = formFocusAspects
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);

      const result = await generateReport(
        formTicker.trim().toUpperCase(),
        formTimeRange,
        focusAspects.length > 0 ? focusAspects : undefined
      );

      // Add a skeleton item to the top of the list
      const newItem: ReportListItem = {
        id: result.id,
        ticker: formTicker.trim().toUpperCase(),
        title: null,
        trigger_type: "manual",
        consensus: null,
        status: "generating",
        latency_ms: null,
        created_at: new Date().toISOString(),
      };
      setReports((prev) => [newItem, ...prev.filter((r) => r.id !== newItem.id)]);
      setTotal((prev) => prev + 1);

      // Start polling
      startPolling(result.id);

      // Reset form
      setFormTicker("");
      setFormFocusAspects("");
      setShowForm(false);
    } catch (e: any) {
      setFormError(e.message || "生成失败");
    } finally {
      setSubmitting(false);
    }
  };

  // Delete handler
  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteReport(deleteTarget.id);
      // Stop polling if active
      if (pollingRef.current.has(deleteTarget.id)) {
        clearInterval(pollingRef.current.get(deleteTarget.id)!);
        pollingRef.current.delete(deleteTarget.id);
      }
      setDeleteTarget(null);
      await loadReports();
    } catch (e) {
      console.error("Failed to delete report:", e);
      setDeleteTarget(null);
    }
  };

  // Refresh handler
  const handleRefresh = () => {
    setLoading(true);
    loadReports();
  };

  // Filter on Enter
  const handleFilterKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      setPage(1);
      setLoading(true);
      loadReports();
    }
  };

  const totalPages = Math.ceil(total / pageSize);

  if (loading) return <p className="text-center py-10">加载中...</p>;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">分析报告</h1>

      {/* Action Bar */}
      <div className="flex items-center gap-3 flex-wrap">
        <button
          onClick={() => setShowForm(!showForm)}
          className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 text-sm font-medium"
        >
          {showForm ? "收起" : "生成报告"}
        </button>
        <input
          type="text"
          placeholder="按标的筛选..."
          value={tickerFilter}
          onChange={(e) => setTickerFilter(e.target.value)}
          onKeyDown={handleFilterKeyDown}
          className="border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <button
          onClick={handleRefresh}
          className="bg-gray-100 text-gray-600 px-3 py-1.5 rounded-lg text-sm hover:bg-gray-200"
        >
          刷新
        </button>
        <span className="text-sm text-gray-500 ml-auto">
          共 {total} 份报告
        </span>
      </div>

      {/* Generate Report Form */}
      {showForm && (
        <div className="bg-white rounded-lg shadow p-4 space-y-3">
          <h2 className="text-sm font-semibold text-gray-700">生成新报告</h2>
          {formError && (
            <p className="text-red-600 text-sm">{formError}</p>
          )}
          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-3">
            <input
              type="text"
              placeholder="标的代码，如 BTC"
              value={formTicker}
              onChange={(e) => setFormTicker(e.target.value)}
              className="border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              disabled={submitting}
            />
            <select
              value={formTimeRange}
              onChange={(e) => setFormTimeRange(e.target.value)}
              className="border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              disabled={submitting}
            >
              {TIME_RANGE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
            <input
              type="text"
              placeholder="关注方面，逗号分隔（可选）"
              value={formFocusAspects}
              onChange={(e) => setFormFocusAspects(e.target.value)}
              className="border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              disabled={submitting}
            />
            <div className="flex gap-2">
              <button
                onClick={handleGenerate}
                disabled={submitting}
                className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm font-medium"
              >
                {submitting ? "提交中..." : "开始生成"}
              </button>
              <button
                onClick={() => {
                  setShowForm(false);
                  setFormError(null);
                }}
                className="bg-gray-100 text-gray-600 px-4 py-2 rounded-lg hover:bg-gray-200 text-sm"
              >
                取消
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Report Card Grid */}
      {reports.length === 0 ? (
        <div className="text-center py-10 text-gray-500">暂无报告</div>
      ) : (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {reports.map((report) => (
            <div
              key={report.id}
              onClick={() => {
                if (report.status !== "generating") {
                  router.push(`/reports/${report.id}`);
                }
              }}
              className={`bg-white rounded-lg shadow p-4 cursor-pointer hover:shadow-md transition-shadow ${
                report.status === "generating" ? "animate-pulse" : ""
              }`}
            >
              {/* Header: Ticker + Trigger Type */}
              <div className="flex items-center justify-between mb-2">
                <span className="text-lg font-bold text-blue-600">
                  {report.ticker}
                </span>
                <span
                  className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                    TRIGGER_CONFIG[report.trigger_type]?.color ||
                    "bg-gray-100 text-gray-700"
                  }`}
                >
                  {TRIGGER_CONFIG[report.trigger_type]?.label ||
                    report.trigger_type}
                </span>
              </div>

              {/* Title */}
              <p className="text-sm text-gray-800 font-medium truncate mb-2">
                {report.status === "generating"
                  ? "生成中..."
                  : report.title || "分析报告"}
              </p>

              {/* Consensus Badge */}
              {report.consensus && CONSENSUS_CONFIG[report.consensus] && (
                <span
                  className={`inline-block text-xs px-2 py-0.5 rounded-full font-medium mb-2 ${
                    CONSENSUS_CONFIG[report.consensus].color
                  }`}
                >
                  {CONSENSUS_CONFIG[report.consensus].label}
                </span>
              )}

              {/* Status (if not done) */}
              {report.status !== "done" && (
                <div className="mb-2">
                  <StatusBadge status={report.status} />
                </div>
              )}

              {/* Time */}
              <p className="text-xs text-gray-500 mb-2">
                {formatDateTime(report.created_at)}
              </p>

              {/* Footer: Latency + Delete */}
              <div className="flex items-center justify-between text-xs">
                <span className="text-gray-400">
                  {report.latency_ms != null
                    ? `耗时: ${formatLatency(report.latency_ms)}`
                    : ""}
                </span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setDeleteTarget(report);
                  }}
                  className="text-red-500 hover:text-red-700"
                >
                  删除
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-4">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="bg-gray-100 text-gray-600 px-4 py-2 rounded-lg text-sm hover:bg-gray-200 disabled:opacity-50"
          >
            上一页
          </button>
          <span className="text-sm text-gray-600">
            第 {page} 页 / 共 {totalPages} 页
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
            className="bg-gray-100 text-gray-600 px-4 py-2 rounded-lg text-sm hover:bg-gray-200 disabled:opacity-50"
          >
            下一页
          </button>
        </div>
      )}

      {/* Delete Confirmation */}
      <ConfirmDialog
        open={!!deleteTarget}
        title="删除报告"
        message={`确定要删除「${deleteTarget?.ticker || ""}」的报告吗？此操作不可撤销。`}
        confirmText="删除"
        variant="danger"
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}

// ============================================================
// Exported Page with Suspense boundary for useSearchParams
// ============================================================

export default function ReportsPage() {
  return (
    <Suspense fallback={<p className="text-center py-10">加载中...</p>}>
      <ReportsPageInner />
    </Suspense>
  );
}
