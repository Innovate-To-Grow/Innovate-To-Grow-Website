import { cpSync, existsSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { transform } from 'esbuild'
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import type { PluginOption } from 'vite'

const configDir = dirname(fileURLToPath(import.meta.url))
const djangoVendorStaticDir = resolve(configDir, '../src/core/static/vendor')

function copyDjangoVendorStaticPlugin(): PluginOption {
  return {
    name: 'copy-django-vendor-static',
    apply: 'build',
    writeBundle(options) {
      if (!existsSync(djangoVendorStaticDir)) {
        this.warn(`Django vendor static directory not found: ${djangoVendorStaticDir}`)
        return
      }

      const outputDir = typeof options.dir === 'string' ? options.dir : resolve(configDir, 'dist')
      cpSync(djangoVendorStaticDir, resolve(outputDir, 'static/vendor'), {
        recursive: true,
        force: true,
      })
    },
  }
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Load env file based on `mode` in the current working directory.
  const env = loadEnv(mode, process.cwd(), '')
  const isProduction = mode === 'production'

  // Backend API URL - defaults to localhost:8000 for development
  const backendUrl = env.VITE_BACKEND_URL || 'http://127.0.0.1:8000'
  const stripProductionDebugStatements = {
    name: 'strip-production-debug-statements',
    async renderChunk(code: string) {
      const result = await transform(code, {
        drop: ['console', 'debugger'],
        legalComments: 'none',
        minify: true,
        sourcemap: false,
        target: 'es2020',
      })

      return {
        code: result.code,
        map: null,
      }
    },
  }

  return {
    plugins: [react(), copyDjangoVendorStaticPlugin(), ...(isProduction ? [stripProductionDebugStatements] : [])],
    esbuild: isProduction
      ? {
          drop: ['console', 'debugger'],
          legalComments: 'none',
        }
      : undefined,
    build: {
      sourcemap: false,
      minify: 'esbuild',
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (id.includes('node_modules/react-dom') || id.includes('node_modules/react/')) {
              return 'react-vendor';
            }
            if (id.includes('node_modules/react-router')) {
              return 'router';
            }
            if (id.includes('node_modules/dompurify')) {
              return 'dompurify';
            }
          },
        },
      },
    },
    server: {
      host: '127.0.0.1',
      proxy: {
        '/api': {
          target: backendUrl,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ''),
        },
        '/media': {
          target: backendUrl,
          changeOrigin: true,
        },
        '/static': {
          target: backendUrl,
          changeOrigin: true,
        },
      },
    },
  }
})
