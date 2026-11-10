import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { formatForecastValue } from "@/charts/forecasts";
import { mockApi, renderWithProviders } from "@/test/mockApi";
import { BankCards } from "./BankCards";
import { BankForecastTable } from "./BankForecastTable";
import { BankOutlook } from "./BankOutlook";
import { BANKS, CARDS, FORECASTS, SUMMARY } from "./testData";

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
});
