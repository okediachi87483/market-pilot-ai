/** See docs/ui-design-system.md §6 — empty states explain *why*, not a generic placeholder. */
export function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex min-h-[120px] items-center justify-center rounded-md border border-dashed border-border-subtle text-center text-sm text-text-tertiary">
      {message}
    </div>
  );
}
