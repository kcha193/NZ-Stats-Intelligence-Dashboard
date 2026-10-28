import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TEST_THEME } from "./theme";

const context = { measureText: vi.fn((s: string) => ({ width: s.length * 7 })), fillRect: vi.fn(), drawImage: vi.fn(), fillText: vi.fn(), scale: vi.fn() };
const chart = vi.hoisted(() => ({ getDataURL: vi.fn(() => "data:image/png;base64,AAA") }));

const readBlob = (blob: Blob) =>
  new Promise<string>((resolve) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.readAsText(blob);
  });

vi.mock("./EChart", () => ({
  EChart: ({ ariaLabel, onReady }: { ariaLabel: string; onReady?: (c: unknown) => void }) => {
    onReady?.(chart);
    return <div role="img" aria-label={ariaLabel} />;
  },
}));
vi.mock("./theme", async (orig) => ({ ...(await orig<typeof import("./theme")>()), useChartTheme: () => TEST_THEME }));

import { ChartCard } from "./ChartCard";
import { CPI_HISTORY_COLUMNS, CPI_TABLE_NOTE } from "@/pages/inflation/format";

const props = {
  title: "Year-ended net migration was a net gain of 20,350 in July 2026",
  question: "How has annual net migration moved since 2001?",
  unit: "people",
  source: { label: "Stats NZ, International migration: July 2026", url: "https://www.stats.govt.nz/x/", updated: "2026-09-14T10:45:00+12:00" },
  caveat: "Latest 16 months are provisional.",
  option: {},
  ariaLabel: "Line chart of year-ended net migration",
  csvFilename: "net.csv",
  csvRows: [{ period: "2026-06", value: 1 }, { period: "2026-07", value: 2 }],
};

