import {defineConfig, devices} from '@playwright/test';

const isCI = Boolean(process.env.CI);

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: {
    timeout: 10_000,
  },
  fullyParallel: true,
  retries: isCI ? 1 : 0,
  // In CI each project runs in its own matrix leg and emits a uniquely-named
  // blob report (PW_PROJECT set per leg) for the downstream merge job; `list`
  // alongside it keeps per-leg failures readable in the job log. Locally `list`.
  reporter: isCI
    ? [['list'], ['blob', {fileName: `report-${(process.env.PW_PROJECT ?? 'all').replace(/[^a-zA-Z0-9_-]/g, '-')}.zip`}]]
    : 'list',
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:4173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  // Local convenience only — CI starts the preview + backend servers itself.
  webServer: isCI
    ? undefined
    : {
        command: 'npm run build && npm run preview -- --host 127.0.0.1 --port 4173',
        url: 'http://127.0.0.1:4173',
        reuseExistingServer: true,
        timeout: 180_000,
      },
  projects: [
    // Desktop engines run the full suite except mobile-only responsive specs.
    {name: 'chromium', use: {...devices['Desktop Chrome']}, grepInvert: /@mobile-only/},
    {name: 'firefox', use: {...devices['Desktop Firefox']}, grepInvert: /@mobile-only/},
    {name: 'webkit', use: {...devices['Desktop Safari']}, grepInvert: /@mobile-only/},
    // Mobile/tablet devices run the core journeys + mobile-only responsive specs.
    {name: 'pixel7', use: {...devices['Pixel 7']}, grep: /@core|@mobile-only/},
    {name: 'iphone14', use: {...devices['iPhone 14']}, grep: /@core|@mobile-only/},
    {name: 'iphone-se', use: {...devices['iPhone SE']}, grep: /@core|@mobile-only/},
    {name: 'ipad', use: {...devices['iPad (gen 7)']}, grep: /@core|@mobile-only/},
  ],
});
