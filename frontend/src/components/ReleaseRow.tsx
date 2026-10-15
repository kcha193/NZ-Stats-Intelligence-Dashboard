import { Link } from "react-router-dom";
import type { ReleaseSummary } from "@/api/types";
import { formatAklDateTime } from "@/lib/format";
import { StatusBadge } from "./StatusBadge";

export function ReleaseRow({ release }: { release: ReleaseSummary }) {
  const title = release.has_analysis ? (
    <Link className="font-medium underline-offset-2 hover:underline" to={`/releases/${release.id}`}>{release.title}</Link>
  ) : release.page_url ? (
    <a className="font-medium underline-offset-2 hover:underline" href={release.page_url} target="_blank" rel="noreferrer">{release.title}</a>
  ) : (
    <span className="font-medium">{release.title}</span>
  );
  return (
    <li className="py-2">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
        {title}
        <StatusBadge status={release.status} />
      </div>
      <p className="text-xs text-muted-foreground">
        {formatAklDateTime(release.published_at)} · {release.category}
      </p>
      {release.headline && <p className="mt-0.5 text-sm">{release.headline}</p>}
    </li>
  );
}
