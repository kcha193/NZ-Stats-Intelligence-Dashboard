const AKL = "Pacific/Auckland";
const MINUS = "\u2212";
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function formatNumber(
  value: number,
  { signed = false, decimals = 0 }: { signed?: boolean; decimals?: number } = {},
): string {
  const abs = Math.abs(value).toLocaleString("en-NZ", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  if (value < 0 && Number(abs.replace(/,/g, "")) !== 0) return `${MINUS}${abs}`;
  return signed && value > 0 ? `+${abs}` : abs;
}

export function formatPercent(p: number | null | undefined, decimals = 1): string {
  if (p === null || p === undefined) return "n/a";
  return `${formatNumber(p, { signed: true, decimals })}%`;
}

export function formatNet(v: number): string {
  const n = Math.round(v);
  if (n === 0) return "no net change";
  return `net ${n > 0 ? "gain" : "loss"} of ${formatNumber(Math.abs(n))}`;
}

export function monthLabel(period: string): string {
  const [y, m] = period.split("-").map(Number);
  return `${MONTHS[m - 1]} ${y}`;
}

export function periodLabel(period: string, frequency: string): string {
  return frequency === "rolling_annual" ? `Year ended ${monthLabel(period)}` : monthLabel(period);
}

const clock = new Intl.DateTimeFormat("en-NZ", {
  timeZone: AKL, year: "numeric", month: "numeric", day: "numeric",
  hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZoneName: "short",
});

function auckland(iso: string): Record<string, string> {
  return Object.fromEntries(clock.formatToParts(new Date(iso)).map((p) => [p.type, p.value]));
}

const monthClock = new Intl.DateTimeFormat("en-NZ", { timeZone: AKL, year: "numeric", month: "2-digit" });

/** The Pacific/Auckland calendar month of an instant, as YYYY-MM. */
export function aklMonth(at: Date): string {
  const p = Object.fromEntries(monthClock.formatToParts(at).map((x) => [x.type, x.value]));
  return `${p.year}-${p.month}`;
}

export function formatAklDate(iso: string): string {
  const p = auckland(iso);
  return `${Number(p.day)} ${MONTHS[Number(p.month) - 1]} ${p.year}`;
}

export function formatAklDateTime(iso: string): string {
  const p = auckland(iso);
  return `${formatAklDate(iso)}, ${p.hour}:${p.minute} ${p.timeZoneName}`;
}

/** Escape text for the HTML strings ECharts tooltips render. */
export function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
