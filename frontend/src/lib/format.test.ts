import { describe, expect, it } from "vitest";
import {
  aklMonth, formatAklDate, formatAklDateTime, formatNet, formatNumber, formatPercent, periodLabel,
} from "./format";

describe("formatNumber", () => {
  it("groups thousands and uses a typographic minus", () => {
    expect(formatNumber(20350)).toBe("20,350");
    expect(formatNumber(-38335)).toBe("−38,335");
    expect(formatNumber(0)).toBe("0");
  });
  it("supports signed output and decimals", () => {
    expect(formatNumber(12, { signed: true })).toBe("+12");
    expect(formatNumber(-12, { signed: true })).toBe("−12");
    expect(formatNumber(0, { signed: true })).toBe("0");
    expect(formatNumber(1.234, { decimals: 1 })).toBe("1.2");
  });
});

describe("formatPercent", () => {
  it("shows n/a when the change is not meaningful", () => {
    expect(formatPercent(null)).toBe("n/a");
    expect(formatPercent(undefined)).toBe("n/a");
  });
  it("is signed with one decimal", () => {
    expect(formatPercent(112.04)).toBe("+112.0%");
    expect(formatPercent(-3.26)).toBe("−3.3%");
  });
});

describe("formatNet", () => {
  it("words gains and losses", () => {
    expect(formatNet(20350)).toBe("net gain of 20,350");
    expect(formatNet(-38335)).toBe("net loss of 38,335");
    expect(formatNet(0)).toBe("no net change");
  });
});

describe("periodLabel", () => {
  it("labels monthly and year-ended periods differently", () => {
    expect(periodLabel("2026-07", "monthly")).toBe("Jul 2026");
    expect(periodLabel("2026-07", "rolling_annual")).toBe("Year ended Jul 2026");
  });
});

describe("Auckland date formatting", () => {
  it("renders the wall-clock time in Pacific/Auckland regardless of the viewer's timezone", () => {
    expect(formatAklDateTime("2026-10-14T10:45:00+13:00")).toMatch(/14 Oct 2026.*10:45/);
    expect(formatAklDateTime("2026-10-13T21:45:00Z")).toMatch(/14 Oct 2026.*10:45/);
    expect(formatAklDate("2026-09-14T10:45:00+12:00")).toBe("14 Sep 2026");
  });
});

describe("aklMonth", () => {
  it("names the Pacific/Auckland calendar month, not the UTC one", () => {
    expect(aklMonth(new Date("2026-10-31T12:00:00Z"))).toBe("2026-11"); // 1 Nov 01:00 NZDT
    expect(aklMonth(new Date("2026-10-31T10:59:59Z"))).toBe("2026-10"); // 31 Oct 23:59 NZDT
    expect(aklMonth(new Date("2026-12-31T11:30:00Z"))).toBe("2027-01"); // year boundary
  });
});
