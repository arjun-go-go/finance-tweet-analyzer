"use client";

import { FormEvent, use, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import AppIcon from "@/components/AppIcon";
import { PageError, PageLoading } from "@/components/PageState";
import TweetMediaGallery from "@/components/TweetMediaGallery";
import {
  fetchIntelligenceDetail,
  submitIntelligenceCorrection,
  type IntelligenceCorrectionCategory,
  type IntelligenceDetailResponse,
} from "@/lib/api";

type JsonRecord = Record<string, unknown>;

const DIRECTION_LABELS: Record<string, string> = {
  bullish: "看多",
  bearish: "看空",
  neutral: "中性",
  none: "无方向",
  mixed: "分歧",
};

const HORIZON_LABELS: Record<string, string> = {
  short: "短期",
  medium: "中期",
  long: "长期",
  unknown: "周期未说明",
};

const OPINION_SOURCE_LABELS: Record<string, string> = {
  author: "博主本人观点",
  quoted: "引用内容",
  third_party: "第三方信息",
  unclear: "观点归属待确认",
};

const KIND_LABELS: Record<string, string> = {
  opinion: "博主观点",
  risk: "风险线索",
  news: "市场动态",
};

const RELATIONSHIP_LABELS: Record<string, string> = {
  primary: "当前原文",
  parent: "上文",
  quoted: "引用推文",
  reposted: "转推来源",
  reply: "回复",
  supporting: "独立佐证",
  thread: "Thread 上下文",
};

const CORRECTION_OPTIONS: Array<{ value: IntelligenceCorrectionCategory; label: string }> = [
  { value: "author_attribution", label: "观点归属" },
  { value: "instrument", label: "标的身份" },
  { value: "direction", label: "方向判断" },
  { value: "context", label: "上下文" },
  { value: "image", label: "图片识别" },
  { value: "other", label: "其他" },
];

function text(value: unknown, fallback = "—") {
  return typeof value === "string" && value.trim() ? value : fallback;
}

function strings(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value
      .map((item) => typeof item === "string" ? item : null)
      .filter((item): item is string => Boolean(item));
  }
  return typeof value === "string" && value.trim() ? [value] : [];
}

