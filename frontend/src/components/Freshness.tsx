import type { SourceHealth } from "@/api/types";
import { formatAklDateTime } from "@/lib/format";

const NAMES: Record<string, string> = {
  calendar_ics: "Release calendar (ICS)",
  calendar_month: "Release listings (monthly)",
  "release:international-migration": "International migration releases",
};

export function Freshness({ sources }: { sources: SourceHealth[] }) {
  if (sources.length === 0) return <p className="text-sm text-muted-foreground">No source has been checked yet.</p>;
  return (
    <ul className="space-y-1.5 text-sm">
      {sources.map((s) => (
        <li key={s.source}>
          <span className="flex items-center gap-2">
            <span aria-hidden className={`size-2 rounded-full ${s.state === "ok" ? "bg-emerald-600" : "bg-amber-600"}`} />
            <span className="font-medium">{NAMES[s.source] ?? s.source}</span>
            <span className="text-xs text-muted-foreground">{s.state === "ok" ? "OK" : "Degraded"}</span>
          </span>
          <span className="block pl-4 text-xs text-muted-foreground">
            Checked {s.last_checked_at ? formatAklDateTime(s.last_checked_at) : "never"}
            {s.last_success_at ? ` · last success ${formatAklDateTime(s.last_success_at)}` : ""}
            {s.state !== "ok" && s.detail ? ` · ${s.detail}` : ""}
          </span>
        </li>
      ))}
    </ul>
  );
}
