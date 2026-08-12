import Link from "next/link";
import AppIcon from "@/components/AppIcon";

export interface BloggerListItem { handle: string; name: string; bio: string | null; avatar_url: string | null; followers_count: number; market_focus: string[] | null; credibility_score: number; verified_count: number; pending_count: number; hit_rate: number | null; }

export default function BloggerCard({ blogger, rank }: { blogger: BloggerListItem; rank?: number }) {
  const confidence = Math.round(blogger.credibility_score);
  const level = confidence >= 65 ? "high" : confidence >= 45 ? "medium" : "low";
  return <Link href={`/bloggers/${encodeURIComponent(blogger.handle)}`} className="source-card">
    <div className={`source-score-line ${level}`} />
    <div className="source-card-head">
      <div className="source-identity">
        {blogger.avatar_url ? <img src={blogger.avatar_url} alt="" /> : <span className="source-avatar">{blogger.handle.replace("@", "").slice(0, 2).toUpperCase()}</span>}
        <div><strong>{blogger.name || blogger.handle}</strong><span>{blogger.handle}</span></div>
      </div>
      {rank && <span className="source-rank">#{String(rank).padStart(2, "0")}</span>}
    </div>
    <p className="source-bio">{blogger.bio || "该信息源尚未补充简介。"}</p>
    <div className="source-focus">{(blogger.market_focus ?? []).slice(0, 4).map((focus) => <span key={focus}>{focus}</span>)}</div>
    <div className="source-evidence"><div><span>可信度</span><strong>{confidence}</strong></div><div><span>已验证观点</span><strong>{blogger.verified_count}</strong></div><div><span>历史命中率</span><strong>{blogger.hit_rate == null ? "—" : `${Math.round(blogger.hit_rate * 100)}%`}</strong></div></div>
    <footer><span>{blogger.followers_count.toLocaleString()} 关注者</span><span>{blogger.pending_count} 条待验证</span><AppIcon name="arrow" className="h-4 w-4" /></footer>
  </Link>;
}
