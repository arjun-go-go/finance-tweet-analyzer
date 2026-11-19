"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { fetchOpinionChanges, type OpinionChange, type OpinionChangesResponse, type OpinionSource } from "@/lib/api";
import { formatDateTime } from "@/lib/datetime";
import { PageEmpty, PageError, PageLoading } from "./PageState";
import TweetMediaGallery from "./TweetMediaGallery";

const DIRECTION = { bullish: "看好", bearish: "看空", neutral: "观望" };
const EVENT = { first_opinion: "首次记录", direction_changed: "方向变化", new_evidence: "新增依据" };
const HORIZON: Record<string, string> = { short: "短期", medium: "中期", long: "长期" };
const MARKET: Record<string, string> = { CN: "A 股", HK: "港股", US: "美股", COMMODITY: "商品", CRYPTO: "加密货币" };

function Direction({ value }: { value: OpinionSource["direction"] }) {
  return <span className={`opinion-direction is-${value}`}>{DIRECTION[value]}</span>;
}

function SourceEvidence({ label, source }: { label: string; source: OpinionSource }) {
  return (
    <section className="opinion-source">
      <div className="opinion-source-head">
        <h3>{label}</h3>
        <Direction value={source.direction} />
        <time dateTime={source.published_at}>{formatDateTime(source.published_at)}</time>
      </div>
      {source.thesis && <p className="opinion-thesis">{source.thesis}</p>}
      <details open>
        <summary>推文原文</summary>
        {source.excerpt && <blockquote>{source.excerpt}</blockquote>}
        <TweetMediaGallery tweetId={source.tweet_id} media={source.media} />
      </details>
      {source.evidence.length > 0 && <ul aria-label="正文证据">{source.evidence.map((line) => <li key={line}>{line}</li>)}</ul>}
      {source.media_evidence.length > 0 && (
        <div className="opinion-image-evidence">
          <strong>图片分析提取</strong>
          <ul>{source.media_evidence.map((line, index) => <li key={index}>{line}</li>)}</ul>
        </div>
      )}
      <a href={`https://x.com/${encodeURIComponent(source.author_handle)}/status/${encodeURIComponent(source.source_id)}`} target="_blank" rel="noreferrer">
        查看 X 上的原文
      </a>
    </section>
  );
}

export default function OpinionChanges() {
  const [data, setData] = useState<OpinionChangesResponse | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [analysisOpen, setAnalysisOpen] = useState(false);

  useEffect(() => {
    const request = new AbortController();
    void fetchOpinionChanges(request.signal).then((result) => {
      if (!request.signal.aborted) setData(result);
    }).catch(() => {
      if (!request.signal.aborted) setError("暂时无法加载关注变化，请重试。");
    });
    return () => request.abort();
  }, [attempt]);

  if (error) return <PageError detail={error} onRetry={() => { setError(""); setAttempt((n) => n + 1); }} />;
  if (!data) return <PageLoading label="正在加载关注变化" />;
  const selected = data.items.find((item) => item.id === selectedId) || data.items[0];
  if (!selected) return (
    <PageEmpty
      title={data.followed_count ? "最近没有可对照的变化" : "还没有关注博主"}
      detail={data.followed_count
        ? `这里展示最近 ${data.display_days} 天可核对的新观点、方向和依据变化。完整推文仍在「全部」。`
        : "到信息源页面关注一个博主，就能在这里对照他的前后观点。"}
      action={!data.followed_count && <Link href="/sources" className="button-primary">去关注博主</Link>}
    />
  );

  function select(item: OpinionChange) {
    setSelectedId(item.id);
    setAnalysisOpen(true);
  }

  return (
    <>
      <p className="activity-view-note">最近 {data.display_days} 天 · {data.items.length} 项变化 · 对照过去 {data.comparison_days} 天的记录</p>
      <div className="activity-workbench">
        <section className="activity-feed" aria-label="关注的博主观点变化">
          {data.items.map((item) => (
            <button
              type="button"
              key={item.id}
              aria-pressed={selected.id === item.id}
              className={`opinion-change-row ${selected.id === item.id ? "is-selected" : ""}`}
              onClick={() => select(item)}
            >
              <span className="opinion-row-meta">
                <strong>{item.symbol}</strong>
                <span>{MARKET[item.market] || item.market}</span>
                <span>{HORIZON[item.horizon] || "期限未明"}</span>
                <time dateTime={item.current.published_at}>{formatDateTime(item.current.published_at)}</time>
              </span>
              <span className="opinion-row-change">
                <span className="opinion-kind">{EVENT[item.kind]}</span>
                {item.previous && item.previous.direction !== item.current.direction && (
                  <><Direction value={item.previous.direction} /><span aria-label="变为">→</span></>
                )}
                <Direction value={item.current.direction} />
              </span>
              <span className="opinion-row-thesis">{item.new_factors[0] || item.current.thesis || item.current.excerpt}</span>
              <span className="opinion-row-author">{item.current.author_name} <span>@{item.current.author_handle}</span></span>
            </button>
          ))}
        </section>

        <button type="button" className={`activity-inspector-backdrop ${analysisOpen ? "is-open" : ""}`} aria-label="关闭原文对照" onClick={() => setAnalysisOpen(false)} />
        <aside className={`activity-inspector ${analysisOpen ? "is-open" : ""}`} aria-label="前后观点证据">
          <div className="activity-inspector-panel" key={selected.id}>
            <header className="activity-inspector-head">
              <div><span>前后观点</span><h2>{selected.symbol} · {EVENT[selected.kind]}</h2><p>{selected.current.author_name} · {HORIZON[selected.horizon] || "期限未明"}</p></div>
              <button type="button" aria-label="关闭原文对照面板" onClick={() => setAnalysisOpen(false)}>×</button>
            </header>
            <div className="activity-inspector-body opinion-inspector-body">
              {selected.new_factors.length > 0 && (
                <section className="opinion-new-factors"><h3>本次原文新增的依据</h3><ul>{selected.new_factors.map((factor) => <li key={factor}>{factor}</li>)}</ul></section>
              )}
              <SourceEvidence label="本次" source={selected.current} />
              {selected.previous ? <SourceEvidence label="前一次" source={selected.previous} /> : (
                <p className="opinion-history-note">过去 {data.comparison_days} 天没有找到此作者对该标的的有效观点记录。</p>
              )}
            </div>
            <footer className="activity-inspector-footer">
              <Link href={`/sources/${encodeURIComponent(selected.current.author_handle)}`}>查看博主页</Link>
            </footer>
          </div>
        </aside>
      </div>
    </>
  );
}
