// Spreadsheets skip leading whitespace, line breaks and invisible characters before reading a formula,
// so the guard looks at the first significant character rather than the first raw one.
// oxlint-disable-next-line no-control-regex -- control characters are exactly what this must match
const LEADING_NOISE = /^[\s\u0000-\u001f\u007f\u00a0\u200b-\u200f\u2028\u2029\ufeff]*/;
const runsAsFormula = (text: string): boolean => {
  if (/^[\t\r\n]/.test(text)) return true;
  return /^[=+\-@]/.test(text.replace(LEADING_NOISE, ""));
};

export function toCsv(rows: Record<string, string | number | null>[]): string {
  if (rows.length === 0) return "";
  const columns = Object.keys(rows[0]);
  const cell = (v: string | number | null): string => {
    if (v === null || v === undefined) return "";
    const s = typeof v === "string" && runsAsFormula(v) ? `'${v}` : String(v);
    return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const lines = [columns.join(",")];
  for (const row of rows) lines.push(columns.map((c) => cell(row[c])).join(","));
  return lines.join("\n") + "\n";
}
