import type { OpsStatus } from "@/api/types";
import { formatAklDateTime } from "@/lib/format";

const LEVEL = { ok: "OK", attention: "Attention", critical: "Critical" } as const;
const BORDER = { ok: "border-border", attention: "border-amber-600/50", critical: "border-destructive/60" } as const;

const COLLECTION = {
  enabled: "On",
  disabled: "Off (by choice)",
  paused: "Paused: the dashboard is not running",
  unknown: "Not known yet",
} as const;

const PROCESS = {
  running: "Running",
  stalled: "Not responding",
  lost: "Stopped unexpectedly",
  stopped: "Stopped",
  never_started: "No record yet",
} as const;

function span(seconds: number): string {
  if (seconds < 90) return `${Math.max(0, Math.round(seconds))} s`;
  if (seconds < 5400) return `${Math.round(seconds / 60)} min`;
  if (seconds < 172800) return `${Math.round(seconds / 3600)} h`;
  return `${Math.round(seconds / 86400)} days`;
}

const at = (iso: string | null | undefined) => (iso ? formatAklDateTime(iso) : "never");

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-sm">{children}</dd>
    </div>
  );
}

/** What an operator needs from the local monitor: is it collecting, is it working, what is next, what to do. */
export function OperationsPanel({ status: s }: { status: OpsStatus }) {
  const p = s.process;
  const best = s.backup.latest_good;
  return (
    <section aria-labelledby="ops" className="space-y-4">
      <h2 id="ops" className="text-lg font-semibold">Operations</h2>
      <p role="status" data-level={s.overall} className={`rounded-md border p-3 text-sm ${BORDER[s.overall]}`}>
        <strong>{LEVEL[s.overall]}.</strong> {s.summary}
      </p>

      <dl className="grid gap-x-8 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
        <Fact label="Data collection">
          <span className="font-medium">{COLLECTION[s.collection.mode]}</span>
          <span className="block text-muted-foreground">{s.collection.summary}</span>
        </Fact>
        <Fact label="Application">
          <span className="font-medium">{PROCESS[p.state]}</span>
          {p.heartbeat_age_seconds != null && (
            <span className="block text-muted-foreground">Last heartbeat {span(p.heartbeat_age_seconds)} ago</span>
          )}
          {!s.database.readable && <span className="block">Database cannot be read</span>}
        </Fact>
        <Fact label="Next official release">
          {s.next_release ? (
            <>
              <span className="font-medium">{s.next_release.title}</span>
              <span className="block text-muted-foreground">
                {s.next_release.reference_period ? `Reference period ${s.next_release.reference_period} · ` : ""}
                {at(s.next_release.scheduled_at)}
              </span>
            </>
          ) : (
            <span className="text-muted-foreground">None known for the supported releases</span>
          )}
        </Fact>
        <Fact label="Release calendar">
          <span className="font-medium">{{ current: "Up to date", missed: "Refresh missed", stale: "Out of date", never: "Never refreshed" }[s.calendar.state]}</span>
          <span className="block text-muted-foreground">
            Last complete refresh {at(s.calendar.last_success_at)}
            {s.calendar.next_refresh_at ? ` · next ${at(s.calendar.next_refresh_at)}` : ""}
          </span>
        </Fact>
        <Fact label="Latest ingestion">
          {s.latest_ingestion ? (
            <>
              <span className="font-medium">{s.latest_ingestion.release_key}</span>
              <span className="block text-muted-foreground">{s.latest_ingestion.outcome} · {at(s.latest_ingestion.finished_at)}</span>
            </>
          ) : (
            <span className="text-muted-foreground">None recorded</span>
          )}
        </Fact>
        <Fact label="Backup">
          {best ? (
            <>
              <span className="font-medium">{best.kind === "bundle" ? "Database and raw files" : "Database only"}, {span(best.age_hours * 3600)} old</span>
              <span className="block text-muted-foreground">
                {best.verification === "verified" ? "Verified" : "Not verified"}{best.raw_artifacts != null ? ` · ${best.raw_artifacts} raw files` : ""}
              </span>
            </>
          ) : (
            <span className="font-medium">No usable backup</span>
          )}
        </Fact>
      </dl>

      <div>
        <h3 className="text-sm font-semibold">What needs attention</h3>
        {s.issues.length === 0 ? (
          <p className="mt-1 text-sm text-muted-foreground">Nothing. Every check is within its limit.</p>
        ) : (
          <ol className="mt-2 space-y-3">
            {s.issues.map((i) => (
              <li key={i.key} className={`rounded-md border p-3 text-sm ${BORDER[i.severity]}`}>
                <p className="font-medium">{LEVEL[i.severity]}: {i.title}</p>
                <p className="mt-1 text-muted-foreground">{i.detail}</p>
                <p className="mt-1"><strong>What to do:</strong> {i.action}</p>
              </li>
            ))}
          </ol>
        )}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <caption className="pb-1 text-left text-sm font-semibold">Is each release current?</caption>
          <thead><tr className="border-b text-xs text-muted-foreground">
            <th scope="col" className="py-1 pr-3 font-medium">Release</th>
            <th scope="col" className="py-1 pr-3 font-medium">Newest reference period</th>
            <th scope="col" className="py-1 pr-3 font-medium">Published</th>
            <th scope="col" className="py-1 pr-3 font-medium">Status</th>
            <th scope="col" className="py-1 font-medium">Next release</th>
          </tr></thead>
          <tbody>
            {s.freshness.map((f) => (
              <tr key={f.series_slug} className="border-b last:border-0">
                <th scope="row" className="py-1.5 pr-3 font-normal">{f.label}</th>
                <td className="py-1.5 pr-3">{f.latest_reference_period ?? "none"}</td>
                <td className="py-1.5 pr-3">{f.latest_published_at ? at(f.latest_published_at) : "never"}</td>
                <td className="py-1.5 pr-3">
                  {f.state === "current" && "Current"}
                  {f.state === "no_data" && "No data yet"}
                  {f.state === "overdue" && `Overdue: ${f.overdue.map((o) => o.release_key).join(", ")}`}
                </td>
                <td className="py-1.5">{f.next_release_at ? at(f.next_release_at) : "none scheduled"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-1 text-xs text-muted-foreground">
          Current means no published release is waiting to be ingested. An old reference period is normal until Stats NZ publishes again.
        </p>
      </div>

      <p className="text-xs text-muted-foreground">
        Alert delivery: {{ none_recorded: "nothing sent yet", ok: "working", failing: "failing (the dashboard itself is not affected)" }[s.alert_delivery.state]}.
        {s.notes.map((n) => ` ${n}`).join("")}
      </p>
    </section>
  );
}
