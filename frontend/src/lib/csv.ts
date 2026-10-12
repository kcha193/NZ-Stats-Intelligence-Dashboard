export function toCsv(rows: Record<string, string | number | null>[]): string {
  if (rows.length === 0) return "";
  const columns = Object.keys(rows[0]);
  const cell = (v: string | number | null): string => {
    if (v === null || v === undefined) return "";
    // Text that a spreadsheet would run as a formula is prefixed with ' (numbers are never prefixed).
    const s = typeof v === "string" && /^[=+\-@\t\r]/.test(v) ? `'${v}` : String(v);
    return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const lines = [columns.join(",")];
  for (const row of rows) lines.push(columns.map((c) => cell(row[c])).join(","));
  return lines.join("\n") + "\n";
}
