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
import { MetricStrip, Pagination, SectionTitle, WorkspacePageHeader } from "@/components/WorkspacePage";

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
  const [uploadZoneKey, setUploadZoneKey] = useState(0);
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
      setUploadZoneKey((value) => value + 1);
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
      ? "is-active"
      : "";

  if (loading) {
    return (
      <div className="space-y-6 animate-pulse">
        <h1 className="text-2xl font-bold">文档管理</h1>
        <div className="bg-white rounded-lg shadow p-4 space-y-3">
          <div className="flex gap-2 mb-4">
            <div className="h-8 w-20 bg-gray-200 rounded-lg" />
            <div className="h-8 w-20 bg-gray-200 rounded-lg" />
            <div className="h-8 w-20 bg-gray-200 rounded-lg" />
          </div>
          <div className="h-24 bg-gray-200 rounded-lg" />
          <div className="h-10 w-full bg-gray-200 rounded-lg" />
          <div className="h-10 w-full bg-gray-200 rounded-lg" />
          <div className="h-10 w-24 bg-gray-200 rounded-lg" />
        </div>
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <div className="grid grid-cols-7 gap-4 px-4 py-3 border-b border-gray-200 bg-gray-50">
            {Array.from({ length: 7 }).map((_, i) => (
              <div key={i} className="h-4 bg-gray-200 rounded w-16" />
            ))}
          </div>
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="grid grid-cols-7 gap-4 px-4 py-4 border-b border-gray-100">
              <div className="h-4 bg-gray-200 rounded w-24" />
              <div className="h-4 bg-gray-200 rounded w-12" />
              <div className="h-4 bg-gray-200 rounded w-14" />
              <div className="h-4 bg-gray-200 rounded w-8" />
              <div className="h-4 bg-gray-200 rounded w-16" />
              <div className="h-4 bg-gray-200 rounded w-20" />
              <div className="h-4 bg-gray-200 rounded w-8" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="product-page">
      <WorkspacePageHeader eyebrow="Private Research" title="私人资料" subtitle="把研报、网页和研究笔记纳入只属于你的检索范围，与市场观点联合分析。" />
      <MetricStrip items={[{ label: "资料总量", value: total, note: "私人研究库" }, { label: "本页已索引", value: documents.filter((doc) => doc.status === "indexed" || doc.status === "ready").length, note: "可用于研究助手" }, { label: "处理中", value: documents.filter((doc) => doc.status === "pending" || doc.status === "processing").length, note: "解析与索引" }]} />

      {/* Upload Area */}
      <section className="library-ingest">
        <div className="library-ingest-header">
          <div className="library-intro"><p className="page-eyebrow">Add evidence</p><h2>添加研究资料</h2><p>资料处理完成后，将自动进入个人检索范围。</p></div>
          {/* Tabs */}
          <div className="segmented-control library-tabs" role="tablist" aria-label="资料录入方式">
            <button type="button" role="tab" aria-selected={activeTab === "upload"} className={tabClass("upload")} onClick={() => { setActiveTab("upload"); setFormError(null); setFormSuccess(null); }}>
              文件上传
            </button>
            <button type="button" role="tab" aria-selected={activeTab === "url"} className={tabClass("url")} onClick={() => { setActiveTab("url"); setFormError(null); setFormSuccess(null); }}>
              URL 提交
            </button>
            <button type="button" role="tab" aria-selected={activeTab === "paste"} className={tabClass("paste")} onClick={() => { setActiveTab("paste"); setFormError(null); setFormSuccess(null); }}>
              文本粘贴
            </button>
          </div>
        </div>

        <div className="library-ingest-body">
          {/* Error/Success Messages */}
          {formError && <p className="form-message is-error">{formError}</p>}
          {formSuccess && <p className="form-message is-success">{formSuccess}</p>}

          {/* Tab 1: File Upload */}
          {activeTab === "upload" && (
            <div className="library-form" role="tabpanel">
              <div className="library-form-primary">
                <FileUploadZone
                  key={uploadZoneKey}
                  onFileSelected={(file) => setUploadFile(file)}
                  disabled={submitting}
                />
              </div>
              <label className="library-field">
                <span>资料标题 <small>可选</small></span>
                <input
                  type="text"
                  placeholder="例如：英伟达 2026 年二季度研究"
                  value={uploadTitle}
                  onChange={(e) => setUploadTitle(e.target.value)}
                  className="field-input"
                  disabled={submitting}
                />
              </label>
              <label className="library-field">
                <span>关联标的 <small>可选，逗号分隔</small></span>
                <input
                  type="text"
                  placeholder="例如：NVDA, AMD"
                  value={uploadTickers}
                  onChange={(e) => setUploadTickers(e.target.value)}
                  className="field-input"
                  disabled={submitting}
                />
              </label>
              <div className="library-form-actions">
                <p>支持 PDF、DOCX、Markdown、TXT，单个文件最大 10 MB。</p>
                <button onClick={handleUploadSubmit} disabled={submitting || !uploadFile} className="button-primary">
                  {submitting ? "上传中..." : "上传并建立索引"}
                </button>
              </div>
            </div>
          )}

          {/* Tab 2: URL Submit */}
          {activeTab === "url" && (
            <div className="library-form" role="tabpanel">
              <label className="library-field library-form-primary">
                <span>网页地址</span>
                <input type="url" inputMode="url" placeholder="https://example.com/research" value={urlValue} onChange={(e) => setUrlValue(e.target.value)} className="field-input" disabled={submitting} />
              </label>
              <label className="library-field">
                <span>资料标题 <small>可选</small></span>
                <input type="text" placeholder="不填写时自动读取网页标题" value={urlTitle} onChange={(e) => setUrlTitle(e.target.value)} className="field-input" disabled={submitting} />
              </label>
              <label className="library-field">
                <span>关联标的 <small>可选，逗号分隔</small></span>
                <input type="text" placeholder="例如：AAPL, MSFT" value={urlTickers} onChange={(e) => setUrlTickers(e.target.value)} className="field-input" disabled={submitting} />
              </label>
              <div className="library-form-actions">
                <p>系统将读取网页正文，并纳入你的私人检索范围。</p>
                <button onClick={handleUrlSubmit} disabled={submitting || !urlValue.trim()} className="button-primary">
                  {submitting ? "提交中..." : "提交并解析网页"}
                </button>
              </div>
            </div>
          )}

          {/* Tab 3: Paste */}
          {activeTab === "paste" && (
            <div className="library-form" role="tabpanel">
              <label className="library-field">
                <span>资料标题</span>
                <input type="text" placeholder="例如：苹果供应链调研笔记" value={pasteTitle} onChange={(e) => setPasteTitle(e.target.value)} className="field-input" disabled={submitting} />
              </label>
              <label className="library-field">
                <span>关联标的 <small>可选，逗号分隔</small></span>
                <input type="text" placeholder="例如：AAPL, 00700.HK" value={pasteTickers} onChange={(e) => setPasteTickers(e.target.value)} className="field-input" disabled={submitting} />
              </label>
              <label className="library-field library-form-primary">
                <span>文本内容</span>
                <textarea placeholder="粘贴研报摘要、会议纪要或自己的研究笔记…" rows={8} value={pasteContent} onChange={(e) => setPasteContent(e.target.value)} className="field-input" disabled={submitting} />
              </label>
              <div className="library-form-actions">
                <p>{pasteContent.length > 0 ? `已输入 ${pasteContent.length.toLocaleString("zh-CN")} 个字符` : "文本只会进入你的私人资料库。"}</p>
                <button onClick={handlePasteSubmit} disabled={submitting || !pasteTitle.trim() || !pasteContent.trim()} className="button-primary">
                  {submitting ? "保存中..." : "保存并建立索引"}
                </button>
              </div>
            </div>
          )}
        </div>
      </section>

      {/* Document List */}
      <section className="library-list"><SectionTitle icon="documents" title="资料索引" meta={`${total} 项`} />
        {documents.length === 0 ? (
          <div className="text-center py-14">
            <div className="text-5xl mb-3">📁</div>
            <p className="text-gray-500 text-lg font-medium mb-1">暂无文档</p>
            <p className="text-gray-400 text-sm">通过上方上传、URL 或粘贴方式添加文档</p>
          </div>
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
            <Pagination page={page} pages={totalPages} onChange={setPage} />
          </>
        )}
      </section>

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
