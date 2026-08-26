const API_BASE = process.env.NEXT_PUBLIC_API_URL || (
  typeof window !== "undefined"
    ? `${window.location.protocol}//${window.location.hostname}:8000`
    : "http://localhost:8000"
);

import { authFetch, getAccessToken } from "./auth";

function apiErrorMessage(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== "object") return fallback;
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (detail && typeof detail === "object") {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === "string" && message.trim()) return message;
    const error = (detail as { error?: unknown }).error;
    if (error === "duplicate_prediction_after_correction") {
      return "同一博主 24 小时内已有相同标的和方向的预测，请保留较早记录并排除当前重复项";
    }
  }
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => (item && typeof item === "object" ? (item as { msg?: unknown }).msg : null))
      .filter((item): item is string => typeof item === "string");
    if (messages.length) return messages.join("；");
  }
  return fallback;
}

export interface IntelligenceEvidence {
  source_type: string;
  source_id: string;
  author: string;
  published_at: string;
  excerpt: string;
  source_url: string;
}

export interface IntelligenceFeedItem {
  id: string;
  kind: "opinion" | "risk" | "news";
  title: string;
  summary: string;
  direction: string;
  tickers: string[];
  author: string;
  confidence: number;
  source_credibility: number;
  importance_score: number;
  score_breakdown: {
    relevance: number;
    freshness: number;
    confidence: number;
    credibility: number;
    risk: number;
    corroboration: number;
    quality_penalty: number;
    total: number;
  };
  score_explanation: string[];
  risk_factors: string[];
    key_points: string[];
    published_at: string;
    first_seen_at: string;
    last_seen_at: string;
    time_bucket: string;
    lifecycle: "new" | "developing" | "confirmed" | "reversed" | "expired";
    event_count: number;
    match_reasons: string[];
  feed_bucket: "personalized" | "market_risk" | "discovery";
  corroboration_count: number;
  evidence: IntelligenceEvidence;
  supporting_evidence: IntelligenceEvidence[];
}

export interface IntelligenceFeedResponse {
  items: IntelligenceFeedItem[];
  total: number;
  context: {
    followed_bloggers: number;
    tracked_tickers: number;
    personalized: boolean;
    fallback_to_market: boolean;
    candidate_total: number;
    personalized_candidates: number;
    market_candidates: number;
    window: "24h" | "3d" | "7d";
    kind: "all" | "risk" | "opinion" | "news";
    generated_at: string;
  };
}

export interface IntelligenceDigestResponse {
  status: "ready" | "empty" | "scope_empty";
  title: string;
  executive_summary: string;
  generated_at: string;
  period_start: string;
  period_end: string;
  metrics: {
    signal_count: number;
    personalized_count: number;
    source_count: number;
    ticker_count: number;
    opinion_count: number;
    news_count: number;
    risk_count: number;
    reversal_count: number;
    corroborated_count: number;
  };
  highlights: IntelligenceFeedItem[];
  attention: IntelligenceFeedItem[];
  context: IntelligenceFeedResponse["context"];
  methodology: string;
}

export interface IntelligenceTweetDetail {
  id: string;
  tweet_id: string;
  author_handle: string;
  author_name: string;
  content: string;
  published_at: string;
  relationship: string;
  tweet_type: string;
  conversation_tweet_id: string | null;
  in_reply_to_tweet_id: string | null;
  quoted_tweet_id: string | null;
  reposted_tweet_id: string | null;
  referenced_tweets: Array<Record<string, unknown>>;
  source_url: string;
}

export interface IntelligenceMediaDetail {
  id: string;
  tweet_id: string;
  width: number | null;
  height: number | null;
  content_type: string | null;
  status: string;
  error_detail: string | null;
  analysis_status: string | null;
  analysis: Record<string, unknown> | null;
}

