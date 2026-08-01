import {devices, type PlaywrightTestConfig} from '@playwright/test';

type PlaywrightProject = NonNullable<PlaywrightTestConfig['projects']>[number];

export const LIVE_SPEC_PATTERNS = [/smoke\.live\.spec\.ts/, /admin\.spec\.ts/];

// Playwright's bundled device registry stops at iPhone 15 / Galaxy S24, so the
// current flagships are defined here as custom descriptors layered on the
// closest stock preset. Only viewport + user-agent are overridden: the viewport
// is what drives responsive layout in these specs, and it differs from the
// preset by only a few CSS px (so effectively the same breakpoints are hit).
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

// These projects contain only fixture-backed specs. They deliberately ignore
// the two real-service specs so `npm run e2e` never needs Django, PostgreSQL, or
// third-party credentials.
export const LOCAL_PROJECTS: PlaywrightProject[] = [
  {
    name: 'chromium',
    use: {...devices['Desktop Chrome']},
    grepInvert: /@mobile-only/,
    testIgnore: LIVE_SPEC_PATTERNS,
  },
  {
    name: 'firefox',
    use: {...devices['Desktop Firefox']},
    grepInvert: /@mobile-only|@admin/,
    testIgnore: LIVE_SPEC_PATTERNS,
  },
  {
    name: 'webkit',
    use: {...devices['Desktop Safari']},
    grepInvert: /@mobile-only|@admin/,
    testIgnore: LIVE_SPEC_PATTERNS,
  },
  {
    name: 'pixel7',
    use: {...devices['Pixel 7']},
    grep: /@core|@mobile-only/,
    testIgnore: LIVE_SPEC_PATTERNS,
  },
  {
    name: 'iphone14',
    use: {...devices['iPhone 14']},
    grep: /@core|@mobile-only/,
    testIgnore: LIVE_SPEC_PATTERNS,
  },
  {
    name: 'iphone-se',
    use: {...devices['iPhone SE']},
    grep: /@core|@mobile-only/,
    testIgnore: LIVE_SPEC_PATTERNS,
  },
  {
    name: 'ipad',
    use: {...devices['iPad (gen 7)']},
    grep: /@core|@mobile-only/,
    testIgnore: LIVE_SPEC_PATTERNS,
  },
  {
    name: 'iphone-17-pro-max',
    use: {...iphone17ProMax},
    grep: /@core|@mobile-only/,
    testIgnore: LIVE_SPEC_PATTERNS,
  },
  {
    name: 'galaxy-s26-ultra',
    use: {...galaxyS26Ultra},
    grep: /@core|@mobile-only/,
    testIgnore: LIVE_SPEC_PATTERNS,
  },
  {
    name: 'galaxy-tab-s9',
    use: {...devices['Galaxy Tab S9']},
    grep: /@core|@mobile-only/,
    testIgnore: LIVE_SPEC_PATTERNS,
  },
];

// The live Django-admin suite is serial and DB-mutating, so one Chromium
// project supplies meaningful browser coverage without multiplying mutations.
export const LIVE_PROJECT: PlaywrightProject = {
  name: 'live-chromium',
  use: {...devices['Desktop Chrome']},
  testMatch: LIVE_SPEC_PATTERNS,
};

export const ALL_PROJECTS: PlaywrightProject[] = [...LOCAL_PROJECTS, LIVE_PROJECT];
