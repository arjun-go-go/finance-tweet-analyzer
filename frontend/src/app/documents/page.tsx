"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import {
  listDocuments,
  uploadDocument,
  submitUrl,
  pasteDocument,
  deleteDocument,
  getDocumentStatus,
  type DocumentItem,
  type DocumentListResponse,
} from "@/lib/api";
import { formatDateTime } from "@/lib/datetime";
import FileUploadZone from "@/components/FileUploadZone";
import StatusBadge from "@/components/StatusBadge";
import ConfirmDialog from "@/components/ConfirmDialog";

type TabType = "upload" | "url" | "paste";

const SOURCE_LABELS: Record<string, string> = {
  upload: "上传",
  url: "URL",
  paste: "粘贴",
};

export default function DocumentsPage() {
  // Tab state
  const [activeTab, setActiveTab] = useState<TabType>("upload");

  // Upload form state
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadTitle, setUploadTitle] = useState("");
  const [uploadTickers, setUploadTickers] = useState("");

  // URL form state
  const [urlValue, setUrlValue] = useState("");
  const [urlTitle, setUrlTitle] = useState("");
  const [urlTickers, setUrlTickers] = useState("");

  // Paste form state
  const [pasteTitle, setPasteTitle] = useState("");
  const [pasteContent, setPasteContent] = useState("");
  const [pasteTickers, setPasteTickers] = useState("");

  // Submission state
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formSuccess, setFormSuccess] = useState<string | null>(null);

  // Document list state
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const pageSize = 10;

  // Delete dialog state
  const [deleteTarget, setDeleteTarget] = useState<DocumentItem | null>(null);

  // Polling ref
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const parseTickers = (input: string): string[] => {
    return input
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
  };

  // Load documents
  const loadDocuments = useCallback(async () => {
    try {
      const result: DocumentListResponse = await listDocuments({
        page,
        page_size: pageSize,
      });
      setDocuments(result.items);
      setTotal(result.total);
    } catch (e) {
      console.error("Failed to load documents:", e);
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  // Status polling
  useEffect(() => {
    const pollableIds = documents
      .filter((doc) => doc.status === "processing" || doc.status === "pending")
      .map((doc) => doc.id);

    if (pollableIds.length === 0) {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
      return;
    }

    pollingRef.current = setInterval(async () => {
      let changed = false;
      for (const id of pollableIds) {
        try {
          const statusRes = await getDocumentStatus(id);
          if (statusRes.status === "indexed" || statusRes.status === "failed") {
            setDocuments((prev) =>
              prev.map((doc) =>
                doc.id === id
                  ? {
                      ...doc,
                      status: statusRes.status as DocumentItem["status"],
                      chunk_count: statusRes.chunk_count,
                      error_detail: statusRes.error_detail,
                    }
                  : doc
              )
            );
            changed = true;
          }
        } catch (e) {
          console.error(`Failed to poll status for ${id}:`, e);
        }
      }
      if (changed) {
        // Re-check if we still have pollable items
        setDocuments((prev) => {
          const stillPolling = prev.some(
            (doc) => doc.status === "processing" || doc.status === "pending"
          );
          if (!stillPolling && pollingRef.current) {
            clearInterval(pollingRef.current);
            pollingRef.current = null;
          }
          return prev;
        });
      }
    }, 3000);

    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, [documents]);

  // Form submission handlers
  const handleUploadSubmit = async () => {
    if (!uploadFile) {
      setFormError("请选择文件");
      return;
    }
    setSubmitting(true);
    setFormError(null);
    setFormSuccess(null);
    try {
      const tickers = parseTickers(uploadTickers);
      await uploadDocument(uploadFile, uploadTitle || undefined, tickers.length > 0 ? tickers : undefined);
      setFormSuccess("文件上传成功");
      setUploadFile(null);
      setUploadTitle("");
      setUploadTickers("");
      await loadDocuments();
      setTimeout(() => setFormSuccess(null), 3000);
    } catch (e: any) {
      setFormError(e.message || "上传失败");
    } finally {
      setSubmitting(false);
    }
  };

  const handleUrlSubmit = async () => {
    if (!urlValue.trim()) {
      setFormError("请输入 URL");
      return;
    }
    setSubmitting(true);
    setFormError(null);
    setFormSuccess(null);
    try {
      const tickers = parseTickers(urlTickers);
      await submitUrl(urlValue.trim(), urlTitle || undefined, tickers.length > 0 ? tickers : undefined);
      setFormSuccess("URL 提交成功");
      setUrlValue("");
      setUrlTitle("");
      setUrlTickers("");
      await loadDocuments();
      setTimeout(() => setFormSuccess(null), 3000);
    } catch (e: any) {
      setFormError(e.message || "提交失败");
    } finally {
      setSubmitting(false);
    }
  };

  const handlePasteSubmit = async () => {
    if (!pasteTitle.trim()) {
      setFormError("请输入文档标题");
      return;
    }
    if (!pasteContent.trim()) {
      setFormError("请输入文本内容");
      return;
    }
    setSubmitting(true);
    setFormError(null);
    setFormSuccess(null);
    try {
      const tickers = parseTickers(pasteTickers);
      await pasteDocument(pasteTitle.trim(), pasteContent.trim(), tickers.length > 0 ? tickers : undefined);
      setFormSuccess("文本保存成功");
      setPasteTitle("");
      setPasteContent("");
      setPasteTickers("");
      await loadDocuments();
      setTimeout(() => setFormSuccess(null), 3000);
    } catch (e: any) {
      setFormError(e.message || "保存失败");
    } finally {
      setSubmitting(false);
    }
  };

  // Delete handler
  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteDocument(deleteTarget.id);
      setDeleteTarget(null);
      await loadDocuments();
    } catch (e: any) {
      console.error("Failed to delete document:", e);
      setDeleteTarget(null);
    }
  };

  const totalPages = Math.ceil(total / pageSize);

  const tabClass = (tab: TabType) =>
    activeTab === tab
      ? "bg-blue-600 text-white px-4 py-2 rounded-lg text-sm"
      : "bg-gray-100 text-gray-600 px-4 py-2 rounded-lg text-sm hover:bg-gray-200";

  if (loading) return <p className="text-center py-10">加载中...</p>;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">文档管理</h1>

      {/* Upload Area */}
      <div className="bg-white rounded-lg shadow p-4">
        {/* Tabs */}
        <div className="flex gap-2 mb-4">
          <button className={tabClass("upload")} onClick={() => { setActiveTab("upload"); setFormError(null); setFormSuccess(null); }}>
            文件上传
          </button>
          <button className={tabClass("url")} onClick={() => { setActiveTab("url"); setFormError(null); setFormSuccess(null); }}>
            URL提交
          </button>
          <button className={tabClass("paste")} onClick={() => { setActiveTab("paste"); setFormError(null); setFormSuccess(null); }}>
            文本粘贴
          </button>
        </div>

        {/* Error/Success Messages */}
        {formError && <p className="text-red-600 text-sm mt-2 mb-2">{formError}</p>}
        {formSuccess && <p className="text-green-600 text-sm mt-2 mb-2">{formSuccess}</p>}

        {/* Tab 1: File Upload */}
        {activeTab === "upload" && (
          <div className="space-y-3">
            <FileUploadZone
              onFileSelected={(file) => setUploadFile(file)}
              disabled={submitting}
            />
            <input
              type="text"
              placeholder="文档标题（可选）"
              value={uploadTitle}
              onChange={(e) => setUploadTitle(e.target.value)}
              className="border rounded-lg px-4 py-2 w-full focus:outline-none focus:ring-2 focus:ring-blue-500"
              disabled={submitting}
            />
            <input
              type="text"
              placeholder="关联标的，逗号分隔（可选）"
              value={uploadTickers}
              onChange={(e) => setUploadTickers(e.target.value)}
              className="border rounded-lg px-4 py-2 w-full focus:outline-none focus:ring-2 focus:ring-blue-500"
              disabled={submitting}
            />
            <button
              onClick={handleUploadSubmit}
              disabled={submitting}
              className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              {submitting ? "上传中..." : "上传"}
            </button>
          </div>
        )}

        {/* Tab 2: URL Submit */}
        {activeTab === "url" && (
          <div className="space-y-3">
            <input
              type="url"
              placeholder="https://..."
              value={urlValue}
              onChange={(e) => setUrlValue(e.target.value)}
              className="border rounded-lg px-4 py-2 w-full focus:outline-none focus:ring-2 focus:ring-blue-500"
              disabled={submitting}
            />
            <input
              type="text"
              placeholder="文档标题（可选）"
              value={urlTitle}
              onChange={(e) => setUrlTitle(e.target.value)}
              className="border rounded-lg px-4 py-2 w-full focus:outline-none focus:ring-2 focus:ring-blue-500"
              disabled={submitting}
            />
            <input
              type="text"
              placeholder="关联标的，逗号分隔（可选）"
              value={urlTickers}
              onChange={(e) => setUrlTickers(e.target.value)}
              className="border rounded-lg px-4 py-2 w-full focus:outline-none focus:ring-2 focus:ring-blue-500"
              disabled={submitting}
            />
            <button
              onClick={handleUrlSubmit}
              disabled={submitting}
              className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              {submitting ? "提交中..." : "提交"}
            </button>
          </div>
        )}

        {/* Tab 3: Paste */}
        {activeTab === "paste" && (
          <div className="space-y-3">
            <input
              type="text"
              placeholder="文档标题"
              value={pasteTitle}
              onChange={(e) => setPasteTitle(e.target.value)}
              className="border rounded-lg px-4 py-2 w-full focus:outline-none focus:ring-2 focus:ring-blue-500"
              disabled={submitting}
            />
            <textarea
              placeholder="粘贴文本内容..."
              rows={6}
              value={pasteContent}
              onChange={(e) => setPasteContent(e.target.value)}
              className="border rounded-lg px-4 py-2 w-full focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y"
              disabled={submitting}
            />
            <input
              type="text"
              placeholder="关联标的，逗号分隔（可选）"
              value={pasteTickers}
              onChange={(e) => setPasteTickers(e.target.value)}
              className="border rounded-lg px-4 py-2 w-full focus:outline-none focus:ring-2 focus:ring-blue-500"
              disabled={submitting}
            />
            <button
              onClick={handlePasteSubmit}
              disabled={submitting}
              className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              {submitting ? "保存中..." : "保存"}
            </button>
          </div>
        )}
      </div>

      {/* Document List */}
      <div className="bg-white rounded-lg shadow p-4">
        {documents.length === 0 ? (
          <p className="text-center py-10 text-gray-500">暂无文档</p>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="text-left text-sm text-gray-500 border-b">
                    <th className="pb-2 font-medium">标题</th>
                    <th className="pb-2 font-medium">来源</th>
                    <th className="pb-2 font-medium">状态</th>
                    <th className="pb-2 font-medium">分块数</th>
                    <th className="pb-2 font-medium">标的</th>
                    <th className="pb-2 font-medium">时间</th>
                    <th className="pb-2 font-medium">操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {documents.map((doc) => (
                    <tr key={doc.id} className="text-sm">
                      <td className="py-3 pr-2 max-w-[200px] truncate" title={doc.title}>
                        {doc.title}
                      </td>
                      <td className="py-3 pr-2">
                        <span className="inline-block bg-gray-100 text-gray-700 text-xs px-2 py-0.5 rounded-full">
                          {SOURCE_LABELS[doc.source_type] || doc.source_type}
                        </span>
                      </td>
                      <td className="py-3 pr-2">
                        <StatusBadge status={doc.status} />
                      </td>
                      <td className="py-3 pr-2 text-gray-600">{doc.chunk_count}</td>
                      <td className="py-3 pr-2">
                        <div className="flex flex-wrap gap-1">
                          {doc.tickers.map((ticker) => (
                            <span
                              key={ticker}
                              className="inline-block bg-blue-50 text-blue-700 text-xs px-2 py-0.5 rounded-full"
                            >
                              {ticker}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="py-3 pr-2 text-gray-500 whitespace-nowrap">
                        {formatDateTime(doc.created_at)}
                      </td>
                      <td className="py-3">
                        <button
                          onClick={() => setDeleteTarget(doc)}
                          className="text-red-600 hover:text-red-800 text-sm"
                        >
                          删除
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-center gap-4 mt-4">
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
          </>
        )}
      </div>

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        open={!!deleteTarget}
        title="删除文档"
        message={`确定要删除文档「${deleteTarget?.title || ""}」吗？此操作不可撤销。`}
        confirmText="删除"
        variant="danger"
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