export interface IntelligenceDetailResponse {
  item: IntelligenceFeedItem;
  tweet: IntelligenceTweetDetail;
  thread: IntelligenceTweetDetail[];
  media: IntelligenceMediaDetail[];
  analysis: Record<string, unknown>;
  instruments: Array<Record<string, unknown>>;
  predictions: Array<Record<string, unknown>>;
  audit: Array<Record<string, unknown>>;
}

export type IntelligenceCorrectionCategory =
  | "author_attribution"
  | "instrument"
  | "direction"
  | "context"
  | "image"
  | "other";

export async function fetchIntelligenceFeed(
  limit = 20,
  window: "24h" | "3d" | "7d" = "24h",
  kind: "all" | "risk" | "opinion" | "news" = "all",
): Promise<IntelligenceFeedResponse> {
  const params = new URLSearchParams({ limit: String(limit), window, kind });
  const res = await authFetch(`${API_BASE}/api/intelligence/feed?${params.toString()}`, { cache: "no-store" });
  if (!res.ok) throw new Error("无法加载今日情报，请检查后端服务或稍后重试。");
  return res.json() as Promise<IntelligenceFeedResponse>;
}

export async function fetchIntelligenceDigest(): Promise<IntelligenceDigestResponse> {
  const res = await authFetch(`${API_BASE}/api/intelligence/digest`, { cache: "no-store" });
  if (!res.ok) throw new Error("无法加载 Twitter 投资情报日报，请稍后重试。");
  return res.json() as Promise<IntelligenceDigestResponse>;
}

export async function fetchIntelligenceDetail(id: string): Promise<IntelligenceDetailResponse> {
  const res = await authFetch(
    `${API_BASE}/api/intelligence/${encodeURIComponent(id)}`,
    { cache: "no-store" },
  );
  if (!res.ok) throw new Error("情报详情加载失败，请稍后重试。");
  return res.json() as Promise<IntelligenceDetailResponse>;
}

export async function submitIntelligenceCorrection(
  id: string,
  data: { category: IntelligenceCorrectionCategory; note: string },
): Promise<{ id: string; topic_id: string; category: string; status: string; created_at: string }> {
  const res = await authFetch(
    `${API_BASE}/api/intelligence/${encodeURIComponent(id)}/corrections`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    },
  );
  const payload = await res.json().catch(() => null);
  if (!res.ok) throw new Error(apiErrorMessage(payload, "反馈提交失败，请稍后重试。"));
  return payload;
}

