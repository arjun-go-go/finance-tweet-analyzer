"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { formatDateTime } from "@/lib/datetime";
import AppIcon from "./AppIcon";
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
  author_avatar_url?: string | null;
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

const CLAIM_TYPE_LABEL: Record<string, string> = {
  recommendation: "操作建议",
  prediction: "可验证预测",
  opinion: "作者观点",
  risk_warning: "风险提示",
  fact: "事实信息",
  news: "新闻信息",
  recap: "历史复盘",
  reference: "仅提及",
};

const FORECAST_TYPE_LABEL: Record<string, string> = {
  price_direction: "价格方向",
  price_target: "目标价格",
  fundamental_metric: "基本面指标",
  event_outcome: "事件结果",
};

const FORECAST_SOURCE_LABEL: Record<string, string> = {
  author: "博主本人",
  quoted: "引用账号",
  third_party: "第三方",
  market_consensus: "市场一致预期",
  company_guidance: "公司 / 管理层指引",
  unclear: "来源待确认",
};

const RISK_LEVEL_LABEL: Record<string, string> = {
  low: "低",
  medium: "中",
  high: "高",
  critical: "极高",
};

const TARGET_OPERATOR_LABEL: Record<string, string> = {
  up: "上涨",
  down: "下跌",
  gte: "不低于",
  lte: "不高于",
  equals: "达到",
  range: "位于区间",
  occurs: "发生",
  not_occurs: "不发生",
  unknown: "未说明",
};

