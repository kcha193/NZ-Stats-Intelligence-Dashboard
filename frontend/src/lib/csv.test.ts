import { describe, expect, it } from "vitest";
import { toCsv } from "./csv";

describe("toCsv", () => {
  it("writes a header and rows", () => {
    expect(toCsv([{ period: "2026-07", value: 5170 }, { period: "2026-06", value: null }])).toBe(
      "period,value\n2026-07,5170\n2026-06,\n",
    );
  });
  it("quotes commas, quotes and newlines", () => {
    expect(toCsv([{ a: 'x,"y"', b: "l1\nl2" }])).toBe('a,b\n"x,""y""","l1\nl2"\n');
  });
  it("returns an empty string for no rows", () => {
    expect(toCsv([])).toBe("");
  });

  it("neutralises spreadsheet formulas in text cells but leaves numbers alone", () => {
    const csv = toCsv([{ name: "=HYPERLINK(\"http://x\")", b: "+1", c: "@SUM(A1)", d: "-cmd", n: -38335, ok: "2026-07" }]);
    const row = csv.split("\n")[1];
    expect(row).toContain("'=HYPERLINK");
    expect(row).toContain("'+1");
    expect(row).toContain("'@SUM(A1)");
    expect(row).toContain("'-cmd");
    expect(row).toContain(",-38335,");
    expect(row.endsWith(",2026-07")).toBe(true);
  });
});