export async function fetchDashboard() {
  const res = await authFetch(`${API_BASE}/api/dashboard/overview`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Failed to fetch dashboard");
  return res.json();
}

export async function fetchTweets(params?: {
  status?: string;
  blogger?: string;
  include_analysis?: boolean;
  limit?: number;
  offset?: number;
}) {
  const sp = new URLSearchParams();
  if (params?.status) sp.set("status", params.status);
  if (params?.blogger) sp.set("blogger", params.blogger);
  if (params?.include_analysis) sp.set("include_analysis", "true");
  if (params?.limit) sp.set("limit", String(params.limit));
  if (params?.offset) sp.set("offset", String(params.offset));
  const res = await authFetch(`${API_BASE}/api/tweets?${sp.toString()}`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Failed to fetch tweets");
  return res.json();
}

export async function fetchAnalyses(params?: {
  blogger?: string;
  sentiment?: string;
  limit?: number;
  offset?: number;
}) {
  const searchParams = new URLSearchParams();
  if (params?.blogger) searchParams.set("blogger", params.blogger);
  if (params?.sentiment) searchParams.set("sentiment", params.sentiment);
  if (params?.limit) searchParams.set("limit", String(params.limit));
  if (params?.offset) searchParams.set("offset", String(params.offset));

  const url = `${API_BASE}/api/analyses?${searchParams.toString()}`;
  const res = await authFetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch analyses");
  return res.json();
}

export async function fetchTickerSummaries(params?: { limit?: number; offset?: number }) {
  const sp = new URLSearchParams();
  sp.set("limit", String(params?.limit ?? 100));
  if (params?.offset) sp.set("offset", String(params.offset));
  const res = await authFetch(`${API_BASE}/api/ticker-summaries?${sp.toString()}`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Failed to fetch ticker summaries");
  return res.json();
}

export async function fetchBloggers(params?: {
  sort?: "credibility" | "verified_count" | "followers" | "pending_count";
}) {
  const sp = new URLSearchParams();
  if (params?.sort) sp.set("sort", params.sort);
  const res = await authFetch(`${API_BASE}/api/bloggers?${sp.toString()}`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Failed to fetch bloggers");
  return res.json();
}

export interface UserAlertItem {
  id: string;
  kind: "high_risk" | "direction_reversal" | "new_prediction" | string;
  severity: "high" | "info" | string;
  title: string;
  message: string;
  target_url: string;
  ticker: string | null;
  blogger_handle: string | null;
  status: "unread" | "read" | "dismissed";
  occurred_at: string;
  read_at: string | null;
}

export interface UserAlertListResponse {
  items: UserAlertItem[];
  total: number;
  unread: number;
  high_priority: number;
}

export async function fetchAlerts(status: "unread" | "read" | "dismissed" | "all" = "unread"): Promise<UserAlertListResponse> {
  const res = await authFetch(`${API_BASE}/api/alerts?status=${status}`, { cache: "no-store" });
  if (!res.ok) throw new Error("提醒加载失败");
  return res.json() as Promise<UserAlertListResponse>;
}

export async function updateAlert(id: string, action: "read" | "dismiss"): Promise<UserAlertItem> {
  const res = await authFetch(`${API_BASE}/api/alerts/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action }),
  });
  if (!res.ok) throw new Error("提醒状态更新失败");
  return res.json() as Promise<UserAlertItem>;
}

export async function readAllAlerts(): Promise<{ updated: number }> {
  const res = await authFetch(`${API_BASE}/api/alerts/read-all`, { method: "POST" });
  if (!res.ok) throw new Error("全部标记已读失败");
  return res.json() as Promise<{ updated: number }>;
}

export async function fetchTweetMediaBlob(tweetId: string, assetId: string): Promise<Blob> {
  const res = await authFetch(
    `${API_BASE}/api/tweets/${encodeURIComponent(tweetId)}/media/${encodeURIComponent(assetId)}`,
    { cache: "force-cache" },
  );
  if (!res.ok) throw new Error("Failed to fetch tweet media");
  return res.blob();
}

export interface BloggerOnboardResult {
  id: string;
  handle: string;
  name: string;
  avatar_url: string | null;
  followed: boolean;
  fetch_enabled: boolean;
  initial_fetch_queued: boolean;
}

export type BloggerIngestionStage = "syncing" | "analyzing" | "ready" | "attention" | "paused";

export interface BloggerIngestionStatus {
  handle: string;
  stage: BloggerIngestionStage;
  message: string;
  progress: number;
  fetch_enabled: boolean;
  last_fetched_at: string | null;
  last_activity_at: string | null;
  collected_tweets: number;
  analyzed_tweets: number;
  processing_tweets: number;
  failed_tweets: number;
}

export async function onboardBlogger(handle: string): Promise<BloggerOnboardResult> {
  const res = await authFetch(`${API_BASE}/api/bloggers/onboard`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ handle }),
  });
  if (!res.ok) {
    const payload = await res.json().catch(() => null) as { detail?: string } | null;
    throw new Error(payload?.detail || "新增信息源失败，请稍后重试");
  }
  return res.json() as Promise<BloggerOnboardResult>;
}

export async function fetchBloggerIngestionStatus(handle: string): Promise<BloggerIngestionStatus> {
  const res = await authFetch(
    `${API_BASE}/api/bloggers/${encodeURIComponent(handle)}/ingestion-status`,
    { cache: "no-store" },
  );
  if (!res.ok) throw new Error("信息源处理状态加载失败");
  return res.json() as Promise<BloggerIngestionStatus>;
}

export async function fetchBloggerDetail(handle: string) {
  const res = await authFetch(
    `${API_BASE}/api/bloggers/${encodeURIComponent(handle)}`,
    { cache: "no-store" },
  );
  if (!res.ok) throw new Error("Failed to fetch blogger detail");
  return res.json();
}

export async function fetchBloggerPredictions(
  handle: string,
  params?: {
    status?: "pending" | "verified" | "all";
    ticker?: string;
    limit?: number;
    offset?: number;
  },
) {
  const sp = new URLSearchParams();
  if (params?.status) sp.set("status", params.status);
  if (params?.ticker) sp.set("ticker", params.ticker);
  if (params?.limit) sp.set("limit", String(params.limit));
  if (params?.offset) sp.set("offset", String(params.offset));
  const res = await authFetch(
    `${API_BASE}/api/bloggers/${encodeURIComponent(handle)}/predictions?${sp.toString()}`,
    { cache: "no-store" },
  );
  if (!res.ok) throw new Error("Failed to fetch blogger predictions");
  return res.json();
}

export async function verifyPrediction(
  id: string,
  body: { verdict: "correct" | "partial" | "incorrect"; note?: string },
) {
  const res = await authFetch(`${API_BASE}/api/predictions/${id}/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let payload: any = null;
    try {
      payload = await res.json();
    } catch {}
    const err: any = new Error("Failed to verify prediction");
    err.status = res.status;
    err.payload = payload;
    throw err;
  }
  return res.json();
}

export async function upsertBlogger(profile: {
  handle: string;
  name?: string;
  bio?: string | null;
  avatar_url?: string | null;
  followers_count?: number;
  market_focus?: string[] | null;
}) {
  const res = await authFetch(`${API_BASE}/api/bloggers/upsert`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(profile),
  });
  if (!res.ok) throw new Error("Failed to upsert blogger");
  return res.json();
}

export async function triggerAnalysis() {
  const res = await authFetch(`${API_BASE}/api/analysis/trigger`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to trigger analysis");
  return res.json();
}

export async function analyzeSingleTweet(tweetId: string) {
  const res = await authFetch(
    `${API_BASE}/api/analysis/tweet/${encodeURIComponent(tweetId)}`,
    { method: "POST" },
  );
  if (!res.ok) throw new Error("Failed to analyze tweet");
  return res.json();
}

export async function analyzeBlogger(handle: string) {
  const res = await authFetch(
    `${API_BASE}/api/analysis/blogger/${encodeURIComponent(handle)}`,
    { method: "POST" },
  );
  if (!res.ok) throw new Error("Failed to analyze blogger");
  return res.json();
}

export async function analyzeBloggers(handles: string[]) {
  const res = await authFetch(`${API_BASE}/api/analysis/bloggers`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ blogger_handles: handles }),
  });
  if (!res.ok) throw new Error("Failed to analyze bloggers");
  return res.json();
}

export async function toggleBloggerFetch(handle: string, fetch_enabled: boolean) {
  const res = await authFetch(
    `${API_BASE}/api/bloggers/${encodeURIComponent(handle)}/fetch-toggle`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fetch_enabled }),
    },
  );
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new Error(data?.detail || "更新定时抓取状态失败");
  }
  return res.json();
}

