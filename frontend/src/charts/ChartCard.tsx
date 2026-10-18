import { useRef, useState, type ReactNode } from "react";
import type { EChartsCoreOption } from "echarts/core";
import { Download, Image as ImageIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toCsv } from "@/lib/csv";
import { formatAklDate, formatAklDateTime } from "@/lib/format";
import { EChart, type ChartInstance } from "./EChart";
import { useChartTheme } from "./theme";
import { captionedChartPng } from "./imageExport";

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
  height?: number;
  controls?: ReactNode;
};

function save(href: string, filename: string) {
  const a = document.createElement("a");
  a.href = href;
  a.download = filename;
  a.click();
}

export function ChartCard({
  title, question, unit, source, caveat, option, ariaLabel, csvFilename, csvRows, height, controls,
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
  const columns = csvRows.length ? Object.keys(csvRows[0]) : [];
  const tail = csvRows.slice(-24);

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
          <Button variant="outline" size="sm" onClick={downloadCsv}>
            <Download className="size-4" aria-hidden /> Download data (CSV)
          </Button>
          <Button variant="outline" size="sm" onClick={exportImage} disabled={exporting}>
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
            <summary className="cursor-pointer">View data table</summary>
            <div className="mt-2 overflow-x-auto" role="region" aria-label={`${title} data table`} tabIndex={0}>
              <table className="w-full text-left">
                <caption className="sr-only">{title}: latest {tail.length} rows</caption>
                <thead>
                  <tr>{columns.map((c) => <th key={c} scope="col" className="pr-4 font-medium">{c}</th>)}</tr>
                </thead>
                <tbody>
                  {tail.map((row, i) => (
                    <tr key={i}>{columns.map((c) => <td key={c} className="pr-4">{row[c] ?? ""}</td>)}</tr>
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
