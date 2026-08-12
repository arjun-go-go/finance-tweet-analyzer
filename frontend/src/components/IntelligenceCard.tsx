import AppIcon from "@/components/AppIcon";
import type { IntelligenceFeedItem } from "@/lib/api";

const directionMap: Record<string, string> = { bullish: "看多", bearish: "看空", neutral: "中性", mixed: "分歧" };
const lifecycleMap: Record<string, string> = { new: "新出现", developing: "持续发展", confirmed: "交叉确认", reversed: "观点反转", expired: "已过期" };

function formatTime(value: string) {
  return new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

export default function IntelligenceCard({ item, selected, onSelect }: { item: IntelligenceFeedItem; selected?: boolean; onSelect: () => void }) {
  return (
    <article className={`intelligence-card ${selected ? "is-selected" : ""}`}>
      <button className="intelligence-card-main" onClick={onSelect}>
        <span className={`evidence-spine ${item.kind === "risk" ? "is-risk" : ""}`}><span /></span>
        <span className="intelligence-copy">
          <span className="intelligence-meta">
            <span className={`direction direction-${item.direction}`}>{directionMap[item.direction] || "中性"}</span>
            <span className={`lifecycle-chip lifecycle-${item.lifecycle}`}>{lifecycleMap[item.lifecycle] || "新出现"}</span>
            <span>{item.kind === "risk" ? "风险线索" : "观点更新"}</span>
            <span>{item.time_bucket} · {formatTime(item.published_at)}</span>
          </span>
          <strong>{item.title}</strong>
          <span className="intelligence-summary">{item.summary}</span>
          <span className="intelligence-footer">
            <span>@{item.author}</span>
            {item.tickers.slice(0, 3).map((ticker) => <span className="ticker-chip" key={ticker}>{ticker}</span>)}
            <span className="match-reason">{item.match_reasons.join(" · ")}</span>
            {item.event_count > 1 && <span className="corroboration-chip">{item.event_count} 次更新</span>}
            {item.corroboration_count > 1 && <span className="corroboration-chip">{item.corroboration_count} 源印证</span>}
          </span>
        </span>
        <span className="importance"><small>重要性</small><b>{item.importance_score}</b></span>
        <AppIcon name="arrow" className="intelligence-arrow" />
      </button>
    </article>
  );
}