export async function excludePrediction(id: string, reason: string) {
  const res = await authFetch(`${API_BASE}/api/predictions/${id}/exclude`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason }),
  });
  if (!res.ok) throw new Error("排除预测失败");
  return res.json();
}

export type InstrumentCorrection = {
  symbol: string;
  name: string;
  asset_type: "equity" | "crypto" | "commodity";
  market: "CN" | "HK" | "US" | "CRYPTO" | "COMMODITY";
  reason: string;
  context_terms?: string[];
};

export type InstrumentValidation = {
  accepted: boolean;
  reason: string;
  instrument?: Record<string, unknown>;
};

export async function validatePredictionInstrument(
  correction: Omit<InstrumentCorrection, "reason" | "context_terms">,
): Promise<InstrumentValidation> {
  const res = await authFetch(`${API_BASE}/api/predictions/instruments/validate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(correction),
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new Error(apiErrorMessage(data, "标的校验失败"));
  return data as InstrumentValidation;
}

export async function correctPredictionInstrument(
  id: string,
  correction: InstrumentCorrection,
) {
  const res = await authFetch(
    `${API_BASE}/api/predictions/${id}/correct-instrument`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(correction),
    },
  );
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new Error(apiErrorMessage(data, "修正标的失败"));
  }
  return res.json();
}

export type MarketVerificationEvidence = {
  id: string;
  status: "ready" | "tracking" | "manual_review" | "market_data_unavailable" | "excluded_non_directional" | "excluded_duplicate";
  provider: string | null;
  provider_symbol: string | null;
  market: string | null;
  start_observed_at: string | null;
  start_price: number | null;
  end_observed_at: string | null;
  end_price: number | null;
  raw_return: number | null;
  directional_return: number | null;
  threshold: number | null;
  proposed_verdict: string | null;
  proposed_score: number | null;
  rule_version: string;
  reason: string | null;
  review_type?: "instrument_identity" | "non_directional" | "market_data" | "duplicate_prediction" | null;
  identity?: {
    symbol?: string | null;
    original_name?: string | null;
    resolved_name?: string | null;
    market?: string | null;
    validation_status?: string | null;
    validation_sources?: string[];
  } | null;
  identity_reason: string | null;
  price_proxy?: {
    business_symbol: string;
    provider_symbol: string;
    disclosure: string;
  } | null;
  correction?: {
    old_symbol?: string;
    new_symbol?: string;
    duplicate_prediction_id?: string;
    reason?: string;
  } | null;
  applied: boolean;
  created_at: string;
};

export type PredictionReviewStats = {
  manual_review: number;
  market_data_unavailable: number;
  due_pending: number;
  tracking: number;
  auto_verified: number;
};

export async function fetchPredictionReviewQueue(params?: {
  status?: "all" | "manual_review" | "market_data_unavailable";
  limit?: number;
  offset?: number;
}) {
  const sp = new URLSearchParams();
  if (params?.status) sp.set("status", params.status);
  if (params?.limit) sp.set("limit", String(params.limit));
  if (params?.offset) sp.set("offset", String(params.offset));
  const res = await authFetch(
    `${API_BASE}/api/predictions/review-queue?${sp.toString()}`,
    { cache: "no-store" },
  );
  if (!res.ok) throw new Error("人工复核队列加载失败");
  return res.json();
}

export type PredictionLifecycleStatus = "tracking" | "due" | "review" | "verified" | "excluded";

export type PredictionOperationStats = {
  total: number;
  tracking: number;
  due: number;
  review: number;
  verified: number;
  excluded: number;
  auto_verified: number;
  market_data_unavailable: number;
};

export async function fetchPredictionOperations(params?: {
  status?: "all" | PredictionLifecycleStatus;
  limit?: number;
  offset?: number;
}) {
  const sp = new URLSearchParams();
  if (params?.status) sp.set("status", params.status);
  if (params?.limit) sp.set("limit", String(params.limit));
  if (params?.offset) sp.set("offset", String(params.offset));
  const res = await authFetch(
    `${API_BASE}/api/predictions/operations?${sp.toString()}`,
    { cache: "no-store" },
  );
  if (!res.ok) throw new Error("预测生命周期加载失败");
  return res.json();
}

export async function retryPredictionMarketVerification(id: string) {
  const res = await authFetch(
    `${API_BASE}/api/predictions/${id}/retry-market-verification`,
    { method: "POST" },
  );
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new Error(apiErrorMessage(data, "行情重试失败"));
  }
  return res.json();
}

// ============================================================
// Chat Conversations API
// ============================================================

export interface FollowedBloggerListResponse {
  items: Array<{
    id: string;
    handle: string;
    name: string;
    bio: string | null;
    avatar_url: string | null;
    followers_count: number;
    market_focus: string[] | null;
    credibility_score: number;
    verified_count: number;
    pending_count: number;
    hit_rate: number | null;
    fetch_enabled: boolean;
    last_fetched_at: string | null;
    last_activity_at: string | null;
    collected_tweets: number;
    analyzed_tweets: number;
    processing_tweets: number;
    failed_tweets: number;
    ingestion_stage: BloggerIngestionStage;
  }>;
  total: number;
}

export async function listMyBloggers(): Promise<FollowedBloggerListResponse> {
  const res = await authFetch(`${API_BASE}/api/me/bloggers`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Failed to list followed bloggers");
  return res.json() as Promise<FollowedBloggerListResponse>;
}

export interface Conversation {
  id: string;
  user_id: string;
  title: string | null;
  status: string;
  message_count: number;
  last_message_at: string | null;
  created_at: string;
}

export interface ConversationListItem {
  id: string;
  title: string | null;
  status: string;
  message_count: number;
  last_message_at: string | null;
  last_message_preview: string | null;
  created_at: string;
}

export interface ChatMessage {
  id: string;
  role: string;
  content: string;
  tool_calls: Record<string, unknown> | null;
  sequence: number;
  created_at: string;
}

export async function createConversation(title?: string) {
  const res = await authFetch(`${API_BASE}/api/chat/conversations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: title || null }),
  });
  if (!res.ok) throw new Error("Failed to create conversation");
  return res.json() as Promise<Conversation>;
}

