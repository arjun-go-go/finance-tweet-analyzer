"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { formatDateTime } from "@/lib/datetime";
import AnalysisInline, {
  groupInstrumentClaims,
  isAuthorStanceClaim,
  isPerformanceEligibleClaim,
  performanceExclusionLabel,
  type AnalysisData,
  type InstrumentClaimData,
  type InstrumentClaimGroup,
  type MarketViewData,
} from "./AnalysisInline";
import TweetMediaGallery, { type TweetMediaItem } from "./TweetMediaGallery";

interface TweetMetrics {
  likes?: number;
  like_count?: number;
  retweets?: number;
  retweet_count?: number;
  views?: number;
  view_count?: number;
}

export interface ActivityTweet {
  id: string;
  tweet_id: string;
  author_handle: string;
  author_name: string;
  content: string;
  published_at: string;
  status: string;
  metrics?: TweetMetrics | null;
  analysis?: AnalysisData | null;
  media?: TweetMediaItem[];
  tweet_type?: string;
  referenced_tweets?: Array<{
    type?: string;
    tweet_id?: string;
    author_handle?: string;
    author_name?: string;
    content?: string;
    published_at?: string;
    media_urls?: Array<{
      id?: string;
      width?: number | null;
      height?: number | null;
      content_type?: string | null;
      media_url?: string;
    }>;
  }>;
}

const DIRECTION_LABEL: Record<string, string> = {
  bullish: "看多",
  bearish: "看空",
  neutral: "中性",
  none: "相关信息",
};

const HORIZON_LABEL: Record<string, string> = {
  short: "短期",
  medium: "中期",
  long: "长期",
  unknown: "",
};

const MARKET_LABEL: Record<string, string> = {
  CN: "A股",
  HK: "港股",
  US: "美股",
  COMMODITY: "商品",
  CRYPTO: "加密货币",
  GLOBAL: "全球市场",
  unknown: "市场待核验",
};

const IMPACT_LABEL: Record<string, string> = {
  positive: "利多",
  negative: "利空",
  mixed: "影响复杂",
  unclear: "影响待观察",
};

const TOPIC_LABEL: Record<string, string> = {
  rates: "利率",
  inflation: "通胀",
  liquidity: "流动性",
  policy: "政策",
  growth: "经济增长",
  geopolitics: "地缘政治",
  earnings: "盈利周期",
  supply_demand: "供需",
  regulation: "监管",
  other: "市场",
};

const RELATION_LABEL: Record<string, string> = {
  reply: "回复",
  quote: "引用推文",
  quoted: "引用推文",
  retweet: "转发",
  repost: "转发",
};

function primaryClaim(group: InstrumentClaimGroup) {
  return group.claims.find(isPerformanceEligibleClaim)
    || group.authorStances[0]
    || group.quotedStances[0]
    || group.risks[0]
    || group.facts[0]
    || group.claims[0];
}

function stanceLabel(group: InstrumentClaimGroup) {
  const stances = group.claims.filter(isPerformanceEligibleClaim);
  if (!stances.length) return performanceExclusionLabel(primaryClaim(group));
  const signatures = new Set(stances.map((claim) => `${claim.horizon}:${claim.direction}`));
  if (signatures.size > 1) return "多周期观点";
  const claim = stances[0];
  return `${HORIZON_LABEL[claim.horizon] || ""}${DIRECTION_LABEL[claim.direction] || "相关信息"}`;
}

function claimSubset(group: InstrumentClaimGroup, claims: InstrumentClaimData[]): InstrumentClaimGroup {
  return groupInstrumentClaims(claims)[0] || { ...group, claims };
}

function sourceLabel(source: string) {
  if (source === "author") return "博主判断";
  if (source === "quoted") return "引用判断";
  if (source === "third_party") return "第三方判断";
  return "归属待确认";
}

