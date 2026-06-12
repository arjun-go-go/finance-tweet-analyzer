import Link from "next/link";

export interface BloggerListItem {
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
}

export default function BloggerCard({ blogger }: { blogger: BloggerListItem }) {
  const score = blogger.credibility_score.toFixed(1);
  const scoreColor =
    blogger.credibility_score >= 65
      ? "text-green-600"
      : blogger.credibility_score >= 45
      ? "text-gray-700"
      : "text-red-600";

  return (
    <Link
      href={`/bloggers/${encodeURIComponent(blogger.handle)}`}
      className="bg-white rounded-lg shadow p-4 hover:shadow-md transition block"
    >
      <div className="flex items-center gap-3 mb-3">
        {blogger.avatar_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={blogger.avatar_url}
            alt={blogger.handle}
            className="w-10 h-10 rounded-full bg-gray-200 object-cover"
          />
        ) : (
          <div className="w-10 h-10 rounded-full bg-gray-200 flex items-center justify-center text-gray-500 text-sm font-bold">
            {blogger.handle.slice(1, 3).toUpperCase()}
          </div>
        )}
        <div className="flex-1 min-w-0">
          <p className="font-bold truncate">{blogger.handle}</p>
          <p className="text-xs text-gray-500 truncate">{blogger.name}</p>
        </div>
      </div>

      {blogger.bio && (
        <p className="text-xs text-gray-500 mb-2 line-clamp-2">{blogger.bio}</p>
      )}

      <div className="flex items-baseline gap-2 mb-2">
        <span
          className={`text-3xl font-bold ${scoreColor}`}
          title="可信度（Bayesian 平滑：α=β=5，n=0 时为 50）"
        >
          {score}
        </span>
        <span className="text-xs text-gray-500">
          (n={blogger.verified_count})
        </span>
      </div>

      <div className="flex flex-wrap gap-1.5 text-xs mb-2">
        <span className="bg-green-100 text-green-800 px-2 py-0.5 rounded">
          已标注 {blogger.verified_count}
        </span>
        <span className="bg-yellow-100 text-yellow-800 px-2 py-0.5 rounded">
          待标注 {blogger.pending_count}
        </span>
        {blogger.hit_rate !== null && (
          <span className="bg-blue-100 text-blue-800 px-2 py-0.5 rounded">
            命中率 {(blogger.hit_rate * 100).toFixed(0)}%
          </span>
        )}
      </div>

      <div className="flex items-center justify-between text-xs text-gray-500">
        <span>粉丝 {blogger.followers_count.toLocaleString()}</span>
        <div className="flex gap-1">
          {(blogger.market_focus ?? []).slice(0, 3).map((m) => (
            <span
              key={m}
              className="bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded"
            >
              {m}
            </span>
          ))}
        </div>
      </div>
    </Link>
  );
}
