import { useSnapshot } from "@/api/useSnapshot";
import { formatAklDateTime } from "@/lib/format";

/**
 * Shown on every page of the published site: when the data was last verified, that this is a snapshot rather than a
 * live feed, and (for a fixture build only) that it is test data.
 */
export function SnapshotStamp() {
  const { data, isLoading } = useSnapshot();
  // Reserve the strip's height while the manifest loads so the page below does not jump when it appears.
  if (isLoading) return <div aria-hidden data-snapshot-stamp className="min-h-12 border-b bg-surface-sunken lg:min-h-[1.9rem] print:hidden" />;
  if (!data) return null;
  if (data.origin === "fixture") {
    return (
      <p role="note" data-snapshot-stamp className="border-b border-destructive/50 bg-destructive/10 px-4 py-2 text-center text-sm font-medium print:hidden">
        Test data built from fixture files. These are not Stats NZ releases and this build must not be published.
      </p>
    );
  }
  return (
    <div data-snapshot-stamp className="border-b bg-surface-sunken print:hidden">
      <p className="mx-auto max-w-[1320px] px-4 py-1.5 text-xs text-muted-foreground lg:px-8">
        <span className="font-medium text-foreground">
          {data.data_updated_at ? `Data last updated ${formatAklDateTime(data.data_updated_at)}` : "No data published yet"}
        </span>
        {" · "}A published snapshot of Stats NZ releases, not a live feed
        <span className="hidden sm:inline">{" · "}Site refreshed {formatAklDateTime(data.generated_at)}</span>
      </p>
    </div>
  );
}
