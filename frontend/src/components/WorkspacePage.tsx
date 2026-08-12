import AppIcon, { type IconName } from "@/components/AppIcon";

export function WorkspacePageHeader({ eyebrow, title, subtitle, actions }: { eyebrow: string; title: string; subtitle: string; actions?: React.ReactNode }) {
  return <header className="page-header"><div><p className="page-eyebrow">{eyebrow}</p><h1 className="page-title">{title}</h1><p className="page-subtitle">{subtitle}</p></div>{actions && <div className="page-actions">{actions}</div>}</header>;
}

export function MetricStrip({ items }: { items: Array<{ label: string; value: React.ReactNode; note?: string }> }) {
  return <div className="metric-strip">{items.map((item) => <div className="metric-item" key={item.label}><span>{item.label}</span><strong>{item.value}</strong>{item.note && <small>{item.note}</small>}</div>)}</div>;
}

export function SectionTitle({ title, meta, icon }: { title: string; meta?: string; icon?: IconName }) {
  return <div className="section-title">{icon && <AppIcon name={icon} className="h-4 w-4" />}<h2>{title}</h2>{meta && <span>{meta}</span>}</div>;
}

export function SegmentedControl<T extends string>({ value, options, onChange }: { value: T; options: Array<{ value: T; label: string }>; onChange: (value: T) => void }) {
  return <div className="segmented-control">{options.map((option) => <button key={option.value} className={value === option.value ? "is-active" : ""} onClick={() => onChange(option.value)}>{option.label}</button>)}</div>;
}

export function Pagination({ page, pages, onChange, zeroBased = false }: { page: number; pages: number; onChange: (page: number) => void; zeroBased?: boolean }) {
  const first = zeroBased ? 0 : 1;
  const last = zeroBased ? pages - 1 : pages;
  const visible = zeroBased ? page + 1 : page;
  if (pages <= 1) return null;
  return <div className="pagination"><button disabled={page <= first} onClick={() => onChange(page - 1)}>上一页</button><span>{visible} / {pages}</span><button disabled={page >= last} onClick={() => onChange(page + 1)}>下一页</button></div>;
}
