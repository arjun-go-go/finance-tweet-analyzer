"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import AppIcon from "@/components/AppIcon";
import {
  fetchAlerts,
  fetchIntelligenceFeed,
  listMyBloggers,
  listTracking,
  readAllAlerts,
  type IntelligenceFeedItem,
  type TrackingItem,
  type UserAlertItem,
} from "@/lib/api";
import { formatDateTime } from "@/lib/datetime";

interface OverlayProps {
  open: boolean;
  onClose: () => void;
}

interface NotificationDrawerProps extends OverlayProps {
  onUnreadChange?: (count: number) => void;
}

interface SourceResult {
  id: string;
  handle: string;
  name: string;
  bio: string | null;
  market_focus: string[] | null;
}

export function GlobalSearchDialog({ open, onClose }: OverlayProps) {
  const [query, setQuery] = useState("");
  const [sources, setSources] = useState<SourceResult[]>([]);
  const [assets, setAssets] = useState<TrackingItem[]>([]);
  const [insights, setInsights] = useState<IntelligenceFeedItem[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    Promise.allSettled([listMyBloggers(), listTracking(), fetchIntelligenceFeed(50, "7d", "all")])
      .then(([sourceResult, assetResult, insightResult]) => {
        if (sourceResult.status === "fulfilled") setSources(sourceResult.value.items);
        if (assetResult.status === "fulfilled") setAssets(assetResult.value.items);
        if (insightResult.status === "fulfilled") setInsights(insightResult.value.items);
      })
      .finally(() => setLoading(false));
  }, [open]);

  useEffect(() => {
    if (!open) setQuery("");
  }, [open]);

  const clean = query.trim().toLocaleLowerCase();
  const sourceMatches = useMemo(() => !clean ? [] : sources.filter((item) =>
    [item.handle, item.name, item.bio || "", ...(item.market_focus || [])]
      .join(" ").toLocaleLowerCase().includes(clean)).slice(0, 4), [clean, sources]);
  const assetMatches = useMemo(() => !clean ? [] : assets.filter((item) =>
    [item.ticker, item.instrument?.resolved_name || "", item.instrument?.name || ""]
      .join(" ").toLocaleLowerCase().includes(clean)).slice(0, 4), [assets, clean]);
  const insightMatches = useMemo(() => !clean ? [] : insights.filter((item) =>
    [item.title, item.summary, item.author, ...item.tickers]
      .join(" ").toLocaleLowerCase().includes(clean)).slice(0, 5), [clean, insights]);
  const resultCount = sourceMatches.length + assetMatches.length + insightMatches.length;

  if (!open) return null;
  return <div className="workspace-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="global-search-dialog" role="dialog" aria-modal="true" aria-label="全局搜索">
      <header>
        <AppIcon name="search" />
        <input autoFocus value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === "Escape") onClose(); }} placeholder="搜索博主、标的或观点" />
        <kbd>ESC</kbd>
        <button type="button" onClick={onClose} aria-label="关闭搜索">×</button>
      </header>
      {!clean ? <div className="global-search-start">
        <span>搜索范围</span>
        <div><b>关注博主</b><b>关注标的</b><b>已采集观点</b><b>原始证据</b></div>
        <p>结果只来自已经采集和核验的数据，不会访问公开网页补全。</p>
      </div> : loading ? <div className="global-search-state"><span className="signal-loader" /><strong>正在检索已采集内容</strong></div>
        : resultCount === 0 ? <div className="global-search-state"><span className="search-state-mark">?</span><strong>没有找到“{query.trim()}”</strong><p>可检查关键词，或先添加一个 Twitter 博主。</p><Link href="/sources?add=1" onClick={onClose}>添加博主</Link></div>
          : <div className="global-search-results">
            <p>找到 {resultCount} 条匹配结果</p>
            {assetMatches.length > 0 && <section><header><strong>关注标的</strong><span>{assetMatches.length}</span></header>{assetMatches.map((item) => <Link key={item.id} href={`/watch/${encodeURIComponent(item.ticker)}`} onClick={onClose}><b className="search-symbol">{item.ticker}</b><span><strong>{item.instrument?.resolved_name || item.instrument?.name || item.ticker}</strong><small>{item.monitor.intelligence_24h || 0} 条 24h 情报</small></span><AppIcon name="arrow" /></Link>)}</section>}
            {sourceMatches.length > 0 && <section><header><strong>博主</strong><span>{sourceMatches.length}</span></header>{sourceMatches.map((item) => <Link key={item.id} href={`/sources/${encodeURIComponent(item.handle)}`} onClick={onClose}><b className="search-avatar">{item.name.slice(0, 2).toUpperCase()}</b><span><strong>{item.name} <i>@{item.handle.replace(/^@/, "")}</i></strong><small>{item.market_focus?.join(" · ") || "Twitter 博主"}</small></span><AppIcon name="arrow" /></Link>)}</section>}
            {insightMatches.length > 0 && <section><header><strong>观点与证据</strong><span>{insightMatches.length}</span></header>{insightMatches.map((item) => <Link key={item.id} href={`/insights/${encodeURIComponent(item.id)}`} onClick={onClose}><b className="search-symbol">{item.tickers[0] || "观点"}</b><span><strong>{item.title}</strong><small>@{item.author.replace(/^@/, "")} · {formatDateTime(item.published_at)}</small></span><AppIcon name="arrow" /></Link>)}</section>}
          </div>}
      <footer><span>只搜索已采集内容</span><Link href={clean ? `/tweets?q=${encodeURIComponent(query.trim())}` : "/tweets"} onClick={onClose}>查看全部推文</Link></footer>
    </section>
  </div>;
}

