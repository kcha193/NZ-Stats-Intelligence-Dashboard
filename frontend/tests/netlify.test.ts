import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { ROUTE_META } from "../src/seo/routes";

// netlify.toml lists the client-side routes explicitly (so unknown addresses get a real 404). This keeps that list
// in step with the router and with the pages that are prerendered.
const root = path.resolve(import.meta.dirname, "../..");
const toml = readFileSync(path.join(root, "netlify.toml"), "utf8");
const app = readFileSync(path.join(import.meta.dirname, "../src/App.tsx"), "utf8");

const rewrites = [...toml.matchAll(/\[\[redirects\]\]\s+from = "([^"]+)"\s+to = "([^"]+)"\s+status = (\d+)/g)].map(
  (m) => ({ from: m[1], to: m[2], status: Number(m[3]) }),
);
const spaFrom = new Set(rewrites.filter((r) => r.status === 200 && r.to === "/_pages/app-shell.html").map((r) => r.from));
const routes = [...app.matchAll(/<Route path="([^"]+)"/g)].map((m) => m[1]).filter((p) => p !== "*" && p !== "/"); // "/" is index.html itself

describe("netlify.toml routing", () => {
  it("serves the app for every route the router defines", () => {
    expect(routes.length).toBeGreaterThanOrEqual(8);
    for (const route of routes) {
      const wanted = route.includes("/:") ? route.replace(/\/:[^/]+$/, "/*") : route;
      expect(spaFrom, `${route} needs a rewrite to the app shell`).toContain(wanted);
    }
  });

  it("has a rewrite for every page the build prerenders", () => {
    for (const route of Object.keys(ROUTE_META).filter((r) => r !== "/")) expect(spaFrom).toContain(route);
  });

  it("answers a missing data file or API call with a real 404 before any wildcard rewrite", () => {
    const data = rewrites.findIndex((r) => r.from === "/data/*");
    const firstWildcard = rewrites.findIndex((r) => r.status === 200 && r.from.endsWith("*"));
    expect(rewrites[data]).toMatchObject({ status: 404 });
    expect(rewrites.find((r) => r.from === "/api/*")).toMatchObject({ status: 404 });
    expect(data).toBeLessThan(firstWildcard);
  });

  it("has no catch-all rewrite, so an unknown address is a 404", () => {
    expect(rewrites.some((r) => r.from === "/*")).toBe(false);
  });
});
