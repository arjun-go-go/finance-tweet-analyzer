const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
  kind: "opinion" | "risk";
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
    kind: "all" | "risk" | "opinion";
    generated_at: string;
  };
}

export async function fetchIntelligenceFeed(
  limit = 20,
  window: "24h" | "3d" | "7d" = "24h",
  kind: "all" | "risk" | "opinion" = "all",
): Promise<IntelligenceFeedResponse> {
  const params = new URLSearchParams({ limit: String(limit), window, kind });
  const res = await authFetch(`${API_BASE}/api/intelligence/feed?${params.toString()}`, { cache: "no-store" });
  if (!res.ok) throw new Error("无法加载今日情报，请检查后端服务或稍后重试。");
  return res.json() as Promise<IntelligenceFeedResponse>;
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
  }>;
  total: number;
}

export interface BookmarkedTweetListResponse {
  items: Array<{
    id: string;
    tweet_id: string;
    author_handle: string;
    author_name: string;
    content: string;
    published_at: string;
    status: string;
    metrics: Record<string, unknown> | null;
  }>;
  total: number;
}

export interface AnalysisJobItem {
  id: string;
  kind: string;
  target_id: string;
  status: string;
  error_code: string | null;
  error_summary: string | null;
  reused_result: boolean;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface AnalysisJobListResponse {
  items: AnalysisJobItem[];
  total: number;
}

export interface AnalysisJobConfirmResponse {
  confirmed: string[];
  skipped: string[];
}

export async function listMyBloggers(): Promise<FollowedBloggerListResponse> {
  const res = await authFetch(`${API_BASE}/api/me/bloggers`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Failed to list followed bloggers");
  return res.json() as Promise<FollowedBloggerListResponse>;
}

export async function listMyTweets(): Promise<BookmarkedTweetListResponse> {
  const res = await authFetch(`${API_BASE}/api/me/tweets`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Failed to list bookmarked tweets");
  return res.json() as Promise<BookmarkedTweetListResponse>;
}

export async function listMyAnalysisJobs(): Promise<AnalysisJobListResponse> {
  const res = await authFetch(`${API_BASE}/api/me/analysis-jobs`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Failed to list analysis jobs");
  return res.json() as Promise<AnalysisJobListResponse>;
}

export async function createAnalysisJob(body: {
  kind: "tweet_analysis" | "blogger_analysis";
  target_id: string;
}): Promise<AnalysisJobItem> {
  const res = await authFetch(`${API_BASE}/api/me/analysis-jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new Error(data?.detail || "Failed to create analysis job");
  }
  return res.json() as Promise<AnalysisJobItem>;
}

export async function confirmAnalysisJobs(
  jobIds: string[],
): Promise<AnalysisJobConfirmResponse> {
  const res = await authFetch(`${API_BASE}/api/me/analysis-jobs/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_ids: jobIds }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new Error(data?.detail || "Failed to confirm analysis jobs");
  }
  return res.json() as Promise<AnalysisJobConfirmResponse>;
}

export interface Conversation {
  id: string;
  user_id: string;
  title: string | null;
  status: string;
  message_count: number;
  total_tokens: number;
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
  token_count: number;
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
// Documents API
// ============================================================

export interface DocumentItem {
  id: string;
  title: string;
  source_type: "upload" | "url" | "paste";
  status: "pending" | "processing" | "ready" | "indexed" | "error";
  char_count: number;
  chunk_count: number;
  tickers: string[];
  publish_date: string | null;
  error_detail: string | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentListResponse {
  items: DocumentItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface DocumentStatusResponse {
  id: string;
  status: string;
  chunk_count: number;
  error_detail: string | null;
}

export async function listDocuments(params?: {
  page?: number;
  page_size?: number;
}): Promise<DocumentListResponse> {
  const sp = new URLSearchParams();
  if (params?.page) sp.set("page", String(params.page));
  if (params?.page_size) sp.set("page_size", String(params.page_size));
  const res = await authFetch(
    `${API_BASE}/api/documents?${sp.toString()}`,
    { cache: "no-store" },
  );
  if (!res.ok) throw new Error("Failed to list documents");
  return res.json() as Promise<DocumentListResponse>;
}

export async function uploadDocument(
  file: File,
  title?: string,
  tickers?: string[],
): Promise<DocumentItem> {
  const formData = new FormData();
  formData.append("file", file);
  if (title) formData.append("title", title);
  if (tickers) formData.append("tickers", JSON.stringify(tickers));
  const res = await authFetch(`${API_BASE}/api/documents/upload`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) throw new Error("Failed to upload document");
  return res.json() as Promise<DocumentItem>;
}

export async function submitUrl(
  url: string,
  title?: string,
  tickers?: string[],
): Promise<DocumentItem> {
  const res = await authFetch(`${API_BASE}/api/documents/url`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, title: title || null, tickers: tickers || [] }),
  });
  if (!res.ok) throw new Error("Failed to submit URL document");
  return res.json() as Promise<DocumentItem>;
}

export async function pasteDocument(
  title: string,
  content: string,
  tickers?: string[],
): Promise<DocumentItem> {
  const res = await authFetch(`${API_BASE}/api/documents/paste`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, content, tickers: tickers || [] }),
  });
  if (!res.ok) throw new Error("Failed to paste document");
  return res.json() as Promise<DocumentItem>;
}

