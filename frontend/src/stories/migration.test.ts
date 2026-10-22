import { describe, expect, it } from "vitest";
import type { SeriesData } from "@/api/types";
import arrivals from "@/test/fixtures/series_arrivals_ry.json";
import departures from "@/test/fixtures/series_departures_ry.json";
import net from "@/test/fixtures/series_net_ry.json";
import nonNz from "@/test/fixtures/series_net_nonnz_ry.json";
import nz from "@/test/fixtures/series_net_nz_ry.json";
import { buildMigrationStories, type MigrationInput } from "./migration";

const input: MigrationInput = {
  net: net as SeriesData, arrivals: arrivals as SeriesData, departures: departures as SeriesData,
  nz: nz as SeriesData, nonNz: nonNz as SeriesData,
  releases: [{ id: 2, release_key: "international-migration:july 2026", status: "published", page_url: "https://www.stats.govt.nz/information-releases/international-migration-july-2026/" }],
};
const byTemplate = (i: MigrationInput) => new Map(buildMigrationStories(i).map((s) => [s.template, s]));

describe("migration stories", () => {
  it("builds three year-ended stories with release provenance and provisional status", () => {
    const stories = buildMigrationStories(input);
    expect(stories.map((s) => s.id)).toEqual(["migration-net-2026-07", "migration-flows-2026-07", "migration-citizenship-2026-07"]);
    for (const s of stories) {
      expect(s.category).toBe("migration");
      expect(s.dataStatus).toBe("provisional");
      expect(s.referenceLabel).toBe("Year ended July 2026");
      expect(s.provenance).toMatchObject({ releaseId: 2, pageUrl: input.releases[0].page_url, publishedAt: "2026-09-14T10:45:00+12:00" });
      expect(s.caveats.join(" ")).toMatch(/provisional/i);
      expect(s.caveats.join(" ")).toMatch(/not comparable with monthly/i);
      expect(s.evidence.every((e) => e.seriesKey.startsWith("mig.ry."))).toBe(true);
    }
  });

  it("compares the year-ended net gain with the same measure a year earlier", () => {
    const s = byTemplate(input).get("migration-net")!;
    expect(s.headline).toBe("Annual net migration gain rises to 20,350");
    expect(s.stat).toMatchObject({ value: "+20,350", unit: "people, net migration in the year ended July 2026", sign: "positive" });
    expect(s.dek).toBe("New Zealand gained 20,350 more migrants than it lost in the year ended July 2026, up from a net gain of 9,592 a year earlier. The latest estimate is provisional.");
    expect(s.context).toContain("The largest annual net gain in the last ten years was 133,738, in the year ended October 2023.");
  });

  it("sets arrivals against departures, each against its own year-earlier value", () => {
    const s = byTemplate(input).get("migration-flows")!;
    expect(s.headline).toBe("Migrant arrivals rise 5.2% while departures fall 3.5%");
    expect(s.dek).toBe("In the year ended July 2026, 134,434 migrants arrived and 114,084 departed, so arrivals exceeded departures by 20,350.");
  });

  it("separates New Zealand citizens from other citizens", () => {
    const s = byTemplate(input).get("migration-citizenship")!;
    expect(s.headline).toBe("Net loss of New Zealand citizens is offset by a larger gain of other citizens");
    expect(s.dek).toBe("In the year ended July 2026, New Zealand citizens recorded a net loss of 38,335 and non-New Zealand citizens a net gain of 58,685.");
    expect(s.stat).toMatchObject({ value: "−38,335", sign: "negative" });
    expect(s.context).toContain("Year-ended net migration of New Zealand citizens has been a loss in every month since January 2022.");
    expect(s.context).toContain("Together they make up the total net gain of 20,350.");
  });

  it("never combines series from different release bundles", () => {
    const stale = { ...(departures as SeriesData), vintage: { ...(departures as SeriesData).vintage, captured_at: "2026-09-15T10:00:00+12:00" } };
    const t = byTemplate({ ...input, departures: stale });
    expect(t.has("migration-flows")).toBe(false);
    expect(t.has("migration-net")).toBe(true);
  });

  it("builds only what the loaded series support", () => {
    expect(buildMigrationStories({ ...input, net: undefined, nz: undefined }).map((s) => s.template)).toEqual(["migration-flows"]);
  });
});

