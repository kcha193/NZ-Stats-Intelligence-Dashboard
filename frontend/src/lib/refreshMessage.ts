import type { RefreshStatus } from "@/api/types";

export type Tone = "busy" | "current" | "updated" | "pending" | "problem";

const PHASE = {
  checking: "Checking for updates…",
  downloading: "Downloading latest release…",
  validating: "Validating statistics…",
} as const;
export const COULD_NOT_REFRESH = "Could not refresh — showing last verified data";

const releases = (n: number) => `${n} release${n === 1 ? "" : "s"}`;

/** One line for the header. Pending releases are always said, never folded into "up to date". */
export function describeRefresh(s: RefreshStatus | undefined, failed: boolean): { tone: Tone; message: string } {
  if (failed) return { tone: "problem", message: COULD_NOT_REFRESH };
  if (!s || s.state === "never") return { tone: "busy", message: PHASE.checking };
  if (s.state === "running") return { tone: "busy", message: PHASE[s.phase ?? "checking"] };
  if (s.state !== "completed") return { tone: "problem", message: COULD_NOT_REFRESH };
  const pending = s.pending.length;
  if (s.ingested > 0) {
    const notes = [
      s.failures.length ? `${s.failures.length} could not be verified` : "",
      pending ? `${releases(pending)} still pending` : "",
    ].filter(Boolean);
    return {
      tone: s.failures.length ? "problem" : "updated",
      message: ["Updated with new data", ...notes].join(" · "),
    };
  }
  if (s.failures.length > 0) return { tone: "problem", message: COULD_NOT_REFRESH };
  if (pending) return { tone: "pending", message: `${releases(pending)} still pending` };
  return { tone: "current", message: "Data is up to date" };
}
