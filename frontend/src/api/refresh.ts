import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, getJson } from "./client";
import { isStaticMode } from "./mode";
import type { RefreshStatus } from "./types";

export const REFRESH_STATUS_KEY = ["refresh-status"] as const;
/** While a check runs, how often the header asks how it is going. */
export const POLL_MS = 1_500;
/** Coming back to a tab hidden this long asks again; the server reuses a recent result, so this is cheap. */
export const RECHECK_AFTER_MS = 5 * 60_000;
/** Views of the calendar and of what is due: a finished check may have changed them without committing data. */
const CALENDAR_VIEWS = new Set(["calendar", "releases", "overview", "health", "ops-status"]);

/**
 * Ask the local server for a check. The custom header makes a cross-origin page need a CORS preflight, which the
 * server never grants; the server also checks Origin and Host (see `nzstats.api.refresh`).
 */
export async function requestRefresh(manual: boolean): Promise<RefreshStatus> {
  const res = await fetch("/api/refresh", {
    method: "POST",
    credentials: "same-origin",
    headers: { Accept: "application/json", "Content-Type": "application/json", "X-NZStats-Client": "dashboard" },
    body: JSON.stringify({ manual }),
  });
  if (!res.ok) throw new ApiError(res.status, res.statusText || `HTTP ${res.status}`);
  return (await res.json()) as RefreshStatus;
}

// One automatic check per page load, however often the header mounts: React StrictMode runs effects twice in
// development, and a remount must not start a second request. A reload is a new page load, and the server's
// single-flight and recent-check window decide whether that means a new check.
let opening: Promise<RefreshStatus> | null = null;
let openedAt = 0;

function openOnce(force = false): Promise<RefreshStatus> {
  if (!opening || force) {
    opening = requestRefresh(false);
    openedAt = Date.now();
    opening.catch(() => {
      /* reported by the caller; a later visit or "Check now" can try again */
    });
  }
  return opening;
}

/** Tests only: forget this page load's automatic check. */
export function resetRefreshForTests(): void {
  opening = null;
  openedAt = 0;
}

export type RefreshView = {
  status: RefreshStatus | undefined;
  failed: boolean; // the local server could not be asked at all
  checkNow: () => void;
  requesting: boolean;
};

/**
 * The on-open refresh: ask once when the dashboard opens, follow the check while it runs, and refresh every other
 * query when new verified data has been committed. Never blocks rendering: pages show stored data throughout.
 */
export function useRefresh(): RefreshView {
  const client = useQueryClient();
  const live = !isStaticMode();
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const [requesting, setRequesting] = useState(false);
  const seenVersion = useRef<string | null | undefined>(undefined);
  const watching = useRef(false);

  const accept = useCallback(
    (s: RefreshStatus) => {
      client.setQueryData(REFRESH_STATUS_KEY, s);
      setFailed(false);
      setReady(true);
    },
    [client],
  );

  useEffect(() => {
    if (!live) return;
    let active = true;
    openOnce()
      .then((s) => active && accept(s))
      .catch(() => active && setFailed(true));
    const onVisible = () => {
      if (document.visibilityState !== "visible" || Date.now() - openedAt < RECHECK_AFTER_MS) return;
      openOnce(true).then(accept, () => setFailed(true));
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      active = false;
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [live, accept]);

  const query = useQuery({
    queryKey: REFRESH_STATUS_KEY,
    queryFn: ({ signal }) => getJson<RefreshStatus>("/api/refresh/status", signal),
    enabled: live && ready,
    staleTime: Infinity,
    refetchInterval: (q) => (q.state.data?.state === "running" ? POLL_MS : false),
  });
  const status = query.data;

  // New verified data (from this check, another tab's or the CLI's): every other query refetches in the background.
  // A check this page watched has finished: the calendar it read may list new or rescheduled releases.
  useEffect(() => {
    if (!status) return;
    const finished = watching.current && status.state !== "running";
    watching.current = status.state === "running";
    const version = status.data_version ?? null;
    if (seenVersion.current === undefined) {
      seenVersion.current = version;
      return;
    }
    if (version !== seenVersion.current) {
      seenVersion.current = version;
      void client.invalidateQueries({ predicate: (q) => q.queryKey[0] !== REFRESH_STATUS_KEY[0] });
    } else if (finished) {
      void client.invalidateQueries({ predicate: (q) => CALENDAR_VIEWS.has(String(q.queryKey[0])) });
    }
  }, [status, client]);

  const checkNow = useCallback(() => {
    setRequesting(true);
    requestRefresh(true)
      .then(accept, () => setFailed(true))
      .finally(() => setRequesting(false));
  }, [accept]);

  return { status, failed, checkNow, requesting };
}
