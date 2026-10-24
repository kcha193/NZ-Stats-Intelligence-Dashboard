import type { ReactNode } from "react";
import { SnapshotUnavailableError } from "@/api/static";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

type QueryLike<T> = {
  data: T | undefined;
  error: Error | null;
  isLoading: boolean;
  isError: boolean;
  refetch: () => unknown;
};

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-md border border-dashed p-6 text-sm">
      <p className="font-medium">{title}</p>
      <p className="mt-1 text-muted-foreground">{body}</p>
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: Error | null; onRetry: () => void }) {
  return (
    <div role="alert" className="rounded-md border border-destructive/40 p-4 text-sm">
      <p className="font-medium">{error instanceof SnapshotUnavailableError ? "Data temporarily unavailable." : "This could not be loaded."}</p>
      <p className="mt-1 text-muted-foreground">{error?.message ?? "Unknown error"}</p>
      <Button className="mt-3" variant="outline" size="sm" onClick={onRetry}>
        Try again
      </Button>
    </div>
  );
}

export function QueryBoundary<T>({
  query, isEmpty, empty, children,
}: {
  query: QueryLike<T>;
  isEmpty?: (data: T) => boolean;
  empty?: ReactNode | ((data: T) => ReactNode);
  children: (data: T) => ReactNode;
}) {
  if (query.isLoading) {
    return (
      <div role="status" aria-label="Loading" className="space-y-3">
        <Skeleton className="h-6 w-1/3" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }
  if (query.isError) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  if (query.data === undefined) return null;
  if (isEmpty?.(query.data)) {
    const shown = typeof empty === "function" ? empty(query.data) : empty;
    return <>{shown ?? <EmptyState title="Nothing to show" body="No data is available yet." />}</>;
  }
  return <>{children(query.data)}</>;
}
