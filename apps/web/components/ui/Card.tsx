import type { ReactNode } from "react";

interface CardProps {
  eyebrow: string;
  mock?: boolean;
  children: ReactNode;
  className?: string;
}

/** Base card shell — see docs/ui-design-system.md §6. */
export function Card({ eyebrow, mock, children, className = "" }: CardProps) {
  return (
    <section
      className={`rounded-md border border-border-subtle bg-bg-1 p-5 ${className}`}
    >
      <div className="mb-3 flex items-center justify-between">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-text-tertiary">
          {eyebrow}
        </span>
        {mock && (
          <span className="font-mono text-[10px] text-text-tertiary">MOCK DATA</span>
        )}
      </div>
      {children}
    </section>
  );
}
