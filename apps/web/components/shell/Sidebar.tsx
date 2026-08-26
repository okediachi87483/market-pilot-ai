"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { NAV_ITEMS } from "@/lib/nav";

interface SidebarProps {
  /** Rendered as a slide-over on small screens; always visible on md+. */
  mobileOpen: boolean;
  onNavigate: () => void;
}

export function Sidebar({ mobileOpen, onNavigate }: SidebarProps) {
  const pathname = usePathname();

  return (
    <>
      {mobileOpen && (
        <button
          aria-label="Close navigation"
          onClick={onNavigate}
          className="fixed inset-0 z-40 bg-black/50 md:hidden"
        />
      )}

      <nav
        aria-label="Primary"
        data-testid="sidebar-nav"
        className={`fixed inset-y-0 left-0 z-50 flex w-[220px] flex-col gap-1 border-r border-border-subtle bg-bg-1 px-3 py-4 transition-transform duration-150 md:static md:z-auto md:translate-x-0 ${
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        } md:flex`}
      >
        <div className="mb-6 flex items-center gap-2 px-2">
          <svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true">
            <path
              d="M2 15 L7 8 L11 12 L18 3"
              fill="none"
              stroke="var(--color-accent-teal)"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <span className="text-sm font-bold tracking-wide text-text-primary">MARKETPILOT</span>
          <span className="rounded-sm bg-accent-teal/15 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-accent-teal">
            AI
          </span>
        </div>

        <ul className="flex flex-col gap-0.5">
          {NAV_ITEMS.map((item) => {
            const active = pathname === item.href;
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  onClick={onNavigate}
                  aria-current={active ? "page" : undefined}
                  className={`block rounded-md px-3 py-2 text-sm transition-colors ${
                    active
                      ? "border-l-2 border-accent-teal bg-bg-2 font-medium text-text-primary"
                      : "border-l-2 border-transparent text-text-secondary hover:bg-bg-2 hover:text-text-primary"
                  }`}
                >
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </>
  );
}
