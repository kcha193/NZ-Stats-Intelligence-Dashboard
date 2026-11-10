import { screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Overview } from "@/api/types";
import { CONSENSUS, FORECASTS, FRESHNESS, REVISIONS, SUMMARY } from "@/components/outlook/bank/testData";
import overview from "@/test/fixtures/overview.json";
import { mockApi, renderWithProviders } from "@/test/mockApi";
import EconomicOutlook from "./EconomicOutlook";

vi.mock("@/charts/EChart", () => ({ EChart: ({ ariaLabel }: { ariaLabel: string }) => <div role="img" aria-label={ariaLabel} /> }));

const BASE = "/api/internal/bank-intelligence";
const routes = (internal: boolean) => ({
  "/api/overview": overview as unknown as Overview,
  "/api/capabilities": { internal_drafts: internal },
  [`${BASE}/summary`]: SUMMARY,
  [`${BASE}/forecasts`]: FORECASTS,
  [`${BASE}/consensus`]: CONSENSUS,
  [`${BASE}/revisions`]: REVISIONS,
  [`${BASE}/freshness`]: FRESHNESS,
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

const urls = (fn: ReturnType<typeof vi.fn>) => fn.mock.calls.map((c) => String(c[0]));

describe("Economic outlook, bank outlooks", () => {
  it("shows the bank section when the server has internal analysis on", async () => {
    mockApi(routes(true));
    renderWithProviders(<EconomicOutlook />);
    expect(await screen.findByRole("heading", { name: "Bank outlooks" })).toBeInTheDocument();
  });

  it("shows no bank section, and asks for no bank data, when internal analysis is off", async () => {
    const fn = mockApi(routes(false));
    renderWithProviders(<EconomicOutlook />);
    expect(await screen.findByRole("heading", { level: 1, name: "Economic outlook" })).toBeInTheDocument();
    await waitFor(() => expect(urls(fn).some((u) => u.includes("/api/capabilities"))).toBe(true));
    expect(screen.queryByRole("heading", { name: "Bank outlooks" })).not.toBeInTheDocument();
    expect(urls(fn).some((u) => u.includes("bank-intelligence"))).toBe(false);
  });

  it("never mounts or requests the bank section on the static site", async () => {
    vi.stubEnv("VITE_DATA_MODE", "static");
    const fn = mockApi(routes(true));
    renderWithProviders(<EconomicOutlook />);
    expect(await screen.findByRole("heading", { level: 1, name: "Economic outlook" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Bank outlooks" })).not.toBeInTheDocument();
    expect(urls(fn).some((u) => u.includes("bank-intelligence") || u.includes("/api/internal"))).toBe(false);
  });
});
