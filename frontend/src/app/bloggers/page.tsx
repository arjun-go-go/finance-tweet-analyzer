"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import AppIcon from "@/components/AppIcon";
import BloggerCard, { type BloggerListItem } from "@/components/BloggerCard";
import { fetchBloggers, listMyBloggers, onboardBlogger, type BloggerOnboardResult } from "@/lib/api";
import { PageEmpty, PageError, PageLoading } from "@/components/PageState";
import { MetricStrip, SectionTitle, SegmentedControl, WorkspacePageHeader } from "@/components/WorkspacePage";

type SortKey = "credibility" | "verified_count" | "followers" | "pending_count";
type SourceScope = "followed" | "all";
const OPTIONS: Array<{ value: SortKey; label: string }> = [
  { value: "credibility", label: "可信度" },
  { value: "verified_count", label: "已验证" },
  { value: "followers", label: "影响力" },
  { value: "pending_count", label: "待验证" },
];

export default function BloggersListPage() {
  const params = useSearchParams();
  const [sort, setSort] = useState<SortKey>((params.get("sort") as SortKey) || "credibility");
  const [scope, setScope] = useState<SourceScope>("followed");
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
      if (scope === "followed") {
        const data = await listMyBloggers();
        const sorted = [...data.items].sort((left, right) => {
          if (sort === "followers") return right.followers_count - left.followers_count;
          if (sort === "verified_count") return right.verified_count - left.verified_count;
          if (sort === "pending_count") return right.pending_count - left.pending_count;
          return right.credibility_score - left.credibility_score;
        });
        setItems(sorted);
      } else {
        setItems(await fetchBloggers({ sort }));
      }
    } catch {
      setError("信息源数据加载失败，请稍后重试。");
    } finally {
      setLoading(false);
    }
  }, [scope, sort]);

  useEffect(() => { load(); }, [load]);

  const stats = useMemo(() => ({
    verified: items.reduce((sum, item) => sum + item.verified_count, 0),
    pending: items.reduce((sum, item) => sum + item.pending_count, 0),
    avg: items.some((item) => item.verified_count > 0) ? Math.round(items.filter((item) => item.verified_count > 0).reduce((sum, item) => sum + item.credibility_score, 0) / items.filter((item) => item.verified_count > 0).length) : null,
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
      subtitle="管理你持续跟踪的 Twitter 博主，并从原推文进入提取结果和历史判断。"
      actions={<button className="button-primary" onClick={() => setShowOnboard(true)}><AppIcon name="research" />新增信息源</button>}
    />
    <MetricStrip items={[
      { label: scope === "followed" ? "我的关注" : "全部来源", value: items.length, note: scope === "followed" ? "进入今日情报" : "平台已收录" },
      { label: "平均预测评分", value: stats.avg ?? "—", note: "仅统计已有验证样本的博主" },
      { label: "已验证预测", value: stats.verified, note: `${stats.pending} 条待验证` },
    ]} />
    <div className="content-toolbar">
      <div className="source-toolbar-heading">
        <SectionTitle icon="sources" title={scope === "followed" ? "我的信息源" : "全部信息源"} meta="点击查看最新推文和提取结果" />
        <SegmentedControl value={scope} options={[{ value: "followed", label: "我的关注" }, { value: "all", label: "全部来源" }]} onChange={setScope} />
      </div>
      <SegmentedControl value={sort} options={OPTIONS} onChange={setSort} />
    </div>
    {loading ? <PageLoading label="正在评估信息源" />
      : error ? <PageError detail={error} onRetry={load} />
        : items.length === 0 ? <PageEmpty title={scope === "followed" ? "还没有关注 Twitter 博主" : "尚无可评估的信息源"} detail="点击“新增信息源”，输入 Twitter Handle 后会自动关注、抓取并分析。" action={<button className="button-primary mt-3" onClick={() => setShowOnboard(true)}>新增信息源</button>} />
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