export async function deleteDocument(id: string): Promise<void> {
  const res = await authFetch(`${API_BASE}/api/documents/${id}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Failed to delete document");
}

export async function getDocumentStatus(
  id: string,
): Promise<DocumentStatusResponse> {
  const res = await authFetch(`${API_BASE}/api/documents/${id}/status`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Failed to get document status");
  return res.json() as Promise<DocumentStatusResponse>;
}

// ============================================================
// Reports API
// ============================================================

export interface ReportListItem {
  id: string;
  ticker: string;
  title: string | null;
  trigger_type: "manual" | "chat" | "scheduled";
  consensus: string | null;
  status: "generating" | "done" | "failed";
  latency_ms: number | null;
  created_at: string;
}

export interface ReportSection {
  name?: string;
  title: string;
  content: string;
  source_type: string;
  error?: string | null;
}

export interface ReportCitation {
  index: number;
  source_type: string;
  title: string;
  snippet: string;
  metadata: Record<string, unknown>;
}

export interface ReportDetail {
  id: string;
  user_id: string;
  ticker: string;
  title: string | null;
  trigger_type: string;
  tracked_ticker_id: string | null;
  sections: Record<string, ReportSection>;
  citations: ReportCitation[];
  summary: string | null;
  consensus: string | null;
  token_usage: Record<string, number> | null;
  latency_ms: number | null;
  status: string;
  error_detail: string | null;
  created_at: string;
}

export interface ReportListResponse {
  items: ReportListItem[];
  total: number;
}

export async function generateReport(
  ticker: string,
  timeRange?: string,
  focusAspects?: string[],
): Promise<{ id: string; status: string }> {
  const res = await authFetch(`${API_BASE}/api/reports/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ticker,
      time_range: timeRange || null,
      focus_aspects: focusAspects || [],
    }),
  });
  if (!res.ok) throw new Error("Failed to generate report");
  return res.json() as Promise<{ id: string; status: string }>;
}

export async function listReports(params?: {
  ticker?: string;
  page?: number;
  size?: number;
}): Promise<ReportListResponse> {
  const sp = new URLSearchParams();
  if (params?.ticker) sp.set("ticker", params.ticker);
  if (params?.page) sp.set("page", String(params.page));
  if (params?.size) sp.set("size", String(params.size));
  const res = await authFetch(
    `${API_BASE}/api/reports?${sp.toString()}`,
    { cache: "no-store" },
  );
  if (!res.ok) throw new Error("Failed to list reports");
  return res.json() as Promise<ReportListResponse>;
}

