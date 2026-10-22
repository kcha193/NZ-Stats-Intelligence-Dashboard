import { describe, expect, it } from "vitest";
import { direction, lastAtLeast, lastAtMost, ppLong, ppShort, quarterName, rate, signedRate, signOf } from "./text";

describe("story wording", () => {
  it("takes direction from the displayed value, so words never contradict the number", () => {
    expect(direction(4.06, 3.08, 1)).toBe("up");
    expect(direction(3.04, 2.96, 1)).toBe("flat"); // both display as 3.0%
    expect(direction(3.04, 3.11, 1)).toBe("down");
    expect(direction(-0.004, 0.004, 2)).toBe("flat");
  });

  it("signs a value by its displayed precision", () => {
    expect(signOf(0.004, 2)).toBe("neutral");
    expect(signOf(-0.009, 2)).toBe("negative");
    expect(signOf(0.824, 2)).toBe("positive");
  });

  it("keeps rates and percentage points distinct, with a true minus sign", () => {
    expect(rate(4.0582)).toBe("4.1%");
    expect(signedRate(-0.428)).toBe("−0.4%");
    expect(signedRate(2.9)).toBe("+2.9%");
    expect(ppShort(0.824)).toBe("+0.82 pp");
    expect(ppShort(-0.009)).toBe("−0.01 pp");
    expect(ppLong(1.0)).toBe("+1.0 percentage points");
    expect(ppLong(-0.04)).toBe("0.0 percentage points");
  });

  it("names quarters in running text", () => {
    expect(quarterName("2026-06")).toBe("June 2026 quarter");
  });

  it("finds the most recent earlier period at or beyond the latest value", () => {
    const pts = [
      { period: "2022-06", value: 7.3 }, { period: "2023-06", value: 6.0 }, { period: "2024-06", value: 3.3 },
      { period: "2025-06", value: 2.7 }, { period: "2026-03", value: 3.1 }, { period: "2026-06", value: 4.1 },
    ];
    expect(lastAtLeast(pts)).toEqual({ period: "2023-06", value: 6.0 });
    expect(lastAtMost([...pts.slice(0, 3), { period: "2026-06", value: 2.0 }])).toBeNull();
    expect(lastAtLeast([{ period: "2026-06", value: 1 }])).toBeNull();
  });
});
