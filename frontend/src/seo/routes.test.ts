import { describe, expect, it } from "vitest";
import { metaFor, ROUTE_META, SITE_NAME, withSiteName } from "./routes";

describe("page metadata", () => {
  it("covers every static route with a distinct title and a description of useful length", () => {
    const titles = Object.values(ROUTE_META).map((m) => withSiteName(m.title));
    expect(new Set(titles).size).toBe(titles.length);
    for (const m of Object.values(ROUTE_META)) {
      expect(withSiteName(m.title).length).toBeLessThanOrEqual(70);
      expect(m.description.length).toBeGreaterThanOrEqual(60);
      expect(m.description.length).toBeLessThanOrEqual(200);
    }
  });

  it("finds a route with or without a trailing slash", () => {
    expect(metaFor("/stories/")).toBe(ROUTE_META["/stories"]);
    expect(metaFor("/")).toBe(ROUTE_META["/"]);
    expect(metaFor("/nope")).toBeUndefined();
  });

  it("adds the site name once", () => {
    expect(withSiteName("Stories")).toBe(`Stories | ${SITE_NAME}`);
    expect(withSiteName(withSiteName("Stories"))).toBe(`Stories | ${SITE_NAME}`);
  });
});
