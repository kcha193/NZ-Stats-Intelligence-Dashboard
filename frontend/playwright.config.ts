import { defineConfig, devices } from "@playwright/test";

const dataDir = process.env.E2E_DATA_DIR ?? "/tmp/nzstats-e2e";
// Override when 8765 is taken by something else on the machine.
const port = process.env.E2E_PORT ?? "8765";

export default defineConfig({
  testDir: "./e2e",
  webServer: {
    command:
      `python ../scripts/seed_e2e_db.py ${dataDir} && ` +
      `NZSTATS_DATA_DIR=${dataDir} NZSTATS_STATIC_DIR=dist nzstats serve --no-scheduler --port ${port}`,
    url: `http://127.0.0.1:${port}/api/health`,
    reuseExistingServer: false,
    timeout: 120_000,
  },
  use: { baseURL: `http://127.0.0.1:${port}`, screenshot: "only-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    { name: "tablet", use: { ...devices["Desktop Chrome"], viewport: { width: 768, height: 1024 } } },
    { name: "mobile", use: { ...devices["Pixel 7"], viewport: { width: 390, height: 844 } } },
  ],
});