function ClaimRow({ group, referenceOnly = false }: { group: InstrumentClaimGroup; referenceOnly?: boolean }) {
  const claim = primaryClaim(group);
  const market = group.instrument.market || group.instrument.market_hint || "unknown";
  const direction = group.claims.find(isPerformanceEligibleClaim)?.direction || "none";
  const explanation = claim?.thesis || claim?.evidence?.[0] || "原文提到了该标的，但没有形成明确方向判断。";
  const referenceLabel = [...new Set(group.claims.map(performanceExclusionLabel))]
    .filter(Boolean)
    .join(" · ");
  const targetHref = group.claims.some((item) => item.instrument.validation_status === "verified")
    ? `/watch/${encodeURIComponent(group.symbol)}`
    : null;

  return (
    <article className={`activity-signal-row is-${direction}`}>
      <div className="activity-signal-identity">
        {targetHref
          ? <Link href={targetHref}><strong>{group.symbol}</strong></Link>
          : <strong>{group.symbol}</strong>}
        <span>{group.instrument.original_name || MARKET_LABEL[market] || market}</span>
      </div>
      <div className="activity-signal-copy">
        <div>
          <b>{referenceOnly ? referenceLabel || "仅供参考" : stanceLabel(group)}</b>
          <span>{referenceOnly ? `${MARKET_LABEL[market] || market} · 不参与多空统计` : MARKET_LABEL[market] || market}</span>
        </div>
        <p>{explanation}</p>
      </div>
    </article>
  );
}

function MarketViewRow({ view }: { view: MarketViewData }) {
  return (
    <article className={`activity-market-row is-${view.impact}`}>
      <div>
        <span>{MARKET_LABEL[view.market] || view.market}</span>
        {view.benchmark && <strong>{view.benchmark}</strong>}
      </div>
      <div>
        <p><b>{IMPACT_LABEL[view.impact] || "影响待观察"}</b><span>{TOPIC_LABEL[view.topic] || "市场"} · {sourceLabel(view.opinion_source)}</span></p>
        <strong>{view.thesis || "原文包含市场信息，但未给出明确影响判断。"}</strong>
      </div>
    </article>
  );
}

