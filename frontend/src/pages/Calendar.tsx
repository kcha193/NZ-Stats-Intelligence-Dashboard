import { useState } from "react";
import { ROUTE_META } from "@/seo/routes";
import { useDocumentTitle } from "@/seo/useDocumentTitle";
import { Dialog } from "@base-ui/react/dialog";
import { Link, useSearchParams } from "react-router-dom";
import { useCalendar } from "@/api/hooks";
import type { ReleaseSummary } from "@/api/types";
import { QueryBoundary } from "@/components/QueryBoundary";
import { ReleaseRow } from "@/components/ReleaseRow";
import { StatusBadge } from "@/components/StatusBadge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Segmented } from "@/components/Segmented";
import { Button } from "@/components/ui/button";
import { aklMonth, formatAklDate, formatAklDateTime, monthLabel } from "@/lib/format";
import { isPublished } from "@/lib/releaseStatus";

const ALL = "all";
const dayKey = (iso: string) => iso.slice(0, 10);
/** A delayed release is a scheduled one whose date moved later, so both are still to come. */
const isUpcoming = (status: string) => status === "scheduled" || status === "delayed";
const matchesStatus = (filter: string, status: string) =>
  filter === ALL || (filter === "scheduled" ? isUpcoming(status) : filter === "published" ? isPublished(status) : status === filter);
/** The whole month as calendar-day bounds (the API treats `to` as inclusive). */
const monthBounds = (month: string) => {
  const [y, m] = month.split("-").map(Number);
  const last = new Date(Date.UTC(y, m, 0)).getUTCDate();
  return { from: `${month}-01`, to: `${month}-${String(last).padStart(2, "0")}` };
};
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
                      <li key={r.id}>
                        <Dialog.Root>
                          <Dialog.Trigger className="block w-full truncate rounded text-left underline-offset-2 hover:underline focus-visible:outline focus-visible:outline-2" aria-label={`Details for ${r.title}`}>
                            {r.title}
                          </Dialog.Trigger>
                          <Dialog.Portal>
                            <Dialog.Backdrop className="fixed inset-0 z-40 bg-background/80" />
                            <Dialog.Popup className="fixed left-1/2 top-1/2 z-50 max-h-[85dvh] w-[calc(100%-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-md border bg-card p-5 text-foreground shadow-lg">
                              <Dialog.Title className="break-words text-lg font-semibold">{r.title}</Dialog.Title>
                              <Dialog.Description className="mt-2 text-sm text-muted-foreground">{formatAklDateTime(r.published_at)}</Dialog.Description>
                              <p className="mt-2 flex flex-wrap items-center gap-2 text-sm"><StatusBadge status={r.status} />{r.category}</p>
                              {r.headline && <p className="mt-3 text-sm">{r.headline}</p>}
                              <div className="mt-4 flex flex-wrap items-center gap-4 text-sm">
                                {r.has_analysis && <Link className="underline underline-offset-2" to={`/releases/${r.id}`}>Read release analysis</Link>}
                                {r.page_url && <a className="underline underline-offset-2" href={r.page_url} target="_blank" rel="noreferrer">Open Stats NZ publication</a>}
                                <Dialog.Close render={<Button variant="outline" size="sm" />}>Close</Dialog.Close>
                              </div>
                            </Dialog.Popup>
                          </Dialog.Portal>
                        </Dialog.Root>
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
  useDocumentTitle(ROUTE_META["/calendar"].title);
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
  // The month grid asks for the month it shows; the list uses the API's default window.
  const [currentMonth] = useState(() => aklMonth(new Date()));
  const month = params.get("month") ?? currentMonth;
  const range = view === "month" ? monthBounds(month) : undefined;
  const q = useCalendar(range?.from, range?.to);
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
            matchesStatus(status, i.status));
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
              {items.length === 0 && view !== "month" ? (
                <p className="rounded-md border border-dashed p-6 text-sm">No releases in this period match the filters.</p>
              ) : view === "month" ? (
                <div className="space-y-2">
                  <div className="flex items-center gap-2 text-sm">
                    <Button variant="outline" size="sm" onClick={() => set("month", shiftMonth(month, -1))}>Previous month</Button>
                    <span className="min-w-28 text-center font-medium">{monthLabel(month)}</span>
                    <Button variant="outline" size="sm" onClick={() => set("month", shiftMonth(month, 1))}>Next month</Button>
                  </div>
                  <MonthGrid items={items} month={month} />
                  {items.length === 0 && (
                    <p className="rounded-md border border-dashed p-4 text-sm">No releases in {monthLabel(month)} match the filters.</p>
                  )}
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
