import { defineConfig, devices } from "@playwright/test";

const dataDir = process.env.E2E_DATA_DIR ?? "/tmp/nzstats-e2e";

export default defineConfig({
  testDir: "./e2e",
  webServer: {
    command:
      `python ../scripts/seed_e2e_db.py ${dataDir} && ` +
      `NZSTATS_DATA_DIR=${dataDir} NZSTATS_STATIC_DIR=dist nzstats serve --no-scheduler --port 8765`,
    url: "http://127.0.0.1:8765/api/health",
    reuseExistingServer: false,
    timeout: 120_000,
  },
  use: { baseURL: "http://127.0.0.1:8765", screenshot: "only-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    { name: "mobile", use: { ...devices["Pixel 7"] } },
  ],
});
