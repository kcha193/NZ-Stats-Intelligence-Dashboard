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

  describe("delayed releases are upcoming (review #4245952785)", () => {
    const base = calendar.items[0];
    const item = (id: number, status: string, published_at: string) => ({
      ...base, id, status, published_at, title: `Release ${id}`, has_analysis: false, headline: null, page_url: null,
    });
    const serve = (items: ReturnType<typeof item>[]) =>
      mockApi({ "/api/calendar": { ...calendar, items } });
    const dayHeadings = () => screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);

    it("puts a day holding only a delayed release with the upcoming days, soonest first", async () => {
      serve([
        item(1, "published", "2026-10-02T10:45:00+13:00"),
        item(2, "delayed", "2026-10-20T10:45:00+13:00"),
        item(3, "scheduled", "2026-10-14T10:45:00+13:00"),
        item(4, "scheduled", "2026-11-12T10:45:00+13:00"),
        item(5, "published", "2026-10-01T10:45:00+13:00"),
      ]);
      renderWithProviders(<Calendar />);
      await screen.findByRole("list", { name: /releases/i });
      expect(dayHeadings()).toEqual(["14 Oct 2026", "20 Oct 2026", "12 Nov 2026", "2 Oct 2026", "1 Oct 2026"]);
    });

    it("groups by Pacific/Auckland day across the midnight and daylight-saving boundaries", async () => {
      serve([
        item(1, "published", "2026-09-26T23:30:00+12:00"),
        item(2, "delayed", "2026-09-27T00:30:00+12:00"), // 27 Sep 2026: NZDT begins at 02:00
        item(3, "delayed", "2026-09-27T23:30:00+13:00"),
        item(4, "published", "2026-09-28T00:15:00+13:00"),
      ]);
      renderWithProviders(<Calendar />);
      await screen.findByRole("list", { name: /releases/i });
      expect(dayHeadings()).toEqual(["27 Sep 2026", "28 Sep 2026", "26 Sep 2026"]);
      const day27 = screen.getByRole("heading", { level: 2, name: "27 Sep 2026" }).closest("li")!;
      expect(within(day27).getByText("Release 2")).toBeInTheDocument();
      expect(within(day27).getByText("Release 3")).toBeInTheDocument();
    });

    it("keeps delayed releases under the Scheduled status filter", async () => {
      serve([
        item(1, "published", "2026-10-02T10:45:00+13:00"),
        item(2, "delayed", "2026-10-20T10:45:00+13:00"),
        item(3, "scheduled", "2026-10-14T10:45:00+13:00"),
      ]);
      renderWithProviders(<Calendar />);
      await userEvent.click(await screen.findByRole("radio", { name: "Scheduled" }));
      const list = screen.getByRole("list", { name: /releases/i });
      expect(within(list).getByText("Release 2")).toBeInTheDocument();
      expect(within(list).getByText("Release 3")).toBeInTheDocument();
      expect(within(list).queryByText("Release 1")).not.toBeInTheDocument();
    });
  });

  it("explains an empty calendar", async () => {
    mockApi({ "/api/calendar": { items: [], last_checked_at: null, last_success_at: null } });
    renderWithProviders(<Calendar />);
    expect(await screen.findByText(/no releases in this period/i)).toBeInTheDocument();
  });
});