export async function listConversations(params?: {
  status?: string;
  limit?: number;
  cursor?: string;
}) {
  const sp = new URLSearchParams();
  if (params?.status) sp.set("status", params.status);
  if (params?.limit) sp.set("limit", String(params.limit));
  if (params?.cursor) sp.set("cursor", params.cursor);
  const res = await authFetch(
    `${API_BASE}/api/chat/conversations?${sp.toString()}`,
    { cache: "no-store" },
  );
  if (!res.ok) throw new Error("Failed to list conversations");
  return res.json() as Promise<{
    items: ConversationListItem[];
    next_cursor: string | null;
    has_more: boolean;
  }>;
}

export async function deleteConversation(conversationId: string) {
  const res = await authFetch(
    `${API_BASE}/api/chat/conversations/${conversationId}`,
    { method: "DELETE" },
  );
  if (!res.ok) throw new Error("Failed to delete conversation");
}

export async function updateConversationTitle(
  conversationId: string,
  title: string,
) {
  const res = await authFetch(
    `${API_BASE}/api/chat/conversations/${conversationId}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    },
  );
  if (!res.ok) throw new Error("Failed to update conversation");
  return res.json() as Promise<Conversation>;
}

export async function listMessages(
  conversationId: string,
  params?: { limit?: number; cursor?: string; direction?: string },
) {
  const sp = new URLSearchParams();
  if (params?.limit) sp.set("limit", String(params.limit));
  if (params?.cursor) sp.set("cursor", params.cursor);
  if (params?.direction) sp.set("direction", params.direction);
  const res = await authFetch(
    `${API_BASE}/api/chat/conversations/${conversationId}/messages?${sp.toString()}`,
    { cache: "no-store" },
  );
  if (!res.ok) throw new Error("Failed to list messages");
  return res.json() as Promise<{
    items: ChatMessage[];
    next_cursor: string | null;
    has_more: boolean;
  }>;
}

// ============================================================
// Tracking API
// ============================================================

export interface TrackingItem {
  id: string;
  user_id: string;
  ticker: string;
  status: "active" | "paused" | "deleted";
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  instrument: {
    symbol?: string;
    resolved_name?: string;
    name?: string;
    market?: string;
    asset_type?: string;
    validation_status?: string;
    validation_sources?: string[];
    price_proxy_symbol?: string;
    price_proxy_disclosure?: string;
  } | null;
  monitor: {
    intelligence_24h?: number;
    direction?: "bullish" | "bearish" | "mixed" | "neutral";
    direction_trend?: "up" | "down" | "flat";
    bullish_count?: number;
    bearish_count?: number;
    active_predictions?: number;
    latest_prediction_sentiment?: string | null;
    risk_count?: number;
    latest_title?: string | null;
    latest_seen_at?: string | null;
    alerts?: Array<{ type: string; level: string; message: string }>;
  };
}

export interface TrackingListResponse {
  items: TrackingItem[];
  total: number;
  summary: { intelligence_24h: number; attention: number };
}

export interface TrackingValidation {
  accepted: boolean;
  reason: string;
  instrument: TrackingItem["instrument"];
}

export async function validateTracking(ticker: string): Promise<TrackingValidation> {
  const res = await authFetch(`${API_BASE}/api/tracking/validate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ticker }),
  });
  if (!res.ok) throw new Error("标的校验失败");
  return res.json() as Promise<TrackingValidation>;
}

