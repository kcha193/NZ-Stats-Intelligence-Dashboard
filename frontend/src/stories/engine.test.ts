import { describe, expect, it } from "vitest";
import type { CpiDashboard } from "@/api/types";
import cpiFixture from "@/test/fixtures/cpi.json";
import { buildCpiStories } from "./cpi";
import { categoryOfId, orderStories, resolveStory, splitTemplate } from "./engine";
import type { Story } from "./types";

const cpi = buildCpiStories(cpiFixture as unknown as CpiDashboard);
const at = (s: Story, publishedAt: string, priority = s.priority): Story =>
  ({ ...s, priority, provenance: { ...s.provenance, publishedAt } });

describe("story engine", () => {
  it("orders by publication instant (newest first), then editorial priority, and drops duplicate ids", () => {
    const older = at(cpi[0], "2026-07-21T10:45:00+12:00");
    const newer = { ...at(cpi[1], "2026-10-16T10:45:00+13:00"), id: "spending-retail-2026-09" };
    const sameTime = at(cpi[2], "2026-07-21T10:45:00+12:00");
    expect(orderStories([sameTime, older, newer, older]).map((s) => s.id)).toEqual([
      "spending-retail-2026-09", "inflation-annual-2026-06", "inflation-tradables-2026-06",
    ]);
  });

  it("splits an identifier into template and reference period", () => {
    expect(splitTemplate("inflation-annual-2026-06")).toEqual({ template: "inflation-annual", period: "2026-06" });
    expect(splitTemplate("nonsense")).toBeNull();
  });

  it("resolves a current id, a superseded id and an unknown id", () => {
    expect(resolveStory(cpi, "inflation-drivers-2026-06")).toEqual({ kind: "found", story: cpi[1] });
    expect(resolveStory(cpi, "inflation-drivers-2026-03")).toEqual({ kind: "superseded", requested: "2026-03", current: cpi[1] });
    expect(resolveStory(cpi, "inflation-drivers-2027-03")).toEqual({ kind: "missing" });
    expect(resolveStory(cpi, "spending-retail-2026-09")).toEqual({ kind: "missing" });
  });

  it("names the category whose data an identifier needs, so only that source has to load", () => {
    expect(categoryOfId("inflation-annual-2026-06")).toBe("inflation");
    expect(categoryOfId("spending-retail-2026-09")).toBe("spending");
    expect(categoryOfId("migration-net-2026-07")).toBe("migration");
    expect(categoryOfId("nonsense")).toBeNull();
    expect(categoryOfId("weather-annual-2026-06")).toBeNull();
  });
});
