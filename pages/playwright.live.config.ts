import {defineConfig} from '@playwright/test';

import {BASE_CONFIG} from './playwright.config';
import {LIVE_PROJECT} from './playwright.projects';

export default defineConfig({
  ...BASE_CONFIG,
  projects: [LIVE_PROJECT],
  webServer: [
    {
      command: '../scripts/e2e/run-live-backend.sh',
      url: 'http://127.0.0.1:8000/readyz/',
      reuseExistingServer: false,
      timeout: 240_000,
      gracefulShutdown: {
        signal: 'SIGTERM',
        timeout: 10_000,
      },
    },
    {
      command:
        'VITE_API_BASE_URL=http://127.0.0.1:8000 npm run build && npm run preview -- --host 127.0.0.1 --port 4173',
      url: 'http://127.0.0.1:4173',
      reuseExistingServer: false,
      timeout: 180_000,
      gracefulShutdown: {
        signal: 'SIGTERM',
        timeout: 10_000,
      },
    },
  ],
});
