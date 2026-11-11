import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { BankForecasts } from "@/api/bank";
import type { Forecast } from "@/api/types";
import { formatForecastValue } from "@/charts/forecasts";
import { mockApi, renderWithProviders } from "@/test/mockApi";
import { BankCards } from "./BankCards";
import { BankForecastTable } from "./BankForecastTable";
import { BankOutlook } from "./BankOutlook";
import { bankForecast, BANKS, CARDS, forecast, FORECASTS, group, SUMMARY } from "./testData";

const BASE = "/api/internal/bank-intelligence";
const routes = (over: Record<string, unknown> = {}) => ({
  "/api/capabilities": { internal_drafts: true },
  [`${BASE}/summary`]: SUMMARY,
  [`${BASE}/forecasts`]: FORECASTS,
  ...over,
});

afterEach(() => vi.unstubAllGlobals());

describe("BankCards", () => {
  it("shows one card per bank with report, date, state and the AI-interpretation label", () => {
    renderWithProviders(<BankCards cards={CARDS} />);
    expect(screen.getAllByRole("article")).toHaveLength(3);
    const a = screen.getByRole("article", { name: /Example Bank A/ });
    expect(within(a).getByText(/SYNTHETIC outlook A/)).toBeInTheDocument();
    expect(within(a).getByText(/1 Oct 2026/)).toBeInTheDocument();
    expect(within(a).getByText("Up to date")).toBeInTheDocument();
    expect(within(a).getByText("AI interpretation")).toBeInTheDocument();
    expect(within(a).getByText(/No automated issue detected/)).toBeInTheDocument();
    const b = screen.getByRole("article", { name: /Example Bank B/ });
    expect(within(b).getByText("Stale")).toBeInTheDocument();
    expect(within(b).getByText(/Failed automated checks/)).toBeInTheDocument();
  });

  it("keeps a reading that failed its checks behind its failure label, closed, and never as the bank's view", () => {
    renderWithProviders(<BankCards cards={CARDS} />);
    const b = screen.getByRole("article", { name: /Example Bank B/ });
    const details = b.querySelector("details");
    expect(details).not.toBeNull();
    expect(details).not.toHaveAttribute("open");
    expect(within(details as HTMLElement).getByText(/failed automated checks/i, { selector: "summary" })).toBeInTheDocument();
    expect(within(details as HTMLElement).getByText(/Synthetic stance with a problem/)).toBeInTheDocument();
    const a = screen.getByRole("article", { name: /Example Bank A/ });
    expect(a.querySelector("details")).toBeNull(); // a clean reading is shown plainly
  });

  it("says when a bank's reports carry no date, rather than calling it up to date", () => {
    renderWithProviders(<BankCards cards={[{ ...CARDS[0], state: "undated", stance: null }]} />);
    const a = screen.getByRole("article", { name: /Example Bank A/ });
    expect(within(a).getByText("Date unknown")).toBeInTheDocument();
    expect(within(a).getByText(/none states a publication date/i)).toBeInTheDocument();
  });

  it("names the series behind a series-level state, beside the report that was received", () => {
    renderWithProviders(<BankCards cards={[{ ...CARDS[0], state: "missing", worst_series: "Weekly Note" }]} />);
    const a = screen.getByRole("article", { name: /Example Bank A/ });
    expect(within(a).getByText("Nothing received · Weekly Note")).toBeInTheDocument();
    expect(within(a).getByText(/SYNTHETIC outlook A/)).toBeInTheDocument();
  });

  it("shows a bank without access as its state and one sentence, with no stance", () => {
    renderWithProviders(<BankCards cards={CARDS} />);
    const c = screen.getByRole("article", { name: /Example Bank C/ });
    expect(within(c).getByText("No access granted")).toBeInTheDocument();
    expect(within(c).getByText(/nothing is collected or shown/i)).toBeInTheDocument();
    expect(within(c).queryByText("AI interpretation")).not.toBeInTheDocument();
  });
});