export function NotificationDrawer({ open, onClose, onUnreadChange }: NotificationDrawerProps) {
  const [items, setItems] = useState<UserAlertItem[]>([]);
  const [unread, setUnread] = useState(0);
  const [loading, setLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    fetchAlerts("unread")
      .then((result) => {
        setItems(result.items.slice(0, 12));
        setUnread(result.unread);
        onUnreadChange?.(result.unread);
      })
      .catch(() => {
        setItems([]);
        setUnread(0);
        onUnreadChange?.(0);
      })
      .finally(() => setLoading(false));
  }, [onUnreadChange]);

  useEffect(() => { if (open) load(); }, [load, open]);
  if (!open) return null;

  return <div className="workspace-overlay workspace-overlay-right" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <aside className="notification-drawer" role="dialog" aria-modal="true" aria-label="研究提醒">
      <header><div><p>Research alerts</p><h2>研究提醒</h2><span>{unread ? `${unread} 条未读` : "当前已读完"}</span></div><button type="button" onClick={onClose} aria-label="关闭提醒">×</button></header>
      <div className="notification-list">
        {loading ? <div className="notification-state"><span className="signal-loader" />正在整理提醒</div>
          : items.length === 0 ? <div className="notification-state"><AppIcon name="alerts" /><strong>没有新的重要变化</strong><p>观点反转、共识形成和预测验证完成后会出现在这里。</p></div>
            : items.map((item) => <Link href={item.target_url} onClick={onClose} key={item.id} className={`notification-row is-${item.severity}`}><span /><div><small>{item.ticker || (item.blogger_handle ? `@${item.blogger_handle.replace(/^@/, "")}` : "Twitter 情报")} · {formatDateTime(item.occurred_at)}</small><strong>{item.title}</strong><p>{item.message}</p></div><AppIcon name="arrow" /></Link>)}
      </div>
      <footer>{unread > 0 && <button type="button" onClick={() => void readAllAlerts().then(load)}>全部标记已读</button>}<Link href="/alerts" onClick={onClose}>查看全部提醒</Link></footer>
    </aside>
  </div>;
}
