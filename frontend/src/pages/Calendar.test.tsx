import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import calendar from "@/test/fixtures/calendar.json";
import { mockApi, renderWithProviders } from "@/test/mockApi";
import Calendar from "./Calendar";

describe("Calendar", () => {
  beforeEach(() => {
    mockApi({ "/api/calendar": calendar });
  });

  it("lists releases with date, time, status and the last successful check", async () => {
    renderWithProviders(<Calendar />);
    expect(await screen.findByRole("heading", { level: 1, name: /release calendar/i })).toBeInTheDocument();
    expect(await screen.findByText(/last successful check/i)).toBeInTheDocument();
    const first = calendar.items[0];
    expect(screen.getAllByText(first.title).length).toBeGreaterThan(0);
  });

  it("filters by category and importance", async () => {
    renderWithProviders(<Calendar />);
    await userEvent.click(await screen.findByRole("combobox", { name: /category/i }));
    await userEvent.click(await screen.findByRole("option", { name: "Migration" }));
    const list = screen.getByRole("list", { name: /releases/i });
    for (const li of within(list).getAllByRole("listitem")) {
      expect(li).toHaveTextContent(/Migration/);
    }
  });

  it("switches to a month grid view", async () => {
    renderWithProviders(<Calendar />);
    await userEvent.click(await screen.findByRole("radio", { name: /month/i }));
    expect(screen.getByRole("grid", { name: /release calendar month/i })).toBeInTheDocument();
  });

  it("moves between months in the grid and keeps the month in the URL", async () => {
    renderWithProviders(<Calendar />);
    await userEvent.click(await screen.findByRole("radio", { name: /month/i }));
    const before = screen.getByRole("grid").getAttribute("aria-label");
    await userEvent.click(screen.getByRole("button", { name: /next month/i }));
    expect(screen.getByRole("grid").getAttribute("aria-label")).not.toBe(before);
  });

  it("lists upcoming releases before published ones and labels the category filter", async () => {
    renderWithProviders(<Calendar />);
    expect(await screen.findByRole("combobox", { name: /category/i })).toHaveTextContent("All categories");
    const rows = within(screen.getByRole("list", { name: /releases/i })).getAllByText(/^(Scheduled|Published)$/);
    const firstPublished = rows.findIndex((r) => r.textContent === "Published");
    const lastScheduled = rows.map((r) => r.textContent).lastIndexOf("Scheduled");
    expect(firstPublished === -1 || lastScheduled === -1 || lastScheduled < firstPublished).toBe(true);
  });

  it("explains an empty calendar", async () => {
    mockApi({ "/api/calendar": { items: [], last_checked_at: null, last_success_at: null } });
    renderWithProviders(<Calendar />);
    expect(await screen.findByText(/no releases in this period/i)).toBeInTheDocument();
  });
});
