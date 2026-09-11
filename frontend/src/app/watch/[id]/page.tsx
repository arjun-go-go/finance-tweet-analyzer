"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import ActivityTweetCard, { type ActivityTweet } from "@/components/ActivityTweetCard";
import AppIcon from "@/components/AppIcon";
import ConfirmDialog from "@/components/ConfirmDialog";
import { PageEmpty, PageError, PageLoading } from "@/components/PageState";
import {
  createTracking,
  deleteTracking,
  fetchTickerSummaries,
  fetchTweets,
  listTracking,
  type TickerSummary,
  type TrackingItem,
} from "@/lib/api";
import { formatDateTime } from "@/lib/datetime";

const MARKET_LABEL: Record<string, string> = {
  CN: "A股",
  HK: "港股",
  US: "美股",
  COMMODITY: "商品",
  CRYPTO: "加密货币",
};

const CONSENSUS_LABEL: Record<string, string> = {
  strong_buy: "多数看多",
  buy: "偏多",
  strong_sell: "多数看空",
  sell: "偏空",
  mixed: "观点分歧",
  neutral: "中性",
  none: "暂无方向",
};

interface TweetFeedResponse {
  items: ActivityTweet[];
  total: number;
}

function percent(value: number, total: number) {
  return total > 0 ? Math.round((value / total) * 100) : 0;
}

