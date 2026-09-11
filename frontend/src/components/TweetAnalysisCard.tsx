"use client";

import { useState } from "react";
import { formatDateTime } from "@/lib/datetime";
import AnalysisInline, {
  groupInstrumentClaims,
  isPerformanceEligibleClaim,
  performanceExclusionLabel,
  type AnalysisData,
  type InstrumentClaimGroup,
} from "./AnalysisInline";
import TweetMediaGallery, { type TweetMediaItem } from "./TweetMediaGallery";

interface TweetMetrics {
  likes?: number;
  retweets?: number;
  views?: number;
}

interface TweetAnalysisCardProps {
  id: string;
  tweetId: string;
  authorHandle: string;
  authorName?: string;
  content: string;
  publishedAt: string;
  status: string;
  metrics?: TweetMetrics | null;
  analysis?: AnalysisData | null;
  twitterTweetId?: string;
  media?: TweetMediaItem[];
  onTriggerAnalysis?: (tweetId: string, handle: string) => void;
}

const STATUS_CONFIG: Record<string, { label: string; color: string }> = {
  analyzed: { label: "已分析", color: "bg-green-100 text-green-700" },
  pending: { label: "待分析", color: "bg-yellow-100 text-yellow-700" },
};

const SENTIMENT_LABEL: Record<string, string> = {
  bullish: "看好",
  bearish: "看空",
  neutral: "中性",
  none: "无方向",
};

function groupStanceLabel(group: InstrumentClaimGroup) {
  const effectiveClaims = group.claims.filter(isPerformanceEligibleClaim);
  const labels = [...new Set(effectiveClaims.map((claim) => SENTIMENT_LABEL[claim.direction]))].filter(Boolean);
  if (labels.length === 0) return performanceExclusionLabel(group.authorStances[0] || group.claims[0]);
  if (labels.length === 1) return labels[0];
  return "多周期";
}

export default function TweetAnalysisCard({
  id,
  authorHandle,
  authorName,
  content,
  publishedAt,
  status,
  metrics,
  analysis,
  twitterTweetId,
  media = [],
  onTriggerAnalysis,
}: TweetAnalysisCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [analysisExpanded, setAnalysisExpanded] = useState(false);

  const statusCfg = STATUS_CONFIG[status] || STATUS_CONFIG.pending;
  const isAnalyzed = status === "analyzed";
  const verifiedClaims = (analysis?.claims || []).filter(
    (claim) => claim.downstream_eligible === true
      || claim.instrument.verification?.downstream_eligible === true
      || (claim.instrument.validation_status === "verified" && claim.instrument.tradable === true),
  );
  const instrumentGroups = groupInstrumentClaims(verifiedClaims);

  // A tweet is only the evidence container; header summaries are claim-level.
  const quickSummary = analysis?.is_investment_related
    ? {
        groups: instrumentGroups.slice(0, 3),
        remainingGroupCount: Math.max(0, instrumentGroups.length - 3),
        totalInstrumentCount: groupInstrumentClaims(analysis.claims || []).length,
      }
    : null;

  return (
    <article className={`tweet-card ${isAnalyzed ? "is-analyzed" : "is-pending"}`}>
      {/* Header row */}
      <div className="tweet-card-header">
        <div className="tweet-author">
          <span>{authorHandle}</span>
          {authorName && (
            <small>{authorName}</small>
          )}
          <span className="status-pill">
            {statusCfg.label}
          </span>
          {isAnalyzed && quickSummary && (
            <>
              <span className="status-pill">{quickSummary.totalInstrumentCount} 个标的</span>
              {analysis?.is_sponsored && <span className="status-pill">含平台推广</span>}
              {quickSummary.groups.length > 0 && (
                <span className="tweet-tickers" aria-label="已核验逐标的观点">
                  {quickSummary.groups.map((group) => (
                    <b key={group.symbol} title="已通过公开数据源核验">
                      {group.symbol}<i>{groupStanceLabel(group)}</i>
                    </b>
                  ))}
                  {quickSummary.remainingGroupCount > 0 && <em>+{quickSummary.remainingGroupCount}</em>}
                </span>
              )}
            </>
          )}
        </div>
      </div>

      {/* Tweet content */}
      <p className={`tweet-content ${expanded ? "" : "line-clamp-3"}`}>
        {content}
      </p>
      {content.length > 200 && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-action"
        >
          {expanded ? "收起" : "展开全部"}
        </button>
      )}

      <TweetMediaGallery tweetId={id} media={media} />

      {/* Inline analysis (expandable) */}
      {isAnalyzed && analysis && (
        <div className="tweet-analysis-toggle">
          <button
            onClick={() => setAnalysisExpanded(!analysisExpanded)}
            className="text-action"
          >
            <span>{analysisExpanded ? "▲" : "▼"}</span>
            {analysisExpanded ? "收起分析详情" : "展开分析详情"}
          </button>
          {analysisExpanded && <AnalysisInline analysis={analysis} />}
        </div>
      )}

      {/* Footer */}
      <footer className="tweet-card-footer">
        <div>
          <span>{formatDateTime(publishedAt)}</span>
          {metrics && (
            <>
              {metrics.likes != null && <span>赞 {metrics.likes}</span>}
              {metrics.retweets != null && <span>转发 {metrics.retweets}</span>}
              {metrics.views != null && <span>浏览 {metrics.views}</span>}
            </>
          )}
        </div>
        <div className="tweet-card-actions">
          {twitterTweetId && (
            <a
              href={`https://x.com/${authorHandle.replace("@", "")}/status/${twitterTweetId}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-action"
            >
              查看原文
            </a>
          )}
          {!isAnalyzed && onTriggerAnalysis && (
            <button
              onClick={() => onTriggerAnalysis(id, authorHandle)}
              className="text-action"
            >
              触发分析
            </button>
          )}
        </div>
      </footer>
    </article>
  );
}
