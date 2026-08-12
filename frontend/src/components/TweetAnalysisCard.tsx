"use client";

import { useState } from "react";
import { formatDateTime } from "@/lib/datetime";
import AnalysisInline from "./AnalysisInline";
import TweetMediaGallery, { type TweetMediaItem } from "./TweetMediaGallery";

interface TweetMetrics {
  likes?: number;
  retweets?: number;
  views?: number;
}

interface AnalysisData {
  tickers: Array<{
    symbol: string;
    original_name: string;
    sentiment: string;
    horizon: string;
    market?: string;
    asset_type?: string;
    tradable?: boolean;
    validation_status?: string;
    validation_sources?: string[];
    risks?: Array<{
      category: string;
      description: string;
      severity: string;
      urgency: string;
    }>;
    ticker_risk_level?: string;
  }>;
  overall_sentiment: string;
  key_points: string[];
  risk_factors: string[];
  risk_level?: string;
  risk_summary?: string;
  confidence: number;
  is_investment_related: boolean;
  reasoning?: string;
  media_summary?: string;
  media_evidence?: string[];
  text_image_consistency?: string;
  media_confidence?: number;
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
  mixed: "分化",
};

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
  const verifiedTickers = (analysis?.tickers || []).filter(
    (ticker) => ticker.validation_status === "verified" && ticker.tradable === true,
  );

  // Extract quick summary from analysis for card header
  const quickSummary = analysis?.is_investment_related
    ? {
        sentiment: analysis.overall_sentiment,
        tickers: verifiedTickers.slice(0, 3).map((t) => t.symbol),
        remainingTickerCount: Math.max(0, verifiedTickers.length - 3),
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
              <span className={`direction direction-${quickSummary.sentiment}`}>
                {SENTIMENT_LABEL[quickSummary.sentiment] || quickSummary.sentiment}
              </span>
              {quickSummary.tickers.length > 0 && (
                <span className="tweet-tickers" aria-label="已核验标的">
                  {quickSummary.tickers.map((ticker) => (
                    <b key={ticker} title="已通过公开数据源核验">{ticker}<i>已核验</i></b>
                  ))}
                  {quickSummary.remainingTickerCount > 0 && <em>+{quickSummary.remainingTickerCount}</em>}
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
