import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { mockApi, renderWithProviders } from "@/test/mockApi";
import countries from "@/test/fixtures/countries.json";
import detail from "@/test/fixtures/release_detail.json";
import netM from "@/test/fixtures/series_net_m.json";
import netRy from "@/test/fixtures/series_net_ry.json";
import arrRy from "@/test/fixtures/series_arrivals_ry.json";
import depRy from "@/test/fixtures/series_departures_ry.json";
import overview from "@/test/fixtures/overview.json";
import releases from "@/test/fixtures/releases.json";
import revisions from "@/test/fixtures/revisions.json";
import { formatNumber } from "@/lib/format";
import Migration from "./Migration";

vi.mock("@/charts/EChart", () => ({
  EChart: ({ ariaLabel, option }: { ariaLabel: string; option: unknown }) => (
    <div role="img" aria-label={ariaLabel} data-option={JSON.stringify(option, (_, v) => (typeof v === "function" ? "fn" : v))} />
  ),
}));

const cit = (key: string) => ({ ...netRy, series: { ...netRy.series, key } });

const baseRoutes = (): Record<string, unknown> => ({
    "/api/overview": overview,
    "/api/releases": releases,
    [`/api/releases/${detail.release.id}`]: detail,
    "/api/series/mig.m.net": netM,
    "/api/series/mig.ry.net": netRy,
    "/api/series/mig.ry.arrivals": arrRy,
    "/api/series/mig.ry.departures": depRy,
    "/api/series/mig.m.arrivals": netM,
    "/api/series/mig.m.departures": netM,
    "/api/series/mig.ry.net.nz": cit("mig.ry.net.nz"),
    "/api/series/mig.ry.net.nonnz": cit("mig.ry.net.nonnz"),
    "/api/series/mig.ry.arrivals.nz": cit("mig.ry.arrivals.nz"),
    "/api/series/mig.ry.arrivals.nonnz": cit("mig.ry.arrivals.nonnz"),
    "/api/series/mig.ry.departures.nz": cit("mig.ry.departures.nz"),
    "/api/series/mig.ry.departures.nonnz": cit("mig.ry.departures.nonnz"),
    "/api/migration/countries": countries,
    "/api/revisions/mig.m.net": revisions,
});

