import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/browser",
  fullyParallel: true,
  // Linux WebKit on shared CI spends significant time on page/input setup.
  // Keep assertion timeouts unchanged; allow setup time without blind retries.
  timeout: process.env.CI ? 60000 : 30000,
  workers: process.env.CI ? 2 : 3,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://127.0.0.1:5178",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: {
    command: "npm run dev -- --port 5178 --strictPort",
    url: "http://127.0.0.1:5178",
    reuseExistingServer: false,
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "firefox", use: { ...devices["Desktop Firefox"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
    { name: "mobile-webkit", use: { ...devices["iPhone 13"] } },
    ...(process.env.EG_BRANDED_BROWSERS
      ? [
          {
            name: "chrome",
            use: { ...devices["Desktop Chrome"], channel: "chrome" },
          },
          {
            name: "edge",
            use: { ...devices["Desktop Edge"], channel: "msedge" },
          },
        ]
      : []),
  ],
});