export default function WatchAssetDetailPage() {
  const params = useParams<{ id: string }>();
  const ticker = decodeURIComponent(params.id).trim().toUpperCase();
  const [tweets, setTweets] = useState<ActivityTweet[]>([]);
  const [tweetTotal, setTweetTotal] = useState(0);
  const [summary, setSummary] = useState<TickerSummary | null>(null);
  const [tracking, setTracking] = useState<TrackingItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [tweetData, summaryData, trackingData] = await Promise.all([
        fetchTweets({ ticker, include_analysis: true, limit: 100 }) as Promise<TweetFeedResponse>,
        fetchTickerSummaries({ limit: 100 }),
        listTracking(),
      ]);
      setTweets(tweetData.items || []);
      setTweetTotal(tweetData.total || 0);
      setSummary(
        summaryData.items.find((item) => item.result.ticker.toUpperCase() === ticker)?.result || null,
      );
      setTracking(
        trackingData.items.find((item) => item.ticker.toUpperCase() === ticker) || null,
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "标的观点加载失败");
    } finally {
      setLoading(false);
    }
  }, [ticker]);

  useEffect(() => { void load(); }, [load]);

  const follow = async () => {
    setBusy(true);
    setNotice("");
    try {
      const item = await createTracking(ticker);
      setTracking(item);
      setNotice(`已关注 ${ticker}`);
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : "关注失败，请稍后重试");
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!tracking) return;
    setConfirming(false);
    setBusy(true);
    setNotice("");
    try {
      await deleteTracking(tracking.id);
      setTracking(null);
      setNotice(`已取消关注 ${ticker}，历史观点仍保留。`);
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : "取消关注失败，请稍后重试");
    } finally {
      setBusy(false);
    }
  };

  const targetClaim = useMemo(
    () => tweets
      .flatMap((tweet) => tweet.analysis?.claims || [])
      .find((claim) => claim.instrument.symbol.toUpperCase() === ticker),
    [ticker, tweets],
  );

  if (loading) return <PageLoading label="正在读取标的观点" />;
  if (error) return <PageError detail={error} onRetry={load} />;

  const trackingInstrument = tracking?.instrument;
  const claimInstrument = targetClaim?.instrument;
  const market = claimInstrument?.market || claimInstrument?.market_hint || trackingInstrument?.market || "";
  const instrumentName = claimInstrument?.original_name
    || trackingInstrument?.resolved_name
    || trackingInstrument?.name
    || "已核验标的";
  const monitor = tracking?.monitor || {};
  const bullish = summary?.bullish_count ?? monitor.bullish_count ?? 0;
  const bearish = summary?.bearish_count ?? monitor.bearish_count ?? 0;
  const neutral = summary?.neutral_count ?? Math.max((monitor.intelligence_24h || 0) - bullish - bearish, 0);
  const claimTotal = summary?.mention_count ?? bullish + bearish + neutral;
  const relatedClaimCount = summary?.related_claim_count ?? claimTotal;
  const hasEffectiveViews = summary?.has_effective_views ?? claimTotal > 0;
  const bloggerCount = hasEffectiveViews
    ? summary?.bloggers.length ?? 0
    : summary?.related_bloggers?.length ?? new Set(tweets.map((tweet) => tweet.author_handle)).size;
  const consensus = summary?.consensus || monitor.direction || "none";
  const latestTweet = tweets[0];

  return (
    <div className="product-page asset-prototype-page">
      <Link className="insight-back" href="/watch"><AppIcon name="arrow" />返回标的</Link>

      <header className="asset-prototype-hero">
        <div>
          <h1>{ticker}</h1>
          <span>{MARKET_LABEL[market] || market || "市场待确认"} · {instrumentName}</span>
        </div>
        <div>
          <strong>{hasEffectiveViews ? CONSENSUS_LABEL[consensus] || "暂无方向" : "仅供参考"}</strong>
          <span>最近观点：{latestTweet ? formatDateTime(latestTweet.published_at) : "暂无"}</span>
        </div>
      </header>

      {notice && <p className="asset-directory-notice" role="status">{notice}</p>}

      <div className="asset-prototype-layout">
        <main>
          <section className="asset-consensus-card">
            <span>可统计的博主本人观点</span>
            <h2>{summary?.summary || `${ticker} 暂无新的明确观点`}</h2>
            <p>
              {hasEffectiveViews
                ? `共收录 ${claimTotal} 项可追溯观点，来自 ${bloggerCount} 位博主。统计只计算博主本人对该标的的明确判断。`
                : relatedClaimCount
                  ? `已收录 ${relatedClaimCount} 项相关信息，但目前仅属于商业相关、引用、第三方或事实信息，不参与多空统计。`
                  : "系统会等待博主发布带有明确标的、方向和证据的观点。"}
            </p>
            {hasEffectiveViews ? <div>
              <div><strong>{percent(bullish, claimTotal)}%</strong><span>看多 · {bullish}</span></div>
              <div><strong>{percent(neutral, claimTotal)}%</strong><span>中性 · {neutral}</span></div>
              <div><strong>{percent(bearish, claimTotal)}%</strong><span>看空 · {bearish}</span></div>
            </div> : <p className="asset-consensus-empty">没有符合统计口径的博主本人观点，因此不生成多空比例或推荐分数。</p>}
          </section>

          <section className="asset-opinion-section asset-tweet-timeline">
            <header><h2>全部相关信息与证据</h2><span>{tweetTotal} 条相关推文</span></header>
            {tweets.length ? (
              <div className="activity-feed">
                {tweets.map((tweet) => <ActivityTweetCard key={tweet.id} tweet={tweet} />)}
              </div>
            ) : (
              <PageEmpty title="暂无可追溯观点" detail="关注关系可以保留；新的相关推文完成分析后会出现在这里。" />
            )}
          </section>
        </main>

        <aside className="asset-prototype-aside">
          <section>
            <span>标的身份</span>
            <div className="asset-identity-proof">
              <b><AppIcon name="check" /></b>
              <div><strong>{ticker} · {MARKET_LABEL[market] || market || "已验证"}</strong><small>{instrumentName}</small></div>
            </div>
          </section>
          <section>
            <span>信息覆盖</span>
            <dl>
              <div><dt>有效观点</dt><dd>{claimTotal} 项</dd></div>
              <div><dt>相关信息</dt><dd>{relatedClaimCount} 项</dd></div>
              <div><dt>相关推文</dt><dd>{tweetTotal} 条</dd></div>
              <div><dt>涉及博主</dt><dd>{bloggerCount} 位</dd></div>
              <div><dt>关注状态</dt><dd>{tracking ? "已关注" : "未关注"}</dd></div>
            </dl>
          </section>
          <section>
            <span>统计口径</span>
            <h3>观点不等于交易建议</h3>
            <p>这里只将博主本人的明确判断纳入统计；引用观点、事实信息，以及与推广方直接相关或关系待确认的观点仅供参考。</p>
            {trackingInstrument?.price_proxy_disclosure && <small>{trackingInstrument.price_proxy_disclosure}</small>}
          </section>
          <div>
            {tracking
              ? <button className="button-secondary" type="button" disabled={busy} onClick={() => setConfirming(true)}>取消关注</button>
              : <button className="button-primary" type="button" disabled={busy} onClick={() => void follow()}>{busy ? "处理中…" : "关注标的"}</button>}
          </div>
        </aside>
      </div>

      <ConfirmDialog
        open={confirming}
        title={`取消关注 ${ticker}？`}
        message="取消后不再进入你的关注列表，历史推文和观点不会删除。"
        confirmText="确认取消"
        variant="danger"
        onConfirm={remove}
        onCancel={() => setConfirming(false)}
      />
    </div>
  );
}
