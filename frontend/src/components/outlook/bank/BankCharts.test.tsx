import { screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { BankConsensusGroup, BankRevisions } from "@/api/bank";
import { renderWithProviders } from "@/test/mockApi";
import { BankConsensusChart } from "./BankConsensusChart";
import { BankDivergence } from "./BankDivergence";
import { BankRevisions as Revisions } from "./BankRevisions";
import { BANKS, CONSENSUS, CONSENSUS_GROUP, forecast } from "./testData";

vi.mock("@/charts/EChart", () => ({ EChart: ({ ariaLabel }: { ariaLabel: string }) => <div role="img" aria-label={ariaLabel} /> }));

const group = (over: Partial<BankConsensusGroup> = {}): BankConsensusGroup => ({ ...CONSENSUS_GROUP, ...over });

describe("BankConsensusChart", () => {
  it("titles three or more banks a consensus, and always says it is not a market consensus", () => {
    renderWithProviders(<BankConsensusChart groups={[group()]} indicator="cpi_inflation" />);
    const figure = screen.getByRole("figure", { name: /Consensus of banks/ });
    expect(within(figure).getByText("Not a market consensus.")).toBeInTheDocument();
    expect(within(figure).getByRole("img", { name: /CPI inflation.*Year to June 2027/ })).toBeInTheDocument();
    expect(within(figure).getByText(/median 2\.4%/i)).toBeInTheDocument();
  });

  it("titles two banks a comparison and never uses the word consensus for them", () => {
    const two = group({ n: 2, title: "Two-bank comparison", std_dev: null, contributors: CONSENSUS_GROUP.contributors.slice(0, 2) });
    const { container } = renderWithProviders(<BankConsensusChart groups={[two]} indicator="cpi_inflation" />);
    expect(screen.getByRole("figure", { name: /Two-bank comparison/ })).toBeInTheDocument();
    expect((container.textContent ?? "").replace(/Not a market consensus\./g, "")).not.toMatch(/consensus/i);
  });

  it("shows no chart for a single bank, only its value and why", () => {
    const one = group({ n: 1, title: "Insufficient banks", status: "insufficient", median: null, mean: null, minimum: null, maximum: null, range: null, std_dev: null, contributors: CONSENSUS_GROUP.contributors.slice(0, 1) });
    renderWithProviders(<BankConsensusChart groups={[one]} indicator="cpi_inflation" />);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByText(/only one bank/i)).toBeInTheDocument();
  });

  it("gives every chart a text alternative table of the same values, markers apart", () => {
    renderWithProviders(<BankConsensusChart groups={[group()]} indicator="cpi_inflation" />);
    const table = screen.getByRole("table", { name: /CPI inflation, Year to June 2027/ });
    expect(within(table).getByText("Example Bank A")).toBeInTheDocument();
    expect(within(table).getByText("2.1%")).toBeInTheDocument();
    expect(within(table).getByText(/Example Reference Bank/)).toBeInTheDocument();
    expect(screen.getByText(/not part of the bank figures/i)).toBeInTheDocument();
  });

  it("lists the forecasts the group left out, by bank, with the reason", () => {
    const stale = {
      forecast: forecast(BANKS[1], 1.0),
      reason: "Published more than 180 days before the newest contribution, so it is left out as stale.",
    };
    renderWithProviders(<BankConsensusChart groups={[group({ excluded: [stale] })]} indicator="cpi_inflation" />);
    expect(screen.getByText(`Example Bank B: ${stale.reason}`)).toBeInTheDocument();
    expect(screen.getByText(/Left out \(1\)/)).toBeInTheDocument();
  });

  it("shows only the chosen indicator, and says so when there is none", () => {
    renderWithProviders(<BankConsensusChart groups={[group()]} indicator="gdp" />);
    expect(screen.queryByRole("figure")).not.toBeInTheDocument();
    expect(screen.getByText(/no comparable bank forecasts for this indicator/i)).toBeInTheDocument();
  });

  it("labels the adjustment when it is stated", () => {
    renderWithProviders(<BankConsensusChart groups={[group({ adjustment: "seasonally_adjusted" })]} indicator="cpi_inflation" />);
    expect(screen.getByText(/seasonally adjusted/i)).toBeInTheDocument();
  });
});

describe("BankDivergence", () => {
  it("ranks groups by spread with each bank's signed distance from the median", () => {
    const narrow = { ...CONSENSUS.divergence[0], group_key: "x", horizon_label: "Year to June 2028", spread: 0.2, banks: CONSENSUS.divergence[0].banks.map((b) => ({ ...b, distance_from_median: b.distance_from_median / 3 })) };
    renderWithProviders(<BankDivergence items={[narrow, CONSENSUS.divergence[0]]} indicator="cpi_inflation" />);
    const items = screen.getAllByRole("listitem").filter((li) => li.closest("ol"));
    expect(items[0]).toHaveTextContent("Year to June 2027");
    expect(items[0]).toHaveTextContent(/0\.6 percentage points/);
    expect(items[0]).toHaveTextContent(/Example Bank A.*[−-]0\.3/);
    expect(items[0]).toHaveTextContent(/Example Bank C.*\+0\.3/);
  });

  it("says nothing is shown without three banks", () => {
    renderWithProviders(<BankDivergence items={[]} indicator="cpi_inflation" />);
    expect(screen.getByText(/needs at least three banks/i)).toBeInTheDocument();
  });
});

describe("BankRevisions", () => {
  const vintage = (published_on: string, value: number, revision: number | null) => ({
    summary_id: 1, published_on, document_title: "SYNTHETIC outlook", value, indicator_label: "Annual CPI inflation",
    horizon: "year to June 2027", qualification: null, evidence: [], superseded: revision === null, revision,
  });
  const series = (key: string, name: string, vintages: ReturnType<typeof vintage>[]) => ({
    key: `${key}|t`, target_key: "t", institution: { key, name, kind: "bank" }, indicator: "cpi_inflation", indicator_name: "CPI inflation",
    unit: "percent", unit_label: "%", basis: "annual_change", basis_label: "Annual change (through the year)",
    horizon_key: "year_to:2027-06", horizon_label: "Year to June 2027", kind: "central", scenario: null, vintages,
    latest: vintages[vintages.length - 1], n_revisions: vintages.length > 1 ? 1 : 0, total_revision: vintages.length > 1 ? 0.4 : null,
  });
  const data = (): BankRevisions => ({
    histories: [{
      adjustment: "not_stated",
      history: {
        series: [
          series("a", "Example Bank A", [vintage("2026-07-01", 2.0, null), vintage("2026-10-01", 2.4, 0.4)]),
          series("b", "Example Bank B", [vintage("2026-10-01", 2.2, null)]),
        ],
        measure_changes: [], excluded: [], note: "",
      },
    }],
  } as unknown as BankRevisions);

  it("draws a chart for a bank with two vintages and only text for one with a single vintage", () => {
    renderWithProviders(<Revisions data={data()} indicator="cpi_inflation" />);
    expect(screen.getByRole("img", { name: /Example Bank A.*2\.0%.*2\.4%/ })).toBeInTheDocument();
    expect(screen.getByText(/Example Bank B/)).toBeInTheDocument();
    expect(screen.getByText(/one forecast so far/i)).toBeInTheDocument();
    expect(screen.getByText(/revised up/i)).toBeInTheDocument();
  });

  it("says when there are no revisions to show", () => {
    renderWithProviders(<Revisions data={{ histories: [], excluded: [] }} indicator="cpi_inflation" />);
    expect(screen.getByText(/no revision history/i)).toBeInTheDocument();
  });
});
