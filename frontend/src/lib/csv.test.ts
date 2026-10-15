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

  it("also neutralises formulas hidden behind leading whitespace, line breaks or invisible characters", () => {
    const hostile = [" =1+1", "\n=1+1", "\r\n@SUM(A1)", "\u00a0+1", "\u200b=1+1", "\ufeff-2+3", "\t=1"];
    for (const v of hostile) {
      const out = toCsv([{ a: v }]).split("\n").slice(1).join("\n");
      // the first significant character of the stored cell must be the neutralising apostrophe
      const cell = out.replace(/^"/, "").replace(/\n$/, "");
      expect(cell.startsWith("'"), JSON.stringify(v)).toBe(true);
    }
    expect(toCsv([{ a: "Total = 5" }])).toBe("a\nTotal = 5\n");
  });
});
