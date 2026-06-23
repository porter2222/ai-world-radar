import Link from "next/link";

export function AppHeader() {
  return (
    <header className="topbar">
      <div className="topbar-inner">
        <Link className="brand" href="/" aria-label="AI World Radar 首页">
          <span className="brand-mark">AI</span>
          <span className="brand-name">AI World Radar</span>
        </Link>
        <div className="top-meta" aria-label="页面日期">
          <span>2026.06.23</span>
        </div>
      </div>
    </header>
  );
}
