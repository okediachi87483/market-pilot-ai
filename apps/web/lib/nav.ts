export interface NavItem {
  label: string;
  href: string;
}

// Single source of truth for navigation — see docs/ui-screen-map.md.
// Sidebar, top bar, and mobile nav all render from this list rather than
// each hand-maintaining their own copy.
export const NAV_ITEMS: NavItem[] = [
  { label: "Command Center", href: "/dashboard" },
  { label: "Markets", href: "/markets" },
  { label: "Watchlist", href: "/watchlist" },
  { label: "Signals", href: "/signals" },
  { label: "AI Analyst", href: "/ai-analyst" },
  { label: "Risk", href: "/risk" },
  { label: "Paper Trading", href: "/paper" },
  { label: "Portfolio", href: "/portfolio" },
  { label: "Positions", href: "/positions" },
  { label: "Trades", href: "/trades" },
  { label: "Alerts", href: "/alerts" },
  { label: "Backtests", href: "/backtests" },
  { label: "Settings", href: "/settings" },
];
