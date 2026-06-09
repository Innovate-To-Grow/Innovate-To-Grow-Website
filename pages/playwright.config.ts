import {defineConfig, devices} from '@playwright/test';

const isCI = Boolean(process.env.CI);

// Playwright's bundled device registry stops at iPhone 15 / Galaxy S24, so the
// current flagships are defined here as custom descriptors layered on the
// closest stock preset. Only viewport + user-agent are overridden: the viewport
// is what drives responsive layout in these specs, and it differs from the
// preset by only a few CSS px (so effectively the same breakpoints are hit).
// The UA strings are best-effort — refresh if exact shipping OS/Chrome build
// strings are needed.
const iphone17ProMax = {
  ...devices['iPhone 15 Pro Max'],
  viewport: {width: 440, height: 763},
  userAgent:
    'Mozilla/5.0 (iPhone; CPU iPhone OS 26_0 like Mac OS X) ' +
    'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 Mobile/15E148 Safari/604.1',
};
const galaxyS26Ultra = {
  ...devices['Galaxy S24'],
  viewport: {width: 412, height: 915},
  userAgent:
    'Mozilla/5.0 (Linux; Android 16; SM-S948B) AppleWebKit/537.36 ' +
    '(KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36',
};

export default defineConfig({
  testDir: './src/__tests__/e2e',
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
    // The live Django-admin suite is @admin-tagged and pinned to chromium only:
    // it is a serial, DB-mutating internal-tool flow where cross-engine reruns
    // add flake surface without meaningful coverage, so firefox/webkit skip it.
    {name: 'chromium', use: {...devices['Desktop Chrome']}, grepInvert: /@mobile-only/},
    {name: 'firefox', use: {...devices['Desktop Firefox']}, grepInvert: /@mobile-only|@admin/},
    {name: 'webkit', use: {...devices['Desktop Safari']}, grepInvert: /@mobile-only|@admin/},
    // Mobile/tablet devices run the core journeys + mobile-only responsive specs.
    {name: 'pixel7', use: {...devices['Pixel 7']}, grep: /@core|@mobile-only/},
    {name: 'iphone14', use: {...devices['iPhone 14']}, grep: /@core|@mobile-only/},
    {name: 'iphone-se', use: {...devices['iPhone SE']}, grep: /@core|@mobile-only/},
    {name: 'ipad', use: {...devices['iPad (gen 7)']}, grep: /@core|@mobile-only/},
    // Current flagships. Playwright's bundled registry stops at iPhone 15 /
    // Galaxy S24, so the two phones use custom descriptors (defined above).
    // Galaxy Tab S9 is a stock preset and the newest Android tablet, covering
    // the Chromium tablet path the WebKit-only `ipad` misses.
    {name: 'iphone-17-pro-max', use: {...iphone17ProMax}, grep: /@core|@mobile-only/},
    {name: 'galaxy-s26-ultra', use: {...galaxyS26Ultra}, grep: /@core|@mobile-only/},
    {name: 'galaxy-tab-s9', use: {...devices['Galaxy Tab S9']}, grep: /@core|@mobile-only/},
  ],
});
