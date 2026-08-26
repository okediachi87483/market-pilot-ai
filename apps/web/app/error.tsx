"use client";

import { useEffect } from "react";
import { ErrorState } from "@/components/ui/ErrorState";

/**
 * Route-level error boundary — see docs/ui-design-system.md §6. Next.js
 * renders this in place of a segment that threw during render.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="flex min-h-[50vh] items-center justify-center">
      <div className="w-full max-w-sm">
        <ErrorState message="Something went wrong loading this page." onRetry={reset} />
      </div>
    </div>
  );
}
