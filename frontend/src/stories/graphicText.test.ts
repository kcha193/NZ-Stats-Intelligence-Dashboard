import { describe, expect, it } from "vitest";
import { describeThumb, fmtValue, largestItems, peakBefore, periodName } from "./graphicText";

describe("graphic labels", () => {
  it("keeps percent and percentage points apart, and signs only what is a change", () => {
    expect(fmtValue(4.058, "pct")).toBe("4.1%");
    expect(fmtValue(-0.4, "pct", true)).toBe("−0.4%");
    expect(fmtValue(2.94, "pct", true)).toBe("+2.9%");
    expect(fmtValue(0.823, "pp")).toBe("+0.82 pp");
    expect(fmtValue(-0.004, "pp")).toBe("0.00 pp");
    expect(fmtValue(20350, "people", true)).toBe("+20,350");
    expect(fmtValue(134434, "people")).toBe("134,434");
  });

  it("names year-ended periods as such, never as a single month", () => {
    expect(periodName("2026-07", "year-ended")).toBe("YE Jul 2026");
    expect(periodName("2026-06", "quarter")).toBe("Jun 2026");
  });

  it("labels a peak only when an earlier point is higher than the latest", () => {
    expect(peakBefore([{ period: "a", value: 1 }, { period: "b", value: 7 }, { period: "c", value: 4 }])?.period).toBe("b");
    expect(peakBefore([{ period: "a", value: 1 }, { period: "b", value: 3 }, { period: "c", value: 4 }])).toBeNull();
  });

  it("describes each graphic with the values it labels", () => {
    expect(describeThumb({
      kind: "line", name: "Year-ended net migration", zero: true, format: "people", period: "year-ended",
      points: [{ period: "2023-10", value: 133738 }, { period: "2024-07", value: 50000 }, { period: "2026-07", value: 20350, provisional: true }],
    })).toBe("Year-ended net migration, YE Oct 2023 to YE Jul 2026. Latest +20,350 (YE Jul 2026, provisional). Peak +133,738 (YE Oct 2023).");
    expect(describeThumb({
      kind: "pair", name: "Annual inflation, tradables and non-tradables", format: "pct",
      items: [{ label: "Tradables", value: 4.9 }, { label: "Non-tradables", value: 3.4 }], gap: { label: "Gap", value: "+1.5 pp" },
    })).toBe("Annual inflation, tradables and non-tradables: Tradables 4.9%; Non-tradables 3.4%. Gap: +1.5 pp.");
    expect(describeThumb({ kind: "bars", name: "Contributions", format: "pp", items: [{ label: "Transport", value: 0.82 }, { label: "Food", value: -0.1 }] }))
      .toBe("Contributions: Transport +0.82 pp, Food −0.10 pp.");
    expect(describeThumb({
      kind: "columns", name: "Retail, monthly change", format: "pct", period: "month",
      points: [{ period: "2026-08", value: -0.9 }, { period: "2026-09", value: -0.4 }],
    })).toBe("Retail, monthly change, last 2 periods: 0 rises and 2 falls. Latest −0.4% (Sep 2026).");
  });

  it("keeps the largest movements in ranked order when a compact graphic cannot show every item", () => {
    const items = [5, 3, 0.1, 0.05, -0.2, -4].map((value, i) => ({ label: `g${i}`, value }));
    expect(largestItems(items, 4).map((i) => i.value)).toEqual([5, 3, -0.2, -4]);
  });
});