describe("BankForecastTable", () => {
  const banks = FORECASTS.banks;

  it("is a real table with a caption, header scopes and a column per bank", () => {
    renderWithProviders(<BankForecastTable data={FORECASTS} banks={banks} indicator="cpi_inflation" />);
    const table = screen.getByRole("table");
    expect(within(table).getByText(/CPI inflation forecasts by bank/i, { selector: "caption" })).toBeInTheDocument();
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(
      expect.arrayContaining(["Example Bank A", "Example Bank B", "Example Bank C"]),
    );
    const row = within(table).getByRole("rowheader", { name: /Year to June 2027/ });
    expect(row).toHaveAttribute("scope", "row");
    expect(within(table).getAllByRole("columnheader")[0]).toHaveAttribute("scope", "col");
  });

  it("shows value, unit and period, and marks a missing forecast without filling it", () => {
    renderWithProviders(<BankForecastTable data={FORECASTS} banks={banks} indicator="cpi_inflation" />);
    expect(screen.getByRole("button", { name: /Example Bank A.*2\.1%/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Example Bank B.*2\.4%/ })).toBeInTheDocument();
    const cells = screen.getAllByText("No forecast");
    expect(cells.length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: /Example Bank C/ })).not.toBeInTheDocument();
  });

  it("keeps zero and negative values and their sign", () => {
    renderWithProviders(<BankForecastTable data={FORECASTS} banks={banks} indicator="ocr" />);
    expect(screen.getByRole("button", { name: new RegExp(formatForecastValue(0, "%").replace(".", "\\.")) })).toBeInTheDocument();
    expect(formatForecastValue(0, "%")).toBe("0.0%");
    const negative = formatForecastValue(-0.25, "%");
    expect(negative).toMatch(/0\.25%$/);
    expect(screen.getByRole("button", { name: new RegExp(negative) })).toBeInTheDocument();
  });

  it("labels a forecast that comes from a weekly note", () => {
    renderWithProviders(<BankForecastTable data={FORECASTS} banks={banks} indicator="ocr" />);
    expect(screen.getByText(/weekly note/i)).toBeInTheDocument();
  });

  it("shows only the chosen indicator, and only the chosen banks as columns", () => {
    const { rerender } = renderWithProviders(<BankForecastTable data={FORECASTS} banks={banks} indicator="ocr" />);
    expect(screen.queryByRole("rowheader", { name: /Year to June 2027/ })).not.toBeInTheDocument();
    expect(screen.getByRole("rowheader", { name: /March 2027 quarter/ })).toBeInTheDocument();
    rerender(<BankForecastTable data={FORECASTS} banks={banks.slice(0, 1)} indicator="ocr" />);
    expect(screen.queryByRole("columnheader", { name: "Example Bank B" })).not.toBeInTheDocument();
  });

  it("tells the reader when no forecast exists for the chosen indicator", () => {
    renderWithProviders(<BankForecastTable data={FORECASTS} banks={banks} indicator="gdp" />);
    expect(screen.getByText(/no bank forecast for this indicator/i)).toBeInTheDocument();
  });

  it("calls onSelect with the forecast behind the clicked cell", async () => {
    const onSelect = vi.fn();
    renderWithProviders(<BankForecastTable data={FORECASTS} banks={banks} indicator="cpi_inflation" onSelect={onSelect} />);
    await userEvent.click(screen.getByRole("button", { name: /Example Bank A.*2\.1%/ }));
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ claim_path: "forecasts[0]", report_kind: "outlook" }));
  });

  it("opens the evidence of the claim behind each row when claims differ only in adjustment or scenario", async () => {
    const quoted = (quote: string, over: Partial<Forecast> = {}) =>
      forecast(BANKS[0], 2.1, { evidence: [{ section_ordinal: 1, page: 2, quote }], ...over });
    const sa = quoted("SYNTHETIC quote: seasonally adjusted");
    const nsa = quoted("SYNTHETIC quote: unadjusted");
    const central = quoted("SYNTHETIC quote: central");
    const downside = quoted("SYNTHETIC quote: downside", { scenario: "SYNTHETIC downside" });
    const forecasts = [
      bankForecast(sa, { claim_path: "forecasts[0]" }, "outlook", "seasonally_adjusted"),
      bankForecast(nsa, { claim_path: "forecasts[1]" }, "outlook", "unadjusted"),
      bankForecast(central, { claim_path: "forecasts[2]" }),
      bankForecast(downside, { claim_path: "forecasts[3]" }),
    ];
    const scenario = { key: "cpi_inflation|percent|annual_change|year_to:2027-06|downside", kind: "scenario", scenario: "SYNTHETIC downside" } as const;
    const data = {
      ...FORECASTS,
      forecasts,
      comparison: [
        { adjustment: "seasonally_adjusted", comparison: { ...FORECASTS.comparison[0].comparison, groups: [group({ rows: [{ forecast: sa, earlier_vintages: [] }] })] } },
        { adjustment: "unadjusted", comparison: { ...FORECASTS.comparison[0].comparison, groups: [group({ rows: [{ forecast: nsa, earlier_vintages: [] }] })] } },
        {
          adjustment: "not_stated",
          comparison: {
            ...FORECASTS.comparison[0].comparison,
            groups: [
              group({ rows: [{ forecast: central, earlier_vintages: [] }] }),
              group({ ...scenario, rows: [{ forecast: downside, earlier_vintages: [] }] }),
            ],
          },
        },
      ],
    } satisfies BankForecasts;
    const onSelect = vi.fn();
    renderWithProviders(<BankForecastTable data={data} banks={BANKS.slice(0, 1)} indicator="cpi_inflation" onSelect={onSelect} />);
    for (const button of screen.getAllByRole("button", { name: /Example Bank A/ })) await userEvent.click(button);
    expect(onSelect.mock.calls.map(([f]) => [f.claim_path, f.adjustment, f.forecast.evidence[0].quote])).toEqual([
      ["forecasts[0]", "seasonally_adjusted", "SYNTHETIC quote: seasonally adjusted"],
      ["forecasts[1]", "unadjusted", "SYNTHETIC quote: unadjusted"],
      ["forecasts[2]", "not_stated", "SYNTHETIC quote: central"],
      ["forecasts[3]", "not_stated", "SYNTHETIC quote: downside"],
    ]);
  });
});