describe("ChartCard", () => {
  beforeEach(() => {
    chart.getDataURL.mockClear();
    context.fillText.mockClear();
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(context as never);
    vi.spyOn(HTMLCanvasElement.prototype, "toDataURL").mockReturnValue("data:image/png;base64,COMPOSED");
    vi.stubGlobal("Image", class {
      width = 1200; height = 800;
      onload?: () => void;
      set src(_value: string) { queueMicrotask(() => this.onload?.()); }
    });
    URL.createObjectURL = vi.fn(() => "blob:x");
    URL.revokeObjectURL = vi.fn();
  });

  it("shows title, question, unit, caveat and a linked source with the update date", () => {
    render(<ChartCard {...props} />);
    expect(screen.getByRole("heading", { name: props.title })).toBeInTheDocument();
    expect(screen.getByText(props.question)).toBeInTheDocument();
    expect(screen.getByText(/Latest 16 months are provisional/)).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /International migration: July 2026/ });
    expect(link).toHaveAttribute("href", "https://www.stats.govt.nz/x/");
    expect(screen.getByText(/14 Sep 2026/)).toBeInTheDocument();
    expect(screen.getByText(/Unit: people/)).toBeInTheDocument();
  });

  it("downloads the chart data as CSV", async () => {
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    render(<ChartCard {...props} />);
    await userEvent.click(screen.getByRole("button", { name: /download data/i }));
    const blob = (URL.createObjectURL as ReturnType<typeof vi.fn>).mock.calls[0][0] as Blob;
    expect(await readBlob(blob)).toBe("period,value\n2026-06,1\n2026-07,2\n");
    expect(click).toHaveBeenCalled();
  });

  it("exports the chart image through the chart instance", async () => {
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    render(<ChartCard {...props} />);
    await userEvent.click(screen.getByRole("button", { name: /export image/i }));
    expect(chart.getDataURL).toHaveBeenCalledWith(expect.objectContaining({ type: "png" }));
    expect(click).toHaveBeenCalled();
    const printed = context.fillText.mock.calls.map((c) => c[0]).join(" ");
    expect(printed).toContain(props.source.url);
    expect(printed).toContain("published 14 Sep 2026");
    expect(printed).toContain(props.caveat);
    expect(click.mock.instances.at(-1)).toHaveAttribute("href", "data:image/png;base64,COMPOSED");
  });

  it("offers the data as an accessible table", async () => {
    render(<ChartCard {...props} />);
    await userEvent.click(screen.getByText(/view data table/i));
    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("row")).toHaveLength(3);
    expect(within(table).getByText("Jul 2026")).toBeInTheDocument();
  });

  it("announces an export failure accessibly and restores its button", async () => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {}).mockClear();
    render(<ChartCard {...props} />);
    const button = screen.getByRole("button", { name: /export image/i });
    await userEvent.click(button);
    expect(await screen.findByRole("status")).toHaveTextContent("Image export failed");
    expect(button).toBeEnabled();
    expect(click).not.toHaveBeenCalled();
  });

  it("shows the capture time as a readable Auckland date, not an ISO string", () => {
    render(<ChartCard {...props} source={{ ...props.source, captured: "2026-10-18T13:00:00+13:00" }} />);
    expect(screen.getByText(/Captured 18 Oct 2026, \d{1,2}:00 NZDT/)).toBeInTheDocument();
    expect(screen.queryByText(/2026-10-18T/)).not.toBeInTheDocument();
  });

  it("preserves unsupported period labels instead of inventing a formatted date", async () => {
    render(<ChartCard {...props} csvRows={[
      { period: "2026-Q2", value: 1 }, { period: "2026-13", value: 2 }, { period: "not dated", value: null },
    ]} />);
    await userEvent.click(screen.getByText("View data table"));
    const table = screen.getByRole("table");
    expect(table).toHaveTextContent("Showing all 3 rows in chart order");
    for (const label of ["2026-Q2", "2026-13", "not dated", "n/a"]) expect(within(table).getByText(label)).toBeInTheDocument();
  });

  it("discloses every selected period including histories longer and shorter than 24 rows", async () => {
    const rows = Array.from({ length: 58 }, (_, i) => ({
      period: `${2012 + Math.floor(i / 4)}-${["03", "06", "09", "12"][i % 4]}`, value: i,
    }));
    const { rerender } = render(<ChartCard {...props} csvRows={rows} />);
    await userEvent.click(screen.getByText("View data table"));
    expect(screen.getByRole("table")).toHaveTextContent("Showing all 58 periods (58 rows), Mar 2012 to Jun 2026");
    expect(within(screen.getByRole("table")).getAllByRole("row")).toHaveLength(59);
    expect(screen.getAllByRole("cell").filter((_, i) => i % 2 === 0).map((c) => c.textContent)).toEqual(
      rows.map((r, i) => `${["Mar", "Jun", "Sep", "Dec"][i % 4]} ${r.period.slice(0, 4)}`),
    );
    rerender(<ChartCard {...props} csvRows={rows.slice(-12)} />);
    expect(screen.getByRole("table")).toHaveTextContent("Showing all 12 periods (12 rows), Sep 2023 to Jun 2026");
    expect(within(screen.getByRole("table")).getAllByRole("row")).toHaveLength(13);
    rerender(<ChartCard {...props} csvRows={[]} />);
    expect(screen.queryByText("View data table")).not.toBeInTheDocument();
  });

  it("formats CPI display cells while preserving missing values, series order and CSV precision", async () => {
    const rows = [
      { period: "2026-03", series_name: "Tradables", index: 1000, quarterly_pct: null, annual_pct: 1.234567, source_reference: "CPIQ.SYNTHETIC" },
      { period: "2026-06", series_name: "Tradables", index: 1002, quarterly_pct: 0, annual_pct: -1.25, source_reference: "CPIQ.SYNTHETIC" },
      { period: "2026-03", series_name: "Non-tradables", index: 1005, quarterly_pct: 0.34567, annual_pct: null, source_reference: "CPIQ.OTHER" },
    ];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    render(<ChartCard {...props} csvRows={rows} tableColumns={CPI_HISTORY_COLUMNS} tableNote={CPI_TABLE_NOTE} />);
    await userEvent.click(screen.getByText("View data table"));
    const table = screen.getByRole("table");
    expect(table).toHaveTextContent("Showing all 2 periods (3 rows), Mar 2026 to Jun 2026");
    expect(within(table).getAllByRole("columnheader").map((c) => c.textContent)).toEqual([
      "Quarter ended", "Series", "Index (June 2017 = 1000)", "Quarterly change (%)", "Annual change (%)",
    ]);
    const cells = within(table).getAllByRole("row").slice(1).map((row) => within(row).getAllByRole("cell"));
    expect(cells.map((row) => row.map((c) => c.textContent))).toEqual([
      ["Mar 2026", "Tradables", "1,000", "n/a", "1.2"],
      ["Jun 2026", "Tradables", "1,002", "0.0", "−1.3"],
      ["Mar 2026", "Non-tradables", "1,005", "0.3", "n/a"],
    ]);
    expect(cells[0][4]).toHaveClass("text-right");
    expect(table).not.toHaveTextContent("CPIQ.SYNTHETIC");
    expect(screen.getByText(CPI_TABLE_NOTE)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /download data/i }));
    const csv = await readBlob((URL.createObjectURL as ReturnType<typeof vi.fn>).mock.calls[0][0] as Blob);
    expect(csv).toContain("2026-03,Tradables,1000,,1.234567,CPIQ.SYNTHETIC");
    expect(csv).toContain("2026-06,Tradables,1002,0,-1.25,CPIQ.SYNTHETIC");
  });

});
