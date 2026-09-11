"use client";

import { useState } from "react";

export interface InstrumentDetail {
  symbol: string;
  original_name?: string;
  market?: string;
  market_hint?: string;
  exchange?: string;
  asset_type?: string;
  listing_status?: string;
  tradable?: boolean;
  validation_status?: string;
  validation_sources?: string[];
  validation_reason?: string;
  validated_at?: string;
  external_ids?: Record<string, string>;
  verification?: {
    status?: string;
    reason?: string;
    downstream_eligible?: boolean;
    sources?: string[];
  };
}

export interface InstrumentClaimData {
  id?: string;
  instrument: InstrumentDetail;
  direction: string;
  horizon: string;
  claim_type: string;
  opinion_source: string;
  thesis: string;
  evidence: string[];
  media_evidence?: string[];
  catalysts?: string[];
  risk_factors?: string[];
  risk_details?: Array<{
    category?: string;
    description?: string;
    severity?: string;
    urgency?: string;
  }>;
  risk_level?: string;
  entry_conditions?: string[];
  invalidation_conditions?: string[];
  price_targets?: Array<Record<string, unknown>>;
  forecast?: {
    prediction_type?: string;
    forecast_source?: string;
    source_name?: string;
    author_adopted?: boolean;
    temporal_expression?: string;
    target_metric?: string;
    target_operator?: string;
    target_value?: string;
    target_unit?: string;
    target_condition?: string;
  };
  confidence: number;
  downstream_eligible?: boolean;
  sponsor_relation?: "none" | "unrelated" | "direct" | "unclear";
  performance_eligible?: boolean;
  performance_exclusion_reason?: string | null;
}

export interface CommercialDisclosureData {
  has_commercial_content?: boolean;
  sponsor_name?: string;
  sponsor_handle?: string;
  disclosure_text?: string;
  placement?: "none" | "footer" | "body" | "image" | "multiple" | "unknown";
}

export interface MarketViewData {
  market: "CN" | "HK" | "US" | "COMMODITY" | "CRYPTO" | "GLOBAL";
  benchmark?: string;
  impact: "positive" | "negative" | "mixed" | "unclear";
  horizon: "short" | "medium" | "long" | "unknown";
  topic: "rates" | "inflation" | "liquidity" | "policy" | "growth" | "geopolitics" | "earnings" | "supply_demand" | "regulation" | "other";
  thesis: string;
  evidence: string[];
  opinion_source: "author" | "quoted" | "third_party" | "unclear";
  confidence: number;
}

export interface AnalysisData {
  claims: InstrumentClaimData[];
  market_views?: MarketViewData[];
  tweet_summary?: string;
  confidence: number;
  is_investment_relevant?: boolean;
  is_investment_related: boolean;
  is_sponsored?: boolean;
  commercial_disclosure?: CommercialDisclosureData;
  reasoning?: string;
  media_summary?: string;
  text_image_consistency?: string;
  media_confidence?: number;
}

const DIRECTION: Record<string, { label: string; badge: string }> = {
  bullish: { label: "看多", badge: "bg-emerald-100 text-emerald-800" },
  bearish: { label: "看空", badge: "bg-rose-100 text-rose-800" },
  neutral: { label: "中性", badge: "bg-slate-100 text-slate-700" },
  none: { label: "无方向", badge: "bg-slate-100 text-slate-500" },
};

const HORIZON: Record<string, string> = {
  short: "短期",
  medium: "中期",
  long: "长期",
  unknown: "周期未说明",
};

const CLAIM_TYPE: Record<string, string> = {
  recommendation: "操作建议",
  prediction: "可验证预测",
  opinion: "作者观点",
  risk_warning: "风险提示",
  fact: "事实",
  news: "新闻",
  recap: "复盘",
  reference: "仅提及",
};

const OPINION_SOURCE: Record<string, string> = {
  author: "博主本人",
  quoted: "引用内容",
  third_party: "第三方",
  unclear: "归属待确认",
};

const FORECAST_TYPE: Record<string, string> = {
  price_direction: "价格方向预测",
  price_target: "目标价格预测",
  fundamental_metric: "基本面预测",
  event_outcome: "事件预测",
};

const FORECAST_SOURCE: Record<string, string> = {
  author: "博主本人",
  quoted: "引用账号",
  third_party: "第三方",
  market_consensus: "市场一致预期",
  company_guidance: "公司 / 管理层指引",
  unclear: "预测者待确认",
};

