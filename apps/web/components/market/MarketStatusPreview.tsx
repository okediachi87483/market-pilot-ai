/** Placeholder — global market status strip. See docs/component-architecture.md (MarketOverview). */
export function MarketStatusPreview() {
  return (
    <div className="flex items-center gap-2 rounded-full border border-border-subtle bg-bg-1 px-3 py-1.5">
      <span className="h-1.5 w-1.5 rounded-full bg-neutral-signal" aria-hidden="true" />
      <span className="text-xs font-semibold text-text-secondary">US EQUITIES &middot; MOCK DATA</span>
    </div>
  );
}
