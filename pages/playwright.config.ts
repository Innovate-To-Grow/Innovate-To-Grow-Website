import {defineConfig, type PlaywrightTestConfig} from '@playwright/test';

import {ALL_PROJECTS, LOCAL_PROJECTS} from './playwright.projects';

const isCI = Boolean(process.env.CI);

export const BASE_CONFIG: PlaywrightTestConfig = {
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
};

export const LOCAL_FRONTEND_SERVER = {
  command: 'npm run build && npm run preview -- --host 127.0.0.1 --port 4173',
  url: 'http://127.0.0.1:4173',
  reuseExistingServer: true,
  timeout: 180_000,
};

export default defineConfig({
  ...BASE_CONFIG,
  // Raw local invocation remains the dependency-free mocked suite. CI starts
  // its services explicitly and receives the full local + live project list.
  webServer: isCI
    ? undefined
    : LOCAL_FRONTEND_SERVER,
  projects: isCI ? ALL_PROJECTS : LOCAL_PROJECTS,
});