export async function getReport(id: string): Promise<ReportDetail> {
  const res = await authFetch(`${API_BASE}/api/reports/${id}`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Failed to get report");
  return res.json() as Promise<ReportDetail>;
}

export async function deleteReport(id: string): Promise<void> {
  const res = await authFetch(`${API_BASE}/api/reports/${id}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`Failed to delete report (${res.status}): ${body || res.statusText}`);
  }
}

// ---- Report SSE streaming ----

export interface ReportStreamCallbacks {
  onSnapshot?: (snapshot: Partial<ReportDetail>) => void;
  onIntent?: (intent: Record<string, unknown>) => void;
  onRetrievalProgress?: (data: {
    node: string;
    count: number;
    errors: Record<string, unknown>;
  }) => void;
  onFused?: (data: { count: number; error?: string | null }) => void;
  onReranked?: (citations: ReportCitation[]) => void;
  onSectionDone?: (section: ReportSection) => void;
  onSynthesized?: (data: {
    summary?: string;
    consensus?: string;
    recommendation?: string;
    latency_ms?: number;
  }) => void;
  onDone?: () => void;
  onError?: (err: string) => void;
}

/** Subscribe to a report's generation progress via SSE.
 * Returns an abort fn the caller invokes on unmount.
 */
export function streamReport(
  id: string,
  callbacks: ReportStreamCallbacks,
): () => void {
  const ac = new AbortController();

  (async () => {
    try {
      const token = getAccessToken();
      const res = await fetch(`${API_BASE}/api/reports/${id}/stream`, {
        method: "GET",
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          Accept: "text/event-stream",
        },
        signal: ac.signal,
      });
      if (!res.ok || !res.body) {
        callbacks.onError?.(`HTTP ${res.status}`);
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // SSE events are delimited by blank line
        let idx: number;
        while ((idx = buffer.indexOf("\n\n")) !== -1) {
          const raw = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);
          const lines = raw.split("\n");
          let event = "message";
          let data = "";
          for (const line of lines) {
            if (line.startsWith("event:")) event = line.slice(6).trim();
            else if (line.startsWith("data:")) data += line.slice(5).trim();
          }
          if (!data) continue;
          let payload: unknown;
          try {
            payload = JSON.parse(data);
          } catch {
            continue;
          }
          dispatch(event, payload, callbacks);
          if (event === "done" || event === "error") {
            ac.abort();
            return;
          }
        }
      }
    } catch (err: unknown) {
      if ((err as Error)?.name === "AbortError") return;
      callbacks.onError?.((err as Error)?.message || "stream failed");
    }
  })();

  return () => ac.abort();
}

function dispatch(
  event: string,
  payload: unknown,
  cb: ReportStreamCallbacks,
): void {
  const data = payload as Record<string, unknown>;
  switch (event) {
    case "snapshot":
      cb.onSnapshot?.(data as Partial<ReportDetail>);
      break;
    case "intent_parsed":
      cb.onIntent?.((data.intent || {}) as Record<string, unknown>);
      break;
    case "retrieval_progress":
      cb.onRetrievalProgress?.(data as never);
      break;
    case "fused":
      cb.onFused?.(data as never);
      break;
    case "reranked":
      cb.onReranked?.((data.citations || []) as ReportCitation[]);
      break;
    case "section_done":
      if (data.section) cb.onSectionDone?.(data.section as ReportSection);
      break;
    case "synthesized":
      cb.onSynthesized?.(data as never);
      break;
    case "done":
      cb.onDone?.();
      break;
    case "error":
      cb.onError?.((data.error as string) || "unknown error");
      break;
    case "ping":
      break;
    default:
      break;
  }
}

// ============================================================
// Tracking API
// ============================================================

export interface TrackingItem {
  id: string;
  user_id: string;
  ticker: string;
  frequency: "daily" | "weekly" | "manual";
  last_report_at: string | null;
  next_run_at: string | null;
  status: "active" | "paused" | "deleted";
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface TrackingListResponse {
  items: TrackingItem[];
  total: number;
}

export async function listTracking(): Promise<TrackingListResponse> {
  const res = await authFetch(`${API_BASE}/api/tracking`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Failed to list tracking");
  return res.json() as Promise<TrackingListResponse>;
}

export async function createTracking(
  ticker: string,
  frequency: string,
): Promise<TrackingItem> {
  const res = await authFetch(`${API_BASE}/api/tracking`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ticker, frequency }),
  });
  if (!res.ok) throw new Error("Failed to create tracking");
  return res.json() as Promise<TrackingItem>;
}

export async function updateTracking(
  id: string,
  data: { frequency?: string; status?: string },
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

export async function triggerTracking(
  id: string,
): Promise<{ report_id: string; status: string }> {
  const res = await authFetch(`${API_BASE}/api/tracking/${id}/trigger`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to trigger tracking");
  return res.json() as Promise<{ report_id: string; status: string }>;
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
    documents: RetrievalResult[];
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
  doc_chunks: number;
  vector_store: {
    public_signals: number;
    user_documents: number;
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
  database_pool: string;
}

export async function fetchRuntimeStats(): Promise<RuntimeStats> {
  const res = await authFetch(`${API_BASE}/api/admin/runtime/stats`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch runtime stats");
  return res.json() as Promise<RuntimeStats>;
}

export interface IndexJobItem {
  doc_chunk_id: string;
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
