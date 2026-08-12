import AppIcon from "@/components/AppIcon";

export function PageLoading({ label = "正在整理情报" }: { label?: string }) {
  return <div className="page-state"><span className="signal-loader" /><strong>{label}</strong><p>正在连接数据源并生成视图。</p></div>;
}

export function PageError({ title = "暂时无法加载", detail, onRetry }: { title?: string; detail: string; onRetry?: () => void }) {
  return <div className="page-state page-state-error"><AppIcon name="alerts" className="h-6 w-6" /><strong>{title}</strong><p>{detail}</p>{onRetry && <button onClick={onRetry} className="button-secondary">重新加载</button>}</div>;
}

export function PageEmpty({ title, detail, action }: { title: string; detail: string; action?: React.ReactNode }) {
  return <div className="page-state"><span className="empty-radar"><span /></span><strong>{title}</strong><p>{detail}</p>{action}</div>;
}

