import { defineConfig, devices } from "@playwright/test";

// Runs the existing browser specs plus the static-site specs against the built static site, served with the rules from
// netlify.toml. A second server runs the live app over the same seeded database, for the visual parity spec.
// Prepare with scripts/e2e_static.sh (seeds, exports a fixture snapshot, builds both sites), which also runs this.
process.env.E2E_MODE = "static";
const dataDir = process.env.E2E_DATA_DIR ?? "/tmp/nzstats-e2e";
const livePort = process.env.E2E_PORT ?? "8765";
const staticPort = process.env.STATIC_PORT ?? "4173";
process.env.LIVE_URL = `http://127.0.0.1:${livePort}`;

export default defineConfig({
  testDir: ".",
  testMatch: ["e2e/**/*.spec.ts", "e2e-static/**/*.spec.ts"],
  webServer: [
    {
      command:
        `python ../scripts/seed_e2e_db.py ${dataDir} && ` +
        `NZSTATS_DATA_DIR=${dataDir} NZSTATS_STATIC_DIR=dist nzstats serve --no-scheduler --port ${livePort}`,
      url: `http://127.0.0.1:${livePort}/api/health`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: `python3 ../scripts/serve_static.py dist-static --port ${staticPort}`,
      url: `http://127.0.0.1:${staticPort}/data/v1/manifest.json`,
      reuseExistingServer: false,
      timeout: 30_000,
    },
  ],
  use: { baseURL: `http://127.0.0.1:${staticPort}`, screenshot: "only-on-failure", reducedMotion: "reduce" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    { name: "tablet", use: { ...devices["Desktop Chrome"], viewport: { width: 768, height: 1024 } } },
    { name: "mobile", use: { ...devices["Pixel 7"], viewport: { width: 390, height: 844 } } },
  ],
});
