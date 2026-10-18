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
    expect(within(table).getByText("2026-07")).toBeInTheDocument();
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
});
