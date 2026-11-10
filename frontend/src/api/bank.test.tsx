import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockApi } from "@/test/mockApi";
import {
  useBankConsensus,
  useBankEvaluation,
  useBankForecasts,
  useBankFreshness,
  useBankRevisions,
  useBankSummary,
  type BankSummary,
} from "./bank";

// SYNTHETIC: fictitious banks and values only.
const SUMMARY: BankSummary = {
  notice: "AI-generated analysis for internal use.",
  cards: [
    {
      key: "example_a", name: "Example Bank A", state: "permission_denied", worst_series: null, report_name: null, published_on: null, stance: null,
    },
  ],
};
const BASE = "/api/internal/bank-intelligence";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

const asked = (fn: ReturnType<typeof vi.fn>) => fn.mock.calls.map(([u]) => new URL(String(u), "http://localhost").pathname + new URL(String(u), "http://localhost").search);

describe("bank-intelligence hooks", () => {
  it("request exactly the internal route, with the dashboard header, when internal drafts are on", async () => {
    const fn = mockApi({ "/api/capabilities": { internal_drafts: true }, [`${BASE}/summary`]: SUMMARY });
    const { result } = renderHook(() => useBankSummary(), { wrapper });
    await waitFor(() => expect(result.current.data).toEqual(SUMMARY));
    expect(asked(fn)).toContain(`${BASE}/summary`);
    const call = fn.mock.calls.find(([u]) => String(u).endsWith("/summary"));
    expect(JSON.stringify(call?.[1])).toContain("dashboard");
  });

  it("use one route each, and pass the indicator to evaluation only", async () => {
    const empty = {};
    const fn = mockApi({
      "/api/capabilities": { internal_drafts: true },
      [`${BASE}/forecasts`]: empty, [`${BASE}/revisions`]: empty, [`${BASE}/consensus`]: empty,
      [`${BASE}/freshness`]: empty, [`${BASE}/evaluation?indicator=gdp`]: empty,
    });
    const hooks = renderHook(
      () => [useBankForecasts(), useBankRevisions(), useBankConsensus(), useBankFreshness(), useBankEvaluation("gdp")],
      { wrapper },
    );
    await waitFor(() => expect(hooks.result.current.every((q) => q.data !== undefined)).toBe(true));
    for (const path of ["forecasts", "revisions", "consensus", "freshness"]) expect(asked(fn)).toContain(`${BASE}/${path}`);
    expect(asked(fn)).toContain(`${BASE}/evaluation?indicator=gdp`);
  });

  it("make no bank request when the server's internal switch is off", async () => {
    const fn = mockApi({ "/api/capabilities": { internal_drafts: false }, [`${BASE}/summary`]: SUMMARY });
    const { result } = renderHook(() => useBankSummary(), { wrapper });
    await waitFor(() => expect(result.current.data).toBeNull());
    expect(asked(fn).some((p) => p.includes("bank-intelligence"))).toBe(false);
  });

  it("make no request at all on the static site", async () => {
    vi.stubEnv("VITE_DATA_MODE", "static");
    const fn = mockApi({ [`${BASE}/summary`]: SUMMARY });
    const { result } = renderHook(() => useBankSummary(), { wrapper });
    await waitFor(() => expect(result.current.data).toBeNull());
    expect(fn).not.toHaveBeenCalled();
  });

  it("treat a 404 as not available rather than an error", async () => {
    mockApi({ "/api/capabilities": { internal_drafts: true } });
    const { result } = renderHook(() => useBankSummary(), { wrapper });
    await waitFor(() => expect(result.current.data).toBeNull());
    expect(result.current.isError).toBe(false);
  });
});
