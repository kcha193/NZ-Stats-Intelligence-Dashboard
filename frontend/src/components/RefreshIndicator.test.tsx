import { StrictMode } from "react";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { resetRefreshForTests } from "@/api/refresh";
import type { RefreshStatus } from "@/api/types";
import { COULD_NOT_REFRESH, describeRefresh } from "@/lib/refreshMessage";
import { RefreshIndicator } from "./RefreshIndicator";

const base: RefreshStatus = {
  mode: "on_open", state: "completed", phase: null, run_id: 1, trigger: "open",
  started_at: "2026-10-30T09:00:00+13:00", finished_at: "2026-10-30T09:01:00+13:00",
  last_success_at: "2026-10-30T09:01:00+13:00", discovered: 0, ingested: 0, unchanged: 0, requests: 4,
  failures: [], pending: [], error_class: null, data_version: "a10", started: false,
  latest: [{ series_slug: "consumers-price-index", label: "Consumers price index", reference_period: "2026-09",
    period_label: "September 2026 quarter", published_at: "2026-10-16T10:45:00+13:00" }],
};
const s = (over: Partial<RefreshStatus>): RefreshStatus => ({ ...base, ...over });

type Reply = RefreshStatus | (() => RefreshStatus) | Response;

/** A local server: POST /api/refresh and GET /api/refresh/status answer from the given queues (last one repeats). */
function server(posts: Reply[], gets: Reply[] = []) {
  const calls: { method: string; url: string; body?: unknown; headers?: HeadersInit }[] = [];
  const next = (q: Reply[]) => (q.length > 1 ? q.shift()! : q[0]);
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    calls.push({ method, url, body: init?.body ? JSON.parse(String(init.body)) : undefined, headers: init?.headers });
    const reply = url.includes("/status") ? next(gets.length ? gets : posts) : next(posts);
    if (reply instanceof Response) return reply;
    const body = typeof reply === "function" ? reply() : reply;
    return new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
  });
  vi.stubGlobal("fetch", fn);
  return calls;
}

function Data({ onFetch, onCalendar }: { onFetch: () => void; onCalendar: () => void }) {
  useQuery({ queryKey: ["cpi"], queryFn: async () => (onFetch(), 1) });
  useQuery({ queryKey: ["calendar", {}], queryFn: async () => (onCalendar(), 1) });
  return <p>stored data</p>;
}

function renderHeader({ strict = false, onFetch = () => {}, onCalendar = () => {} } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const tree = (
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <RefreshIndicator />
        <Data onFetch={onFetch} onCalendar={onCalendar} />
      </MemoryRouter>
    </QueryClientProvider>
  );
  return render(strict ? <StrictMode>{tree}</StrictMode> : tree);
}

beforeEach(() => resetRefreshForTests());

describe("describeRefresh", () => {
  it.each([
    [s({ state: "running", phase: "checking" }), "Checking for updates…"],
    [s({ state: "running", phase: "downloading" }), "Downloading latest release…"],
    [s({ state: "running", phase: "validating" }), "Validating statistics…"],
    [s({}), "Data is up to date"],
    [s({ ingested: 2 }), "Updated with new data"],
    [s({ state: "failed", error_class: "network" }), COULD_NOT_REFRESH],
    [s({ state: "interrupted" }), COULD_NOT_REFRESH],
    [s({ failures: [{ key: "x", outcome: "failed", error_class: "validation_failed" }] }), COULD_NOT_REFRESH],
    [s({ ingested: 1, failures: [{ key: "x", outcome: "failed", error_class: "validation_failed" }] }),
      "Updated with new data · 1 could not be verified"],
  ])("says what the check is doing", (status, message) => {
    expect(describeRefresh(status, false).message).toBe(message);
  });

  it("never calls data with pending releases up to date", () => {
    const pending = [{ release_key: "a:b", reason: "catch_up_limit" as const, series_slug: null, label: null, reference_period: null, period_label: null, published_at: null }];
    expect(describeRefresh(s({ pending }), false).message).toBe("1 release still pending");
    expect(describeRefresh(s({ ingested: 1, pending: [...pending, pending[0]] }), false).message).toBe(
      "Updated with new data · 2 releases still pending",
    );
  });

  it("reports an unreachable server as a failed refresh", () => {
    expect(describeRefresh(undefined, true).message).toBe(COULD_NOT_REFRESH);
  });
});

