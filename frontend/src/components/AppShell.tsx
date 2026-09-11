"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import AppIcon, { type IconName } from "@/components/AppIcon";
import { GlobalSearchDialog, NotificationDrawer } from "@/components/WorkspaceOverlays";
import { fetchAlerts } from "@/lib/api";
import { logout } from "@/lib/auth";

interface NavItem {
  href: string;
  label: string;
  icon: IconName;
  aliases?: string[];
}

const primary: NavItem[] = [
  { href: "/", label: "动态", icon: "tweets" },
  { href: "/sources", label: "博主", icon: "sources" },
  { href: "/watch", label: "标的", icon: "watchlist" },
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
  const [unreadAlerts, setUnreadAlerts] = useState(0);
  const [searchOpen, setSearchOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);

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
        setSearchOpen(true);
      }
      if (event.key === "Escape") {
        setSearchOpen(false);
        setNotificationsOpen(false);
      }
    };
    window.addEventListener("keydown", focusSearch);
    return () => window.removeEventListener("keydown", focusSearch);
  }, []);

  const isActive = (item: NavItem) =>
    matchesPath(pathname, item.href) ||
    (item.aliases ?? []).some((alias) => matchesPath(pathname, alias));

  return (
    <div className="workspace-shell">
      <aside className="workspace-sidebar">
        <Link href="/" className="workspace-brand" aria-label="Signal 动态">
          <span className="workspace-brand-mark"><span /></span>
          <div>
            <strong>Signal</strong>
            <small>标的与市场观点</small>
          </div>
        </Link>

        <nav className="workspace-nav" aria-label="主导航">
          {primary.map((item) => (
            <NavLink key={item.href} item={item} active={isActive(item)} />
          ))}
        </nav>

        <div className="workspace-sidebar-footer">
          <p className="workspace-sidebar-note">
            <strong>观点来自原文</strong>
            识别每条推文里的标的观点与市场影响。
          </p>
          <div className="workspace-profile-row">
            <Link
              href="/settings"
              className={`workspace-profile ${matchesPath(pathname, "/settings") ? "is-active" : ""}`}
            >
              <span className="workspace-avatar">SD</span>
              <span><strong>个人工作台</strong><small>研究偏好与账户</small></span>
            </Link>
            <button type="button" className="workspace-signout" onClick={logout}>退出</button>
          </div>
        </div>
      </aside>

      <main className="workspace-main">
        <header className="workspace-topbar">
          <Link href="/" className="workspace-mobile-brand">Signal</Link>
          <div className="workspace-search" role="search" onClick={() => setSearchOpen(true)}>
            <span className="workspace-search-icon"><AppIcon name="search" /></span>
            <input
              readOnly
              value=""
              onFocus={() => setSearchOpen(true)}
              placeholder="搜索博主、标的或推文"
              aria-label="打开全局搜索"
            />
            <kbd>Ctrl K</kbd>
          </div>
          <div className="workspace-top-actions">
            <button type="button" className="workspace-icon-button" onClick={() => setNotificationsOpen(true)} aria-label={unreadAlerts ? `${unreadAlerts} 条未读提醒` : "研究提醒"}>
              <AppIcon name="alerts" />
              {unreadAlerts > 0 && <span className="workspace-alert-count">{unreadAlerts > 99 ? "99+" : unreadAlerts}</span>}
            </button>
            <Link href="/sources?add=1" className="workspace-add-source">
              <AppIcon name="plus" /><span>添加博主</span>
            </Link>
            <Link href="/settings" className="workspace-mobile-settings" aria-label="个人设置"><AppIcon name="settings" /></Link>
          </div>
        </header>
        <div className="workspace-content">{children}</div>
      </main>
      <GlobalSearchDialog open={searchOpen} onClose={() => setSearchOpen(false)} />
      <NotificationDrawer
        open={notificationsOpen}
        onClose={() => setNotificationsOpen(false)}
        onUnreadChange={setUnreadAlerts}
      />
    </div>
  );
}