const MARKET: Record<string, string> = {
  CN: "A股",
  HK: "港股",
  US: "美股",
  CRYPTO: "加密市场",
  COMMODITY: "商品",
  UNKNOWN: "市场待确认",
};

const SOURCE: Record<string, string> = {
  akshare: "AKShare",
  sec_edgar: "SEC EDGAR",
  openfigi: "OpenFIGI",
  binance: "Binance",
  eia_pet_rwtc_d: "EIA WTI",
  binance_paxg_proxy: "Binance PAXG 黄金代理",
};

const AUTHOR_STANCE_TYPES = new Set(["recommendation", "prediction", "opinion"]);
const STANCE_DIRECTIONS = new Set(["bullish", "bearish", "neutral"]);

export function isAuthorStanceClaim(claim: InstrumentClaimData) {
  return claim.opinion_source === "author"
    && AUTHOR_STANCE_TYPES.has(claim.claim_type)
    && STANCE_DIRECTIONS.has(claim.direction);
}

export function isPerformanceEligibleClaim(claim: InstrumentClaimData) {
  if (typeof claim.performance_eligible === "boolean") return claim.performance_eligible;
  return eligible(claim)
    && isAuthorStanceClaim(claim)
    && claim.sponsor_relation !== "direct"
    && claim.sponsor_relation !== "unclear";
}

const PERFORMANCE_EXCLUSION: Record<string, string> = {
  instrument_not_verified: "标的身份待确认",
  opinion_not_author: "非博主本人观点",
  opinion_source_unclear: "观点归属待确认",
  direction_not_comparable: "未形成明确方向",
  sponsor_related: "与推广方直接相关",
  sponsor_relation_unclear: "商业关联待确认",
};

export function performanceExclusionLabel(claim: InstrumentClaimData) {
  const reasons: string[] = [];
  if (claim.sponsor_relation === "direct") reasons.push("与推广方直接相关");
  else if (claim.sponsor_relation === "unclear") reasons.push("商业关联待确认");
  if (claim.opinion_source === "quoted") reasons.push("引用观点");
  else if (claim.opinion_source === "third_party") reasons.push("第三方观点");
  else if (claim.opinion_source === "unclear") reasons.push("观点归属待确认");
  const typeReason: Record<string, string> = {
    risk_warning: "风险提示",
    fact: "事实提及",
    news: "新闻信息",
    recap: "历史复盘",
    reference: "仅提及标的",
  };
  if (typeReason[claim.claim_type]) reasons.push(typeReason[claim.claim_type]);
  if (["recommendation", "prediction", "opinion"].includes(claim.claim_type) && claim.direction === "none") {
    reasons.push("未形成明确方向");
  }
  if (claim.downstream_eligible === false) reasons.push("标的身份待确认");
  if (!reasons.length && claim.performance_exclusion_reason) {
    reasons.push(PERFORMANCE_EXCLUSION[claim.performance_exclusion_reason] || "不满足统计口径");
  }
  return [...new Set(reasons)].join(" · ") || "仅供参考";
}

function isQuotedStanceClaim(claim: InstrumentClaimData) {
  return claim.opinion_source !== "author"
    && AUTHOR_STANCE_TYPES.has(claim.claim_type)
    && STANCE_DIRECTIONS.has(claim.direction);
}

export interface InstrumentClaimGroup {
  symbol: string;
  instrument: InstrumentDetail;
  claims: InstrumentClaimData[];
  authorStances: InstrumentClaimData[];
  quotedStances: InstrumentClaimData[];
  facts: InstrumentClaimData[];
  risks: InstrumentClaimData[];
}

export function groupInstrumentClaims(claims: InstrumentClaimData[]): InstrumentClaimGroup[] {
  const groups = new Map<string, InstrumentClaimData[]>();
  claims.forEach((claim) => {
    const symbol = claim.instrument?.symbol || "未知标的";
    groups.set(symbol, [...(groups.get(symbol) || []), claim]);
  });
  return [...groups.entries()].map(([symbol, items]) => ({
    symbol,
    instrument: items[0]?.instrument || { symbol },
    claims: items,
    authorStances: items.filter(isAuthorStanceClaim),
    quotedStances: items.filter(isQuotedStanceClaim),
    risks: items.filter((claim) => claim.claim_type === "risk_warning"),
    facts: items.filter(
      (claim) => !isAuthorStanceClaim(claim)
        && !isQuotedStanceClaim(claim)
        && claim.claim_type !== "risk_warning",
    ),
  }));
}

