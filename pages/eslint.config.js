import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

import { qualityConfigs } from './eslint.quality.js'

export default defineConfig([
  globalIgnores(['dist', 'coverage', 'playwright-report']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    linterOptions: {
      // A suppression that no longer suppresses anything must be deleted, so
      // documented exceptions to the quality limits cannot go stale.
      reportUnusedDisableDirectives: 'error',
    },
  },
  // Hard size/complexity limits (eslint.quality.js); advisory levels are only
  // reported by `npm run quality:report`.
  ...qualityConfigs('hard'),
  {
    // Route configuration module: defines lazy-loaded route components inline
    // alongside the (non-component) `router` export. It is not a fast-refresh
    // target, so react-refresh's only-export-components rule does not apply.
    files: ['src/app/router/router.tsx'],
    rules: {
      'react-refresh/only-export-components': 'off',
    },
  },
])
