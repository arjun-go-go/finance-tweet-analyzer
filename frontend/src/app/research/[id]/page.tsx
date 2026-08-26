"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { getResearchWorkspace, runResearchTopic, updateResearchMonitor, type ResearchWorkspace } from "@/lib/api";

export default function ResearchWorkspacePage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<ResearchWorkspace | null>(null);
  const [frequency, setFrequency] = useState<"daily" | "weekly">("weekly");
  const load = () => getResearchWorkspace(id).then(setData);
  useEffect(() => { load(); const timer = setInterval(load, 5000); return () => clearInterval(timer); }, [id]);
  if (!data) return <div className="page-loading">正在加载研究工作区…</div>;
  const topic = data.topic; const latest = data.conclusions[0];
  return <div className="research-workspace-page">
    <header className="page-header"><div><p className="eyebrow">Research topic</p><h1>{topic.title}</h1><p>{topic.research_question}</p></div><div className="research-actions"><button onClick={async () => { await runResearchTopic(id); load(); }}>重新研究</button>{!topic.monitor_enabled && <select value={frequency} onChange={(event) => setFrequency(event.target.value as "daily" | "weekly")}><option value="daily">每日</option><option value="weekly">每周</option></select>}<button onClick={async () => { await updateResearchMonitor(id, !topic.monitor_enabled, topic.monitor_enabled ? topic.monitor_frequency : frequency); load(); }}>{topic.monitor_enabled ? "停止持续监控" : `开启${frequency === "daily" ? "每日" : "每周"}监控`}</button></div></header>
    {topic.last_error && <div className="research-error">{topic.last_error}</div>}
    <div className="research-workspace-grid"><main><section className="research-conclusion"><span>当前结论 · v{latest?.version || 0}</span><h2>{latest?.conclusion || (topic.status === "queued" || topic.status === "running" ? "研究正在执行" : "尚未形成结论")}</h2>{latest && <><h3>核心逻辑</h3><p>{latest.thesis}</p><h3>反面证据与缺口</h3><p>{latest.counter_evidence}</p><h3>主要风险</h3><ul>{latest.risks.map((risk) => <li key={risk}>{risk}</li>)}</ul><small>置信度 {(latest.confidence * 100).toFixed(0)}% · 引用 {latest.evidence_keys.join(", ") || "无"}</small></>}</section><section className="research-history"><h2>结论版本</h2>{data.conclusions.map((item) => <article key={item.id}><b>v{item.version}</b><p>{item.conclusion}</p><small>{new Date(item.created_at).toLocaleString("zh-CN")}</small></article>)}</section></main><aside><h2>证据板</h2>{data.evidence.map((item) => <article key={item.id}><span>{item.evidence_key} · {item.source_type}</span><b>{item.author ? `@${item.author}` : item.tickers.join(", ")}</b><p>{item.excerpt}</p><small>{item.published_at ? new Date(item.published_at).toLocaleString("zh-CN") : "时间未知"} · 相关度 {item.relevance_score.toFixed(2)}</small>{item.source_url && <a href={item.source_url} target="_blank">查看原文</a>}</article>)}</aside></div>
  </div>;
}