function eligible(claim: InstrumentClaimData) {
  if (typeof claim.downstream_eligible === "boolean") {
    return claim.downstream_eligible;
  }
  return claim.instrument.verification
    ? claim.instrument.verification.downstream_eligible === true
    : claim.instrument.validation_status === "verified"
      && claim.instrument.tradable === true;
}

function priceTargetText(target: Record<string, unknown>) {
  const type = String(target.target_type || "目标");
  const value = String(target.value || "").trim();
  const currency = String(target.currency || "").trim();
  const condition = String(target.condition || "").trim();
  return [type, [value, currency].filter(Boolean).join(" "), condition]
    .filter(Boolean)
    .join(" · ");
}

export default function AnalysisInline({ analysis }: { analysis: AnalysisData }) {
  const [showReasoning, setShowReasoning] = useState(false);
  const [openVerification, setOpenVerification] = useState<string | null>(null);

  if (!analysis.is_investment_related && !analysis.is_investment_relevant) {
    return <div className="analysis-inline-detail mt-2 border-l-2 border-slate-200 pl-3 text-xs text-slate-500">非投资内容</div>;
  }

  const claims = analysis.claims || [];
  const groups = groupInstrumentClaims(claims);
  const disclosure = analysis.commercial_disclosure;
  const sponsor = disclosure?.sponsor_handle || disclosure?.sponsor_name;
  return (
    <div className="analysis-inline-detail mt-3 space-y-3 rounded-lg bg-white/70 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <strong className="text-sm text-slate-900">逐标的观点</strong>
          <span className="ml-2 text-xs text-slate-500">{groups.length} 个标的 · {claims.length} 项提取</span>
        </div>
        <span className="text-xs text-slate-500" title="表示结构化提取可靠度，不代表观点正确概率">
          提取置信度 {Math.round((analysis.confidence || 0) * 100)}%
        </span>
      </div>

      {analysis.tweet_summary && <p className="text-xs leading-5 text-slate-600">{analysis.tweet_summary}</p>}
      {analysis.is_sponsored && <p className="rounded bg-amber-50 p-2 text-xs leading-5 text-amber-800">
        含商业推广{sponsor ? `（${sponsor.startsWith("@") ? sponsor : sponsor}）` : ""}：
        系统已按每项观点判断商业关联；直接相关或关系待确认的内容仅供参考，无直接关联的作者观点可参与标的共识，符合预测契约时才计入预测成绩。
      </p>}
      {analysis.is_sponsored && disclosure?.disclosure_text && <p className="rounded border border-amber-100 px-2 py-1 text-[11px] leading-5 text-slate-500">
        推广披露：{disclosure.disclosure_text}
      </p>}

      {claims.length === 0 ? (
        <div className="rounded-md border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600">
          这条推文与投资研究有关，但没有提取到可归属到具体标的的观点。
        </div>
      ) : (
        <div className="space-y-2">
          {groups.map((group) => {
            const instrument = group.instrument;
            const isEligible = group.claims.some(eligible);
            const effectiveClaims = group.claims.filter(isPerformanceEligibleClaim);
            const exclusionClaim = group.authorStances[0] || group.claims[0];
            const key = group.symbol;
            const sources = (
              instrument.verification?.sources
              || instrument.validation_sources
              || []
            ).map((source) => SOURCE[source] || source);
            return (
              <article
                key={key}
                className={`rounded-lg border p-3 ${isEligible ? "border-emerald-200 bg-white" : "border-amber-200 bg-amber-50/50"}`}
              >
                <header className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <b className="rounded bg-slate-950 px-2 py-0.5 font-mono text-xs text-white">{group.symbol}</b>
                      {group.authorStances.length === 0 ? (
                        <span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-600">博主未明确表态</span>
                      ) : group.authorStances.map((claim, index) => {
                        const direction = DIRECTION[claim.direction] || DIRECTION.none;
                        return <span key={claim.id || `${claim.horizon}-${index}`} className={`rounded px-2 py-0.5 text-xs font-semibold ${direction.badge}`}>
                          {HORIZON[claim.horizon] && claim.horizon !== "unknown" ? `${HORIZON[claim.horizon]} ` : ""}{direction.label}
                        </span>;
                      })}
                    </div>
                    <p className="mt-1 text-[11px] text-slate-500">
                      {MARKET[instrument.market || instrument.market_hint || "UNKNOWN"] || instrument.market} · {group.claims.length} 项相关信息
                    </p>
                  </div>
                  <span className={`shrink-0 rounded px-2 py-1 text-[11px] font-semibold ${effectiveClaims.length ? "bg-emerald-50 text-emerald-700" : "bg-amber-100 text-amber-800"}`}>
                    {effectiveClaims.length
                      ? "有效观点 · 参与统计"
                      : isEligible
                        ? performanceExclusionLabel(exclusionClaim)
                        : "标的身份待确认"}
                  </span>
                </header>

                <div className="mt-3 space-y-3">
                  {group.authorStances.length > 0 && <section>
                    <b className="text-[11px] text-slate-500">博主主观点</b>
                    {group.authorStances.map((claim, index) => {
                      const evidence = [...new Set([...(claim.evidence || []), ...(claim.media_evidence || [])])];
                      return <div key={claim.id || `author-${index}`} className="mt-1 rounded bg-slate-50 p-2">
                        <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-500"><span>{HORIZON[claim.horizon] || "周期未说明"}</span><span>{CLAIM_TYPE[claim.claim_type] || claim.claim_type}</span></div>
                        {analysis.is_sponsored && <p className="mt-1 text-[11px] font-medium text-amber-700">
                          {isPerformanceEligibleClaim(claim)
                            ? "与推广方无直接关联 · 商业规则不排除"
                            : `${performanceExclusionLabel(claim)} · 不计入博主表现`}
                        </p>}
                        <p className="mt-1 text-sm leading-6 text-slate-800">{claim.thesis || evidence[0] || "未提取到明确论点。"}</p>
                        {claim.forecast?.prediction_type && claim.forecast.prediction_type !== "none" && <p className="mt-1 rounded bg-cyan-50/70 px-2 py-1 text-xs leading-5 text-cyan-900">
                          {FORECAST_TYPE[claim.forecast.prediction_type] || claim.forecast.prediction_type}
                          {claim.forecast.target_metric ? ` · ${claim.forecast.target_metric}` : ""}
                          {claim.forecast.target_value ? ` ${claim.forecast.target_value}${claim.forecast.target_unit ? ` ${claim.forecast.target_unit}` : ""}` : ""}
                          {claim.forecast.temporal_expression ? ` · 时间依据：${claim.forecast.temporal_expression}` : " · 未提供时间依据"}
                          {claim.forecast.forecast_source ? ` · 预测来源：${claim.forecast.source_name || FORECAST_SOURCE[claim.forecast.forecast_source] || claim.forecast.forecast_source}` : ""}
                          {claim.forecast.author_adopted ? " · 博主明确采纳" : claim.forecast.forecast_source && claim.forecast.forecast_source !== "author" ? " · 不计入博主预测成绩" : ""}
                        </p>}
                        {evidence.length > 0 && <p className="mt-1 text-xs leading-5 text-slate-600">证据：{evidence.join("；")}</p>}
                        {(claim.catalysts?.length || claim.risk_factors?.length || claim.invalidation_conditions?.length) ? <div className="mt-2 grid gap-2 md:grid-cols-2">
                          <p className="rounded bg-emerald-50/70 p-2 text-xs text-slate-600"><b className="text-emerald-800">催化：</b>{claim.catalysts?.join("；") || "未明确"}</p>
                          <p className="rounded bg-rose-50/70 p-2 text-xs text-slate-600"><b className="text-rose-800">风险：</b>{[...(claim.risk_factors || []), ...(claim.invalidation_conditions || [])].join("；") || "未明确"}</p>
                        </div> : null}
                        {claim.risk_details?.length ? <p className="mt-2 text-xs leading-5 text-slate-600">
                          风险等级：{claim.risk_details.map((risk) => `${risk.description || risk.category || "风险"}（${risk.severity || "等级待确认"} / ${risk.urgency || "时点待确认"}）`).join("；")}
                        </p> : null}
                        {claim.entry_conditions?.length ? <p className="mt-1 text-xs leading-5 text-slate-600">入场条件：{claim.entry_conditions.join("；")}</p> : null}
                        {claim.invalidation_conditions?.length ? <p className="mt-1 text-xs leading-5 text-slate-600">失效条件：{claim.invalidation_conditions.join("；")}</p> : null}
                        {claim.price_targets?.length ? <p className="mt-1 text-xs leading-5 text-slate-600">价格水平：{claim.price_targets.map(priceTargetText).join("；")}</p> : null}
                        <p className="mt-1 text-[11px] text-slate-400">该项提取置信度 {Math.round((claim.confidence || 0) * 100)}%</p>
                      </div>;
                    })}
                  </section>}

                  {group.quotedStances.length > 0 && <section className="border-l-2 border-violet-200 pl-3">
                    <b className="text-[11px] text-violet-800">引用 / 第三方观点</b>
                    {group.quotedStances.map((claim, index) => <p key={claim.id || `quoted-${index}`} className="mt-1 text-xs leading-5 text-slate-600">
                      {OPINION_SOURCE[claim.opinion_source] || "归属待确认"} · {DIRECTION[claim.direction]?.label || "无明确方向"}：{claim.thesis || claim.evidence?.[0] || "未提取到摘要"}
                      {claim.forecast?.temporal_expression ? `（${FORECAST_TYPE[claim.forecast.prediction_type || ""] || "预测"} · ${claim.forecast.temporal_expression}）` : ""}
                      {claim.evidence?.length ? `；依据：${claim.evidence.join("；")}` : ""}
                    </p>)}
                  </section>}

                  {group.facts.length > 0 && <section className="border-l-2 border-cyan-200 pl-3">
                    <b className="text-[11px] text-cyan-800">事实与补充信息</b>
                    {group.facts.map((claim, index) => <p key={claim.id || `fact-${index}`} className="mt-1 text-xs leading-5 text-slate-600">
                      {CLAIM_TYPE[claim.claim_type] || claim.claim_type} · {OPINION_SOURCE[claim.opinion_source] || "归属待确认"}：{claim.thesis || claim.evidence?.[0] || "未提取到摘要"}
                      {claim.evidence?.length ? `；依据：${claim.evidence.join("；")}` : ""}
                    </p>)}
                  </section>}

                  {group.risks.length > 0 && <section className="rounded bg-rose-50/70 p-2">
                    <b className="text-[11px] text-rose-800">风险提示（不等于看空）</b>
                    {group.risks.map((claim, index) => <p key={claim.id || `risk-${index}`} className="mt-1 text-xs leading-5 text-slate-600">
                      {claim.thesis || claim.risk_factors?.join("；") || claim.evidence?.[0] || "未提取到风险摘要"}
                    </p>)}
                  </section>}
                </div>

                <footer className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-2 text-[11px] text-slate-500">
                  <span>最高提取置信度 {Math.round(Math.max(...group.claims.map((claim) => claim.confidence || 0)) * 100)}%</span>
                  {(sources.length > 0 || instrument.validation_reason || instrument.verification?.reason) && (
                    <button type="button" className="font-medium text-cyan-700" onClick={() => setOpenVerification(openVerification === key ? null : key)}>
                      {openVerification === key ? "收起标的核验" : "查看标的核验"}
                    </button>
                  )}
                </footer>
                {openVerification === key && (
                  <div className="mt-2 rounded bg-slate-50 p-2 text-[11px] leading-5 text-slate-600">
                    <p>{instrument.verification?.reason || instrument.validation_reason || "公开数据源尚未确认该标的身份。"}</p>
                    {sources.length > 0 && <p>核验来源：{sources.join("、")}</p>}
                    {instrument.exchange && <p>交易场所：{instrument.exchange}</p>}
                    {instrument.validated_at && <p>核验时间：{new Date(instrument.validated_at).toLocaleString("zh-CN")}</p>}
                  </div>
                )}
              </article>
            );
          })}
        </div>
      )}

      {analysis.media_summary && (
        <p className="rounded bg-cyan-50 p-2 text-xs leading-5 text-cyan-900">图片补充：{analysis.media_summary}</p>
      )}
      {analysis.reasoning && (
        <div>
          <button type="button" className="text-xs font-medium text-slate-500 hover:text-slate-800" onClick={() => setShowReasoning(!showReasoning)}>
            {showReasoning ? "隐藏拆分依据" : "查看拆分依据"}
          </button>
          {showReasoning && <p className="mt-2 rounded bg-slate-50 p-2 text-xs leading-5 text-slate-600">{analysis.reasoning}</p>}
        </div>
      )}
    </div>
  );
}
