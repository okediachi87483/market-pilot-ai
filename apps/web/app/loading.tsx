import { Skeleton } from "@/components/ui/Skeleton";

/** Route-level loading fallback, shown while a segment's data resolves. */
export default function Loading() {
  return (
    <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
      <Skeleton className="h-40" />
      <Skeleton className="h-40" />
      <Skeleton className="h-40" />
    </div>
  );
}
