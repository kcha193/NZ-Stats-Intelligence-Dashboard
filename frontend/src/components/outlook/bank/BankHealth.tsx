import type { BankStatus } from "@/api/bank";
import { formatAklDate, formatCivilDate } from "@/lib/format";
import { STATE_LABELS } from "./labels";

const Date_ = ({ value, civil }: { value: string | null; civil?: boolean }) =>
  value ? <>{civil ? formatCivilDate(value) : formatAklDate(value)}</> : <><span aria-hidden>–</span><span className="sr-only">not yet</span></>;

/** Each bank's report series with its state in words and four separate dates: published, ingested, analysed, checked. */
export function BankHealth({ rows }: { rows: BankStatus[] }) {
  return (
    <div role="region" aria-label="Bank source health" tabIndex={0} className="relative overflow-x-auto">
      <table className="w-full min-w-[40rem] border-collapse text-sm">
        <caption className="sr-only">Bank source health: state and dates for each report series</caption>
        <thead>
          <tr className="border-b-2 border-rule-strong text-left">
            {["Bank", "Series", "State", "Newest report", "Ingested", "Analysed", "Last checked"].map((h) => (
              <th key={h} scope="col" className="py-2 pr-4 font-medium">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.flatMap((b) =>
            b.series.length === 0
              ? [(
                <tr key={b.key} className="border-b">
                  <th scope="row" className="py-2 pr-4 text-left font-medium">{b.name}</th>
                  <td className="pr-4"><span aria-hidden>–</span><span className="sr-only">none</span></td>
                  <td className="pr-4">{STATE_LABELS[b.state]}</td>
                  {[0, 1, 2, 3].map((i) => <td key={i} className="pr-4"><Date_ value={null} /></td>)}
                </tr>
              )]
              : b.series.map((s) => (
                <tr key={`${b.key}|${s.series_key}`} className="border-b">
                  <th scope="row" className="py-2 pr-4 text-left font-medium">{b.name}</th>
                  <td className="pr-4">{s.series_name}</td>
                  <td className="pr-4">{STATE_LABELS[s.state]}</td>
                  <td className="pr-4"><Date_ value={s.newest_published_on} civil /></td>
                  <td className="pr-4"><Date_ value={s.ingested_at} /></td>
                  <td className="pr-4"><Date_ value={s.analysed_at} /></td>
                  <td className="pr-4"><Date_ value={s.last_checked_at} /></td>
                </tr>
              )),
          )}
        </tbody>
      </table>
    </div>
  );
}
