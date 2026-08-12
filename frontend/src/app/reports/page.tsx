"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { deleteReport, generateReport, getReport, listReports, type ReportListItem } from "@/lib/api";
import { formatDateTime, formatLatency } from "@/lib/datetime";
import ConfirmDialog from "@/components/ConfirmDialog";
import AppIcon from "@/components/AppIcon";
import { PageEmpty, PageError, PageLoading } from "@/components/PageState";
import { MetricStrip, Pagination, SectionTitle, SegmentedControl, WorkspacePageHeader } from "@/components/WorkspacePage";

const RANGES = [{ value: "1w", label: "近 1 周" }, { value: "2w", label: "近 2 周" }, { value: "1m", label: "近 1 月" }, { value: "3m", label: "近 3 月" }];
const CONSENSUS: Record<string, string> = { strong_buy: "强烈看多", buy: "看多", neutral: "中性", sell: "看空", strong_sell: "强烈看空" };
const TRIGGER: Record<string, string> = { manual: "手动研究", chat: "助手生成", scheduled: "定时简报" };

function ReportsPageInner() {
  const router = useRouter(); const searchParams = useSearchParams();
  const [reports, setReports] = useState<ReportListItem[]>([]); const [total, setTotal] = useState(0); const [page, setPage] = useState(1); const [loading, setLoading] = useState(true); const [error, setError] = useState("");
  const [filterDraft, setFilterDraft] = useState(searchParams.get("ticker") || ""); const [tickerFilter, setTickerFilter] = useState(searchParams.get("ticker") || "");
  const [showForm, setShowForm] = useState(false); const [ticker, setTicker] = useState(""); const [range, setRange] = useState("1w"); const [focus, setFocus] = useState(""); const [submitting, setSubmitting] = useState(false); const [notice, setNotice] = useState(""); const [deleteTarget, setDeleteTarget] = useState<ReportListItem | null>(null);
  const polling = useRef<Map<string, ReturnType<typeof setInterval>>>(new Map()); const pageSize = 9;
  const load = useCallback(async () => { setLoading(true); setError(""); try { const data = await listReports({ ticker: tickerFilter || undefined, page, size: pageSize }); setReports(data.items); setTotal(data.total); } catch { setError("简报列表加载失败，请稍后重试。"); } finally { setLoading(false); } }, [page, tickerFilter]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => () => { polling.current.forEach(clearInterval); polling.current.clear(); }, []);
  const watch = useCallback((id: string) => { if (polling.current.has(id)) return; const timer = setInterval(async () => { try { const detail = await getReport(id); if (["done", "failed"].includes(detail.status)) { clearInterval(timer); polling.current.delete(id); setReports((prev) => prev.map((item) => item.id === id ? { ...item, status: detail.status as ReportListItem["status"], title: detail.title, consensus: detail.consensus, latency_ms: detail.latency_ms } : item)); } } catch { /* keep polling */ } }, 3000); polling.current.set(id, timer); }, []);
  useEffect(() => { reports.filter((item) => item.status === "generating").forEach((item) => watch(item.id)); }, [reports, watch]);
  const create = async () => { if (!ticker.trim()) { setNotice("请输入需要研究的标的代码。"); return; } setSubmitting(true); setNotice(""); try { const symbol = ticker.trim().toUpperCase(); const result = await generateReport(symbol, range, focus.split(",").map((value) => value.trim()).filter(Boolean)); const item: ReportListItem = { id: result.id, ticker: symbol, title: null, trigger_type: "manual", consensus: null, status: "generating", latency_ms: null, created_at: new Date().toISOString() }; setReports((prev) => [item, ...prev]); setTotal((value) => value + 1); watch(result.id); setTicker(""); setFocus(""); setShowForm(false); } catch { setNotice("简报任务创建失败，请稍后重试。"); } finally { setSubmitting(false); } };
  const remove = async () => { if (!deleteTarget) return; await deleteReport(deleteTarget.id); polling.current.delete(deleteTarget.id); setDeleteTarget(null); await load(); };
  const finished = reports.filter((item) => item.status === "done").length; const generating = reports.filter((item) => item.status === "generating").length;
  return <div className="product-page">
    <WorkspacePageHeader eyebrow="Investment Briefs" title="研究简报" subtitle="把分散观点、私人资料和历史证据整理成结构化标的研究结论。" actions={<button className="button-primary" onClick={() => setShowForm((value) => !value)}><AppIcon name="briefs" className="h-4 w-4" />生成简报</button>} />
    <MetricStrip items={[{ label: "简报总数", value: total, note: "全部研究记录" }, { label: "本页已完成", value: finished, note: "可查看结论" }, { label: "生成中", value: generating, note: "后台任务" }]} />
    {showForm && <section className="composer-panel brief-composer"><div><p className="page-eyebrow">New brief</p><h2>创建研究任务</h2><p>指定标的、研究窗口和希望重点回答的问题。</p></div><div className="composer-fields"><label>标的代码<input value={ticker} onChange={(event) => setTicker(event.target.value)} placeholder="例如 NVDA" /></label><label>研究窗口<SegmentedControl value={range} options={RANGES} onChange={setRange} /></label><label>关注问题<input value={focus} onChange={(event) => setFocus(event.target.value)} placeholder="估值, 催化剂, 风险（可选）" /></label><button className="button-primary" disabled={submitting} onClick={create}>{submitting ? "正在创建" : "开始生成"}</button></div></section>}
    {notice && <div className="inline-notice">{notice}</div>}
    <div className="content-toolbar"><SectionTitle icon="briefs" title="简报档案" meta={`${total} 份`} /><div className="search-compact"><AppIcon name="search" className="h-4 w-4" /><input value={filterDraft} onChange={(event) => setFilterDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") { setPage(1); setTickerFilter(filterDraft.trim().toUpperCase()); } }} placeholder="按 ticker 筛选" /><button onClick={() => { setPage(1); setTickerFilter(filterDraft.trim().toUpperCase()); }}>应用</button></div></div>
    {loading ? <PageLoading label="正在整理研究简报" /> : error ? <PageError detail={error} onRetry={load} /> : reports.length === 0 ? <PageEmpty title="暂无研究简报" detail="创建第一份标的简报，系统会聚合市场观点与私人证据。" action={<button className="button-primary" onClick={() => setShowForm(true)}>生成简报</button>} /> : <div className="brief-grid">{reports.map((report) => <article className={`brief-card ${report.status}`} key={report.id} onClick={() => report.status !== "generating" && router.push(`/reports/${report.id}`)}><div className="brief-card-top"><span>{TRIGGER[report.trigger_type] ?? report.trigger_type}</span><span className={`status-pill ${report.status}`}>{report.status === "done" ? "已完成" : report.status === "generating" ? "生成中" : "失败"}</span></div><strong className="brief-ticker">{report.ticker}</strong><h3>{report.title || (report.status === "generating" ? "正在汇总观点与证据…" : "标的研究简报")}</h3><div className="brief-consensus">{report.consensus ? <span className={`direction direction-${report.consensus.includes("sell") ? "bearish" : report.consensus.includes("buy") ? "bullish" : "neutral"}`}>{CONSENSUS[report.consensus] ?? report.consensus}</span> : <span>等待研究结论</span>}</div><footer><span>{formatDateTime(report.created_at)}</span><span>{report.latency_ms == null ? "" : formatLatency(report.latency_ms)}</span><button onClick={(event) => { event.stopPropagation(); setDeleteTarget(report); }}>删除</button></footer></article>)}</div>}
    <Pagination page={page} pages={Math.ceil(total / pageSize)} onChange={setPage} />
    <ConfirmDialog open={!!deleteTarget} title="删除研究简报" message={`确定删除「${deleteTarget?.ticker ?? ""}」简报吗？`} confirmText="删除" variant="danger" onConfirm={remove} onCancel={() => setDeleteTarget(null)} />
  </div>;
}

export default function ReportsPage() { return <Suspense fallback={<PageLoading label="正在读取研究简报" />}><ReportsPageInner /></Suspense>; }
