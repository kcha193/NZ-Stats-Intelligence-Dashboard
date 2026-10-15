import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Kpi } from "@/api/types";
import { KpiCard } from "./KpiCard";

const kpi = (over: Partial<Kpi["metric"]> = {}): Kpi => ({
  release_id: 7,
  published_at: "2026-09-14T10:45:00+12:00",
  source_url: "https://www.stats.govt.nz/information-releases/international-migration-july-2026/",
  metric: {
    series_key: "mig.ry.net", label: "Net migration, year ended", value: 20350, unit: "people",
    frequency: "rolling_annual", period: "2026-07", period_label: "Year ended Jul 2026",
    status: "provisional", std_error: null,
    change_prior: { label: "vs year ended Jun 2026", comparison_period: "2026-06", previous: 17479, absolute: 2871, percent: 16.4 },
    change_year_ago: { label: "vs year ended Jul 2025", comparison_period: "2025-07", previous: 9600, absolute: 10750, percent: 112 },
    ...over,
  },
});

describe("KpiCard", () => {
  it("shows value, unit, reference period, comparisons, status, publication date and source", () => {
    render(<KpiCard kpi={kpi()} />);
    expect(screen.getByText("Net migration, year ended")).toBeInTheDocument();
    expect(screen.getByText("20,350")).toBeInTheDocument();
    expect(screen.getAllByText(/people/).length).toBeGreaterThan(0);
    expect(screen.getByText("Year ended Jul 2026")).toBeInTheDocument();
    expect(screen.getByText(/\+10,750/)).toBeInTheDocument();
    expect(screen.getByText(/\+112\.0%/)).toBeInTheDocument();
    expect(screen.getByText("Provisional")).toBeInTheDocument();
    expect(screen.getByText(/14 Sep 2026/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /source/i })).toHaveAttribute("href", expect.stringContaining("stats.govt.nz"));
  });

  it("shows n/a instead of a misleading percentage for a negative base", () => {
    const k = kpi({
      value: -38335,
      change_year_ago: { label: "vs year ended Jul 2025", comparison_period: "2025-07", previous: -40000, absolute: 1665, percent: null },
    });
    render(<KpiCard kpi={k} />);
    expect(screen.getByText("−38,335")).toBeInTheDocument();
    expect(screen.getByText(/n\/a/)).toBeInTheDocument();
  });
});
