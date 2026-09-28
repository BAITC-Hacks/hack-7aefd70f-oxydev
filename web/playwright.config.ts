import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  reporter: "list",
  use: {
    baseURL: process.env.QADAM_BASE_URL || "http://127.0.0.1:8765",
    browserName: "chromium",
    channel: "chrome",
    headless: true,
    permissions: ["camera", "microphone"],
    launchOptions: { args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"] },
    screenshot: "only-on-failure",
  },
});