export async function listTracking(): Promise<TrackingListResponse> {
  const res = await authFetch(`${API_BASE}/api/tracking/`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Failed to list tracking");
  return res.json() as Promise<TrackingListResponse>;
}

export async function createTracking(ticker: string): Promise<TrackingItem> {
  const res = await authFetch(`${API_BASE}/api/tracking/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ticker }),
  });
  if (!res.ok) {
    const payload = await res.json().catch(() => null) as { detail?: string } | null;
    throw new Error(payload?.detail || "添加标的失败");
  }
  return res.json() as Promise<TrackingItem>;
}

export async function updateTracking(
  id: string,
  data: { status?: string },
): Promise<TrackingItem> {
  const res = await authFetch(`${API_BASE}/api/tracking/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to update tracking");
  return res.json() as Promise<TrackingItem>;
}

export async function deleteTracking(id: string): Promise<void> {
  const res = await authFetch(`${API_BASE}/api/tracking/${id}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Failed to delete tracking");
}

// ============================================================
// Retrieval Debug API
// ============================================================

export interface RetrievalResult {
  unique_id: string;
  content: string;
  source_type: string;
  metadata: Record<string, unknown>;
  score: number;
}

export interface RetrievalDebugResponse {
  intent: Record<string, unknown>;
  paths: {
    tweets: RetrievalResult[];
    analyses: RetrievalResult[];
    structured: RetrievalResult[];
    bm25: RetrievalResult[];
  };
  es_debug?: {
    index?: string;
    query?: Record<string, unknown> | null;
    raw_hits?: Array<Record<string, unknown>>;
    results?: RetrievalResult[];
    error?: string;
  };
  fused: RetrievalResult[];
  reranked: RetrievalResult[];
  rerank_debug?: {
    input_count: number;
    selected_indices: Array<{ index: number; score: number }>;
  };
  latency_ms: Record<string, number>;
}

export async function debugRetrieve(
  query: string,
  ticker?: string,
  bloggerFilter?: string[],
): Promise<RetrievalDebugResponse> {
  const res = await authFetch(`${API_BASE}/api/debug/retrieve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query,
      ticker: ticker || null,
      blogger_filter: bloggerFilter?.length ? bloggerFilter : null,
    }),
  });
  if (!res.ok) throw new Error("Failed to debug retrieve");
  return res.json() as Promise<RetrievalDebugResponse>;
}

