import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockApi, renderWithProviders } from "@/test/mockApi";
import { BankEvidence } from "./BankEvidence";
import { BankHealth } from "./BankHealth";
import { BankOutlook } from "./BankOutlook";
import { CONSENSUS, FORECASTS, FRESHNESS, REVISIONS, SUMMARY, bankForecast, CPI_A } from "./testData";

vi.mock("@/charts/EChart", () => ({ EChart: ({ ariaLabel }: { ariaLabel: string }) => <div role="img" aria-label={ariaLabel} /> }));

const BASE = "/api/internal/bank-intelligence";
const routes = () => ({
  "/api/capabilities": { internal_drafts: true },
  [`${BASE}/summary`]: SUMMARY,
  [`${BASE}/forecasts`]: FORECASTS,
  [`${BASE}/consensus`]: CONSENSUS,
  [`${BASE}/revisions`]: REVISIONS,
  [`${BASE}/freshness`]: FRESHNESS,
});

afterEach(() => vi.unstubAllGlobals());

describe("BankEvidence", () => {
  const item = bankForecast(CPI_A, { claim_path: "forecasts[3]", forecast_author: "Example Bank A" });

  it("shows the source passage, the document, the place in it, the author and the checker", () => {
    renderWithProviders(<BankEvidence item={item} onClose={() => {}} />);
    const dialog = screen.getByRole("dialog", { name: /Example Bank A.*Year to June 2027|Example Bank A.*year to June 2027/i });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(within(dialog).getByText(/SYNTHETIC quote: inflation is forecast to ease/)).toBeInTheDocument();
    expect(within(dialog).getByText("SYNTHETIC outlook")).toBeInTheDocument();
    expect(within(dialog).getByText(/section 1, page 2/i)).toBeInTheDocument();
    expect(within(dialog).getByText("verify-5")).toBeInTheDocument();
    expect(within(dialog).getByText("forecasts[3]")).toBeInTheDocument();
    expect(within(dialog).getByText(/automated checks, not a person/i)).toBeInTheDocument();
  });

  it("says a table figure was read directly from the report's table, not by an AI, and escapes its text", () => {
    const f = { ...CPI_A, summary_id: -4, evidence: [{ section_ordinal: -1, page: 6, quote: "Annual CPI inflation <b>(%)</b> | Forecast / Jun-26 | 2.6" }] };
    const table = bankForecast(f, { claim_path: "tables[4:2]", extraction_method: "table", verifier_version: "tables-1" });
    renderWithProviders(<BankEvidence item={table} onClose={() => {}} />);
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/read directly from a table in the report/i)).toBeInTheDocument();
    expect(within(dialog).getByText(/table cell, page 6/i)).toBeInTheDocument();
    expect(within(dialog).queryByText(/section -1/i)).not.toBeInTheDocument();
    expect(within(dialog).getByText(/no ai was used/i)).toBeInTheDocument();
    expect(within(dialog).queryByText(/automated checks, not a person/i)).not.toBeInTheDocument();
    expect(within(dialog).getByText(/<b>\(%\)<\/b>/)).toBeInTheDocument(); // shown as text, not parsed as markup
    expect(dialog.querySelector("b")).toBeNull();
  });

  it("closes on Escape and on the close button, and traps Tab inside", async () => {
    const onClose = vi.fn();
    renderWithProviders(<BankEvidence item={item} onClose={onClose} />);
    const close = screen.getByRole("button", { name: "Close" });
    await waitFor(() => expect(close).toHaveFocus());
    await userEvent.tab();
    expect(close).toHaveFocus(); // the only focusable element: Tab stays inside the dialog
    await userEvent.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);
    await userEvent.click(close);
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});

describe("BankHealth", () => {
  it("lists each series with its state in words and four separate dates", () => {
    renderWithProviders(<BankHealth rows={FRESHNESS.banks} />);
    const table = screen.getByRole("table", { name: /source health/i });
    for (const header of ["Bank", "Series", "State", "Newest report", "Ingested", "Analysed", "Last checked"]) {
      expect(within(table).getByRole("columnheader", { name: header })).toBeInTheDocument();
    }
    const row = within(table).getByRole("row", { name: /Quarterly Outlook/ });
    expect(within(row).getByText("Up to date")).toBeInTheDocument();
    expect(within(row).getByText("1 Oct 2026")).toBeInTheDocument();
    expect(within(row).getByText("26 Oct 2026")).toBeInTheDocument();
    expect(within(row).getByText("27 Oct 2026")).toBeInTheDocument();
    expect(within(row).getByText("10 Nov 2026")).toBeInTheDocument();
  });

  it("shows a bank with no series as one row with its state", () => {
    renderWithProviders(<BankHealth rows={[{ key: "example_c", name: "Example Bank C", state: "permission_denied", series: [] }]} />);
    const row = screen.getByRole("row", { name: /Example Bank C/ });
    expect(within(row).getByText("No access granted")).toBeInTheDocument();
  });
});

describe("BankOutlook, all sections", () => {
  it("opens the evidence drawer from a table cell, closes it on Escape and returns focus to the cell", async () => {
    mockApi(routes());
    renderWithProviders(<BankOutlook />);
    const cell = await screen.findByRole("button", { name: /Example Bank A.*2\.1%/ });
    cell.focus();
    await userEvent.keyboard("{Enter}");
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/SYNTHETIC quote/)).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(cell).toHaveFocus();
  });

  it("lists what was left out and why, by bank name, under the table, the consensus and the revisions", async () => {
    const left = (code: string) => [
      { institution_key: "example_b", summary_id: 2, claim_path: "forecasts[0]", code, reason: `SYNTHETIC reason for ${code}` },
    ];
    mockApi({
      ...routes(),
      [`${BASE}/forecasts`]: { ...FORECASTS, excluded: left("claim_failed_checks") },
      [`${BASE}/consensus`]: { ...CONSENSUS, consensus: { ...CONSENSUS.consensus, excluded: left("newer_claim_unusable") } },
      [`${BASE}/revisions`]: { ...REVISIONS, excluded: left("no_publication_date") },
    });
    renderWithProviders(<BankOutlook />);
    await screen.findByRole("heading", { name: "Revisions" });
    for (const code of ["claim_failed_checks", "newer_claim_unusable", "no_publication_date"]) {
      expect(screen.getByText(`Example Bank B: SYNTHETIC reason for ${code}`)).toBeInTheDocument();
    }
    expect(screen.getAllByText(/Left out \(1\)/)).toHaveLength(3);
  });

  it("shows no left-out list when nothing was left out", async () => {
    mockApi(routes());
    renderWithProviders(<BankOutlook />);
    await screen.findByRole("heading", { name: "Revisions" });
    expect(screen.queryByText(/Left out/)).not.toBeInTheDocument();
  });

  it("shows the consensus, divergence and source health sections", async () => {
    mockApi(routes());
    renderWithProviders(<BankOutlook />);
    expect(await screen.findByRole("figure", { name: /Consensus of banks/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Where banks disagree" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Revisions" })).toBeInTheDocument();
    expect(await screen.findByRole("table", { name: /source health/i })).toBeInTheDocument();
  });
});
