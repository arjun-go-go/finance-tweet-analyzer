interface SentimentMap {
  bullish: number | null;
  bearish: number | null;
  neutral: number | null;
}

interface TopTicker {
  ticker: string;
  verified: number;
  hit_rate: number;
}

interface Props {
  credibilityScore: number;
  verifiedCount: number;
  pendingCount: number;
  hitRateOverall: number | null;
  hitRateBySentiment: SentimentMap;
  topTickers: TopTicker[];
}

const SENTIMENT_LABEL: Record<keyof SentimentMap, string> = {
  bullish: "看好",
  bearish: "看空",
  neutral: "中性",
};

export default function BloggerStatsHeader({
  credibilityScore,
  verifiedCount,
  pendingCount,
  hitRateOverall,
  hitRateBySentiment,
  topTickers,
}: Props) {
  const score = credibilityScore.toFixed(1);
  const scoreColor =
    credibilityScore >= 65
      ? "text-green-600"
      : credibilityScore >= 45
      ? "text-gray-700"
      : "text-red-600";

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-white rounded-lg shadow p-4">
          <p className="text-xs text-gray-500 mb-1">可信度（Bayesian）</p>
          <p className={`text-3xl font-bold ${scoreColor}`}>{score}</p>
          <p className="text-xs text-gray-500 mt-1">n={verifiedCount}</p>
        </div>
        <div className="bg-white rounded-lg shadow p-4">
          <p className="text-xs text-gray-500 mb-1">已标注</p>
          <p className="text-3xl font-bold">{verifiedCount}</p>
        </div>
        <div className="bg-white rounded-lg shadow p-4">
          <p className="text-xs text-gray-500 mb-1">待标注</p>
          <p className="text-3xl font-bold text-orange-500">{pendingCount}</p>
        </div>
        <div className="bg-white rounded-lg shadow p-4">
          <p className="text-xs text-gray-500 mb-1">总命中率</p>
          <p className="text-3xl font-bold">
            {hitRateOverall === null
              ? "—"
              : `${(hitRateOverall * 100).toFixed(0)}%`}
          </p>
        </div>
      </div>

      <div className="bg-white rounded-lg shadow p-4 grid md:grid-cols-2 gap-6">
        <div>
          <p className="text-sm font-semibold mb-2">情绪命中率</p>
          <div className="flex gap-3 text-sm">
            {(Object.keys(SENTIMENT_LABEL) as Array<keyof SentimentMap>).map(
              (k) => {
                const v = hitRateBySentiment[k];
                return (
                  <span key={k} className="flex items-center gap-1">
                    <span className="text-gray-500">{SENTIMENT_LABEL[k]}</span>
                    <span className="font-semibold">
                      {v === null ? "—" : `${(v * 100).toFixed(0)}%`}
                    </span>
                  </span>
                );
              },
            )}
          </div>
        </div>
        <div>
          <p className="text-sm font-semibold mb-2">高命中标的</p>
          {topTickers.length === 0 ? (
            <p className="text-xs text-gray-500">尚无足够数据</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {topTickers.map((t) => (
                <span
                  key={t.ticker}
                  className="bg-blue-100 text-blue-800 px-2 py-0.5 rounded text-xs"
                >
                  {t.ticker} {(t.hit_rate * 100).toFixed(0)}% (n={t.verified})
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
