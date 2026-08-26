"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import AppIcon from "@/components/AppIcon";
import BloggerCard, { type BloggerListItem } from "@/components/BloggerCard";
import ConfirmDialog from "@/components/ConfirmDialog";
import {
  fetchBloggerIngestionStatus,
  fetchBloggers,
  listMyBloggers,
  onboardBlogger,
  unfollowBlogger,
  type BloggerIngestionStage,
  type BloggerIngestionStatus,
  type BloggerOnboardResult,
} from "@/lib/api";
import { PageEmpty, PageError, PageLoading } from "@/components/PageState";
import { SegmentedControl, WorkspacePageHeader } from "@/components/WorkspacePage";

type SortKey = "credibility" | "verified_count" | "followers" | "pending_count";
type SourceScope = "followed" | "all";
type SourceFilter = "all" | "active" | "syncing" | "attention" | "paused";

const STAGE_LABELS: Record<BloggerIngestionStage, string> = {
  syncing: "首次同步中",
  analyzing: "正在提取投资信息",
  ready: "采集与分析已完成",
  attention: "部分内容需要处理",
  paused: "定时采集已暂停",
};

export default function BloggersListPage() {
  const params = useSearchParams();
  const sort = (params.get("sort") as SortKey) || "credibility";
  const [scope, setScope] = useState<SourceScope>("followed");
  const [items, setItems] = useState<BloggerListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showOnboard, setShowOnboard] = useState(false);
  const [handle, setHandle] = useState("");
  const [onboarding, setOnboarding] = useState(false);
  const [onboardError, setOnboardError] = useState("");
  const [onboarded, setOnboarded] = useState<BloggerOnboardResult | null>(null);
  const [ingestion, setIngestion] = useState<BloggerIngestionStatus | null>(null);
  const [filter, setFilter] = useState<SourceFilter>("all");
  const [unfollowTarget, setUnfollowTarget] = useState<BloggerListItem | null>(null);
  const [unfollowingId, setUnfollowingId] = useState<string | null>(null);
  const [unfollowNotice, setUnfollowNotice] = useState<{ kind: "success" | "error"; message: string } | null>(null);

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

  useEffect(() => {
    if (params.get("add") === "1") setShowOnboard(true);
  }, [params]);

  useEffect(() => {
    if (!onboarded) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      try {
        const next = await fetchBloggerIngestionStatus(onboarded.handle);
        if (cancelled) return;
        setIngestion(next);
        if (next.stage === "syncing" || next.stage === "analyzing") {
          timer = setTimeout(poll, 2500);
        }
      } catch {
        if (!cancelled) timer = setTimeout(poll, 4000);
      }
    };
    poll();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [onboarded]);

  const sourceStats = useMemo(() => ({
    active: items.filter((item) => ["syncing", "analyzing", "ready"].includes(item.ingestion_stage)).length,
    syncing: items.filter((item) => ["syncing", "analyzing"].includes(item.ingestion_stage)).length,
    attention: items.filter((item) => item.ingestion_stage === "attention").length,
    paused: items.filter((item) => item.ingestion_stage === "paused").length,
  }), [items]);

  const visibleItems = useMemo(() => items.filter((item) => {
    if (filter === "active") return ["syncing", "analyzing", "ready"].includes(item.ingestion_stage);
    if (filter === "syncing") return ["syncing", "analyzing"].includes(item.ingestion_stage);
    if (filter === "attention") return item.ingestion_stage === "attention";
    if (filter === "paused") return item.ingestion_stage === "paused";
    return true;
  }), [filter, items]);

  const closeOnboard = () => {
    if (onboarding) return;
    setShowOnboard(false);
    setHandle("");
    setOnboardError("");
    setOnboarded(null);
    setIngestion(null);
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

  const confirmUnfollow = async () => {
    if (!unfollowTarget) return;
    const target = unfollowTarget;
    setUnfollowTarget(null);
    setUnfollowingId(target.id);
    setUnfollowNotice(null);
    try {
      await unfollowBlogger(target.id);
      setItems((current) => current.filter((item) => item.id !== target.id));
      setUnfollowNotice({ kind: "success", message: `已取消关注 @${target.handle.replace(/^@/, "")}。` });
    } catch (unfollowError) {
      setUnfollowNotice({
        kind: "error",
        message: unfollowError instanceof Error ? unfollowError.message : "取消关注失败，请稍后重试。",
      });
    } finally {
      setUnfollowingId(null);
    }
  };

  return <div className="product-page source-library-page">
    <WorkspacePageHeader
      eyebrow="Source Intelligence"
      title="信息源"
      subtitle="只保留值得长期观察的人；系统持续采集公开推文、Thread 与图片，并提取可追溯的投资信息。"
      actions={<button className="button-primary" onClick={() => setShowOnboard(true)}><AppIcon name="plus" />新增信息源</button>}
    />
    <div className="source-library-summary">
      <span><i className="source-live-dot" /><strong>{sourceStats.active} 个来源正在工作</strong>{sourceStats.syncing ? `，${sourceStats.syncing} 个仍在首次处理` : ""}</span>
      <small>{sourceStats.attention ? `${sourceStats.attention} 个需要处理` : sourceStats.paused ? `${sourceStats.paused} 个已暂停` : "所有信息源状态正常"}</small>
    </div>
    <div className="source-library-toolbar">
      <SegmentedControl value={scope} options={[{ value: "followed", label: "我的关注" }, { value: "all", label: "全部来源" }]} onChange={(next) => { setScope(next); setFilter("all"); }} />
      <div className="source-library-filters">
        {([
          ["all", "全部"],
          ["active", "采集中"],
          ["syncing", "处理中"],
          ["attention", "需处理"],
          ["paused", "已暂停"],
        ] as Array<[SourceFilter, string]>).map(([value, label]) => <button key={value} className={filter === value ? "is-active" : ""} onClick={() => setFilter(value)}>{label}</button>)}
      </div>
      <span>{visibleItems.length} 位博主</span>
    </div>
    {unfollowNotice && <div className={`source-library-notice is-${unfollowNotice.kind}`} role="status">
      <span>{unfollowNotice.message}</span>
      <button type="button" onClick={() => setUnfollowNotice(null)} aria-label="关闭提示"><AppIcon name="close" /></button>
    </div>}
    {loading ? <PageLoading label="正在整理信息源" />
      : error ? <PageError detail={error} onRetry={load} />
        : items.length === 0 ? <PageEmpty title={scope === "followed" ? "还没有关注 Twitter 博主" : "尚无可评估的信息源"} detail="点击“新增信息源”，输入 Twitter Handle 后会自动关注、抓取并分析。" action={<button className="button-primary mt-3" onClick={() => setShowOnboard(true)}>新增信息源</button>} />
          : visibleItems.length === 0 ? <PageEmpty title="当前筛选下没有信息源" detail="切换其他状态，或新增一个 Twitter 信息源。" />
            : <div className="source-library-list">{visibleItems.map((blogger) => <BloggerCard
              key={blogger.handle}
              blogger={blogger}
              onUnfollow={scope === "followed" ? () => setUnfollowTarget(blogger) : undefined}
              unfollowing={unfollowingId === blogger.id}
            />)}</div>}

    <ConfirmDialog
      open={Boolean(unfollowTarget)}
      title="取消关注信息源"
      message={unfollowTarget ? `取消关注 @${unfollowTarget.handle.replace(/^@/, "")} 后，它将不再进入你的今日情报和助手研究范围。历史推文会保留，定时抓取设置不会改变。` : ""}
      confirmText="取消关注"
      variant="danger"
      onConfirm={confirmUnfollow}
      onCancel={() => setUnfollowTarget(null)}
    />

    {showOnboard && <div className="source-onboard-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) closeOnboard(); }}>
      <section className="source-onboard-dialog" role="dialog" aria-modal="true" aria-labelledby="source-onboard-title">
        <button className="source-onboard-close" onClick={closeOnboard} aria-label="关闭"><AppIcon name="close" /></button>
        {!onboarded ? <>
          <div className="source-onboard-heading">
            <span className="source-onboard-mark"><AppIcon name="sources" /></span>
            <div><p>One-step source setup</p><h2 id="source-onboard-title">新增信息源</h2><span>输入 Twitter Handle，系统核对公开身份后自动开始采集。</span></div>
          </div>
          <form onSubmit={submitOnboard} className="source-onboard-form">
            <label htmlFor="twitter-handle">Twitter Handle</label>
            <div className="source-handle-input"><span>@</span><input id="twitter-handle" value={handle} onChange={(event) => setHandle(event.target.value)} placeholder="elonmusk" autoFocus disabled={onboarding} /></div>
            {!onboarding && !onboardError && <p className="source-onboard-help">只采集公开内容，不需要提供 Twitter 密码。</p>}
            {onboarding && <div className="source-onboard-check is-checking"><i /><span><strong>正在核对公开账号</strong><small>确认身份后会自动加入关注并启动首次采集。</small></span></div>}
            {onboardError && <div className="source-onboard-check is-error"><b>!</b><span><strong>暂时无法添加</strong><small>{onboardError}</small></span></div>}
            <button className="button-primary source-onboard-submit" type="submit" disabled={onboarding}>{onboarding ? "正在核对…" : "检查并开始采集"}<AppIcon name="arrow" /></button>
          </form>
        </> : <div className="source-onboard-success source-onboard-progress">
          <p>Source connected</p>
          <h2>@{onboarded.handle} 已加入关注</h2>
          <div className="source-onboard-profile">
            {onboarded.avatar_url ? <img src={onboarded.avatar_url} alt="" /> : <span>{onboarded.handle.slice(0, 2).toUpperCase()}</span>}
            <div><strong>{onboarded.name || `@${onboarded.handle}`}</strong><small>@{onboarded.handle} · 公开身份已核对</small></div>
          </div>
          <div className={`source-onboard-runtime state-${ingestion?.stage || "syncing"}`}>
            <div><strong>{STAGE_LABELS[ingestion?.stage || "syncing"]}</strong><span>{ingestion?.progress ?? 15}%</span></div>
            <i><b style={{ width: `${ingestion?.progress ?? 15}%` }} /></i>
            <p>{ingestion?.message || "资料与关注关系已保存，正在等待采集任务执行。"}</p>
          </div>
          <ol className="source-onboard-steps">
            <li className="is-done"><b>✓</b><span>身份核对<small>公开账号资料已保存</small></span></li>
            <li className="is-done"><b>✓</b><span>加入关注<small>已进入你的研究范围</small></span></li>
            <li className={ingestion && ingestion.stage !== "syncing" ? "is-done" : "is-active"}><b>{ingestion && ingestion.stage !== "syncing" ? "✓" : "3"}</b><span>采集推文与图片<small>{ingestion?.collected_tweets ? `已采集 ${ingestion.collected_tweets} 条` : "后台异步执行"}</small></span></li>
            <li className={ingestion?.stage === "ready" ? "is-done" : ingestion?.stage === "analyzing" ? "is-active" : ""}><b>{ingestion?.stage === "ready" ? "✓" : "4"}</b><span>提取投资信息<small>{ingestion?.analyzed_tweets ? `已完成 ${ingestion.analyzed_tweets} 条` : "文本与图片联合分析"}</small></span></li>
          </ol>
          <div><Link className="button-primary" href={`/sources/${encodeURIComponent(onboarded.handle)}`}>查看信息源<AppIcon name="arrow" /></Link><button className="button-secondary" onClick={closeOnboard}>在后台继续</button></div>
        </div>}
      </section>
    </div>}
  </div>;
}
