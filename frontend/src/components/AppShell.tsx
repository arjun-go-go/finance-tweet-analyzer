"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import AppIcon, { type IconName } from "@/components/AppIcon";
import { logout } from "@/lib/auth";

const primary = [
  { href: "/", label: "今日情报", icon: "pulse" as const },
  { href: "/tracking", label: "Watchlist", icon: "watchlist" as const },
  { href: "/bloggers", label: "信息源", icon: "sources" as const },
  { href: "/chat", label: "研究助手", icon: "research" as const },
  { href: "/reports", label: "简报", icon: "briefs" as const },
];

const library = [
  { href: "/tweets", label: "推文情报", icon: "tweets" as const },
  { href: "/documents", label: "私人资料", icon: "documents" as const },
];

function NavLink({ item, active, onClick }: { item: { href: string; label: string; icon: IconName }; active: boolean; onClick?: () => void }) {
  return (
    <Link href={item.href} onClick={onClick} className={`workspace-nav-link ${active ? "is-active" : ""}`}>
      <AppIcon name={item.icon} />
      <span>{item.label}</span>
      {active && <span className="workspace-nav-pip" />}
    </Link>
  );
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const isActive = (href: string) => href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);

  const sidebar = (
    <>
      <div className="workspace-brand">
        <span className="workspace-brand-mark"><span /></span>
        <div>
          <strong>Signal Desk</strong>
          <small>投资情报工作台</small>
        </div>
      </div>
      <nav className="workspace-nav" aria-label="主导航">
        <p className="workspace-nav-label">工作台</p>
        {primary.map((item) => <NavLink key={item.href} item={item} active={isActive(item.href)} onClick={() => setOpen(false)} />)}
        <p className="workspace-nav-label workspace-nav-label-spaced">资料库</p>
        {library.map((item) => <NavLink key={item.href} item={item} active={isActive(item.href)} onClick={() => setOpen(false)} />)}
      </nav>
      <div className="workspace-sidebar-footer">
        <Link href="/me" className={`workspace-utility-link ${isActive("/me") ? "is-active" : ""}`}><AppIcon name="settings" />个人设置</Link>
        <Link href="/admin/runtime" className={`workspace-utility-link ${pathname.startsWith("/admin") ? "is-active" : ""}`}><AppIcon name="admin" />系统管理</Link>
        <Link href="/admin/predictions" className={`workspace-utility-link ${isActive("/admin/predictions") ? "is-active" : ""}`}><AppIcon name="evidence" />预测复核</Link>
        <button onClick={logout} className="workspace-signout">退出登录</button>
      </div>
    </>
  );

  return (
    <div className="workspace-shell">
      <aside className="workspace-sidebar">{sidebar}</aside>
      <header className="workspace-mobile-header">
        <button onClick={() => setOpen(true)} aria-label="打开导航"><AppIcon name="menu" /></button>
        <span className="workspace-brand-mark"><span /></span>
        <strong>Signal Desk</strong>
      </header>
      {open && <div className="workspace-mobile-overlay" onClick={() => setOpen(false)} />}
      <aside className={`workspace-mobile-drawer ${open ? "is-open" : ""}`}>
        <button className="workspace-drawer-close" onClick={() => setOpen(false)} aria-label="关闭导航"><AppIcon name="close" /></button>
        {sidebar}
      </aside>
      <main className="workspace-main"><div className="workspace-content">{children}</div></main>
    </div>
  );
}