describe("RefreshIndicator", () => {
  it("asks once per page load, even under StrictMode, from this dashboard only", async () => {
    const calls = server([s({ started: true, state: "running", phase: "checking" })], [s({})]);
    renderHeader({ strict: true });
    expect(await screen.findByRole("button", { name: /data refresh/i })).toBeInTheDocument();
    const posts = calls.filter((c) => c.method === "POST");
    expect(posts).toHaveLength(1);
    expect(posts[0].body).toEqual({ manual: false });
    expect(posts[0].headers).toMatchObject({ "X-NZStats-Client": "dashboard" });
  });

  it("shows stored data straight away and keeps it while the check runs", async () => {
    server([s({ state: "running", phase: "downloading" })]);
    renderHeader();
    expect(screen.getByText("stored data")).toBeInTheDocument();
    expect(await screen.findByRole("status")).toHaveTextContent("Downloading latest release…");
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("follows the check and refetches the dashboards when new data is committed", async () => {
    const onFetch = vi.fn();
    server(
      [s({ started: true, state: "running", phase: "checking", data_version: "a10" })],
      [s({ state: "running", phase: "validating", data_version: "a10" }), s({ ingested: 1, data_version: "a11" })],
    );
    renderHeader({ onFetch });
    await waitFor(() => expect(onFetch).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Validating statistics…"), { timeout: 5000 });
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Updated with new data"), { timeout: 5000 });
    await waitFor(() => expect(onFetch).toHaveBeenCalledTimes(2));
  });

  it("refetches only the calendar views when the check found no new data", async () => {
    const onFetch = vi.fn();
    const onCalendar = vi.fn();
    server([s({ started: true, state: "running", phase: "checking" })], [s({})]);
    renderHeader({ onFetch, onCalendar });
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Data is up to date"), { timeout: 5000 });
    await waitFor(() => expect(onCalendar).toHaveBeenCalledTimes(2));
    expect(onFetch).toHaveBeenCalledTimes(1);
  });

  it("renders nothing in offline mode", async () => {
    const calls = server([s({ mode: "off", state: "never", latest: [] })]);
    renderHeader();
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(screen.queryByRole("button", { name: /data refresh/i })).not.toBeInTheDocument();
  });

  it("says when refresh status is unavailable and keeps stored data visible", async () => {
    server([new Response("{}", { status: 500 })]);
    renderHeader();
    expect(await screen.findByRole("status")).toHaveTextContent("Refresh status unavailable — showing stored data");
  });

  it("separates the last successful check from the reference period of the statistics", async () => {
    const user = userEvent.setup();
    server([s({ pending: [{ release_key: "gross-domestic-product:june 2026 quarter", reason: "not_published_yet",
      series_slug: "gross-domestic-product", label: "Gross domestic product", reference_period: "2026-06", period_label: "June 2026 quarter", published_at: null }] })]);
    renderHeader();
    await user.click(await screen.findByRole("button", { name: /data refresh/i }));
    expect(screen.getByText("Last successful check").nextSibling).toHaveTextContent("30 Oct 2026, 09:01");
    const latest = screen.getByRole("list", { name: "Latest statistics held" });
    expect(within(latest).getByText(/September 2026 quarter/)).toBeInTheDocument();
    const pending = screen.getByRole("list", { name: "Releases still pending" });
    expect(pending).toHaveTextContent("Gross domestic product June 2026 quarter: files not out yet");
  });

  it("checks again on request, and not while a check is running", async () => {
    const user = userEvent.setup();
    const calls = server([s({}), s({ started: true, state: "running", phase: "checking" })], [s({}), s({ state: "running", phase: "checking" })]);
    renderHeader();
    await user.click(await screen.findByRole("button", { name: /data refresh/i }));
    await user.click(screen.getByRole("button", { name: "Check now" }));
    await waitFor(() => expect(calls.filter((c) => c.method === "POST")).toHaveLength(2));
    expect(calls.filter((c) => c.method === "POST")[1].body).toEqual({ manual: true });
    await waitFor(() => expect(screen.getByRole("button", { name: "Check now" })).toBeDisabled());
  });

  it("asks again when the tab returns after a long absence, and not after a short one", async () => {
    const calls = server([s({})]);
    renderHeader();
    await screen.findByRole("button", { name: /data refresh/i });
    const visible = () => act(() => void document.dispatchEvent(new Event("visibilitychange")));
    visible();
    expect(calls.filter((c) => c.method === "POST")).toHaveLength(1);
    const now = Date.now();
    vi.spyOn(Date, "now").mockReturnValue(now + 6 * 60_000);
    visible();
    await waitFor(() => expect(calls.filter((c) => c.method === "POST")).toHaveLength(2));
    vi.restoreAllMocks();
  });
});

describe("collection mode before automatic refresh", () => {
  it.each(["scheduler", "off"] as const)("only reads status in %s mode", async (mode) => {
    const calls = server([new Response("{}", { status: 403 })], [s({ mode })]);
    renderHeader({ strict: true });
    await waitFor(() => expect(calls.length).toBeGreaterThan(0));
    await act(async () => {});
    expect(calls.map((c) => [c.method, c.url])).toEqual([["GET", "/api/refresh/status"]]);
    expect(screen.queryByRole("button", { name: /data refresh/i })).not.toBeInTheDocument();
  });

  it("gets status before one StrictMode POST and keeps the security header", async () => {
    const calls = server([s({})], [s({})]);
    renderHeader({ strict: true });
    await waitFor(() => expect(calls.filter((c) => c.method === "POST")).toHaveLength(1));
    expect(calls[0]).toMatchObject({ method: "GET", url: "/api/refresh/status" });
    const post = calls.find((c) => c.method === "POST")!;
    expect(new Headers(post.headers).get("X-NZStats-Client")).toBe("dashboard");
  });

  it("reports status failure separately and retries status before posting", async () => {
    const calls = server([s({})], [new Response("{}", { status: 503 }), s({})]);
    renderHeader();
    expect(await screen.findByRole("status")).toHaveTextContent("Refresh status unavailable");
    expect(calls.every((c) => c.method === "GET")).toBe(true);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /data refresh/i }));
    await user.click(screen.getByRole("button", { name: "Retry status" }));
    await waitFor(() => expect(calls.filter((c) => c.method === "POST")).toHaveLength(1));
    expect(calls[1]).toMatchObject({ method: "GET", url: "/api/refresh/status" });
  });

  it("reports an actual POST failure after on-open mode was confirmed", async () => {
    const calls = server([new Response("{}", { status: 500 })], [s({})]);
    renderHeader();
    expect(await screen.findByRole("status")).toHaveTextContent(COULD_NOT_REFRESH);
    expect(calls[0].method).toBe("GET");
    expect(calls[1].method).toBe("POST");
  });
});

