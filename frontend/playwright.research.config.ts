import { defineConfig, devices } from "@playwright/test";

// The economic outlook with published research, over SYNTHETIC data only: the fixture Stats NZ database plus
// scripts/seed_research_demo.py (fictional institutions, its own registry file). Public research is switched on for
// this server alone. Needs the backend venv on PATH and a fresh `npm run build`.
const dataDir = process.env.E2E_RESEARCH_DATA_DIR ?? "/tmp/nzstats-e2e-research";
const port = process.env.E2E_RESEARCH_PORT ?? "8766";

export default defineConfig({
  testDir: "./e2e-research",
  webServer: {
    command:
      `rm -rf ${dataDir} && python ../scripts/seed_e2e_db.py ${dataDir} && python ../scripts/seed_research_demo.py ${dataDir} && ` +
      `NZSTATS_DATA_DIR=${dataDir} NZSTATS_STATIC_DIR=dist NZSTATS_PUBLIC_RESEARCH=1 ` +
      `NZSTATS_RESEARCH_SOURCES_FILE=${dataDir}/research_sources.synthetic.toml nzstats serve --no-scheduler --port ${port}`,
    url: `http://127.0.0.1:${port}/api/health`,
    reuseExistingServer: false,
    timeout: 180_000,
  },
  use: { baseURL: `http://127.0.0.1:${port}`, screenshot: "only-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    { name: "tablet", use: { ...devices["Desktop Chrome"], viewport: { width: 768, height: 1024 } } },
    { name: "mobile", use: { ...devices["Pixel 7"], viewport: { width: 390, height: 844 } } },
  ],
});
