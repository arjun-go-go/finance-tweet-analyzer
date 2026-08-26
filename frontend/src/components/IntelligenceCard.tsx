import AppIcon from "@/components/AppIcon";
import type { IntelligenceFeedItem } from "@/lib/api";

const DIRECTION_LABELS: Record<string, string> = {
  bullish: "看多",
  bearish: "看空",
  neutral: "中性",
  mixed: "分歧",
};

const KIND_LABELS: Record<string, string> = {
  opinion: "博主观点",
  risk: "风险线索",
  news: "市场动态",
};

function formatTime(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function evidenceLabel(item: IntelligenceFeedItem) {
  if (item.corroboration_count > 1) return "多源印证";
  if (item.confidence >= 0.75) return "较充分";
  return "单一来源";
}

export default function IntelligenceCard({
  item,
  selected,
  onSelect,
}: {
  item: IntelligenceFeedItem;
  selected?: boolean;
  onSelect: () => void;
}) {
  return (
    <article className={`today-signal ${selected ? "is-selected" : ""}`}>
      <button
        className="today-signal-main"
        onClick={onSelect}
        aria-pressed={selected}
        aria-controls="today-evidence-preview"
      >
        <span className={`today-signal-spine is-${item.kind}`} />
        <span className="today-signal-copy">
          <span className="today-signal-meta">
            <b className={`direction-${item.direction}`}>
              {DIRECTION_LABELS[item.direction] || "中性"}
            </b>
            <span>{KIND_LABELS[item.kind] || "投资观点"}</span>
            <span>@{item.author}</span>
            <span>{formatTime(item.published_at)}</span>
          </span>
          <strong>{item.title}</strong>
          <span className="today-signal-summary">{item.summary}</span>
          <span className="today-signal-foot">
            {item.tickers.slice(0, 4).map((ticker) => (
              <b key={ticker}>{ticker}</b>
            ))}
            <span>{item.match_reasons.join(" · ")}</span>
            {item.corroboration_count > 1 && (
              <span>{item.corroboration_count} 个独立来源</span>
            )}
          </span>
        </span>
        <span className="today-signal-proof">
          <small>证据</small>
          <b>{evidenceLabel(item)}</b>
        </span>
        <AppIcon name="arrow" className="today-signal-arrow" />
      </button>
    </article>
  );
}