export interface EsAdminStats {
  elasticsearch: {
    alias: string;
    current_write_index: string | null;
    total: number;
    source_counts: Record<string, number>;
  };
  content_chunks: number;
  vector_store: {
    public_signals: number;
  };
  index_jobs: Record<string, Record<string, number>>;
}

export interface RuntimeStats {
  queues: Record<string, number>;
  outbox: {
    statuses: Record<string, number>;
    oldest_pending_age_seconds: number;
  };
  index_jobs: Record<string, Record<string, number>>;
  tweet_analysis: Record<string, number>;
  vision: {
    statuses: Record<string, number>;
    attempts: number;
    average_confidence: number;
    assets: Record<string, number>;
    usage: {
      input_tokens: number;
      output_tokens: number;
      total_tokens: number;
      provider_cost_usd: number;
    };
  };
  prediction_verification: {
    enabled: boolean;
    interval_minutes: number;
    batch_size: number;
    task: {
      status: "never_run" | "running" | "success" | "failed";
      task_id: string | null;
      last_started_at: string | null;
      last_finished_at: string | null;
      last_success_at: string | null;
      last_error_at: string | null;
      last_error: string | null;
      consecutive_failures: number;
      last_result: Record<string, number | string>;
      next_scheduled_at: string | null;
    };
    sources: Record<string, {
      label: string;
      status: "unknown" | "healthy" | "degraded" | "failed";
      provider: string | null;
      last_checked_at: string | null;
      last_success_at: string | null;
      last_error_at: string | null;
      last_error: string | null;
      consecutive_failures: number;
      total_calls: number;
      total_successes: number;
      total_failures: number;
      fallback_count: number;
    }>;
    alerts: Array<{ level: string; source: string; message: string }>;
  };
  database_pool: string;
}

