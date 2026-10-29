import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import gdp from "@/test/fixtures/gdp.json";
import labour from "@/test/fixtures/labour_market.json";
import { mockApi, renderWithProviders } from "@/test/mockApi";
import GrossDomesticProduct from "./GrossDomesticProduct";
import LabourMarket from "./LabourMarket";
import OfficialCashRate from "./OfficialCashRate";

vi.mock("@/charts/EChart", () => ({ EChart: ({ ariaLabel, option }: { ariaLabel: string; option: unknown }) =>
  <div role="img" aria-label={ariaLabel} data-option={JSON.stringify(option)} /> }));

const option = (name: string) => JSON.parse(screen.getByRole("img", { name }).getAttribute("data-option")!);

it("GDP: names each growth measure, its period and source", async () => {
  mockApi({ "/api/gdp": gdp });
  renderWithProviders(<GrossDomesticProduct />);
  expect(await screen.findByRole("heading", { name: "Gross domestic product", level: 1 })).toBeInTheDocument();
  const kpis = screen.getByRole("region", { name: "GDP key indicators" });
  expect(kpis).toHaveTextContent("Quarterly GDP growth");
  expect(kpis).toHaveTextContent("0.2%");
  expect(kpis).toHaveTextContent("Annual average GDP growth");
  expect(kpis).toHaveTextContent("1.7%");
  expect(kpis).toHaveTextContent("2.6%");
  expect(screen.getByText(/rose 0.2% in the June 2026 quarter/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Official Stats NZ release" })).toHaveAttribute("href", expect.stringContaining("stats.govt.nz"));
  expect(screen.getByRole("link", { name: "Compare with forecasts" })).toHaveAttribute("href", "/economic-outlook");
});

it("GDP: switches between measures without putting two on one axis", async () => {
  mockApi({ "/api/gdp": gdp });
  renderWithProviders(<GrossDomesticProduct />);
  const user = userEvent.setup();
  await screen.findByRole("img", { name: "GDP growth history" });
  expect(option("GDP growth history").series).toHaveLength(1);
  expect(option("GDP growth history").series[0].type).toBe("bar");
  await user.click(within(screen.getByRole("group", { name: "Growth measure" })).getByRole("radio", { name: "Annual average" }));
  const avg = option("GDP growth history");
  expect(avg.series).toHaveLength(1);
  expect(avg.series[0].name).toBe("Annual average GDP growth (production, real)");
});

it("GDP: shows first-published against latest growth with the revision", async () => {
  mockApi({ "/api/gdp": gdp });
  renderWithProviders(<GrossDomesticProduct />);
  const chart = await screen.findByRole("img", { name: "GDP growth, first published and latest" });
  const opt = JSON.parse(chart.getAttribute("data-option")!);
  expect(opt.series.map((s: { name: string }) => s.name)).toEqual(["First published", "Latest"]);
  expect(screen.getAllByText(/earliest stored/).length).toBeGreaterThan(0);
});

it("GDP: a missing dashboard is an explicit state", async () => {
  mockApi({});
  renderWithProviders(<GrossDomesticProduct />);
  expect(await screen.findByText("GDP data has not been ingested yet")).toBeInTheDocument();
});

it("Labour market: HLFS rates and the LCI stay separate", async () => {
  mockApi({ "/api/labour-market": labour });
  renderWithProviders(<LabourMarket />);
  expect(await screen.findByRole("heading", { name: "Labour market", level: 1 })).toBeInTheDocument();
  const kpis = screen.getByRole("region", { name: "Labour market key indicators" });
  expect(kpis).toHaveTextContent("5.6%");
  expect(kpis).toHaveTextContent("Labour Cost Index, annual change");
  expect(screen.getByText(/first published as 5.3%/)).toBeInTheDocument();
  expect(option("Labour market rate history").series).toHaveLength(1);
  expect(option("Labour Cost Index annual change").series[0].name).toBe("Labour Cost Index, annual change");
  expect(screen.getAllByText(/not average earnings/).length).toBeGreaterThan(0);
});

it("Labour market: switching the rate redraws one series", async () => {
  mockApi({ "/api/labour-market": labour });
  renderWithProviders(<LabourMarket />);
  const user = userEvent.setup();
  await screen.findByRole("img", { name: "Labour market rate history" });
  await user.click(within(screen.getByRole("group", { name: "Rate" })).getByRole("radio", { name: "Underutilisation" }));
  const o = option("Labour market rate history");
  expect(o.series).toHaveLength(1);
  expect(o.series[0].name).toBe("Underutilisation rate (HLFS, seasonally adjusted)");
});

it("OCR: explains why no figure is shown and never shows a rate", async () => {
  renderWithProviders(<OfficialCashRate />);
  expect(screen.getByRole("heading", { name: "Official Cash Rate", level: 1 })).toBeInTheDocument();
  expect(screen.getByText(/not yet approved/)).toBeInTheDocument();
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
  expect(document.body.textContent).not.toMatch(/\d\.\d{2}%/);
});