it.each(["scheduler", "off", "on_open"] as const)("never posts from a LAN host in %s mode", async (mode) => {
  vi.stubGlobal("location", new URL("http://192.168.1.42:8000/"));
  try {
    const calls = server([new Response("{}", { status: 403 })], [s({ mode })]);
    renderHeader();
    await waitFor(() => expect(calls).toHaveLength(1));
    await act(async () => {});
    expect(calls[0]).toMatchObject({ method: "GET", url: "/api/refresh/status" });
    expect(screen.queryByRole("button", { name: /data refresh/i })).not.toBeInTheDocument();
  } finally {
    vi.unstubAllGlobals();
  }
});

it("refetches stored dashboards when ingestion finishes before the POST responds", async () => {
  const onFetch = vi.fn();
  server([s({ ingested: 1, data_version: "a11" })], [s({ data_version: "a10" })]);
  renderHeader({ onFetch });
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Updated with new data"));
  await waitFor(() => expect(onFetch).toHaveBeenCalledTimes(2));
});

it("clears a failed visibility status check when a later poll succeeds", async () => {
  server([s({})], [s({ state: "running", phase: "checking" }), new Response("{}", { status: 503 }), s({ ingested: 1, data_version: "a11" })]);
  renderHeader();
  expect(await screen.findByRole("status")).toHaveTextContent("Checking for updates");
  const now = Date.now();
  vi.spyOn(Date, "now").mockReturnValue(now + 6 * 60_000);
  act(() => void document.dispatchEvent(new Event("visibilitychange")));
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Refresh status unavailable"));
  vi.restoreAllMocks();
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Updated with new data"), { timeout: 5000 });
});