describe("BankOutlook", () => {
  it("renders nothing when the server has internal analysis off", async () => {
    mockApi(routes({ "/api/capabilities": { internal_drafts: false } }));
    renderWithProviders(<BankOutlook />);
    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
    expect(screen.queryByRole("heading", { name: /bank outlooks/i })).not.toBeInTheDocument();
  });

  it("shows the notice, the cards and the table, and filters by indicator and bank", async () => {
    mockApi(routes());
    renderWithProviders(<BankOutlook />);
    expect(await screen.findByRole("heading", { name: "Bank outlooks" })).toBeInTheDocument();
    expect(screen.getByText(/Not independently reviewed/)).toBeInTheDocument();
    expect(screen.getAllByRole("article")).toHaveLength(3);
    expect(screen.getByRole("rowheader", { name: /Year to June 2027/ })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: "OCR" }));
    expect(await screen.findByRole("rowheader", { name: /March 2027 quarter/ })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: BANKS[0].name }));
    expect(screen.getAllByRole("article")).toHaveLength(1);
  });

  it("never calls a result verified, reviewed or approved (apart from the fixed notice)", async () => {
    mockApi(routes());
    const { container } = renderWithProviders(<BankOutlook />);
    await screen.findByRole("heading", { name: "Bank outlooks" });
    const text = (container.textContent ?? "").replace(/Not independently reviewed\./g, "");
    expect(text).not.toMatch(/\b(verified|reviewed|approved)\b/i);
  });

  it.each([
    ["no access", { cards: CARDS.map((c) => ({ ...c, state: "permission_denied", stance: null, report_name: null, published_on: null })) }, { ...FORECASTS, forecasts: [], comparison: [] }, /no bank source has been granted access/i],
    ["nothing imported", { cards: CARDS.map((c) => ({ ...c, state: "missing", stance: null, report_name: null, published_on: null })) }, { ...FORECASTS, forecasts: [], comparison: [] }, /no bank documents have been imported/i],
    ["nothing eligible", SUMMARY, { ...FORECASTS, forecasts: [], comparison: [] }, /no forecast is eligible/i],
  ])("says which empty state applies: %s", async (_name, summary, forecasts, expected) => {
    mockApi(routes({ [`${BASE}/summary`]: { notice: "n", ...summary }, [`${BASE}/forecasts`]: forecasts }));
    renderWithProviders(<BankOutlook />);
    expect(await screen.findByText(expected)).toBeInTheDocument();
  });

  it("lists claims that the comparison or the revision analysis could not use, with the reason", async () => {
    const [, bankB] = BANKS;
    const noUnit = forecast(bankB, 1.0, { unit: null });
    const noHorizon = forecast(BANKS[2], 1.2, { horizon: "next year" });
    const comparison = FORECASTS.comparison.map((c, i) =>
      i === 0 ? { ...c, comparison: { ...c.comparison, excluded: [{ forecast: noUnit, reason: "SYNTHETIC comparison reason: no unit." }] } } : c);
    const revisions = {
      histories: [{ adjustment: "not_stated", history: { series: [], measure_changes: [], excluded: [{ forecast: noHorizon, reason: "SYNTHETIC history reason: horizon." }] } }],
      excluded: [],
    };
    mockApi(routes({ [`${BASE}/forecasts`]: { ...FORECASTS, comparison }, [`${BASE}/revisions`]: revisions }));
    renderWithProviders(<BankOutlook />);
    expect(await screen.findByText(/SYNTHETIC comparison reason: no unit\./)).toBeInTheDocument();
    expect(await screen.findByText(/SYNTHETIC history reason: horizon\./)).toBeInTheDocument();
  });

  it("still lists what was left out, and why, when every claim was rejected and no forecast remains", async () => {
    const rejected = {
      ...FORECASTS,
      forecasts: [],
      comparison: [],
      excluded: [
        { institution_key: BANKS[0].key, summary_id: 1, claim_path: "forecasts[0]", code: "claim_failed_checks", reason: "SYNTHETIC reason: the claim failed an automated check." },
      ],
    };
    mockApi(routes({ [`${BASE}/forecasts`]: rejected }));
    renderWithProviders(<BankOutlook />);
    expect(await screen.findByText(/no forecast is eligible/i)).toBeInTheDocument();
    expect(screen.getByText("Left out (1)")).toBeInTheDocument();
    expect(screen.getByText(/SYNTHETIC reason: the claim failed an automated check\./)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});
