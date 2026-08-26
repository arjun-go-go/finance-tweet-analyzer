"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { fetchMe, logout, type AuthUser } from "@/lib/auth";
import AppIcon from "@/components/AppIcon";
import { PageError, PageLoading } from "@/components/PageState";
import { WorkspacePageHeader } from "@/components/WorkspacePage";

export default function MePage() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchMe()
      .then((value) => {
        if (!value) setError("登录状态已失效，请重新登录。");
        else setUser(value);
      })
      .catch(() => setError("账户信息加载失败。"));
  }, []);

  return <div className="product-page settings-page">
    <WorkspacePageHeader
      eyebrow="Account"
      title="个人设置"
      subtitle="账户只负责身份与数据隔离；研究范围由关注博主和关注标的统一管理。"
    />

    {error ? <PageError detail={error} /> : !user ? <PageLoading label="正在读取账户信息" /> : <div className="settings-grid">
      <section className="settings-card">
        <span className="workspace-avatar">{user.username.slice(0, 2).toUpperCase()}</span>
        <div><p className="page-eyebrow">Account identity</p><h2>{user.username}</h2><p>{user.email}</p><small>账户状态：{user.status}</small></div>
      </section>

      <section className="settings-card settings-scope-card">
        <div><AppIcon name="sources" /><strong>关注博主</strong><span>定义系统持续采集和优先展示的信息源。</span></div>
        <Link className="button-secondary" href="/sources">管理信息源</Link>
      </section>

      <section className="settings-card settings-scope-card">
        <div><AppIcon name="watchlist" /><strong>关注标的</strong><span>定义今日情报和助手回答的个人研究范围。</span></div>
        <Link className="button-secondary" href="/watch">管理关注标的</Link>
      </section>

      <section className="settings-card settings-signout-card">
        <div><strong>退出当前账户</strong><span>本地访问令牌会被清除。</span></div>
        <button className="text-danger" type="button" onClick={logout}>退出登录</button>
      </section>
    </div>}
  </div>;
}
