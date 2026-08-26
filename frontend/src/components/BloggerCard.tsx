import Link from "next/link";
import AppIcon from "@/components/AppIcon";
import type { BloggerIngestionStage } from "@/lib/api";
import { formatDate } from "@/lib/datetime";

export interface BloggerListItem {
  id: string;
  handle: string;
  name: string;
  bio: string | null;
  avatar_url: string | null;
  followers_count: number;
  market_focus: string[] | null;
  credibility_score: number;
  score_status?: string;
  score_label?: string;
  sample_confidence?: number;
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
}

const STAGE_COPY: Record<BloggerIngestionStage, { label: string; detail: string }> = {
  syncing: { label: "首次同步中", detail: "正在获取公开内容" },
  analyzing: { label: "正在分析", detail: "文本与图片处理中" },
  ready: { label: "正常采集", detail: "内容会持续自动更新" },
  attention: { label: "部分失败", detail: "已有内容仍可查看" },
  paused: { label: "已暂停", detail: "不会继续定时采集" },
};

interface BloggerCardProps {
  blogger: BloggerListItem;
  onUnfollow?: () => void;
  unfollowing?: boolean;
}

export default function BloggerCard({ blogger, onUnfollow, unfollowing = false }: BloggerCardProps) {
  const stage = STAGE_COPY[blogger.ingestion_stage];
  const activity = blogger.last_activity_at || blogger.last_fetched_at;
  return <article className={`source-library-row ${onUnfollow ? "has-action" : ""}`}>
    <Link href={`/sources/${encodeURIComponent(blogger.handle)}`} className="source-library-main">
      <div className="source-library-identity">
        {blogger.avatar_url ? <img src={blogger.avatar_url} alt="" /> : <span className="source-avatar">{blogger.handle.replace("@", "").slice(0, 2).toUpperCase()}</span>}
        <div>
          <strong>{blogger.name || blogger.handle}</strong>
          <span>@{blogger.handle.replace(/^@/, "")}</span>
        </div>
      </div>
      <div className="source-library-copy">
        <p>{blogger.bio || "该信息源尚未补充简介。"}</p>
        <div>{(blogger.market_focus ?? []).slice(0, 3).map((focus) => <span key={focus}>{focus}</span>)}</div>
      </div>
      <div className={`source-library-state state-${blogger.ingestion_stage}`}>
        <i />
        <span><strong>{stage.label}</strong><small>{stage.detail}</small></span>
      </div>
      <div className="source-library-output">
        <strong>{blogger.analyzed_tweets}</strong>
        <span>条已提取</span>
        <small>{activity ? formatDate(activity) : "等待首次同步"}</small>
      </div>
      <AppIcon name="arrow" className="source-library-arrow" />
    </Link>
    {onUnfollow && <button
      type="button"
      className="source-library-unfollow"
      onClick={onUnfollow}
      disabled={unfollowing}
      aria-label={`取消关注 @${blogger.handle.replace(/^@/, "")}`}
    >{unfollowing ? "处理中…" : "取消关注"}</button>}
  </article>;
}