export async function fetchRuntimeStats(): Promise<RuntimeStats> {
  const res = await authFetch(`${API_BASE}/api/admin/runtime/stats`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch runtime stats");
  return res.json() as Promise<RuntimeStats>;
}

export interface IndexJobItem {
  content_chunk_id: string;
  target: string;
  status: string;
  attempts: number;
  error_message?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export async function fetchEsAdminStats(): Promise<EsAdminStats> {
  const res = await authFetch(`${API_BASE}/api/admin/es/stats`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch ES stats");
  return res.json() as Promise<EsAdminStats>;
}

export async function fetchEsIndexJobs(params?: {
  target?: string;
  status?: string;
  limit?: number;
  offset?: number;
}): Promise<{ items: IndexJobItem[]; total: number }> {
  const sp = new URLSearchParams();
  if (params?.target) sp.set("target", params.target);
  if (params?.status) sp.set("status", params.status);
  sp.set("limit", String(params?.limit ?? 50));
  sp.set("offset", String(params?.offset ?? 0));
  const res = await authFetch(`${API_BASE}/api/admin/es/jobs?${sp.toString()}`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Failed to fetch index jobs");
  return res.json() as Promise<{ items: IndexJobItem[]; total: number }>;
}

export async function rebuildEsAlias(params?: {
  batchSize?: number;
  targetIndex?: string;
  switchAlias?: boolean;
}): Promise<{ task_id: string; status: string }> {
  const sp = new URLSearchParams();
  sp.set("batch_size", String(params?.batchSize ?? 500));
  if (params?.targetIndex) sp.set("target_index", params.targetIndex);
  if (params?.switchAlias != null) sp.set("switch_alias", String(params.switchAlias));
  const res = await authFetch(`${API_BASE}/api/admin/es/alias/rebuild?${sp.toString()}`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to rebuild ES alias");
  return res.json() as Promise<{ task_id: string; status: string }>;
}

export async function reconcileIndexes(batchSize = 1000): Promise<{ task_id: string; status: string }> {
  const res = await authFetch(
    `${API_BASE}/api/admin/es/reconcile?batch_size=${batchSize}`,
    { method: "POST" },
  );
  if (!res.ok) throw new Error("Failed to reconcile indexes");
  return res.json() as Promise<{ task_id: string; status: string }>;
}

export { getAccessToken };
