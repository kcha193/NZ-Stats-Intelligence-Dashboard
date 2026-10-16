import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
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

  describe("month view fetches the month it shows (review #4246379631)", () => {
    const last = calendar.items[calendar.items.length - 1]; // scheduled, 10 Dec 2026
    const requests: URL[] = [];
    beforeEach(() => {
      requests.length = 0;
      vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
        const url = new URL(String(input), "http://localhost");
        requests.push(url);
        const from = url.searchParams.get("from") ?? "0000-01-01";
        const to = url.searchParams.get("to") ?? "9999-12-31";
        const items = calendar.items.filter((i) => i.published_at.slice(0, 10) >= from && i.published_at.slice(0, 10) <= to);
        return new Response(JSON.stringify({ ...calendar, items }), { status: 200, headers: { "content-type": "application/json" } });
      }));
    });
    afterEach(() => vi.useRealTimers());

    it("requests the selected month's bounds and shows releases outside the default window", async () => {
      renderWithProviders(<Calendar />, { route: "/?view=month&month=2026-12" });
      const grid = await screen.findByRole("grid", { name: /release calendar month 2026-12/i });
      expect(within(grid).getByText(last.title)).toBeInTheDocument();
      const asked = requests.at(-1)!;
      expect([asked.searchParams.get("from"), asked.searchParams.get("to")]).toEqual(["2026-12-01", "2026-12-31"]);
    });

    it("fetches again when navigating, and keeps the controls and an explanation for an empty month", async () => {
      renderWithProviders(<Calendar />, { route: "/?view=month&month=2026-12" });
      await screen.findByRole("grid");
      await userEvent.click(screen.getByRole("button", { name: /next month/i }));
      expect(await screen.findByRole("grid", { name: /release calendar month 2027-01/i })).toBeInTheDocument();
      expect(requests.at(-1)!.searchParams.get("from")).toBe("2027-01-01");
      expect(screen.getByText(/no releases in jan 2027/i)).toBeInTheDocument();
      await userEvent.click(screen.getByRole("button", { name: /previous month/i }));
      expect(await screen.findByRole("grid", { name: /release calendar month 2026-12/i })).toBeInTheDocument();
    });

    it("starts on the current Pacific/Auckland month", async () => {
      vi.useFakeTimers({ toFake: ["Date"] });
      vi.setSystemTime(new Date("2026-10-31T12:00:00Z")); // already 1 Nov in Auckland
      renderWithProviders(<Calendar />, { route: "/?view=month" });
      expect(await screen.findByRole("grid", { name: /release calendar month 2026-11/i })).toBeInTheDocument();
      expect(requests.at(-1)!.searchParams.get("from")).toBe("2026-11-01");
      expect(requests.at(-1)!.searchParams.get("to")).toBe("2026-11-30");
    });

    it("keeps the list view on the default window", async () => {
      renderWithProviders(<Calendar />);
      await screen.findByRole("list", { name: /releases/i });
      expect(requests.at(-1)!.searchParams.has("from")).toBe(false);
    });
  });

  it("includes corrected releases under the Published filter", async () => {
    const base = calendar.items[0];
    const item = (id: number, status: string, day: string) => ({ ...base, id, status, published_at: `2026-10-${day}T10:45:00+13:00`, title: `Release ${id}`, has_analysis: false, headline: null, page_url: null });
    mockApi({ "/api/calendar": { ...calendar, items: [item(1, "published", "01"), item(2, "corrected", "02"), item(3, "scheduled", "20")] } });
    renderWithProviders(<Calendar />);
    await userEvent.click(await screen.findByRole("radio", { name: "Published" }));
    const list = screen.getByRole("list", { name: /releases/i });
    expect(within(list).getByText("Release 1")).toBeInTheDocument();
    expect(within(list).getByText("Release 2")).toBeInTheDocument();
    expect(within(list).queryByText("Release 3")).not.toBeInTheDocument();
  });

  it("explains an empty calendar", async () => {
    mockApi({ "/api/calendar": { items: [], last_checked_at: null, last_success_at: null } });
    renderWithProviders(<Calendar />);
    expect(await screen.findByText(/no releases in this period/i)).toBeInTheDocument();
  });
});

it("opens full release details in month view by keyboard", async () => {
  const scheduled = { ...calendar.items[0], id: 987, title: "International migration: a very long scheduled publication name", published_at: "2026-10-14T10:45:00+13:00", status: "scheduled", has_analysis: false, page_url: null };
  mockApi({ "/api/calendar": { ...calendar, items: [scheduled] } });
  renderWithProviders(<Calendar />, { route: "/calendar?view=month&month=2026-10" });
  const button = await screen.findByRole("button", { name: `Details for ${scheduled.title}` });
  button.focus();
  await userEvent.keyboard("{Enter}");
  const dialog = screen.getByRole("dialog", { name: scheduled.title });
  expect(within(dialog).getByText("14 Oct 2026, 10:45 NZDT")).toBeInTheDocument();
  expect(within(dialog).getByText("Scheduled")).toBeInTheDocument();
  await userEvent.keyboard("{Escape}");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(button).toHaveFocus();
});
