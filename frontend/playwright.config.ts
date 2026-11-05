import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 45_000,
  fullyParallel: false,
  workers: 1,
  reporter: [['list'], ['json', { outputFile: process.env.LAB_REPORT_PATH || '../test-results/frontend.json' }]],
  outputDir: '../test-results/browser',
  use: {
    baseURL: process.env.LAB_UI_URL || 'http://127.0.0.1:8000',
    viewport: { width: 1440, height: 1000 },
    headless: true,
    channel: process.env.LAB_BROWSER_CHANNEL || 'msedge',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
})
