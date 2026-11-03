import { defineConfig } from "@playwright/test";

// One smoke test: load the built app served by FastAPI and see the Analyse page.
export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 30000,
  use: {
    baseURL: process.env.PXP_URL || "http://127.0.0.1:8000",
    // Use whatever Chromium is installed (set PW_CHROME to override); avoids a CDN download in the lab.
    launchOptions: process.env.PW_CHROME ? { executablePath: process.env.PW_CHROME } : {},
  },
  reporter: "line",
});
