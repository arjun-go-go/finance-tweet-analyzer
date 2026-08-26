"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import AppIcon, { type IconName } from "@/components/AppIcon";
import { fetchAlerts } from "@/lib/api";
import { logout } from "@/lib/auth";

interface NavItem {
  href: string;
  label: string;
  icon: IconName;
  aliases?: string[];
}

const primary: NavItem[] = [
  { href: "/", label: "今日", icon: "pulse" },
  { href: "/sources", label: "信息源", icon: "sources", aliases: ["/bloggers"] },
  { href: "/watch", label: "关注", icon: "watchlist", aliases: ["/tracking"] },
  { href: "/assistant", label: "助手", icon: "research", aliases: ["/chat"] },
];

function matchesPath(pathname: string, href: string) {
  return href === "/"
    ? pathname === "/"
    : pathname === href || pathname.startsWith(`${href}/`);
}

function NavLink({ item, active }: { item: NavItem; active: boolean }) {
  return (
    <Link
      href={item.href}
      className={`workspace-nav-link ${active ? "is-active" : ""}`}
      aria-current={active ? "page" : undefined}
    >
      <AppIcon name={item.icon} />
      <span>{item.label}</span>
    </Link>
  );
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const searchInput = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [unreadAlerts, setUnreadAlerts] = useState(0);

  useEffect(() => {
    let active = true;
    fetchAlerts("unread")
      .then((result) => {
        if (active) setUnreadAlerts(result.unread);
      })
      .catch(() => {
        // Navigation must remain available when the optional alert service is unavailable.
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const focusSearch = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        searchInput.current?.focus();
      }
    };
    window.addEventListener("keydown", focusSearch);
    return () => window.removeEventListener("keydown", focusSearch);
  }, []);

  const isActive = (item: NavItem) =>
    matchesPath(pathname, item.href) ||
    (item.aliases ?? []).some((alias) => matchesPath(pathname, alias));

  const submitSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const normalized = query.trim();
    router.push(normalized ? `/tweets?q=${encodeURIComponent(normalized)}` : "/tweets");
  };

  return (
    <div className="workspace-shell">
      <aside className="workspace-sidebar">
        <Link href="/" className="workspace-brand" aria-label="Signal Desk 首页">
          <span className="workspace-brand-mark"><span /></span>
          <div>
            <strong>Signal Desk</strong>
            <small>Twitter 投资情报</small>
          </div>
        </Link>

        <nav className="workspace-nav" aria-label="主导航">
          {primary.map((item) => (
            <NavLink key={item.href} item={item} active={isActive(item)} />
          ))}
        </nav>

        <div className="workspace-sidebar-footer">
          <p className="workspace-sidebar-note">
            <strong>只保留重要信号</strong>
            从关注的 Twitter 博主中提取可追溯的投资观点。
          </p>
          <div className="workspace-profile-row">
            <Link
              href="/settings"
              className={`workspace-profile ${matchesPath(pathname, "/settings") || matchesPath(pathname, "/me") ? "is-active" : ""}`}
            >
              <span className="workspace-avatar">SD</span>
              <span><strong>个人设置</strong><small>研究偏好与账户</small></span>
            </Link>
            <button type="button" className="workspace-signout" onClick={logout}>退出</button>
          </div>
        </div>
      </aside>

      <main className="workspace-main">
        <header className="workspace-topbar">
          <Link href="/" className="workspace-mobile-brand">Signal Desk</Link>
          <form className="workspace-search" role="search" onSubmit={submitSearch}>
            <button type="submit" aria-label="搜索推文、博主或标的"><AppIcon name="search" /></button>
            <input
              ref={searchInput}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索推文、博主或标的"
              aria-label="搜索推文、博主或标的"
            />
            <kbd>Ctrl K</kbd>
          </form>
          <div className="workspace-top-actions">
            <Link href="/alerts" className="workspace-icon-button" aria-label={unreadAlerts ? `${unreadAlerts} 条未读提醒` : "研究提醒"}>
              <AppIcon name="alerts" />
              {unreadAlerts > 0 && <span className="workspace-alert-count">{unreadAlerts > 99 ? "99+" : unreadAlerts}</span>}
            </Link>
            <Link href="/sources?add=1" className="workspace-add-source">
              <AppIcon name="plus" /><span>新增信息源</span>
            </Link>
            <Link href="/settings" className="workspace-mobile-settings" aria-label="个人设置"><AppIcon name="settings" /></Link>
          </div>
        </header>
        <div className="workspace-content">{children}</div>
      </main>
    </div>
  );
}
