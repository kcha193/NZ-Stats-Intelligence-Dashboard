import type { Adjustment, BankState, ReportKind } from "@/api/bank";

/** Plain-English wording for the bank views. None of it says verified, reviewed or approved. */
export const STATE_LABELS: Record<BankState, string> = {
  ok: "Up to date",
  stale: "Stale",
  missing: "Nothing received",
  blocked: "Blocked by the source",
  unsupported: "Not supported yet",
  permission_denied: "No access granted",
};

export const STATE_SENTENCES: Record<BankState, string> = {
  ok: "",
  stale: "The newest report is older than this series' usual schedule.",
  missing: "Access is in place but no report has been received yet.",
  blocked: "The source refused the last request; the last good data is kept.",
  unsupported: "This source has no report series defined yet.",
  permission_denied: "No access has been granted for this source yet, so nothing is collected or shown.",
};

export const CLAIM_LABELS = {
  clean: "No automated issue detected",
  warning: "Automated warning",
  failed: "Failed automated checks",
} as const;

export const KIND_LABELS: Record<ReportKind, string | null> = {
  outlook: null,
  weekly: "weekly note",
  commentary: "commentary",
  other: "other report",
};

export const ADJUSTMENT_LABELS: Record<Adjustment, string | null> = {
  seasonally_adjusted: "seasonally adjusted",
  unadjusted: "unadjusted",
  not_stated: null,
};

export const INDICATORS = [
  { value: "cpi_inflation", label: "CPI" },
  { value: "gdp", label: "GDP" },
  { value: "ocr", label: "OCR" },
  { value: "unemployment", label: "Unemployment" },
] as const;

export const INDICATOR_NAMES: Record<string, string> = {
  cpi_inflation: "CPI inflation",
  gdp: "GDP",
  ocr: "Official cash rate",
  unemployment: "Unemployment",
};
