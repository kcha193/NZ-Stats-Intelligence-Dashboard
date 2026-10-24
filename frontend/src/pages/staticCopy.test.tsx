import { screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { resetSnapshotCache } from "@/api/static";
import { renderWithProviders } from "@/test/mockApi";
import ElectronicCardTransactions from "./ElectronicCardTransactions";
import Inflation from "./Inflation";

const SID = "a".repeat(64);
const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status, headers: { "content-type": "application/json" } });

beforeEach(() => {
  resetSnapshotCache();
  vi.stubEnv("VITE_DATA_MODE", "static");
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) =>
    String(input).endsWith("manifest.json")
      ? json({ schema_version: 1, origin: "production", snapshot_id: SID, generated_at: "2026-10-24T08:00:00Z", data_updated_at: null })
      : json({ detail: "not found" }, 404)));
});
afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("a dashboard whose data is not in the snapshot", () => {
  it.each([
    ["Inflation", Inflation, /CPI data has not been published yet/],
    ["Card spending", ElectronicCardTransactions, /Card transactions data has not been published yet/],
  ])("%s says it has not been published, in words for visitors", async (_name, Page, title) => {
    renderWithProviders(<Page />);
    expect(await screen.findByText(title)).toBeInTheDocument();
    expect(screen.queryByText(/backfill|ingested|scheduled refresh/i)).not.toBeInTheDocument();
  });
});
