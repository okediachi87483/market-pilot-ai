/** See docs/ui-design-system.md §6 — names what failed and whether it's retryable. */
export function ErrorState({
  message,
  retryable = true,
  onRetry,
}: {
  message: string;
  retryable?: boolean;
  onRetry?: () => void;
}) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-md border border-negative/40 bg-negative/10 px-4 py-6 text-center">
      <p className="text-sm text-text-secondary">{message}</p>
      {retryable && onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="rounded-md border border-border-default bg-bg-2 px-3 py-1.5 text-xs font-semibold text-text-primary hover:bg-bg-3"
        >
          Retry
        </button>
      )}
    </div>
  );
}