describe("migration release status", () => {
  const corrected: MigrationInput = { ...input, releases: [{ ...input.releases[0], status: "corrected" }] };

  it("carries the matching release summary's status into every story's provenance", () => {
    expect(buildMigrationStories(input).map((s) => s.provenance.status)).toEqual(["published", "published", "published"]);
    const stories = buildMigrationStories(corrected);
    expect(stories).toHaveLength(3);
    expect(stories.map((s) => s.provenance.status)).toEqual(["corrected", "corrected", "corrected"]);
  });

  it("puts the correction first among the caveats, as the CPI and card spending stories do", () => {
    for (const s of buildMigrationStories(corrected)) {
      expect(s.caveats[0]).toBe("Corrected release: Stats NZ corrected this release after first publishing it.");
      expect(s.caveats.join(" ")).toMatch(/provisional/i);
    }
    for (const s of buildMigrationStories(input)) expect(s.caveats.join(" ")).not.toMatch(/Corrected release/);
  });

  it("uses the status of the release that matches the series vintage, not another release's", () => {
    const other = { id: 9, release_key: "international-migration:june 2026", status: "corrected", page_url: null };
    const stories = buildMigrationStories({ ...input, releases: [other, input.releases[0]] });
    expect(stories.map((s) => s.provenance.status)).toEqual(["published", "published", "published"]);
  });

  it("falls back to published, the status of any ingested release, when no summary matches", () => {
    expect(buildMigrationStories({ ...input, releases: [] }).map((s) => s.provenance.status)).toEqual(["published", "published", "published"]);
  });
});

describe("migration net headline and dek at zero", () => {
  /** Sets the latest year-ended net, and optionally the same month a year earlier. */
  const withNet = (latest: number, yearAgo?: number) => {
    const points = (net as SeriesData).points.map((p) => ({ ...p }));
    points[points.length - 1].value = latest;
    if (yearAgo !== undefined) points[points.length - 13].value = yearAgo;
    return byTemplate({ ...input, net: { ...(net as SeriesData), points } }).get("migration-net")!;
  };

  it("describes a balanced year rather than a gain of zero", () => {
    const s = withNet(0);
    expect(s.headline).toBe("Annual net migration is balanced");
    expect(s.dek).toBe("Arrivals and departures were balanced in the year ended July 2026, compared with a net gain of 9,592 a year earlier. The latest estimate is provisional.");
  });

  it("describes a balanced year earlier as no net change, not 'a no net change'", () => {
    const s = withNet(20350, 0);
    expect(s.dek).toBe("New Zealand gained 20,350 more migrants than it lost in the year ended July 2026, compared with no net change a year earlier. The latest estimate is provisional.");
  });
});

describe("migration stories from different release bundles", () => {
  const older = { release_key: "international-migration:june 2026", title: "International migration: June 2026", published_at: "2026-08-14T10:45:00+12:00", captured_at: "2026-08-14T11:00:00+12:00" };
  /** A citizenship pair from an earlier release: the latest one did not include the citizenship chart. */
  const citizenshipFromJune = (d: SeriesData): SeriesData => ({ ...d, vintage: { ...d.vintage, ...older }, points: d.points.slice(0, -1) });
  const mixed: MigrationInput = {
    ...input,
    nz: citizenshipFromJune(nz as SeriesData), nonNz: citizenshipFromJune(nonNz as SeriesData),
    releases: [
      input.releases[0],
      { id: 1, release_key: older.release_key, status: "corrected", page_url: "https://www.stats.govt.nz/information-releases/international-migration-june-2026/" },
    ],
  };

  it("builds the citizenship story from the pair's own bundle, with that release's provenance and status", () => {
    const stories = buildMigrationStories(mixed);
    expect(stories.map((s) => s.id)).toEqual(["migration-net-2026-07", "migration-flows-2026-07", "migration-citizenship-2026-06"]);
    const [netStory, , cit] = stories;
    expect(cit.referenceLabel).toBe("Year ended June 2026");
    expect(cit.provenance).toMatchObject({ releaseId: 1, releaseKey: older.release_key, status: "corrected", publishedAt: older.published_at });
    expect(cit.caveats[0]).toMatch(/^Corrected release/);
    expect(cit.evidence.every((e) => e.releaseKey === older.release_key)).toBe(true);
    expect(netStory.provenance).toMatchObject({ releaseId: 2, status: "published" });
  });

  it("does not add the net total from a different bundle to the citizenship story", () => {
    const cit = byTemplate(mixed).get("migration-citizenship")!;
    expect(cit.context.join(" ")).not.toMatch(/Together they make up/);
  });

  it("still withholds a pair whose two series come from different bundles", () => {
    const split = { ...mixed, nonNz: nonNz as SeriesData };
    expect(byTemplate(split).has("migration-citizenship")).toBe(false);
  });
});
