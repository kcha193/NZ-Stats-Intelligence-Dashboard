import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import type { ForecastEvaluation } from "@/api/types";
import evaluation from "@/test/fixtures/research_synthetic_evaluation.json";
import { mockApi, renderWithProviders } from "@/test/mockApi";
import { ForecastTrack } from "./ForecastTrack";

vi.mock("@/charts/EChart", () => ({ EChart: ({ ariaLabel }: { ariaLabel: string }) =>
  <div role="img" aria-label={ariaLabel} /> }));

const unverified = () => {
  const data = structuredClone(evaluation) as unknown as ForecastEvaluation;
  data.evaluated = data.evaluated.map((row) => ({ ...row,
    first: row.first ? { ...row.first, first_release: false } : null,
    error_first: null, outcome_revision: null,
  }));
  data.summaries = [];
  data.rankings = [];
  return data;
};

const renderEvaluation = (data: ForecastEvaluation) => {
  mockApi({
    "/api/research/forecast-history": { series: [], measure_changes: [], excluded: [], note: "" },
    "/api/research/forecast-evaluation": data,
  });
  renderWithProviders(<ForecastTrack indicator="cpi_inflation" />);
};

it("keeps observed outcomes visible without scoring an unverified first-publication baseline", async () => {
  renderEvaluation(unverified());
  expect(await screen.findByText(/First-published outcomes are unverified/)).toBeInTheDocument();
  expect(screen.queryByRole("figure", { name: "Forecast minus first-published outcome" })).not.toBeInTheDocument();
  await userEvent.setup().click(screen.getByText(/Matched forecasts/));
  const table = screen.getByRole("table", { name: "Forecasts matched to official outcomes" });
  expect(within(table).getAllByText(/earliest stored/).length).toBeGreaterThan(0);
  expect(within(table).getAllByText("Not scored").length).toBeGreaterThan(0);
});

it("draws first-publication errors only for the verified subset", async () => {
  const data = unverified();
  const row = data.evaluated.find((entry) => entry.first)!;
  row.first!.first_release = true;
  row.error_first = 0.3;
  renderEvaluation(data);
  const chart = await screen.findByRole("img", { name: /^Forecast errors:/ });
  expect(chart).toHaveAccessibleName(/0\.3 points/);
  expect(chart).not.toHaveAccessibleName(/quarter  points/);
});
