export type IconName =
  | "pulse"
  | "watchlist"
  | "sources"
  | "research"
  | "briefs"
  | "alerts"
  | "tweets"
  | "documents"
  | "settings"
  | "admin"
  | "menu"
  | "close"
  | "arrow"
  | "external"
  | "evidence"
  | "search";

const paths: Record<IconName, React.ReactNode> = {
  pulse: <><path d="M3 12h4l2.2-6 4.2 12 2.4-6H21" /></>,
  watchlist: <><path d="M4 19V9m6 10V5m6 14v-7m5 7H3" /></>,
  sources: <><circle cx="12" cy="8" r="3" /><path d="M5 20a7 7 0 0 1 14 0M4 4l2 2m14-2-2 2" /></>,
  research: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5M10.5 7v7m-3.5-3.5h7" /></>,
  briefs: <><path d="M6 3h9l4 4v14H6z" /><path d="M14 3v5h5M9 12h7M9 16h7" /></>,
  alerts: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" /></>,
  tweets: <><path d="M5 5h14v11H9l-4 4z" /><path d="M8 9h8M8 12h5" /></>,
  documents: <><path d="M5 3h10l4 4v14H5z" /><path d="M14 3v5h5" /></>,
  settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1A1.7 1.7 0 0 0 9 4.6 1.7 1.7 0 0 0 10 3v-.2h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z" /></>,
  admin: <><path d="M4 5h16v14H4z" /><path d="M8 9h8M8 13h5" /></>,
  menu: <><path d="M4 7h16M4 12h16M4 17h16" /></>,
  close: <><path d="m6 6 12 12M18 6 6 18" /></>,
  arrow: <><path d="m9 18 6-6-6-6" /></>,
  external: <><path d="M14 4h6v6M20 4l-9 9" /><path d="M18 13v6H5V6h6" /></>,
  evidence: <><path d="M5 4h14v16H5z" /><path d="M8 8h8M8 12h8M8 16h5" /></>,
  search: <><circle cx="11" cy="11" r="7" /><path d="m16 16 5 5" /></>,
};

export default function AppIcon({ name, className = "" }: { name: IconName; className?: string }) {
  return (
    <svg className={className} width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {paths[name]}
    </svg>
  );
}
