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
});
