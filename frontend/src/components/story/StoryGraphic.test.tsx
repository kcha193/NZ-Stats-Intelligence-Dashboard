import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { CpiDashboard, EctDashboard, SeriesData } from "@/api/types";
import cpiFixture from "@/test/fixtures/cpi.json";
import ectFixture from "@/test/fixtures/ect.json";
import arrivals from "@/test/fixtures/series_arrivals_ry.json";
import departures from "@/test/fixtures/series_departures_ry.json";
import net from "@/test/fixtures/series_net_ry.json";
import nonNz from "@/test/fixtures/series_net_nonnz_ry.json";
import nz from "@/test/fixtures/series_net_nz_ry.json";
import { buildCpiStories } from "@/stories/cpi";
import { buildEctStories } from "@/stories/ect";
import { buildMigrationStories } from "@/stories/migration";
import { StoryGraphic } from "./StoryGraphic";

const stories = new Map([
  ...buildCpiStories(cpiFixture as unknown as CpiDashboard),
  ...buildEctStories(ectFixture as unknown as EctDashboard),
  ...buildMigrationStories({
    net: net as SeriesData, arrivals: arrivals as SeriesData, departures: departures as SeriesData, nz: nz as SeriesData, nonNz: nonNz as SeriesData, releases: [],
  }),
].map((s) => [s.template, s]));
const draw = (template: string, size: "sm" | "lg" = "sm") => render(<StoryGraphic thumb={stories.get(template)!.thumb} size={size} />);

describe("StoryGraphic", () => {
  it("labels the latest annual inflation rate and the ten-year peak, in percent", () => {
    draw("inflation-annual");
    const img = screen.getByRole("img", { name: /^Annual CPI inflation, Sep 2016 to Jun 2026\. Latest 4\.1% \(Jun 2026\)\. Peak 7\.3% \(Jun 2022\)\.$/ });
    expect(img).toHaveTextContent("4.1%");
    expect(img).toHaveTextContent("Peak 7.3%, Jun 2022");
  });

  it("prints contributions in percentage points and says when a compact graphic shows only the largest", () => {
    draw("inflation-drivers");
    const img = screen.getByRole("img", { name: /^Contribution to quarterly inflation, by group: Transport \+0\.82 pp/ });
    expect(img).toHaveTextContent("+0.82 pp");
    expect(img).not.toHaveTextContent(/\+0\.82%/);
    expect(img).toHaveTextContent(/Largest 6 of \d+ shown/);
  });

  it("shows every group in the large version", () => {
    draw("inflation-drivers", "lg");
    expect(screen.getByRole("img")).not.toHaveTextContent(/Largest \d+ of/);
  });

  it("draws tradables and non-tradables on one axis through 0% and states the gap in percentage points", () => {
    draw("inflation-tradables");
    const img = screen.getByRole("img", { name: /Tradables 4\.9%; Non-tradables 3\.4%\. Gap: \+1\.5 pp\./ });
    expect(img).toHaveTextContent("0%");
    expect(img).toHaveTextContent("+1.5 pp");
  });

  it("marks provisional migration estimates and names year-ended periods", () => {
    draw("migration-net");
    const img = screen.getByRole("img", { name: /Latest \+20,350 \(YE Jul 2026, provisional\)/ });
    expect(img).toHaveTextContent("provisional");
    expect(img).toHaveTextContent("YE Jul 2026");
  });

  it("states the signed monthly change for the latest month on the retail columns", () => {
    draw("spending-retail");
    expect(screen.getByRole("img", { name: /Latest −0\.4% \(Sep 2026\)/ })).toHaveTextContent("−0.4%");
  });

  it("gives arrivals and departures as counts, with their difference", () => {
    draw("migration-flows");
    expect(screen.getByRole("img")).toHaveTextContent(/134,434.*114,084.*Arrivals minus departures: \+20,350/);
  });
});
