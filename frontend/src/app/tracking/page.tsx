"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  listTracking,
  createTracking,
  updateTracking,
  deleteTracking,
  triggerTracking,
  type TrackingItem,
} from "@/lib/api";
import { formatDateTime } from "@/lib/datetime";
import StatusBadge from "@/components/StatusBadge";
import ConfirmDialog from "@/components/ConfirmDialog";

// ============================================================
// Frequency Badge Config
// ============================================================

const FREQUENCY_CONFIG: Record<string, { color: string; label: string }> = {
  daily: { color: "bg-blue-100 text-blue-700", label: "每天" },
  weekly: { color: "bg-purple-100 text-purple-700", label: "每周" },
  manual: { color: "bg-gray-100 text-gray-700", label: "手动" },
};

// ============================================================
// Tracking Page
// ============================================================

export default function TrackingPage() {
  const router = useRouter();

  // List state
  const [items, setItems] = useState<TrackingItem[]>([]);
  const [loading, setLoading] = useState(true);

  // Add form state
  const [showForm, setShowForm] = useState(false);
  const [formTicker, setFormTicker] = useState("");
  const [formFrequency, setFormFrequency] = useState("daily");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // Trigger state
  const [triggerLoading, setTriggerLoading] = useState<string | null>(null);
  const [triggerError, setTriggerError] = useState<string | null>(null);
  const [triggerSuccess, setTriggerSuccess] = useState<string | null>(null);

  // Delete dialog state
  const [deleteTarget, setDeleteTarget] = useState<TrackingItem | null>(null);

  // Dropdown menu state
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    if (!openMenuId) return;
    const handler = () => setOpenMenuId(null);
    document.addEventListener("click", handler);
    return () => document.removeEventListener("click", handler);
  }, [openMenuId]);

  // Load tracking list
  const loadList = async () => {
    try {
      const result = await listTracking();
      setItems(result.items);
    } catch (e) {
      console.error("Failed to load tracking:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadList();
  }, []);

  // Clear trigger messages after delay
  useEffect(() => {
    if (triggerSuccess) {
      const timer = setTimeout(() => setTriggerSuccess(null), 3000);
      return () => clearTimeout(timer);
    }
  }, [triggerSuccess]);

  useEffect(() => {
    if (triggerError) {
      const timer = setTimeout(() => setTriggerError(null), 5000);
      return () => clearTimeout(timer);
    }
  }, [triggerError]);

  // Submit new subscription
  const handleSubmit = async () => {
    if (!formTicker.trim()) {
      setFormError("请输入标的代码");
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      await createTracking(formTicker.trim().toUpperCase(), formFrequency);
      setFormTicker("");
      setFormFrequency("daily");
      setShowForm(false);
      setLoading(true);
      await loadList();
    } catch (e: any) {
      setFormError(e.message || "订阅失败");
    } finally {
      setSubmitting(false);
    }
  };

  // Toggle pause/resume
  const handleToggleStatus = async (item: TrackingItem) => {
    const newStatus = item.status === "active" ? "paused" : "active";
    try {
      await updateTracking(item.id, { status: newStatus });
      setItems((prev) =>
        prev.map((i) => (i.id === item.id ? { ...i, status: newStatus } : i))
      );
    } catch (e) {
      console.error("Failed to update tracking status:", e);
    }
  };

  // Trigger report
  const handleTrigger = async (item: TrackingItem) => {
    setTriggerLoading(item.id);
    setTriggerError(null);
    setTriggerSuccess(null);
    try {
      const result = await triggerTracking(item.id);
      setTriggerSuccess(`已触发「${item.ticker}」报告生成`);
      setTimeout(() => {
        router.push(`/reports/${result.report_id}`);
      }, 1000);
    } catch (e: any) {
      setTriggerError(e.message || "触发失败");
    } finally {
      setTriggerLoading(null);
    }
  };

  // Delete handler
  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteTracking(deleteTarget.id);
      setDeleteTarget(null);
      setLoading(true);
      await loadList();
    } catch (e) {
      console.error("Failed to delete tracking:", e);
      setDeleteTarget(null);
    }
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold">标的追踪</h1>
          <p className="text-sm text-gray-500 mt-1">订阅标的，自动生成分析报告</p>
        </div>
        <div className="bg-white rounded-lg shadow overflow-hidden animate-pulse">
          <div className="grid grid-cols-6 gap-4 px-4 py-3 border-b border-gray-200 bg-gray-50">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-4 bg-gray-200 rounded w-16" />
            ))}
          </div>
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="grid grid-cols-6 gap-4 px-4 py-4 border-b border-gray-100">
              <div className="h-4 bg-gray-200 rounded w-12" />
              <div className="h-4 bg-gray-200 rounded w-16" />
              <div className="h-4 bg-gray-200 rounded w-14" />
              <div className="h-4 bg-gray-200 rounded w-20" />
              <div className="h-4 bg-gray-200 rounded w-20" />
              <div className="h-4 bg-gray-200 rounded w-24" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl font-bold">标的追踪</h1>
        <p className="text-sm text-gray-500 mt-1">
          订阅标的，自动生成分析报告
        </p>
      </div>

      {/* Trigger Feedback Messages */}
      {triggerSuccess && (
        <div className="bg-green-50 border border-green-200 text-green-700 text-sm px-4 py-2 rounded-lg">
          {triggerSuccess}
        </div>
      )}
      {triggerError && (
        <div className="bg-red-50 border border-red-200 text-red-700 text-sm px-4 py-2 rounded-lg">
          {triggerError}
        </div>
      )}

      {/* Add Subscription Button */}
      <div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 text-sm font-medium"
        >
          {showForm ? "收起" : "添加订阅"}
        </button>
      </div>

      {/* Add Subscription Form */}
      {showForm && (
        <div className="bg-white rounded-lg shadow p-4 space-y-3">
          <h2 className="text-sm font-semibold text-gray-700">添加新订阅</h2>
          {formError && <p className="text-red-600 text-sm">{formError}</p>}
          <div className="flex items-center gap-3 flex-wrap">
            <input
              type="text"
              placeholder="标的代码，如 BTC, ETH"
              value={formTicker}
              onChange={(e) => setFormTicker(e.target.value)}
              className="border rounded-lg px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              disabled={submitting}
            />
            <select
              value={formFrequency}
              onChange={(e) => setFormFrequency(e.target.value)}
              className="border rounded-lg px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              disabled={submitting}
            >
              <option value="daily">每天</option>
              <option value="weekly">每周</option>
              <option value="manual">手动</option>
            </select>
            <button
              onClick={handleSubmit}
              disabled={submitting}
              className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm font-medium"
            >
              {submitting ? "提交中..." : "订阅"}
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
      )}

      {/* Subscription Table */}
      {items.length === 0 ? (
        <div className="text-center py-14 bg-white rounded-lg shadow">
          <div className="text-5xl mb-3">📡</div>
          <p className="text-gray-500 text-lg font-medium mb-1">暂无追踪订阅</p>
          <p className="text-gray-400 text-sm">点击上方「添加订阅」按钮，开启自动报告生成</p>
        </div>
      ) : (
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left text-sm font-medium text-gray-500 px-4 py-3">
                  标的
                </th>
                <th className="text-left text-sm font-medium text-gray-500 px-4 py-3">
                  频率
                </th>
                <th className="text-left text-sm font-medium text-gray-500 px-4 py-3">
                  状态
                </th>
                <th className="text-left text-sm font-medium text-gray-500 px-4 py-3">
                  上次报告
                </th>
                <th className="text-left text-sm font-medium text-gray-500 px-4 py-3">
                  下次执行
                </th>
                <th className="text-left text-sm font-medium text-gray-500 px-4 py-3">
                  操作
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {items.map((item) => (
                <tr key={item.id} className="hover:bg-gray-50">
                  {/* 标的 */}
                  <td className="px-4 py-3">
                    <button
                      onClick={() => router.push(`/reports?ticker=${item.ticker}`)}
                      className="font-bold text-gray-900 hover:text-blue-600 transition-colors"
                    >
                      {item.ticker}
                    </button>
                  </td>

                  {/* 频率 */}
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex items-center text-xs px-2 py-0.5 rounded-full font-medium ${
                        FREQUENCY_CONFIG[item.frequency]?.color ||
                        "bg-gray-100 text-gray-700"
                      }`}
                    >
                      {FREQUENCY_CONFIG[item.frequency]?.label ||
                        item.frequency}
                    </span>
                  </td>

                  {/* 状态 */}
                  <td className="px-4 py-3">
                    <StatusBadge status={item.status} />
                  </td>

                  {/* 上次报告 */}
                  <td className="px-4 py-3 text-sm text-gray-600">
                    {formatDateTime(item.last_report_at) || "—"}
                  </td>

                  {/* 下次执行 */}
                  <td className="px-4 py-3 text-sm text-gray-600">
                    {formatDateTime(item.next_run_at) || "—"}
                  </td>

                  {/* 操作 */}
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleTrigger(item)}
                        disabled={triggerLoading === item.id}
                        className="border border-blue-300 text-blue-600 hover:bg-blue-50 px-3 py-1 rounded text-sm disabled:opacity-50 whitespace-nowrap"
                      >
                        {triggerLoading === item.id
                          ? "触发中..."
                          : "触发报告"}
                      </button>

                      <div className="relative">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setOpenMenuId(openMenuId === item.id ? null : item.id);
                          }}
                          className="border border-gray-300 text-gray-600 hover:bg-gray-50 px-2 py-1 rounded text-sm"
                        >
                          更多 ▼
                        </button>

                        {openMenuId === item.id && (
                          <div className="absolute right-0 mt-1 w-32 bg-white rounded-lg shadow-lg border border-gray-200 z-10 py-1">
                            <button
                              onClick={() => {
                                setOpenMenuId(null);
                                handleToggleStatus(item);
                              }}
                              className="block w-full text-left px-3 py-1.5 text-sm hover:bg-gray-50 text-gray-700"
                            >
                              {item.status === "active" ? "暂停追踪" : "恢复追踪"}
                            </button>
                            <button
                              onClick={() => {
                                setOpenMenuId(null);
                                router.push(`/reports?ticker=${item.ticker}`);
                              }}
                              className="block w-full text-left px-3 py-1.5 text-sm hover:bg-gray-50 text-gray-700"
                            >
                              查看报告
                            </button>
                            <button
                              onClick={() => {
                                setOpenMenuId(null);
                                setDeleteTarget(item);
                              }}
                              className="block w-full text-left px-3 py-1.5 text-sm hover:bg-gray-50 text-red-600"
                            >
                              删除
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        open={!!deleteTarget}
        title="删除订阅"
        message={`确定要删除「${deleteTarget?.ticker || ""}」的追踪订阅吗？此操作不可撤销。`}
        confirmText="删除"
        variant="danger"
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
