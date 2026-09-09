import { defineConfig, devices } from '@playwright/test'

/**
 * End-to-end tests run against the Flask server serving the built bundle.
 *
 *   cd apps/ops-web && npm run build
 *   cd ../.. && .\.venv\Scripts\python.exe manage.py seed-ops
 *   cd apps/ops-web && npm run test:e2e
 *
 * Set E2E_BASE_URL to point at an already-running server; otherwise Playwright
 * starts `manage.py serve` from the repository root.
 */
const baseURL = process.env.E2E_BASE_URL ?? 'http://127.0.0.1:5000'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  timeout: 60_000,
  expect: { timeout: 10_000, toHaveScreenshot: { maxDiffPixelRatio: 0.02 } },
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : [['list']],
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
    locale: 'en-US',
    timezoneId: 'America/Chicago',
  },
  projects: [
    { name: 'desktop-1440', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } } },
    { name: 'desktop-1366', use: { ...devices['Desktop Chrome'], viewport: { width: 1366, height: 768 } }, grep: /@responsive/ },
    { name: 'tablet-768', use: { ...devices['Desktop Chrome'], viewport: { width: 768, height: 1024 }, hasTouch: true }, grep: /@responsive/ },
    { name: 'mobile-390', use: { ...devices['Desktop Chrome'], viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true }, grep: /@responsive/ },
  ],
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : {
        command: '..\\..\\.venv\\Scripts\\python.exe ..\\..\\manage.py serve',
        url: `${baseURL}/healthz`,
        reuseExistingServer: true,
        timeout: 120_000,
        env: { ASME_ENV: 'development', ASME_OUTBOX_WORKER: '0', ASME_SESSION_COOKIE_SECURE: '0' },
      },
})
