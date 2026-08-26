/**
 * Loading state — a skeleton shaped like the eventual content, not a
 * centered spinner that causes layout shift. See docs/ui-design-system.md §6.
 */
export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div
      role="status"
      aria-label="Loading"
      className={`animate-pulse rounded-md bg-bg-2 ${className}`}
    />
  );
}
