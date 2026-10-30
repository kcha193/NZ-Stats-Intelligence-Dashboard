import { useHealth, useOpsStatus } from "@/api/hooks";
import { isStaticMode } from "@/api/mode";
import { ROUTE_META } from "@/seo/routes";
import { useDocumentTitle } from "@/seo/useDocumentTitle";
import { QueryBoundary } from "@/components/QueryBoundary";
import { OperationsPanel } from "@/components/health/OperationsPanel";
import { formatAklDateTime } from "@/lib/format";

export default function Health() {
  const snapshot = isStaticMode();
  useDocumentTitle(ROUTE_META["/health"].title);
  const q = useHealth();
  const ops = useOpsStatus();
  return (
    <div className="space-y-5">
      <h1 className="text-xl font-semibold tracking-tight">Data health</h1>
      {!snapshot && ops.data && <OperationsPanel status={ops.data} />}
      {!snapshot && ops.isLoading && (
        <p role="status" aria-label="Loading operational status" className="text-sm text-muted-foreground">
          Loading operational status…
        </p>
      )}
      {!snapshot && ops.isError && (
        <p role="status" className="rounded-md border border-amber-600/50 p-3 text-sm">
          Operational status could not be loaded. Check the terminal running the dashboard and retry.
        </p>
      )}
      <QueryBoundary query={q}>
        {(d) => {
          const degraded = d.sources.filter((s) => s.state !== "ok");
          return (
            <div className="space-y-5">
              <div>
                <p className="text-sm text-muted-foreground">
                  {snapshot
                    ? `When each Stats NZ source was last checked and last succeeded, as of the last published snapshot. ${d.series_count} series, ${d.vintage_count} stored vintages.`
                    : `What the monitor has checked, and whether it worked. ${d.series_count} series, ${d.vintage_count} stored vintages. Database ${d.database_ok ? "OK" : "unavailable"}.`}
                </p>
              </div>
              {degraded.length > 0 && (
                <p role="status" className="rounded-md border border-amber-600/50 p-3 text-sm">
                  {degraded.length} source{degraded.length > 1 ? "s are" : " is"} degraded. The last known good data is still being shown; nothing has been overwritten by a failed update.
                </p>
              )}
              <section aria-labelledby="sources">
                <h2 id="sources" className="text-lg font-semibold">Sources</h2>
                <div className="overflow-x-auto">
                  <table className="mt-2 w-full text-left text-sm">
                    <caption className="sr-only">Sources</caption>
                    <thead><tr className="border-b text-xs text-muted-foreground">
                      <th scope="col" className="py-1 pr-3 font-medium">Source</th><th scope="col" className="py-1 pr-3 font-medium">State</th>
                      <th scope="col" className="py-1 pr-3 font-medium">Last checked</th><th scope="col" className="py-1 pr-3 font-medium">Last success</th>
                      <th scope="col" className="py-1 font-medium">Detail</th>
                    </tr></thead>
                    <tbody>
                      {d.sources.map((s) => (
                        <tr key={s.source} className="border-b last:border-0">
                          <th scope="row" className="py-1.5 pr-3 font-normal">{s.source}</th>
                          <td className="py-1.5 pr-3">{s.state === "ok" ? "OK" : "Degraded"}</td>
                          <td className="py-1.5 pr-3">{s.last_checked_at ? formatAklDateTime(s.last_checked_at) : "never"}</td>
                          <td className="py-1.5 pr-3">{s.last_success_at ? formatAklDateTime(s.last_success_at) : "never"}</td>
                          <td className="py-1.5">{s.detail ?? ""}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
              {!snapshot && <section aria-labelledby="runs">
                <h2 id="runs" className="text-lg font-semibold">Recent ingestion runs</h2>
                <div className="overflow-x-auto">
                  <table className="mt-2 w-full text-left text-sm">
                    <caption className="sr-only">Recent ingestion runs</caption>
                    <thead><tr className="border-b text-xs text-muted-foreground">
                      <th scope="col" className="py-1 pr-3 font-medium">When</th><th scope="col" className="py-1 pr-3 font-medium">Release</th>
                      <th scope="col" className="py-1 pr-3 font-medium">Outcome</th><th scope="col" className="py-1 font-medium">Error class and detail</th>
                    </tr></thead>
                    <tbody>
                      {d.recent_runs.map((r, i) => (
                        <tr key={i} className="border-b last:border-0">
                          <td className="py-1.5 pr-3">{formatAklDateTime(r.started_at)}</td>
                          <td className="py-1.5 pr-3">{r.release_key}</td>
                          <td className="py-1.5 pr-3">{r.outcome}</td>
                          <td className="py-1.5">{r.error_class ? `${r.error_class}: ${r.detail ?? ""}` : (r.detail ?? "")}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>}
              <p className="text-xs text-muted-foreground">
                Release counts: {Object.entries(d.release_counts).map(([k, v]) => `${k} ${v}`).join(" · ") || "none"}. Error classes: network, blocked, not_found (not yet published), layout_changed, validation_failed, unexpected. See docs/troubleshooting.md.
              </p>
            </div>
          );
        }}
      </QueryBoundary>
    </div>
  );
}
