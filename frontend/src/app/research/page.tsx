"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  createResearchTopic,
  getResearchBrief,
  getResearchOpportunities,
  listResearchTopics,
  runResearchTopic,
  type ResearchBrief,
  type ResearchOpportunity,
  type ResearchTopic,
} from "@/lib/api";

export default function ResearchTopicsPage() {
  const [items, setItems] = useState<ResearchTopic[]>([]);
  const [brief, setBrief] = useState<ResearchBrief | null>(null);
  const [opportunities, setOpportunities] = useState<ResearchOpportunity[]>([]);
  const [question, setQuestion] = useState("");
  const [ticker, setTicker] = useState("");
  const [busy, setBusy] = useState(false);
  const load = () => Promise.all([
    listResearchTopics().then(setItems),
    getResearchBrief().then(setBrief),
    getResearchOpportunities().then(setOpportunities),
  ]).catch(() => undefined);
  useEffect(() => { load(); }, []);

  const create = async () => {
    if (!question.trim()) return;
    setBusy(true);
    try {
      const topic = await createResearchTopic({ title: question.trim().slice(0, 60), research_question: question.trim(), tickers: ticker.trim() ? [ticker.trim().toUpperCase()] : [], source_scope: ["public_signals", "tweets"], time_range: "1w" });
      await runResearchTopic(topic.id);
      setQuestion(""); setTicker(""); await load();
    } finally { setBusy(false); }
  };

  const startOpportunity = async (item: ResearchOpportunity) => {
    setBusy(true);
    try {
      const topic = await createResearchTopic({ title: item.title.slice(0, 60), research_question: `分析 ${item.tickers.join(", ")} 相关的新市场信号：${item.title}`, tickers: item.tickers, source_scope: ["public_signals", "tweets"], time_range: "1w" });
      await runResearchTopic(topic.id);
      await load();
    } finally { setBusy(false); }
  };

  return <div className="research-topics-page">
    <header className="page-header"><div><p className="eyebrow">Research workspace</p><h1>研究课题</h1><p>把一次问答沉淀为可验证、可持续更新的研究成果。</p></div></header>
    <section className="research-overview-grid">
      <article className="research-brief-panel"><div><span>今日研究简报</span><b>{brief ? brief.personalized.length + brief.risks.length + brief.discoveries.length : 0} 条</b></div><p>与你的关注范围有关 {brief?.personalized.length || 0} 条，市场风险 {brief?.risks.length || 0} 条，新发现 {brief?.discoveries.length || 0} 条。</p></article>
      <article className="research-brief-panel"><div><span>待研究机会</span><b>{opportunities.length} 个</b></div><p>从近 7 日市场发现中排除已有课题，避免重复研究。</p></article>
    </section>
    <section className="research-create-panel"><div><label>研究问题</label><textarea value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="例如：NVDA 最近是否出现观点反转？" /></div><div><label>核心标的</label><input value={ticker} onChange={(e) => setTicker(e.target.value)} placeholder="NVDA" /></div><button onClick={create} disabled={busy || !question.trim()}>{busy ? "正在创建" : "开始深度研究"}</button></section>
    {opportunities.length > 0 && <section className="research-opportunities"><div className="section-heading"><div><span>Opportunity discovery</span><h2>自动发现的研究机会</h2></div></div><div className="research-opportunity-grid">{opportunities.map((item) => <article key={item.id}><div><span>{item.tickers.join(", ")}</span><b>{item.importance_score}</b></div><h3>{item.title}</h3><p>{item.summary}</p><small>{item.reason}</small><button onClick={() => startOpportunity(item)} disabled={busy}>建立研究课题</button></article>)}</div></section>}
    <section className="research-topic-grid">{items.map((item) => <Link href={`/research/${item.id}`} key={item.id} className="research-topic-card"><div><span>{item.mode === "deep" ? "深度研究" : "快速研究"}</span><b className={`status-${item.status}`}>{item.status}</b></div><h2>{item.title}</h2><p>{item.research_question}</p><footer><span>{item.tickers.join(", ") || "跨市场"}</span><span>{item.monitor_enabled ? `${item.monitor_frequency === "daily" ? "每日" : "每周"}监控` : "未持续监控"}</span></footer></Link>)}</section>
  </div>;
}