function record(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as JsonRecord
    : {};
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function verdictLabel(value: unknown) {
  const verdict = text(value, "tracking");
  return ({ correct: "已命中", incorrect: "未命中", excluded: "已排除", tracking: "跟踪中" } as Record<string, string>)[verdict] || "跟踪中";
}

function validationStatusLabel(value: string) {
  return ({
    verified: "已核验",
    ambiguous: "待复核",
    manual_review: "待复核",
    invalid: "无效标的",
    unverified: "未验证",
  } as Record<string, string>)[value] || "未验证";
}

export default function IntelligenceDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [detail, setDetail] = useState<IntelligenceDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showCorrection, setShowCorrection] = useState(false);
  const [category, setCategory] = useState<IntelligenceCorrectionCategory>("instrument");
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [correctionError, setCorrectionError] = useState("");
  const [submitted, setSubmitted] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    fetchIntelligenceDetail(id)
      .then((data) => { if (active) setDetail(data); })
      .catch((loadError) => {
        if (active) setError(loadError instanceof Error ? loadError.message : "情报详情加载失败");
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [id]);

  const instruments = useMemo(() => {
    if (!detail) return [];
    const unique = new Map<string, JsonRecord>();
    detail.instruments.forEach((item) => {
      const symbol = text(item.symbol, "未知标的");
      if (!unique.has(symbol)) unique.set(symbol, item);
    });
    return [...unique.values()];
  }, [detail]);

  const submitCorrection = async (event: FormEvent) => {
    event.preventDefault();
    if (note.trim().length < 2) return;
    setSubmitting(true);
    setCorrectionError("");
    try {
      await submitIntelligenceCorrection(id, { category, note: note.trim() });
      setSubmitted(true);
    } catch (submitError) {
      setCorrectionError(submitError instanceof Error ? submitError.message : "反馈提交失败");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) return <PageLoading label="正在还原完整证据链" />;
  if (error || !detail) return <PageError detail={error || "没有找到这条情报。"} />;

  const { item, tweet } = detail;
  const claim = record(detail.claim);
  const primaryMedia = detail.media
    .filter((media) => media.tweet_id === tweet.id && media.status === "downloaded")
    .map(({ id: mediaId, width, height, content_type }) => ({ id: mediaId, width, height, content_type }));
  const thread = detail.thread.filter((entry) => entry.id !== tweet.id);
  const catalysts = [...new Set([
    ...strings(claim.catalysts),
    ...strings(claim.entry_conditions),
  ])];
  const invalidations = [...new Set([
    ...strings(claim.invalidation_conditions),
    ...strings(claim.risk_factors),
  ])];
  const claimEvidence = [...new Set([
    ...strings(claim.evidence),
    ...strings(claim.media_evidence),
  ])];
  const showDirection = item.kind === "opinion"
    && ["bullish", "bearish", "neutral"].includes(item.direction);
  const thesisLabel = item.kind === "risk"
    ? "风险线索"
    : item.kind === "news"
      ? "事实摘要"
      : "核心观点";

  return (
    <div className="product-page insight-detail-page">
      <Link href="/" className="insight-back"><AppIcon name="arrow" />返回今天</Link>

      <div className="insight-detail-layout">
        <main className="insight-detail-main">
          <header className="insight-hero">
            <div className="insight-hero-meta">
              {showDirection && <span className={`direction-${item.direction}`}>{DIRECTION_LABELS[item.direction] || "未明确方向"}</span>}
              <span>{KIND_LABELS[item.kind] || "投资观点"}</span>
              <span>{formatDate(item.published_at)}</span>
            </div>
            <h1>{item.title}</h1>
            <p>{item.summary}</p>
            <div className="insight-origin">
              <span>{tweet.author_handle.slice(0, 2).toUpperCase()}</span>
              <div><strong>{tweet.author_name || `@${tweet.author_handle}`}</strong><small>@{tweet.author_handle} · {OPINION_SOURCE_LABELS[text(claim.opinion_source, "unclear")] || "观点归属待确认"}</small></div>
              <a href={tweet.source_url} target="_blank" rel="noreferrer">查看 Twitter <AppIcon name="external" /></a>
            </div>
          </header>

          <section className="insight-thesis">
            <span>{thesisLabel}</span>
            <p>{text(claim.thesis, item.summary)}</p>
            <small>{showDirection ? `${DIRECTION_LABELS[text(claim.direction, item.direction)] || "未明确方向"} · ` : ""}{HORIZON_LABELS[text(claim.horizon, item.horizon)] || "周期未说明"}</small>
          </section>

          {claimEvidence.length > 0 && (
            <section className="insight-section">
              <header><div><span>Claim evidence</span><h2>这项观点的直接证据</h2></div><small>{claimEvidence.length} 条</small></header>
              <ul>{claimEvidence.map((value) => <li key={value}>{value}</li>)}</ul>
            </section>
          )}

          {(catalysts.length > 0 || invalidations.length > 0) && (
            <section className="insight-section">
              <header><div><span>Decision boundary</span><h2>什么会强化或推翻判断</h2></div><small>不是无条件推荐</small></header>
              <div className="insight-boundaries">
                <div><strong>可能强化判断</strong>{catalysts.length ? <ul>{catalysts.map((value) => <li key={value}>{value}</li>)}</ul> : <p>当前分析没有给出明确强化条件。</p>}</div>
                <div className="is-risk"><strong>可能使判断失效</strong>{invalidations.length ? <ul>{invalidations.map((value) => <li key={value}>{value}</li>)}</ul> : <p>当前分析没有给出明确失效条件。</p>}</div>
              </div>
            </section>
          )}

          <section className="insight-section">
            <header><div><span>Original evidence</span><h2>原推文与图片</h2></div><small>完整上下文</small></header>
            <article className="insight-tweet">
              <div className="insight-tweet-head"><span>{tweet.author_handle.slice(0, 2).toUpperCase()}</span><div><strong>@{tweet.author_handle}</strong><small>{RELATIONSHIP_LABELS[tweet.relationship] || "原推文"}</small></div><time>{formatDate(tweet.published_at)}</time></div>
              <p>{tweet.content}</p>
              <TweetMediaGallery tweetId={tweet.id} media={primaryMedia} />
            </article>
            {detail.media.length > 0 && (
              <div className="insight-media-analysis">
                {detail.media.map((media, index) => {
                  const mediaAnalysis = record(media.analysis);
                  return (
                    <article key={media.id} className={media.status !== "downloaded" ? "is-failed" : ""}>
                      <span>图片 {index + 1}</span>
                      <strong>{media.status === "downloaded" ? text(mediaAnalysis.summary, "图片已归档，暂无单图摘要") : "图片归档失败"}</strong>
                      {strings(mediaAnalysis.visual_evidence).length > 0 && <p>{strings(mediaAnalysis.visual_evidence).join("；")}</p>}
                      {text(mediaAnalysis.ocr_text, "") && <blockquote>{text(mediaAnalysis.ocr_text, "")}</blockquote>}
                      <small>{media.analysis_status === "completed" ? "视觉识别完成" : media.error_detail || "等待视觉识别"}</small>
                    </article>
                  );
                })}
              </div>
            )}
          </section>

          {(thread.length > 0 || tweet.referenced_tweets.length > 0) && (
            <section className="insight-section">
              <header><div><span>Conversation context</span><h2>Thread 与引用关系</h2></div><small>区分本人判断与转述</small></header>
              <div className="insight-thread">
                {thread.map((entry) => (
                  <article key={entry.id}><span>{RELATIONSHIP_LABELS[entry.relationship] || "上下文"}</span><div><strong>@{entry.author_handle}</strong><p>{entry.content}</p><small>{formatDate(entry.published_at)}</small></div></article>
                ))}
                {tweet.referenced_tweets.map((reference, index) => (
                  <article key={`${text(reference.tweet_id, "reference")}-${index}`}><span>{RELATIONSHIP_LABELS[text(reference.type, "thread")] || "引用内容"}</span><div><strong>@{text(reference.author_handle, "未知来源")}</strong><p>{text(reference.content, "引用内容未完整采集")}</p><small>{text(reference.published_at, "")}</small></div></article>
                ))}
              </div>
            </section>
          )}

          {instruments.length > 0 && (
            <section className="insight-section">
              <header><div><span>Instrument identity</span><h2>标的身份核验</h2></div><small>{instruments.length} 个标的</small></header>
              <div className="insight-instruments">
                {instruments.map((instrument) => {
                  const symbol = text(instrument.symbol, "未知标的");
                  const validationStatus = text(instrument.validation_status, "unverified");
                  return (
                    <article key={symbol}>
                      <div><strong>{symbol}</strong><span>{text(instrument.resolved_name, text(instrument.original_name, "待确认"))}</span></div>
                      <b className={`is-${validationStatus}`}>{validationStatusLabel(validationStatus)}</b>
                      <dl><div><dt>市场</dt><dd>{text(instrument.market, text(instrument.market_hint, "—"))}</dd></div><div><dt>资产类型</dt><dd>{text(instrument.asset_type)}</dd></div><div><dt>上市状态</dt><dd>{text(instrument.listing_status)}</dd></div></dl>
                      <p>{text(instrument.validation_reason, text(instrument.evidence, "系统未提供核验说明"))}</p>
                    </article>
                  );
                })}
              </div>
            </section>
          )}

          {detail.predictions.length > 0 && (
            <section className="insight-section">
              <header><div><span>Prediction audit</span><h2>预测与行情验证</h2></div><small>{detail.predictions.length} 条记录</small></header>
              <div className="insight-predictions">
                {detail.predictions.map((prediction) => {
                  const verification = record(prediction.market_verification);
                  const target = record(prediction.target_spec);
                  return (
                    <article key={text(prediction.id)}>
                      <strong>{text(prediction.ticker)}</strong>
                      <div><span>{text(prediction.prediction_type, "price_direction")} · {DIRECTION_LABELS[text(prediction.sentiment)] || text(prediction.sentiment)}</span><small>{text(target.target_value, text(target.target_metric, ""))}{target.target_unit ? ` ${text(target.target_unit)}` : ""} · 时间依据 {text(prediction.temporal_expression, text(prediction.horizon_source, "未说明"))} · {prediction.verifiable_at ? `验证时间 ${formatDate(String(prediction.verifiable_at))}` : "等待专用验证器"}</small></div>
                      <b className={`is-${text(prediction.verdict, "tracking")}`}>{verdictLabel(prediction.verdict)}</b>
                      {Object.keys(verification).length > 0 && <p>{text(verification.provider, "行情源")} · {text(verification.reason, "行情验证记录已保存")}</p>}
                    </article>
                  );
                })}
              </div>
            </section>
          )}

          <section className="insight-section insight-audit">
            <header><div><span>Analysis audit</span><h2>分析与版本记录</h2></div><small>结果可追溯</small></header>
            {detail.audit.map((audit) => (
              <div key={text(audit.event_id)}><span>分析模型<strong>{text(audit.model_used)}</strong></span><span>流水线<strong>{text(audit.pipeline_version)}</strong></span><span>情报投影<strong>{text(audit.projection_version)}</strong></span><span>生成时间<strong>{audit.projected_at ? formatDate(String(audit.projected_at)) : "—"}</strong></span></div>
            ))}
          </section>
        </main>

        <aside className="insight-detail-aside">
          <section><span>跟踪对象</span><h2>{item.tickers[0] || "市场"}</h2><p>{HORIZON_LABELS[item.horizon] || "周期未说明"}</p><dl><div><dt>方向</dt><dd>{DIRECTION_LABELS[item.direction] || "无方向"}</dd></div><div><dt>置信度</dt><dd>{Math.round(item.confidence * 100)}%</dd></div><div><dt>独立来源</dt><dd>{item.corroboration_count}</dd></div><div><dt>重要性</dt><dd>{item.importance_score}</dd></div></dl></section>
          <section><span>使用说明</span><strong>这是观点证据，不是交易指令</strong><p>结论来自已采集推文与图片，并会随新证据和行情验证继续更新。</p></section>
          <div><button className="button-secondary" onClick={() => { setShowCorrection(true); setSubmitted(false); setCorrectionError(""); }}>哪里识别有误？</button></div>
        </aside>
      </div>

      {showCorrection && (
        <div className="insight-correction-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget && !submitting) setShowCorrection(false); }}>
          <form className="insight-correction-dialog" onSubmit={submitCorrection}>
            <header><div><p className="page-eyebrow">Improve recognition</p><h2>哪里识别有误？</h2><span>反馈会进入复核记录，不会直接改写现有结论。</span></div><button type="button" onClick={() => setShowCorrection(false)}><AppIcon name="close" /></button></header>
            {submitted ? <div className="insight-correction-success"><b>✓</b><h3>反馈已记录</h3><p>管理员复核前，当前情报和原始证据不会被修改。</p><button type="button" className="button-primary" onClick={() => setShowCorrection(false)}>完成</button></div> : <>
              <div className="insight-correction-options">{CORRECTION_OPTIONS.map((option) => <button type="button" key={option.value} className={category === option.value ? "is-active" : ""} onClick={() => setCategory(option.value)}>{option.label}</button>)}</div>
              <label><span>补充说明</span><textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder="请指出具体哪里不准确，以及正确内容是什么。" rows={5} /></label>
              {correctionError && <p className="source-onboard-error">{correctionError}</p>}
              <footer><button type="button" className="button-secondary" onClick={() => setShowCorrection(false)}>取消</button><button className="button-primary" disabled={submitting || note.trim().length < 2}>{submitting ? "正在提交…" : "提交复核"}</button></footer>
            </>}
          </form>
        </div>
      )}
    </div>
  );
}
