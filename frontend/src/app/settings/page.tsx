"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import AppIcon from "@/components/AppIcon";
import { PageError, PageLoading } from "@/components/PageState";
import { fetchMe, logout, type AuthUser } from "@/lib/auth";

type SettingsTab = "profile" | "scope" | "alerts" | "security";

const TABS: Array<{ value: SettingsTab; label: string }> = [
  { value: "profile", label: "个人资料" },
  { value: "scope", label: "研究范围" },
  { value: "alerts", label: "提醒" },
  { value: "security", label: "账户安全" },
];

export default function SettingsPage() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [tab, setTab] = useState<SettingsTab>("profile");
  const [error, setError] = useState("");

  useEffect(() => {
    fetchMe().then((value) => value ? setUser(value) : setError("登录状态已失效，请重新登录。"))
      .catch(() => setError("账户信息加载失败。"));
  }, []);

  return <div className="product-page settings-prototype-page">
    <header className="settings-prototype-heading"><p className="page-eyebrow">Preferences</p><h1>账户与偏好</h1><p>只保留影响情报范围、提醒和账户安全的必要设置。</p></header>
    {error ? <PageError detail={error} /> : !user ? <PageLoading label="正在读取账户信息" /> : <div className="settings-prototype-layout">
      <nav aria-label="设置分类">{TABS.map((item) => <button key={item.value} className={tab === item.value ? "is-active" : ""} onClick={() => setTab(item.value)}>{item.label}</button>)}</nav>
      <main>
        {tab === "profile" && <>
          <section className="settings-prototype-section"><h2>个人资料</h2><div className="settings-account-row"><span>{user.username.slice(0, 2).toUpperCase()}</span><div><strong>{user.username}</strong><small>{user.email}</small></div><b>{user.status === "active" ? "账户正常" : user.status}</b></div></section>
          <section className="settings-prototype-section"><h2>产品边界</h2><p>Signal 只整理已关注 Twitter 信息源中的投资观点。市场价格仅用于预测验证，内容不构成投资建议。</p></section>
        </>}

        {tab === "scope" && <>
          <section className="settings-prototype-section"><h2>研究范围</h2><p>首页和助手以正式关注关系为准，不从历史记忆猜测你的范围。</p><div className="settings-scope-list"><Link href="/sources"><AppIcon name="sources" /><span><strong>信息源</strong><small>管理持续采集的 Twitter 博主</small></span><AppIcon name="arrow" /></Link><Link href="/watch"><AppIcon name="watchlist" /><span><strong>关注标的</strong><small>管理需要聚合观点的股票、商品和加密货币</small></span><AppIcon name="arrow" /></Link></div></section>
          <section className="settings-prototype-section"><h2>支持市场</h2><div className="settings-market-list"><span>A股</span><span>港股</span><span>美股</span><span>原油</span><span>黄金</span><span>加密货币</span></div></section>
        </>}

        {tab === "alerts" && <>
          <section className="settings-prototype-section"><h2>提醒原则</h2><p>只在观点反转、高风险线索、新预测和预测验证完成时生成提醒；普通更新仍保留在“今日”。</p><div className="settings-alert-rule"><span><AppIcon name="alerts" /></span><div><strong>重要变化优先</strong><small>提醒由正式关注关系触发，不使用记忆偏好推断。</small></div><b>已启用</b></div></section>
          <section className="settings-prototype-section settings-section-action"><div><h2>提醒记录</h2><p>查看未读、已读与已忽略提醒。</p></div><Link className="button-secondary" href="/alerts">管理提醒</Link></section>
        </>}

        {tab === "security" && <>
          <section className="settings-prototype-section"><h2>登录安全</h2><div className="settings-security-row"><div><strong>登录账户</strong><small>{user.email}</small></div><b>已登录</b></div><div className="settings-security-row"><div><strong>访问隔离</strong><small>关注、对话和提醒按当前账户隔离。</small></div><b>已启用</b></div></section>
          <section className="settings-prototype-section settings-danger-section"><h2>账户</h2><p>退出后会清除当前浏览器保存的访问令牌。</p><button type="button" onClick={logout}>退出登录</button></section>
        </>}
      </main>
    </div>}
  </div>;
}
