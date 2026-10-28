import { useRef, useState, type ReactNode } from "react";
import type { EChartsCoreOption } from "echarts/core";
import { Download, Image as ImageIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toCsv } from "@/lib/csv";
import { saveFile as save } from "@/lib/download";
import { formatAklDate, formatAklDateTime, monthLabel } from "@/lib/format";
import { EChart, type ChartInstance } from "./EChart";
import { useChartTheme } from "./theme";
import { captionedChartPng } from "./imageExport";

type Cell = string | number | null;
const isPeriod = (value: Cell): value is string => typeof value === "string" && /^\d{4}-(0[1-9]|1[0-2])$/.test(value);
export type ChartTableColumn = {
  key: string;
  label: string;
  numeric?: boolean;
  format?: (value: Cell) => string;
};

type Props = {
  title: string;
  question: string;
  unit: string;
  source: { label: string; url?: string | null; updated?: string | null; captured?: string | null };
  caveat?: string;
  option: EChartsCoreOption;
  ariaLabel: string;
  csvFilename: string;
  csvRows: Record<string, string | number | null>[];
  tableColumns?: readonly ChartTableColumn[];
  tableNote?: string;
  height?: number;
  controls?: ReactNode;
};

export function ChartCard({
  title, question, unit, source, caveat, option, ariaLabel, csvFilename, csvRows, tableColumns, tableNote, height, controls,
}: Props) {
  const chart = useRef<ChartInstance | null>(null);
  const theme = useChartTheme();
  const [exporting, setExporting] = useState(false);
  const [exportStatus, setExportStatus] = useState("");
  const publication = source.updated
    ? `published ${formatAklDate(source.updated)}`
    : "publication date unavailable";
  const captured = source.captured ? formatAklDateTime(source.captured) : null;
  const capture = captured ? `Captured ${captured} (vintage).` : null;
  // Exported images keep the exact instant as provenance beside the readable time.
  const exportCapture = captured ? `Captured ${captured} (${source.captured}; vintage).` : null;
  const columns = tableColumns ?? (csvRows.length ? Object.keys(csvRows[0]).map((key) => ({
    key, label: key.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase()),
  })) : []);
  const periods = [...new Set(csvRows.map((row) => row.period ?? row.reference_period)
    .filter(isPeriod))].sort();
  const range = periods.length
    ? `Showing all ${periods.length} periods (${csvRows.length} rows), ${monthLabel(periods[0])} to ${monthLabel(periods.at(-1)!)}.`
    : `Showing all ${csvRows.length} rows in chart order.`;
  const displayCell = (column: ChartTableColumn, value: Cell) => {
    if (value == null) return "n/a";
    if (column.format) return column.format(value);
    return (column.key === "period" || column.key === "reference_period") && isPeriod(value) ? monthLabel(value) : value;
  };

  const downloadCsv = () => {
    const url = URL.createObjectURL(new Blob([toCsv(csvRows)], { type: "text/csv;charset=utf-8" }));
    save(url, csvFilename);
    URL.revokeObjectURL(url);
  };
  const exportImage = async () => {
    setExporting(true);
    setExportStatus("");
    try {
      const url = chart.current?.getDataURL({
        type: "png", pixelRatio: 2, backgroundColor: theme.surface,
      });
      if (!url) throw new Error("Chart is not ready");
      const paragraphs = [
        title, question, `Unit: ${unit}. Source: ${source.label}, ${publication}.`,
        source.url ?? "Source URL unavailable.", exportCapture, caveat,
      ].filter((p): p is string => Boolean(p));
      save(await captionedChartPng(url, paragraphs, theme), csvFilename.replace(/\.csv$/, ".png"));
      setExportStatus("Chart image exported with source information.");
    } catch {
      setExportStatus("Image export failed. Please try again once the chart is ready.");
    } finally {
      setExporting(false);
    }
  };

  return (
    <figure className="min-w-0 break-inside-avoid rounded-md border bg-card p-4 print:border-0 print:p-0">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-base font-semibold leading-snug">{title}</h3>
          <p className="mt-0.5 text-sm text-muted-foreground">{question}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2 print:hidden">
          {controls}
          <Button variant="outline" size="sm" className="min-h-11 min-w-11 sm:min-h-0 sm:min-w-0" onClick={downloadCsv}>
            <Download className="size-4" aria-hidden /> Download data (CSV)
          </Button>
          <Button variant="outline" size="sm" className="min-h-11 min-w-11 sm:min-h-0 sm:min-w-0" onClick={exportImage} disabled={exporting}>
            <ImageIcon className="size-4" aria-hidden /> Export image (PNG)
          </Button>
        </div>
      </div>
      <div className="mt-3">
        <EChart option={option} ariaLabel={ariaLabel} height={height} onReady={(c) => (chart.current = c)} />
      </div>
      <figcaption className="mt-2 space-y-1 text-xs text-muted-foreground">
        <p>
          Unit: {unit}. Source:{" "}
          {source.url ? (
            <a className="underline underline-offset-2" href={source.url} target="_blank" rel="noreferrer">
              {source.label}
            </a>
          ) : (
            source.label
          )}
          {`, ${publication}`}.
        </p>
        {capture && <p>{capture}</p>}
        {caveat && <p>{caveat}</p>}
        <p role="status" className="print:hidden">{exportStatus}</p>
        {csvRows.length > 0 && (
          <details className="print:hidden">
            <summary className="min-h-11 cursor-pointer py-3 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 sm:min-h-0 sm:py-0">View data table</summary>
            {tableNote && <p className="mt-2">{tableNote}</p>}
            <div className="mt-2 overflow-x-auto" role="region" aria-label={`${title} data table`} tabIndex={0}>
              <table className="w-full text-left">
                <caption className="mb-2 text-left">{range}</caption>
                <thead>
                  <tr>{columns.map((c) => <th key={c.key} scope="col" className={`py-1 pr-4 font-medium ${c.numeric ? "text-right" : ""}`}>{c.label}</th>)}</tr>
                </thead>
                <tbody>
                  {csvRows.map((row, i) => (
                    <tr key={i} className="border-t">{columns.map((c) => (
                      <td key={c.key} className={`whitespace-nowrap py-1 pr-4 ${c.numeric ? "text-right tabular-nums" : ""}`}>
                        {displayCell(c, row[c.key])}
                      </td>
                    ))}</tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        )}
      </figcaption>
    </figure>
  );
}
