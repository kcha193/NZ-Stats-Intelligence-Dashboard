import { Link, useSearchParams } from "react-router-dom";
import { useCalendar } from "@/api/hooks";
import type { ReleaseSummary } from "@/api/types";
import { QueryBoundary } from "@/components/QueryBoundary";
import { ReleaseRow } from "@/components/ReleaseRow";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Segmented } from "@/components/Segmented";
import { Button } from "@/components/ui/button";
import { formatAklDate, formatAklDateTime, monthLabel } from "@/lib/format";

const ALL = "all";
const dayKey = (iso: string) => iso.slice(0, 10);
/** A delayed release is a scheduled one whose date moved later, so both are still to come. */
const isUpcoming = (status: string) => status === "scheduled" || status === "delayed";
const shiftMonth = (month: string, by: number) => {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(Date.UTC(y, m - 1 + by, 1));
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
};

/** Upcoming days first (soonest first), then published days (most recent first). */
function orderDays(grouped: Map<string, ReleaseSummary[]>): [string, ReleaseSummary[]][] {
  const days = [...grouped];
  const upcoming = days.filter(([, rs]) => rs.some((r) => isUpcoming(r.status))).sort(([a], [b]) => a.localeCompare(b));
  const past = days.filter(([, rs]) => !rs.some((r) => isUpcoming(r.status))).sort(([a], [b]) => b.localeCompare(a));
  return [...upcoming, ...past];
}

function MonthGrid({ items, month }: { items: ReleaseSummary[]; month: string }) {
  const [y, m] = month.split("-").map(Number);
  const lead = (new Date(Date.UTC(y, m - 1, 1)).getUTCDay() + 6) % 7; // Monday-first
  const days = new Date(Date.UTC(y, m, 0)).getUTCDate();
  const byDay = new Map<string, ReleaseSummary[]>();
  for (const r of items) byDay.set(dayKey(r.published_at), [...(byDay.get(dayKey(r.published_at)) ?? []), r]);
  const cells: (number | null)[] = [...Array(lead).fill(null), ...Array.from({ length: days }, (_, i) => i + 1)];
  while (cells.length % 7) cells.push(null);
  const weeks = Array.from({ length: cells.length / 7 }, (_, w) => cells.slice(w * 7, w * 7 + 7));
  return (
    <table role="grid" aria-label={`Release calendar month ${month}`} className="w-full table-fixed border-collapse text-xs">
      <thead>
        <tr>{["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => <th key={d} scope="col" className="border bg-muted p-1 font-medium">{d}</th>)}</tr>
      </thead>
      <tbody>
        {weeks.map((week, w) => (
          <tr key={w}>
            {week.map((day, i) => {
              const rels = day ? byDay.get(`${month}-${String(day).padStart(2, "0")}`) ?? [] : [];
              return (
                <td key={i} className="h-20 border p-1 align-top">
                  {day && <span className="text-muted-foreground">{day}</span>}
                  <ul className="mt-0.5 space-y-0.5">
                    {rels.map((r) => (
                      <li key={r.id} className="truncate" title={r.title}>
                        {r.has_analysis ? <Link className="underline-offset-2 hover:underline" to={`/releases/${r.id}`}>{r.title}</Link> : r.title}
                      </li>
                    ))}
                  </ul>
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function Calendar() {
  const [params, setParams] = useSearchParams();
  const category = params.get("category") ?? ALL;
  const importance = params.get("importance") ?? ALL;
  const status = params.get("status") ?? ALL;
  const view = params.get("view") ?? "list";
  const set = (k: string, v: string) => {
    const next = new URLSearchParams(params);
    if (v === ALL || v === "list") next.delete(k);
    else next.set(k, v);
    setParams(next, { replace: true });
  };
  const q = useCalendar();
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Release calendar</h1>
        <p className="text-sm text-muted-foreground">Scheduled and recently published Stats NZ releases (Pacific/Auckland time).</p>
      </div>
      <QueryBoundary query={q}>
        {(d) => {
          const categories = [...new Set(d.items.map((i) => i.category))].sort();
          const items = d.items.filter((i) =>
            (category === ALL || i.category === category) &&
            (importance === ALL || i.importance === importance) &&
            (status === ALL || (status === "scheduled" ? isUpcoming(i.status) : i.status === status)));
          const month = params.get("month") ?? (items[0] ?? d.items[0])?.published_at.slice(0, 7) ?? "";
          const grouped = new Map<string, ReleaseSummary[]>();
          for (const r of items) grouped.set(dayKey(r.published_at), [...(grouped.get(dayKey(r.published_at)) ?? []), r]);
          return (
            <>
              <p className="text-xs text-muted-foreground">
                Last successful check: {d.last_success_at ? formatAklDateTime(d.last_success_at) : "never"}
                {d.last_checked_at && d.last_checked_at !== d.last_success_at ? ` · last attempt ${formatAklDateTime(d.last_checked_at)}` : ""}
              </p>
              <div className="flex flex-wrap items-center gap-3">
                <Select value={category} onValueChange={(v) => set("category", v ?? ALL)}>
                  <SelectTrigger aria-label="Category" className="w-56"><SelectValue placeholder="Category">{(v: string | null) => (v && v !== ALL ? v : "All categories")}</SelectValue></SelectTrigger>
                  <SelectContent>
                    <SelectItem value={ALL}>All categories</SelectItem>
                    {categories.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                  </SelectContent>
                </Select>
                <Segmented value={importance} onChange={(v) => set("importance", v)} label="Importance" options={[{ value: "all", label: "Any importance" },
{ value: "high", label: "High" },
{ value: "medium", label: "Medium" }]} />
                <Segmented value={status} onChange={(v) => set("status", v)} label="Status" options={[{ value: "all", label: "Any status" },
{ value: "scheduled", label: "Scheduled" },
{ value: "published", label: "Published" }]} />
                <Segmented value={view} onChange={(v) => set("view", v)} label="View" options={[{ value: "list", label: "List" },
{ value: "month", label: "Month" }]} />
              </div>
              {items.length === 0 ? (
                <p className="rounded-md border border-dashed p-6 text-sm">No releases in this period match the filters.</p>
              ) : view === "month" ? (
                <div className="space-y-2">
                  <div className="flex items-center gap-2 text-sm">
                    <Button variant="outline" size="sm" onClick={() => set("month", shiftMonth(month, -1))}>Previous month</Button>
                    <span className="min-w-28 text-center font-medium">{monthLabel(month)}</span>
                    <Button variant="outline" size="sm" onClick={() => set("month", shiftMonth(month, 1))}>Next month</Button>
                  </div>
                  <MonthGrid items={items} month={month} />
                </div>
              ) : (
                <ul aria-label="Releases" className="space-y-4">
                  {orderDays(grouped).map(([day, rels]) => (
                    <li key={day}>
                      <h2 className="text-sm font-semibold">{formatAklDate(rels[0].published_at)}</h2>
                      <ul className="divide-y rounded-md border px-3">{rels.map((r) => <ReleaseRow key={r.id} release={r} />)}</ul>
                    </li>
                  ))}
                </ul>
              )}
            </>
          );
        }}
      </QueryBoundary>
    </div>
  );
}
