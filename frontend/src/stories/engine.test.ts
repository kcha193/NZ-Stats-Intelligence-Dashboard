import { describe, expect, it } from "vitest";
import type { CpiDashboard } from "@/api/types";
import cpiFixture from "@/test/fixtures/cpi.json";
import { buildCpiStories } from "./cpi";
import { arrangeCollection, categoryOfId, glanceStories, neighbours, orderStories, relatedStories, resolveStory, splitTemplate } from "./engine";
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

describe("homepage arrangement", () => {
  const story = (id: string, category: Story["category"], glance = false): Story =>
    ({ ...cpi[0], id, category, glance: glance ? cpi[0].glance : undefined });

  it("takes one headline measure per category, in a fixed reading order, only from stories that carry one", () => {
    const stories = [story("m", "migration", true), story("s2", "spending"), story("i", "inflation", true), story("s", "spending", true)];
    expect(glanceStories(stories).map((s) => s.id)).toEqual(["i", "s", "m"]);
    expect(glanceStories([story("s2", "spending")])).toEqual([]);
  });

  it("varies the collection: the prominent and supporting stories avoid repeating a category when they can", () => {
    const lead = story("lead", "spending");
    const rest = [story("a", "spending"), story("b", "migration"), story("c", "migration"), story("d", "inflation"), story("e", "inflation")];
    const c = arrangeCollection(lead, rest);
    expect(c.prominent?.id).toBe("b");
    expect(c.supporting.map((s) => s.id)).toEqual(["a", "d"]);
    expect(c.rest.map((s) => s.id)).toEqual(["c", "e"]);
  });

  it("arranges what exists without inventing slots", () => {
    expect(arrangeCollection(story("lead", "spending"), [])).toEqual({ prominent: undefined, supporting: [], rest: [] });
    const one = arrangeCollection(story("lead", "spending"), [story("a", "spending")]);
    expect(one.prominent?.id).toBe("a");
    expect(one.supporting).toEqual([]);
  });
});

describe("story navigation", () => {
  const s = (id: string, category: Story["category"]): Story => ({ ...cpi[0], id, category });
  const feed = [s("a", "spending"), s("b", "inflation"), s("c", "spending"), s("d", "migration"), s("e", "spending")];

  it("relates stories on the same topic first, then others, newest first, never the story itself", () => {
    expect(relatedStories(feed, feed[0], 3).map((x) => x.id)).toEqual(["c", "e", "b"]);
    expect(relatedStories(feed, feed[3], 2).map((x) => x.id)).toEqual(["a", "b"]);
  });

  it("gives the previous and next story in feed order, and nothing past either end", () => {
    expect(neighbours(feed, "c")).toEqual({ previous: feed[1], next: feed[3] });
    expect(neighbours(feed, "a")).toEqual({ previous: undefined, next: feed[1] });
    expect(neighbours(feed, "zz")).toEqual({ previous: undefined, next: undefined });
  });
});
