"use client";

interface TopBarProps {
  title: string;
  onMenuClick: () => void;
}

export function TopBar({ title, onMenuClick }: TopBarProps) {
  return (
    <header className="flex h-16 shrink-0 items-center justify-between border-b border-border-subtle px-4 md:px-8">
      <div className="flex items-center gap-3">
        <button
          type="button"
          aria-label="Open navigation"
          onClick={onMenuClick}
          className="rounded-md p-1.5 text-text-secondary hover:bg-bg-2 hover:text-text-primary md:hidden"
        >
          <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true">
            <path
              d="M3 5 H17 M3 10 H17 M3 15 H17"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
            />
          </svg>
        </button>
        <h1 className="text-[17px] font-semibold text-text-primary">{title}</h1>
      </div>

      <div className="flex items-center gap-2 rounded-full border border-border-subtle bg-bg-1 px-3 py-1.5">
        <span
          aria-hidden="true"
          className="h-1.5 w-1.5 rounded-full bg-neutral-signal"
        />
        <span className="text-xs font-semibold text-text-secondary">MOCK DATA</span>
      </div>
    </header>
  );
}
