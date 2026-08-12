"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import AppIcon from "@/components/AppIcon";
import BloggerCard, { type BloggerListItem } from "@/components/BloggerCard";
import { fetchBloggers, onboardBlogger, type BloggerOnboardResult } from "@/lib/api";
import { PageEmpty, PageError, PageLoading } from "@/components/PageState";
import { MetricStrip, SectionTitle, SegmentedControl, WorkspacePageHeader } from "@/components/WorkspacePage";

type SortKey = "credibility" | "verified_count" | "followers" | "pending_count";
const OPTIONS: Array<{ value: SortKey; label: string }> = [
  { value: "credibility", label: "可信度" },
  { value: "verified_count", label: "已验证" },
  { value: "followers", label: "影响力" },
  { value: "pending_count", label: "待验证" },
];

export default function BloggersListPage() {
  const params = useSearchParams();
  const [sort, setSort] = useState<SortKey>((params.get("sort") as SortKey) || "credibility");
  const [items, setItems] = useState<BloggerListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showOnboard, setShowOnboard] = useState(false);
  const [handle, setHandle] = useState("");
  const [onboarding, setOnboarding] = useState(false);
  const [onboardError, setOnboardError] = useState("");
  const [onboarded, setOnboarded] = useState<BloggerOnboardResult | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setItems(await fetchBloggers({ sort }));
    } catch {
      setError("信息源数据加载失败，请稍后重试。");
    } finally {
      setLoading(false);
    }
  }, [sort]);

  useEffect(() => { load(); }, [load]);

  const stats = useMemo(() => ({
    verified: items.reduce((sum, item) => sum + item.verified_count, 0),
    pending: items.reduce((sum, item) => sum + item.pending_count, 0),
    avg: items.length ? Math.round(items.reduce((sum, item) => sum + item.credibility_score, 0) / items.length) : 0,
  }), [items]);

  const closeOnboard = () => {
    if (onboarding) return;
    setShowOnboard(false);
    setHandle("");
    setOnboardError("");
    setOnboarded(null);
  };

  const submitOnboard = async (event: FormEvent) => {
    event.preventDefault();
    const normalized = handle.trim().replace(/^@/, "");
    if (!normalized) {
      setOnboardError("请输入 Twitter Handle");
      return;
    }
    setOnboarding(true);
    setOnboardError("");
    try {
      const result = await onboardBlogger(normalized);
      setOnboarded(result);
      await load();
    } catch (err) {
      setOnboardError(err instanceof Error ? err.message : "新增信息源失败，请稍后重试");
    } finally {
      setOnboarding(false);
    }
  };

  return <div className="product-page">
    <WorkspacePageHeader
      eyebrow="Source Intelligence"
      title="信息源"
      subtitle="比较博主的可信度、历史观点和关注市场，决定哪些声音值得进入你的研究范围。"
      actions={<button className="button-primary" onClick={() => setShowOnboard(true)}><AppIcon name="research" />新增信息源</button>}
    />
    <MetricStrip items={[
      { label: "已收录信息源", value: items.length, note: "当前数据集" },
      { label: "平均可信度", value: stats.avg, note: "基于已验证观点" },
      { label: "已验证观点", value: stats.verified, note: `${stats.pending} 条待验证` },
    ]} />
    <div className="content-toolbar">
      <SectionTitle icon="sources" title="来源排行" meta="点击信息源查看观点证据" />
      <SegmentedControl value={sort} options={OPTIONS} onChange={setSort} />
    </div>
    {loading ? <PageLoading label="正在评估信息源" />
      : error ? <PageError detail={error} onRetry={load} />
        : items.length === 0 ? <PageEmpty title="尚无可评估的信息源" detail="新增 Twitter 博主后，系统会自动采集和分析最新内容。" />
          : <div className="source-grid">{items.map((blogger, index) => <BloggerCard key={blogger.handle} blogger={blogger} rank={index + 1} />)}</div>}

    {showOnboard && <div className="source-onboard-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) closeOnboard(); }}>
      <section className="source-onboard-dialog" role="dialog" aria-modal="true" aria-labelledby="source-onboard-title">
        <button className="source-onboard-close" onClick={closeOnboard} aria-label="关闭"><AppIcon name="close" /></button>
        {!onboarded ? <>
          <div className="source-onboard-heading">
            <span className="source-onboard-mark"><AppIcon name="sources" /></span>
            <div><p>New intelligence source</p><h2 id="source-onboard-title">新增 Twitter 信息源</h2><span>输入博主用户名，系统会完成建档并启动首次研究流程。</span></div>
          </div>
          <form onSubmit={submitOnboard} className="source-onboard-form">
            <label htmlFor="twitter-handle">Twitter Handle</label>
            <div className="source-handle-input"><span>@</span><input id="twitter-handle" value={handle} onChange={(event) => setHandle(event.target.value)} placeholder="elonmusk" autoFocus disabled={onboarding} /></div>
            {onboardError && <p className="source-onboard-error">{onboardError}</p>}
            <div className="source-onboard-pipeline" aria-label="一键新增流程">
              <span><b>01</b>获取公开资料</span><span><b>02</b>加入我的关注</span><span><b>03</b>开启定时抓取</span><span><b>04</b>首次抓取分析</span>
            </div>
            <button className="button-primary source-onboard-submit" type="submit" disabled={onboarding}>{onboarding ? "正在建立信息源…" : "新增并开始追踪"}<AppIcon name="arrow" /></button>
          </form>
        </> : <div className="source-onboard-success">
          <span className="source-success-mark">✓</span>
          <p>Source connected</p>
          <h2>@{onboarded.handle} 已开始追踪</h2>
          <span>资料与关注关系已保存，首次推文抓取及分析任务已进入队列。</span>
          <div><Link className="button-primary" href={`/bloggers/${encodeURIComponent(onboarded.handle)}`}>查看信息源<AppIcon name="arrow" /></Link><button className="button-secondary" onClick={closeOnboard}>完成</button></div>
        </div>}
      </section>
    </div>}
  </div>;
}
