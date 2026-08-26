import { EmptyState } from "@/components/ui/EmptyState";

/** Shared scaffold for routes not yet implemented beyond the shell — see docs/ui-screen-map.md. */
export function ScreenPlaceholder({ description }: { description: string }) {
  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <div className="w-full max-w-md">
        <EmptyState message={description} />
      </div>
    </div>
  );
}