describe("Migration page", () => {
  beforeEach(() => {
    mockApi(baseRoutes());
  });

  it("renders findings first, then the seven analytical views, each with a source and export", async () => {
    renderWithProviders(<Migration />);
    expect(await screen.findByRole("heading", { name: /international migration/i, level: 1 })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: /key statistical findings/i })).toBeInTheDocument();
    const charts = await screen.findAllByRole("figure");
    expect(charts.length).toBeGreaterThanOrEqual(6);
    for (const name of [/net migration/i, /arrivals and departures/i, /monthly estimate .* year ended/i, /citizenship/i, /country/i, /revisions/i]) {
      expect(screen.getAllByRole("heading", { level: 3, name }).length).toBeGreaterThan(0);
    }
    expect((await screen.findAllByRole("button", { name: /download data/i })).length).toBeGreaterThanOrEqual(6);
  });

  it("keeps monthly and year-ended frequencies separate when toggled", async () => {
    renderWithProviders(<Migration />);
    const group = await screen.findByRole("group", { name: /net migration frequency/i });
    await userEvent.click(within(group).getByRole("radio", { name: /monthly/i }));
    const chart = await screen.findByRole("img", { name: "Monthly net migration chart" });
    expect(chart.getAttribute("data-option")).toContain('"type":"bar"');
    await userEvent.click(within(group).getByRole("radio", { name: /year ended/i }));
    expect(await screen.findByRole("img", { name: "Year-ended net migration chart" })).toBeInTheDocument();
  });

  it("states the revision coverage limitation", async () => {
    renderWithProviders(<Migration />);
    expect(await screen.findByText(revisions.coverage.note.slice(0, 40), { exact: false })).toBeInTheDocument();
  });

  it("derived country ranking says it is derived and excludes regions from the ranking", async () => {
    renderWithProviders(<Migration />);
    expect((await screen.findAllByText(/derived/i)).length).toBeGreaterThan(0);
  });

  describe("chart titles carry the status of the latest value (audit)", () => {
    const finalise = (d: typeof netRy) => ({ ...d, points: d.points.map((p) => ({ ...p, status: "final" })) });
    const titles = async () => {
      for (const name of [/^Year-ended net migration:/, /^Arrivals and departures/, /by citizenship/]) {
        await screen.findByRole("heading", { level: 3, name });
      }
      return screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent ?? "");
    };

    it("marks a provisional latest value in the trend, arrivals/departures and citizenship titles", async () => {
      renderWithProviders(<Migration />);
      const all = await titles();
      expect(all.find((t) => t.startsWith("Year-ended net migration:"))).toMatch(/year ended Jul 2026, provisional\)/);
      expect(all.find((t) => t.startsWith("Arrivals and departures"))).toMatch(/year ended Jul 2026, provisional:/);
      expect(all.find((t) => t.includes("by citizenship"))).toMatch(/year ended Jun 2026|year ended Jul 2026/);
      expect(all.find((t) => t.includes("by citizenship"))).toMatch(/, provisional:/);
    });

    it("says nothing about provisional status when the latest values are final", async () => {
      mockApi({
        ...baseRoutes(),
        "/api/series/mig.ry.net": finalise(netRy),
        "/api/series/mig.ry.arrivals": finalise(arrRy),
        "/api/series/mig.ry.departures": finalise(depRy),
        "/api/series/mig.ry.net.nz": finalise(cit("mig.ry.net.nz") as typeof netRy),
        "/api/series/mig.ry.net.nonnz": finalise(cit("mig.ry.net.nonnz") as typeof netRy),
      });
      renderWithProviders(<Migration />);
      const all = await titles();
      for (const prefix of ["Year-ended net migration:", "Arrivals and departures"]) {
        expect(all.find((t) => t.startsWith(prefix))).not.toMatch(/provisional/);
      }
      expect(all.find((t) => t.includes("by citizenship"))).not.toMatch(/provisional/);
    });
  });

  describe("citizenship chart (review #4253711087)", () => {
    const nzWith = (patch: Record<string, unknown>) => ({ ...cit("mig.ry.net.nz"), ...patch });

    it("declines to combine series that come from different vintages", async () => {
      const older = nzWith({ vintage: { ...netRy.vintage, captured_at: "2026-10-12T09:00:00+13:00" } });
      mockApi({ ...baseRoutes(), "/api/series/mig.ry.net.nz": older });
      renderWithProviders(<Migration />);
      expect(await screen.findByText(/different releases or ingests/i)).toBeInTheDocument();
      expect(screen.queryByRole("img", { name: /by citizenship chart/i })).not.toBeInTheDocument();
    });

    it("states the values for the latest period both series share", async () => {
      const shorter = nzWith({ points: netRy.points.slice(0, -1) });
      mockApi({ ...baseRoutes(), "/api/series/mig.ry.net.nz": shorter });
      renderWithProviders(<Migration />);
      const shared = netRy.points[netRy.points.length - 2];
      const heading = await screen.findByRole("heading", { level: 3, name: /by citizenship/i });
      expect(heading).toHaveTextContent(`non-NZ citizens ${formatNumber(shared.value)}, NZ citizens ${formatNumber(shared.value)}`);
      expect(heading).toHaveTextContent("year ended Jun 2026");
      expect(heading).not.toHaveTextContent(formatNumber(netRy.points[netRy.points.length - 1].value));
    });

    it("still combines series from one vintage", async () => {
      renderWithProviders(<Migration />);
      expect(await screen.findByRole("img", { name: /by citizenship chart/i })).toBeInTheDocument();
    });
  });
});
