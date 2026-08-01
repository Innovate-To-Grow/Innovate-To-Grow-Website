import {defineConfig} from '@playwright/test';

import {BASE_CONFIG, LOCAL_FRONTEND_SERVER} from './playwright.config';
import {LOCAL_PROJECTS} from './playwright.projects';

export default defineConfig({
  ...BASE_CONFIG,
  projects: LOCAL_PROJECTS,
  webServer: LOCAL_FRONTEND_SERVER,
});
