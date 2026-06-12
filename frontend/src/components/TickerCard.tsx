interface TickerCardProps {
  ticker: string;
  mentionCount: number;
  bloggers: string[];
  consensus: string;
  bullishCount: number;
  bearishCount: number;
  recommendationScore: number;
  summary: string;
}

export default function TickerCard({
  ticker,
  mentionCount,
  bloggers,
  consensus,
  bullishCount,
  bearishCount,
  recommendationScore,
  summary,
}: TickerCardProps) {
  const consensusConfig: Record<string, { label: string; color: string }> = {
    strong_buy: { label: "强烈推荐", color: "bg-green-600 text-white" },
    buy: { label: "推荐买入", color: "bg-green-400 text-white" },
    neutral: { label: "中性观望", color: "bg-gray-400 text-white" },
    sell: { label: "建议卖出", color: "bg-red-400 text-white" },
    strong_sell: { label: "强烈看空", color: "bg-red-600 text-white" },
  };

  const config = consensusConfig[consensus] || consensusConfig.neutral;

  return (
    <div className="bg-white rounded-lg shadow p-5 border-t-4 border-blue-500">
      <div className="flex justify-between items-start mb-3">
        <div>
          <h3 className="text-xl font-bold">{ticker}</h3>
          <span className="text-xs text-gray-500">
            {mentionCount} 条推文提及 · {bloggers.length} 位博主
          </span>
        </div>
        <div className="text-right">
          <span className={`px-3 py-1 rounded-full text-sm font-semibold ${config.color}`}>
            {config.label}
          </span>
          <p className="text-2xl font-bold mt-1">{recommendationScore}</p>
          <p className="text-xs text-gray-500">推荐指数</p>
        </div>
      </div>

      <div className="flex gap-4 mb-3 text-sm">
        <span className="text-green-600">看好 {bullishCount}</span>
        <span className="text-red-600">看空 {bearishCount}</span>
      </div>

      <p className="text-sm text-gray-700 mb-3">{summary}</p>

      <div className="flex flex-wrap gap-1">
        {bloggers.map((b) => (
          <span
            key={b}
            className="bg-gray-100 text-gray-600 px-2 py-0.5 rounded text-xs"
          >
            {b}
          </span>
        ))}
      </div>
    </div>
  );
}
