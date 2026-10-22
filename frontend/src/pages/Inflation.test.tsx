import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import data from "@/test/fixtures/cpi.json";
import { mockApi, renderWithProviders } from "@/test/mockApi";
import Inflation from "./Inflation";

vi.mock("@/charts/EChart", () => ({
  EChart: ({ ariaLabel, option }: { ariaLabel: string; option: unknown }) => (
    <div role="img" aria-label={ariaLabel} data-option={JSON.stringify(option)} />
  ),
}));
const optionOf = (name: string) => JSON.parse(screen.getByRole("img", { name }).getAttribute("data-option")!);
beforeEach(() => mockApi({ "/api/cpi": data }));

it("shows the verified headline indicators with units, comparisons and provenance", async () => {
  renderWithProviders(<Inflation />);
  expect(await screen.findByRole("heading", { name: "Inflation", level: 1 })).toBeInTheDocument();
  const kpis = screen.getByRole("region", { name: "CPI key indicators" });
  for (const text of ["4.1%", "1.5%", "4.9%", "3.4%", "Annual CPI inflation", "Tradables", "Non-tradables"]) {
    expect(kpis).toHaveTextContent(text);
  }
  expect(kpis).toHaveTextContent("3.1% in the March 2026 quarter");
  expect(kpis).toHaveTextContent("+1.0 percentage points");
  expect(screen.getByText(/Latest reference quarter: June 2026/)).toHaveTextContent("Published 21 Jul 2026");
  for (const name of ["Headline CPI history", "Tradables versus non-tradables", "Inflation drivers", "Component explorer", "Latest release analysis", "Methodology"]) {
    expect(screen.getByRole("heading", { name })).toBeInTheDocument();
  }
});

it("changes the history range and keeps a zero line and the reference band", async () => {
  renderWithProviders(<Inflation />);
  const user = userEvent.setup();
  await screen.findByRole("heading", { name: "Inflation", level: 1 });
  expect(optionOf("Annual CPI inflation history").xAxis.data).toHaveLength(40);
  const ranges = within(screen.getByRole("group", { name: "History range" }));
  await user.click(ranges.getByRole("radio", { name: "3 years" }));
  expect(optionOf("Annual CPI inflation history").xAxis.data).toHaveLength(12);
  expect(optionOf("Quarterly CPI inflation history").xAxis.data).toHaveLength(12);
  await user.click(ranges.getByRole("radio", { name: "Full history" }));
  expect(optionOf("Annual CPI inflation history").xAxis.data.length).toBeGreaterThan(40);
  expect(optionOf("Annual CPI inflation history").title.text).toMatch(/1% to 3% reference band/);
  await user.click(screen.getByRole("checkbox", { name: /1% to 3% reference band/ }));
  expect(optionOf("Annual CPI inflation history").series[0].markArea).toBeUndefined();
  expect(optionOf("Quarterly CPI inflation history").series[0].markLine.data).toEqual([{ yAxis: 0 }]);
});

it("switches between quarterly and annual contributions and always labels percentage points", async () => {
  renderWithProviders(<Inflation />);
  const user = userEvent.setup();
  await screen.findByRole("heading", { name: "Inflation drivers" });
  let option = optionOf("CPI group contributions");
  expect(option.xAxis.name).toBe("Percentage points");
  expect(option.yAxis.data[0]).toBe("Transport");
  expect(option.series[0].data[0].value).toBe(0.824);
  await user.click(screen.getByRole("radio", { name: "Annual contribution" }));
  option = optionOf("CPI group contributions");
  expect(option.series[0].data[0].value).toBe(1.484);
  expect(option.xAxis.name).toBe("Percentage points");
  expect(screen.getByText(/groups sum to 4\.00 against a headline change of 4\.06/)).toBeInTheDocument();
});

it("says when contributions were not published instead of drawing anything", async () => {
  const none = structuredClone(data);
  none.contributions = none.contributions.map((b) => ({ ...b, available: false, items: [], sum_points: null, headline_pct: null, gap_points: null, note: "Group contributions were not published in this release; none are shown or estimated." }));
  mockApi({ "/api/cpi": none });
  renderWithProviders(<Inflation />);
  expect(await screen.findByText(/were not published in this release/)).toBeInTheDocument();
  expect(screen.queryByRole("img", { name: "CPI group contributions" })).not.toBeInTheDocument();
});

it("explores official groups with source metadata and the three views", async () => {
  renderWithProviders(<Inflation />);
  const user = userEvent.setup();
  const select = await screen.findByLabelText("CPI component");
  const names = within(select).getAllByRole("option").map((o) => o.textContent);
  for (const n of ["Food", "Alcoholic beverages and tobacco", "Household contents and services", "Miscellaneous goods and services", "Electricity", "Petrol"]) {
    expect(names).toContain(n);
  }
  await user.selectOptions(select, "transport");
  await user.click(screen.getByRole("radio", { name: "Index" }));
  expect(optionOf("CPI component history").yAxis.name).toMatch(/June 2017 = 1000/);
  expect(screen.getByLabelText("Component source")).toHaveTextContent("CPIQ.SE907");
  await user.click(screen.getByRole("radio", { name: "Quarterly change" }));
  expect(optionOf("CPI component history").series[0].type).toBe("bar");
  expect(screen.getByRole("table", { name: "Latest price change by group" })).toHaveTextContent("Transport");
});

it("keeps chart exports, official underlying measures, analysis and safe methodology links", async () => {
  renderWithProviders(<Inflation />);
  await screen.findByRole("heading", { name: "Inflation", level: 1 });
  expect(screen.getAllByRole("button", { name: /download data/i })).toHaveLength(5);
  expect(screen.getAllByRole("button", { name: /export image/i })).toHaveLength(5);
  expect(screen.getByRole("table", { name: "Official underlying measures" })).toHaveTextContent("Weighted median");
  expect(screen.getByText(/does not define core inflation/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Full release analysis" })).toHaveAttribute("href", `/releases/${data.analysis.release.id}`);
  for (const link of screen.getAllByRole("link", { name: /Stats NZ/ })) {
    expect(link.getAttribute("href")).toMatch(/^https:\/\/www\.stats\.govt\.nz\//);
    expect(link).toHaveAttribute("rel", expect.stringContaining("noreferrer"));
  }
});

it("shows a plain empty state before any CPI release is ingested", async () => {
  mockApi({});
  renderWithProviders(<Inflation />);
  expect(await screen.findByText("CPI data has not been ingested yet")).toBeInTheDocument();
});

it("shows n/a, never an invented 0.0%, when a rate is not available", async () => {
  const gap = structuredClone(data);
  for (const slug of ["tradables", "non_tradables"]) {
    const series = gap.series.find((x) => x.slug === slug && x.adjustment === "none")!;
    series.points[series.points.length - 1].quarterly_pct = null as unknown as number;
  }
  mockApi({ "/api/cpi": gap });
  renderWithProviders(<Inflation />);
  const user = userEvent.setup();
  await screen.findByRole("heading", { name: "Inflation", level: 1 });
  await user.click(within(screen.getByRole("group", { name: "Rate" })).getByRole("radio", { name: "Quarterly" }));
  expect(screen.getByText(/tradables n\/a, non-tradables n\/a/)).toBeInTheDocument();
});
