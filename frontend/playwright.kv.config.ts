import { defineConfig } from '@playwright/test'
import base from './playwright.config'

export default defineConfig({ ...base, testIgnore: [], testMatch: 'kv*.spec.ts', timeout: 90_000,
  reporter: [['list'], ['json', { outputFile: process.env.LAB_REPORT_PATH || '../test-results/kv-frontend.json' }]],
  use: { ...base.use, baseURL: process.env.LAB_UI_URL || 'http://127.0.0.1:19100' },
})
