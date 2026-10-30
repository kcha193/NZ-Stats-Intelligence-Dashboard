import { useEffect, useId, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, Clock, RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";
import { useRefresh } from "@/api/refresh";
import type { RefreshStatus } from "@/api/types";
import { formatAklDateTime } from "@/lib/format";
import { describeRefresh, type Tone } from "@/lib/refreshMessage";

const REASON: Record<RefreshStatus["pending"][number]["reason"], string> = {
  not_published_yet: "files not out yet; checked again next time",
  rejected_today: "rejected today; retried tomorrow",
  blocked_cooldown: "Stats NZ asked us to wait; retried later",
  catch_up_limit: "next in the queue; fetched on the next check",
  request_budget: "next in the queue; fetched on the next check",
  stopped: "not reached this time; fetched on the next check",
};

function Icon({ tone }: { tone: Tone }) {
  const cls = "size-4 shrink-0";
  if (tone === "busy") return <RefreshCw aria-hidden className={`${cls} text-accent-ink motion-safe:animate-spin`} />;
  if (tone === "problem") return <AlertTriangle aria-hidden className={`${cls} text-amber-600 dark:text-amber-400`} />;
  if (tone === "pending") return <Clock aria-hidden className={`${cls} text-muted-foreground`} />;
  return <CheckCircle2 aria-hidden className={`${cls} ${tone === "updated" ? "text-accent-ink" : "text-muted-foreground"}`} />;
}

const at = (iso: string | null | undefined) => (iso ? formatAklDateTime(iso) : "not yet");

/**
 * The on-open refresh in the header: what the check is doing, and on request its details and "Check now". Renders
 * nothing unless the server runs the on-open refresh, so offline mode and the static site look exactly as before.
 */
export function RefreshIndicator() {
  const { status, failed, checkNow, requesting } = useRefresh();
  const [open, setOpen] = useState(false);
  const id = useId();
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        button.current?.focus();
      }
    };
    const onPointer = (e: PointerEvent) => {
      if (root.current && !root.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointer);
    };
  }, [open]);

  if (!failed && status?.mode !== "on_open") return null;
  const { tone, message } = describeRefresh(status, failed);
  const busy = tone === "busy" || requesting;

  return (
    <div ref={root} className="sm:relative" data-refresh-indicator>
      <p role="status" className="sr-only">{message}</p>
      <button
        ref={button}
        type="button"
        aria-expanded={open}
        aria-controls={id}
        aria-label={`Data refresh: ${message}`}
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1.5 rounded-sm px-2 py-2 text-xs text-muted-foreground hover:text-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-ink"
      >
        <Icon tone={tone} />
        <span className="hidden whitespace-nowrap lg:inline">{message.split(" · ")[0]}</span>
      </button>
      <div
        id={id}
        hidden={!open}
        className="absolute inset-x-0 top-full z-40 border-b bg-background p-4 text-sm shadow-[0_12px_32px_-16px_rgb(15_23_42/0.25)] sm:inset-x-auto sm:right-0 sm:mt-3 sm:w-[24rem] sm:rounded-md sm:border"
      >
        <p className="font-medium">{message}</p>
        <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
          <dt className="text-muted-foreground">Last successful check</dt>
          <dd>{at(status?.last_success_at)}</dd>
          {status?.finished_at && status.finished_at !== status.last_success_at && (
            <>
              <dt className="text-muted-foreground">Last attempt</dt>
              <dd>{at(status.finished_at)}</dd>
            </>
          )}
        </dl>
        {status && status.latest.length > 0 && (
          <div className="mt-3">
            <p className="text-xs text-muted-foreground">Latest statistics held (reference period, published)</p>
            <ul className="mt-1 space-y-0.5 text-xs" aria-label="Latest statistics held">
              {status.latest.map((l) => (
                <li key={l.series_slug}>
                  <span className="font-medium">{l.label}</span>: {l.period_label ?? l.reference_period ?? "—"}
                  <span className="text-muted-foreground"> · published {formatAklDateTime(l.published_at)}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {status && status.pending.length > 0 && (
          <div className="mt-3">
            <p className="text-xs text-muted-foreground">Still pending</p>
            <ul className="mt-1 space-y-0.5 text-xs" aria-label="Releases still pending">
              {status.pending.map((p) => (
                <li key={p.release_key}>
                  <span className="font-medium">{p.label ?? p.release_key}</span>
                  {p.period_label ? ` ${p.period_label}` : ""}: {REASON[p.reason]}
                </li>
              ))}
            </ul>
          </div>
        )}
        {status && status.failures.length > 0 && (
          <p className="mt-3 text-xs">
            {status.failures.length} item{status.failures.length === 1 ? "" : "s"} could not be verified, so the last
            verified data is shown. <Link className="underline underline-offset-4" to="/health">Data health</Link> has
            the detail.
          </p>
        )}
        <div className="mt-4 flex items-center justify-between gap-3">
          <button
            type="button"
            onClick={checkNow}
            disabled={busy}
            className="shrink-0 whitespace-nowrap rounded-sm border px-3 py-1.5 text-xs font-medium hover:bg-muted disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-ink"
          >
            Check now
          </button>
          <span className="text-xs text-muted-foreground">Checks run on the server; you can keep reading.</span>
        </div>
      </div>
    </div>
  );
}
