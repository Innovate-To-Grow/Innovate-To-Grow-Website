import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

import {defineConfig} from 'vitest/config';
import react from '@vitejs/plugin-react';

const configDir = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': resolve(configDir, 'src'),
    },
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{ts,tsx}'],
    setupFiles: ['src/__tests__/setup.ts'],
    testTimeout: 30000,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov', 'json-summary'],
      reportsDirectory: 'coverage',
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        'src/**/*.test.{ts,tsx}',
        'src/__tests__/**',
        'src/main.tsx',
        'src/app/providers.tsx',
        'src/app/router.tsx',
        'src/vite-env.d.ts',
      ],
      thresholds: {
        statements: 30,
        branches: 25,
        functions: 20,
        lines: 30,
      },
    },
  },
});