export default function ActivityTweetCard({ tweet }: { tweet: ActivityTweet }) {
  const [expanded, setExpanded] = useState(false);
  const [showEvidence, setShowEvidence] = useState(false);
  const analysis = tweet.analysis;
  const claims = useMemo(() => analysis?.claims || [], [analysis?.claims]);
  const groups = useMemo(() => groupInstrumentClaims(claims), [claims]);
  const effectiveGroups = useMemo(
    () => groups
      .map((group) => claimSubset(group, group.claims.filter(isPerformanceEligibleClaim)))
      .filter((group) => group.claims.length > 0),
    [groups],
  );
  const referenceGroups = useMemo(
    () => groups
      .map((group) => claimSubset(group, group.claims.filter((claim) => !isPerformanceEligibleClaim(claim))))
      .filter((group) => group.claims.length > 0),
    [groups],
  );
  const effectiveClaimCount = effectiveGroups.reduce((total, group) => total + group.claims.length, 0);
  const referenceClaimCount = referenceGroups.reduce((total, group) => total + group.claims.length, 0);
  const marketViews = analysis?.market_views || [];
  const isProcessing = ["pending", "analyzing", "retrying"].includes(tweet.status);
  const isFailed = tweet.status === "failed";
  const hasAnalysis = groups.length > 0 || marketViews.length > 0;
  const hasEvidence = Boolean(
    analysis && (
    analysis.tweet_summary
    || claims.length > 0
    || groups.some((group) => group.claims.some((claim) => claim.evidence?.length || claim.risk_factors?.length))
    || marketViews.some((view) => view.evidence?.length)),
  );
  const references = tweet.referenced_tweets || [];
  const hasExplicitAuthorView = claims.some(isAuthorStanceClaim);
  const handle = tweet.author_handle.replace(/^@/, "");
  const metrics = tweet.metrics || {};
  const likes = metrics.likes ?? metrics.like_count;
  const reposts = metrics.retweets ?? metrics.retweet_count;
  const views = metrics.views ?? metrics.view_count;

  return (
    <article className="activity-card">
      <header className="activity-card-author">
        <Link href={`/sources/${encodeURIComponent(handle)}`}>
          <strong>{tweet.author_name || `@${handle}`}</strong>
          <span>@{handle}</span>
        </Link>
        <div>
          {tweet.tweet_type && tweet.tweet_type !== "original" && <span>{RELATION_LABEL[tweet.tweet_type] || tweet.tweet_type}</span>}
          <time dateTime={tweet.published_at}>{formatDateTime(tweet.published_at)}</time>
        </div>
      </header>

      <p className={`activity-card-content ${expanded ? "is-expanded" : ""}`}>{tweet.content}</p>
      {tweet.content.length > 240 && (
        <button className="activity-text-button" type="button" onClick={() => setExpanded((value) => !value)}>
          {expanded ? "收起" : "展开原文"}
        </button>
      )}

      <TweetMediaGallery tweetId={tweet.id} media={tweet.media || []} />

      {references.map((reference, index) => {
        const referenceHandle = (reference.author_handle || "").replace(/^@/, "");
        return (
          <blockquote className="activity-reference" key={reference.tweet_id || `${referenceHandle}-${index}`}>
            <header>
              <div><strong>{reference.author_name || (referenceHandle ? `@${referenceHandle}` : "引用内容")}</strong>{referenceHandle && <span>@{referenceHandle}</span>}</div>
              <span>{RELATION_LABEL[reference.type || ""] || "引用内容"}{reference.published_at ? ` · ${formatDateTime(reference.published_at)}` : ""}</span>
            </header>
            <p>{reference.content || "引用原文暂不可用"}</p>
            <small className="activity-reference-attribution">{hasExplicitAuthorView ? "当前博主另有明确观点，以下方逐标的分析为准" : "仅作引用，未识别到当前博主明确认同"}</small>
            {reference.media_urls?.length ? <TweetMediaGallery tweetId={tweet.id} media={reference.media_urls.filter((item) => item.id).map((item) => ({ id: item.id as string, width: item.width, height: item.height, content_type: item.content_type }))} /> : null}
            {reference.tweet_id && referenceHandle && <a href={`https://x.com/${referenceHandle}/status/${reference.tweet_id}`} target="_blank" rel="noreferrer">查看引用原文</a>}
          </blockquote>
        );
      })}

      <section className="activity-analysis" aria-label="推文分析">
        {effectiveGroups.length > 0 && (
          <div className="activity-analysis-section">
            <div className="activity-analysis-label"><span>有效观点</span><small>{effectiveClaimCount} 项计入统计</small></div>
            <div className="activity-signal-list">{effectiveGroups.map((group) => <ClaimRow key={group.symbol} group={group} />)}</div>
          </div>
        )}

        {referenceGroups.length > 0 && (
          <div className="activity-analysis-section">
            <div className="activity-analysis-label"><span>相关标的 · 仅供参考</span><small>{referenceClaimCount} 项不参与统计</small></div>
            <div className="activity-signal-list">{referenceGroups.map((group) => <ClaimRow key={group.symbol} group={group} referenceOnly />)}</div>
          </div>
        )}

        {marketViews.length > 0 && (
          <div className="activity-analysis-section">
            <div className="activity-analysis-label"><span>{groups.length ? "市场背景" : "市场判断"}</span><small>{marketViews.length} 项</small></div>
            <div className="activity-market-list">{marketViews.map((view, index) => <MarketViewRow key={`${view.market}-${view.topic}-${index}`} view={view} />)}</div>
          </div>
        )}

        {!hasAnalysis && (
          <p className="activity-analysis-empty">
            {isProcessing
              ? "正在分析这条推文"
              : isFailed
                ? "分析暂未完成"
                : "未识别到明确投资标的或可判断的市场影响"}
          </p>
        )}

        {analysis?.is_sponsored && <p className="activity-sponsored">
          含平台推广。系统按每项观点的商业关联分别处理：直接相关或关系待确认的内容仅供参考；无直接关联的作者观点可参与共识，满足预测契约后才计入成绩。
        </p>}

        {hasEvidence && (
          <>
            <button className="activity-evidence-toggle" type="button" onClick={() => setShowEvidence((value) => !value)}>
              {showEvidence ? "收起完整分析" : "查看完整分析"}
            </button>
            {showEvidence && (
              <div className="activity-full-analysis">
                {analysis && <AnalysisInline analysis={analysis} />}
              </div>
            )}
          </>
        )}
      </section>

      <footer className="activity-card-footer">
        <div>
          {likes != null && <span>赞 {likes}</span>}
          {reposts != null && <span>转发 {reposts}</span>}
          {views != null && <span>浏览 {views}</span>}
        </div>
        <a href={`https://x.com/${handle}/status/${tweet.tweet_id}`} target="_blank" rel="noreferrer">查看原推文</a>
      </footer>
    </article>
  );
}
