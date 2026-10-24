import { afterEach, describe, expect, it, vi } from "vitest";
import { absoluteUrl, siteOrigin } from "./siteUrl";

afterEach(() => vi.unstubAllEnvs());

describe("siteOrigin", () => {
  it("is the page origin when no canonical site is configured", () => {
    vi.stubEnv("VITE_SITE_URL", "");
    expect(siteOrigin()).toBe(window.location.origin);
  });

  it("prefers the configured canonical origin and ignores trailing slashes", () => {
    vi.stubEnv("VITE_SITE_URL", "https://nzstats.example/");
    expect(absoluteUrl("/stories/x")).toBe("https://nzstats.example/stories/x");
  });
});