const SPONSOR_RELATION_LABEL: Record<string, string> = {
  none: "无商业内容",
  unrelated: "与推广方无直接关联",
  direct: "与推广方直接相关",
  unclear: "商业关系待确认",
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

function isVerifiedInstrument(instrument: InstrumentClaimData["instrument"]) {
  if (instrument.verification) {
    return instrument.verification.status === "verified"
      && instrument.verification.downstream_eligible === true;
  }
  return instrument.validation_status === "verified" && instrument.tradable === true;
}

function compactReferenceLabel(claim: InstrumentClaimData) {
  if (!isVerifiedInstrument(claim.instrument)) return "身份待确认";
  if (claim.sponsor_relation === "direct") return "商业相关";
  if (claim.sponsor_relation === "unclear") return "商业关系待确认";
  if (claim.opinion_source === "quoted") return "引用观点";
  if (claim.opinion_source === "third_party") return "第三方观点";
  if (claim.opinion_source === "unclear") return "归属待确认";
  if (claim.claim_type === "risk_warning") return "风险提示";
  if (["fact", "news", "recap", "reference"].includes(claim.claim_type)) return "仅提及";
  return claim.direction === "none" ? "无明确方向" : "仅供参考";
}

function formatPriceTarget(target: Record<string, unknown>) {
  const targetType: Record<string, string> = {
    entry: "入场",
    target: "目标",
    stop: "止损",
    support: "支撑",
    resistance: "阻力",
    other: "价格",
  };
  const type = targetType[String(target.target_type || "other")] || "价格";
  const value = [target.value, target.currency].filter(Boolean).join(" ");
  return [type, value, target.condition].filter(Boolean).join("：");
}

interface SubjectBadge {
  key: string;
  subject: string;
  detail: string;
  tone: string;
  title: string;
  href?: string;
}

function ActivitySubjectStrip({ groups, marketViews }: { groups: InstrumentClaimGroup[]; marketViews: MarketViewData[] }) {
  const badges: SubjectBadge[] = [];
  const seen = new Set<string>();
  const addBadge = (badge: SubjectBadge) => {
    if (seen.has(badge.key)) return;
    seen.add(badge.key);
    badges.push(badge);
  };

  groups.forEach((group) => {
    const href = group.claims.some((claim) => isVerifiedInstrument(claim.instrument))
      ? `/watch/${encodeURIComponent(group.symbol)}`
      : undefined;
    const authorStances = group.authorStances;
    const quotedStances = group.quotedStances;

    if (authorStances.length) {
      authorStances.forEach((claim) => {
        const direction = DIRECTION_LABEL[claim.direction] || "相关信息";
        const horizon = HORIZON_LABEL[claim.horizon] || "";
        const eligible = isPerformanceEligibleClaim(claim);
        const suffix = eligible ? "" : ` · ${compactReferenceLabel(claim)}`;
        addBadge({
          key: `instrument:${group.symbol}:author:${claim.horizon}:${claim.direction}:${suffix}`,
          subject: group.symbol,
          detail: `${horizon}${direction}${suffix}`,
          tone: eligible ? claim.direction : "reference",
          title: eligible ? "博主本人有效观点" : performanceExclusionLabel(claim),
          href,
        });
      });
      return;
    }

    if (quotedStances.length) {
      quotedStances.forEach((claim) => {
        const direction = DIRECTION_LABEL[claim.direction] || "相关信息";
        const horizon = HORIZON_LABEL[claim.horizon] || "";
        addBadge({
          key: `instrument:${group.symbol}:${claim.opinion_source}:${claim.horizon}:${claim.direction}`,
          subject: group.symbol,
          detail: `${claim.opinion_source === "quoted" ? "引用" : "第三方"}${horizon}${direction}`,
          tone: "reference",
          title: performanceExclusionLabel(claim),
          href,
        });
      });
      return;
    }

    const claim = primaryClaim(group);
    if (!claim) return;
    addBadge({
      key: `instrument:${group.symbol}:mention`,
      subject: group.symbol,
      detail: compactReferenceLabel(claim),
      tone: "none",
      title: performanceExclusionLabel(claim),
      href,
    });
  });

  marketViews.forEach((view) => {
    const subject = view.benchmark || MARKET_LABEL[view.market] || view.market;
    const sourcePrefix = view.opinion_source === "author"
      ? ""
      : view.opinion_source === "quoted"
        ? "引用"
        : view.opinion_source === "third_party"
          ? "第三方"
          : "归属待确认 · ";
    const impact = IMPACT_LABEL[view.impact] || "影响待观察";
    addBadge({
      key: `market:${subject}:${view.impact}:${view.horizon}:${view.opinion_source}`,
      subject,
      detail: `${sourcePrefix}${impact}`,
      tone: view.opinion_source === "author" ? `market-${view.impact}` : "reference",
      title: `${TOPIC_LABEL[view.topic] || "市场"} · ${sourceLabel(view.opinion_source)}`,
    });
  });

  if (!badges.length) return null;
  return (
    <div className="activity-subject-strip" aria-label="推文提取的投资标的与市场判断">
      {badges.map((badge) => {
        const content = <><b>{badge.subject}</b><span>{badge.detail}</span></>;
        const className = `activity-subject-chip is-${badge.tone}`;
        return badge.href
          ? <Link className={className} href={badge.href} key={badge.key} title={badge.title}>{content}</Link>
          : <span className={className} key={badge.key} title={badge.title}>{content}</span>;
      })}
    </div>
  );
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

function PanelClaim({ claim, referenceOnly }: { claim: InstrumentClaimData; referenceOnly: boolean }) {
  const direction = DIRECTION_LABEL[claim.direction] || "相关信息";
  const evidence = [...new Set([...(claim.evidence || []), ...(claim.media_evidence || [])])];
  const risks = claim.risk_factors || [];
  const invalidations = claim.invalidation_conditions || [];
  const forecast = claim.forecast;
  const hasForecast = Boolean(forecast?.prediction_type && forecast.prediction_type !== "none");
  const forecastTarget = [forecast?.target_value, forecast?.target_unit].filter(Boolean).join(" ");

  return (
    <article className={`activity-inspector-claim is-${claim.direction || "none"}`}>
      <div className="activity-inspector-claim-meta">
        <span className="activity-inspector-direction">{referenceOnly ? performanceExclusionLabel(claim) : direction}</span>
        <span>{HORIZON_LABEL[claim.horizon] || "周期未说明"}</span>
        <span>{CLAIM_TYPE_LABEL[claim.claim_type] || claim.claim_type}</span>
        <span>{sourceLabel(claim.opinion_source)}</span>
      </div>
      <p>{claim.thesis || evidence[0] || "原文提到了该标的，但没有形成明确方向判断。"}</p>
      {evidence.length > 0 && (
        <div className="activity-inspector-evidence">
          <b>判断依据</b>
          <ul>{evidence.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul>
        </div>
      )}
      {(claim.catalysts?.length || risks.length || invalidations.length || claim.entry_conditions?.length) ? (
        <div className="activity-inspector-factors">
          {claim.catalysts?.length ? <div className="is-catalyst"><b>催化条件</b><span>{claim.catalysts.join("；")}</span></div> : null}
          {risks.length ? <div className="is-risk"><b>风险因素</b><span>{risks.join("；")}</span></div> : null}
          {claim.entry_conditions?.length ? <div className="is-entry"><b>入场条件</b><span>{claim.entry_conditions.join("；")}</span></div> : null}
          {invalidations.length ? <div className="is-invalidation"><b>失效条件</b><span>{invalidations.join("；")}</span></div> : null}
        </div>
      ) : null}
      {claim.risk_details?.length ? (
        <div className="activity-inspector-risk-details">
          <b>风险明细{claim.risk_level ? ` · ${RISK_LEVEL_LABEL[claim.risk_level] || claim.risk_level}风险` : ""}</b>
          <ul>{claim.risk_details.map((risk, index) => (
            <li key={`${risk.description || risk.category}-${index}`}>
              {risk.description || risk.category || "风险信息"}
              {(risk.severity || risk.urgency) && <span>{[risk.severity, risk.urgency].filter(Boolean).join(" / ")}</span>}
            </li>
          ))}</ul>
        </div>
      ) : null}
      {(hasForecast || claim.price_targets?.length) ? (
        <div className="activity-inspector-forecast">
          <b>预测与价格条件</b>
          {hasForecast && <dl>
            <div><dt>预测类型</dt><dd>{FORECAST_TYPE_LABEL[forecast?.prediction_type || ""] || forecast?.prediction_type}</dd></div>
            <div><dt>预测来源</dt><dd>{forecast?.source_name || FORECAST_SOURCE_LABEL[forecast?.forecast_source || "unclear"]}</dd></div>
            {forecast?.temporal_expression && <div><dt>时间依据</dt><dd>{forecast.temporal_expression}</dd></div>}
            {forecast?.target_metric && <div><dt>目标指标</dt><dd>{forecast.target_metric}</dd></div>}
            {forecast?.target_operator && forecast.target_operator !== "unknown" && <div><dt>目标关系</dt><dd>{TARGET_OPERATOR_LABEL[forecast.target_operator] || forecast.target_operator}</dd></div>}
            {forecastTarget && <div><dt>目标值</dt><dd>{forecastTarget}</dd></div>}
            {forecast?.target_condition && <div><dt>成立条件</dt><dd>{forecast.target_condition}</dd></div>}
            <div><dt>博主采纳</dt><dd>{forecast?.author_adopted ? "已明确采纳" : "未明确采纳"}</dd></div>
          </dl>}
          {claim.price_targets?.length ? <p>价格水平：{claim.price_targets.map(formatPriceTarget).join("；")}</p> : null}
        </div>
      ) : null}
      <small>
        提取置信度 {Math.round((claim.confidence || 0) * 100)}%
        {claim.sponsor_relation && claim.sponsor_relation !== "none" ? ` · ${SPONSOR_RELATION_LABEL[claim.sponsor_relation]}` : ""}
        {referenceOnly ? ` · ${performanceExclusionLabel(claim)} · 不参与多空统计` : " · 参与多空统计"}
      </small>
    </article>
  );
}

function PanelInstrument({ group, referenceOnly = false }: { group: InstrumentClaimGroup; referenceOnly?: boolean }) {
  const market = group.instrument.market || group.instrument.market_hint || "unknown";
  const verified = group.claims.some((item) => isVerifiedInstrument(item.instrument));
  const targetHref = verified
    ? `/watch/${encodeURIComponent(group.symbol)}`
    : null;
  const instrumentName = group.instrument.resolved_name || group.instrument.original_name;

  return (
    <section className={`activity-inspector-instrument ${referenceOnly ? "is-reference" : ""}`}>
      <header>
        <div>
          {targetHref ? <Link href={targetHref}>{group.symbol}</Link> : <strong>{group.symbol}</strong>}
          <span>{instrumentName || MARKET_LABEL[market] || market}</span>
        </div>
        <small>{MARKET_LABEL[market] || market}{group.instrument.exchange ? ` · ${group.instrument.exchange}` : ""} · {verified ? "身份已验证" : "身份待确认"}</small>
      </header>
      {!verified && group.instrument.validation_reason && <p className="activity-inspector-identity-note">{group.instrument.validation_reason}</p>}
      <div className="activity-inspector-claim-list">
        {group.claims.map((claim, index) => (
          <PanelClaim key={claim.id || `${group.symbol}-${claim.horizon}-${index}`} claim={claim} referenceOnly={referenceOnly} />
        ))}
      </div>
    </section>
  );
}

export function ActivityAnalysisPanel({ tweet, onClose }: { tweet: ActivityTweet; onClose?: () => void }) {
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
  const marketViews = analysis?.market_views || [];
  const hasAnalysis = groups.length > 0 || marketViews.length > 0;
  const handle = tweet.author_handle.replace(/^@/, "");
  const isProcessing = ["pending", "analyzing", "retrying"].includes(tweet.status);

  return (
    <div className="activity-inspector-panel">
      <header className="activity-inspector-head">
        <div>
          <span>推文分析</span>
          <h2>{tweet.author_name || `@${handle}`}</h2>
          <p>@{handle} · {formatDateTime(tweet.published_at)}</p>
        </div>
        {onClose && <button type="button" onClick={onClose} aria-label="关闭分析面板"><AppIcon name="close" /></button>}
      </header>

      <div className="activity-inspector-body" tabIndex={0} aria-label="推文完整分析，可滚动查看">
        {analysis?.tweet_summary && (
          <section className="activity-inspector-summary">
            <span>核心摘要 · 提取置信度 {Math.round((analysis.confidence || 0) * 100)}%</span>
            <p>{analysis.tweet_summary}</p>
          </section>
        )}

        {analysis?.media_summary && (
          <section className="activity-inspector-media-summary">
            <span>图片信息</span>
            <p>{analysis.media_summary}</p>
            {analysis.text_image_consistency && analysis.text_image_consistency !== "no_media" && (
              <small>图文关系：{analysis.text_image_consistency} · 图片提取置信度 {Math.round((analysis.media_confidence || 0) * 100)}%</small>
            )}
          </section>
        )}

        {effectiveGroups.length > 0 && (
          <section className="activity-inspector-section">
            <div className="activity-inspector-title"><h3>有效观点</h3><span>{effectiveGroups.reduce((count, group) => count + group.claims.length, 0)} 项计入统计</span></div>
            {effectiveGroups.map((group) => <PanelInstrument key={group.symbol} group={group} />)}
          </section>
        )}

        {referenceGroups.length > 0 && (
          <section className="activity-inspector-section is-reference">
            <div className="activity-inspector-title"><h3>相关标的 · 仅供参考</h3><span>{referenceGroups.reduce((count, group) => count + group.claims.length, 0)} 项不参与统计</span></div>
            {referenceGroups.map((group) => <PanelInstrument key={group.symbol} group={group} referenceOnly />)}
          </section>
        )}

        {marketViews.length > 0 && (
          <section className="activity-inspector-section is-market">
            <div className="activity-inspector-title"><h3>{groups.length ? "市场背景" : "市场判断"}</h3><span>{marketViews.length} 项</span></div>
            <div className="activity-inspector-market-list">
              {marketViews.map((view, index) => (
                <article className={`activity-inspector-market is-${view.impact}`} key={`${view.market}-${view.topic}-${index}`}>
                  <div><b>{IMPACT_LABEL[view.impact] || "影响待观察"}</b><span>{view.benchmark || MARKET_LABEL[view.market] || view.market}</span><span>{TOPIC_LABEL[view.topic] || "市场"}</span></div>
                  <p>{view.thesis || "原文包含市场信息，但未给出明确影响判断。"}</p>
                  {view.evidence?.length ? <small>依据：{view.evidence.join("；")}</small> : null}
                  <small>{HORIZON_LABEL[view.horizon] || "周期未说明"} · {sourceLabel(view.opinion_source)} · 提取置信度 {Math.round((view.confidence || 0) * 100)}%</small>
                </article>
              ))}
            </div>
          </section>
        )}

        {!hasAnalysis && (
          <div className="activity-inspector-empty">
            <strong>{isProcessing ? "分析正在进行" : "暂无明确投资判断"}</strong>
            <p>{isProcessing ? "完成后会在这里按标的展示方向、依据与风险。" : "这条推文未识别到明确标的观点或市场影响。"}</p>
          </div>
        )}

        {analysis?.is_sponsored && (
          <div className="activity-inspector-sponsored">
            <b>含平台推广</b>
            <p>商业关联会按每项观点分别判断，直接相关或关系待确认的内容不计入成绩。</p>
            {(analysis.commercial_disclosure?.sponsor_handle || analysis.commercial_disclosure?.sponsor_name) && (
              <small>推广方：{analysis.commercial_disclosure.sponsor_handle || analysis.commercial_disclosure.sponsor_name}</small>
            )}
            {analysis.commercial_disclosure?.disclosure_text && <small>披露原文：{analysis.commercial_disclosure.disclosure_text}</small>}
          </div>
        )}
      </div>

      <footer className="activity-inspector-footer">
        <a href={`https://x.com/${handle}/status/${tweet.tweet_id}`} target="_blank" rel="noreferrer">查看原推文 <AppIcon name="external" /></a>
      </footer>
    </div>
  );
}

interface ActivityTweetCardProps {
  tweet: ActivityTweet;
  selectable?: boolean;
  selected?: boolean;
  onOpenAnalysis?: () => void;
}

export default function ActivityTweetCard({ tweet, selectable = false, selected = false, onOpenAnalysis }: ActivityTweetCardProps) {
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

  const directionSummary = useMemo(() => {
    const labels = effectiveGroups
      .map((group) => group.claims.find(isPerformanceEligibleClaim)?.direction)
      .filter((direction): direction is string => Boolean(direction))
      .map((direction) => DIRECTION_LABEL[direction] || "相关信息");
    return [...new Set(labels)];
  }, [effectiveGroups]);

  return (
    <article className={`activity-card ${selectable ? "is-selectable" : ""} ${selected ? "is-selected" : ""}`}>
      <header className="activity-card-author">
        <Link className="activity-card-identity" href={`/sources/${encodeURIComponent(handle)}`}>
          {tweet.author_avatar_url ? (
            <img className="activity-card-avatar" src={tweet.author_avatar_url} alt="" />
          ) : (
            <span className="activity-card-avatar is-fallback" aria-hidden="true">
              {(tweet.author_name || handle).trim().slice(0, 2).toUpperCase()}
            </span>
          )}
          <span className="activity-card-author-copy">
            <strong>{tweet.author_name || `@${handle}`}</strong>
            <span>@{handle}</span>
          </span>
        </Link>
        <div>
          {tweet.tweet_type && tweet.tweet_type !== "original" && <span>{RELATION_LABEL[tweet.tweet_type] || tweet.tweet_type}</span>}
          <time dateTime={tweet.published_at}>{formatDateTime(tweet.published_at)}</time>
        </div>
      </header>

      {selectable && <ActivitySubjectStrip groups={groups} marketViews={marketViews} />}

      {selectable && (
        <button
          className="activity-analysis-trigger"
          type="button"
          aria-pressed={selected}
          onClick={onOpenAnalysis}
        >
          <span>
            <b>{hasAnalysis ? "查看推文分析" : isProcessing ? "分析进行中" : "查看分析结果"}</b>
            <small>
              {effectiveClaimCount ? `${effectiveClaimCount} 项有效观点` : "无有效标的观点"}
              {referenceClaimCount ? ` · ${referenceClaimCount} 项参考信息` : ""}
              {marketViews.length ? ` · ${marketViews.length} 项市场判断` : ""}
            </small>
          </span>
          <span className="activity-analysis-trigger-directions">
            {directionSummary.slice(0, 3).map((label) => <i key={label}>{label}</i>)}
            <AppIcon name="arrow" />
          </span>
        </button>
      )}

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

      {!selectable && <section className="activity-analysis" aria-label="推文分析">
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
      </section>}

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
