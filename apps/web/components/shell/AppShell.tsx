"use client";

import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";
import { NAV_ITEMS } from "@/lib/nav";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";

/**
 * The application shell: sidebar navigation, top bar with a derived page
 * title, and the main content area. Every route renders inside this.
 * See docs/architecture.md and docs/ui-screen-map.md.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const pathname = usePathname();

  const title = NAV_ITEMS.find((item) => item.href === pathname)?.label ?? "MarketPilot AI";

  return (
    <div className="flex min-h-dvh bg-bg-0">
      <Sidebar mobileOpen={mobileNavOpen} onNavigate={() => setMobileNavOpen(false)} />

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar title={title} onMenuClick={() => setMobileNavOpen(true)} />
        <main className="flex-1 overflow-y-auto px-4 py-6 md:px-8 md:py-8">{children}</main>
      </div>
    </div>
  );
}
