const path = require("path");
const { defineConfig, devices } = require("@playwright/test");
const { VIEWPORTS } = require("./routes");
const {
  loadDotenv,
  ensureDirs,
  assertSafeBaseUrl,
  authStatePath,
} = require("./helpers/layout");

loadDotenv();
ensureDirs();

const BASE_URL = process.env.BASE_URL || "http://127.0.0.1:8000";
assertSafeBaseUrl(BASE_URL);

const viewportProjects = VIEWPORTS.map((vp) => ({
  name: vp.name,
  dependencies: ["setup"],
  use: {
    ...devices["Desktop Chrome"],
    browserName: "chromium",
    viewport: { width: vp.width, height: vp.height },
    storageState: authStatePath("personel"),
    screenshot: "only-on-failure",
    video: "off",
    trace: "retain-on-failure",
  },
}));

module.exports = defineConfig({
  testDir: __dirname,
  testMatch: /responsive\.spec\.js$/,
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  // Local Django + SQLite is sensitive to parallel load; keep QA gentle by default.
  workers: process.env.QA_WORKERS ? Number(process.env.QA_WORKERS) : 1,
  timeout: 180_000,
  expect: { timeout: 30_000 },
  outputDir: path.join(__dirname, "test-results"),
  reporter: [
    ["list"],
    ["html", { open: "never", outputFolder: path.join(__dirname, "reports", "html") }],
    [path.join(__dirname, "helpers", "summary-reporter.js")],
  ],
  use: {
    baseURL: BASE_URL,
    headless: true,
    actionTimeout: 30_000,
    navigationTimeout: 180_000,
    // Read-only: never accept downloads that mutate; no geolocation etc.
    ignoreHTTPSErrors: true,
  },
  projects: [
    {
      name: "setup",
      testMatch: /auth\.setup\.js$/,
      use: {
        baseURL: BASE_URL,
        storageState: undefined,
      },
    },
    ...viewportProjects,
  ],
});
