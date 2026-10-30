import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { defineConfig, loadEnv, type Plugin, type Rollup } from 'vite'
import react from '@vitejs/plugin-react'

const configDir = dirname(fileURLToPath(import.meta.url))

/**
 * Preconnects to the API origin when VITE_API_BASE_URL is another host (production:
 * https://api.i2g.ucmerced.edu), so its TLS handshake overlaps the bundle download instead of
 * delaying the first API call. The app's reads go without credentials: an anonymous `crossorigin`.
 */
function apiPreconnect(apiBaseUrl: string | undefined): Plugin {
  return {
    name: 'itg-api-preconnect',
    transformIndexHtml() {
      if (!apiBaseUrl || !/^https?:\/\//.test(apiBaseUrl)) return
      const href = new URL(apiBaseUrl).origin
      return [{ tag: 'link', attrs: { rel: 'preconnect', href, crossorigin: true }, injectTo: 'head' }]
    },
  }
}

// Route pages whose chunks the HTML starts fetching straight away on a matching URL (keep in step
// with src/app/router/router.tsx). Otherwise a route chunk is only requested once the entry bundle
// has downloaded and run, a third round trip before the page, its data request and its largest
// paint can start.
const PRELOADED_ROUTES: ReadonlyArray<readonly [pathPattern: string, routeModule: string]> = [
  ['^/current-projects/?$', 'src/routes/ProjectsPage/index.ts'],
  ['^/presenting-teams/?$', 'src/routes/PresentingTeamsPage/index.ts'],
  ['^/past-projects(/[^/]+)?/?$', 'src/routes/PastProjectsPage/index.ts'],
  ['^/(projects|past-projects/project)/[^/]+/?$', 'src/routes/ProjectDetailPage/index.ts'],
]

/** A chunk's files (itself, its static imports, their CSS) that the entry does not already load. */
function chunkFiles(bundle: Rollup.OutputBundle, root: Rollup.OutputChunk, loaded: Set<string>): string[] {
  const files: string[] = []
  const visit = (fileName: string) => {
    const chunk = bundle[fileName]
    if (loaded.has(fileName) || chunk?.type !== 'chunk') return
    loaded.add(fileName)
    files.push(fileName)
    for (const css of chunk.viteMetadata?.importedCss ?? []) {
      if (!loaded.has(css)) files.push(css)
      loaded.add(css)
    }
    chunk.imports.forEach(visit)
  }
  visit(root.fileName)
  return files
}

/**
 * Inlines a small script that, on a URL in PRELOADED_ROUTES, adds modulepreload / preload links for
 * that route's chunk and its CSS, so they download alongside the entry bundle. The links match the
 * ones Vite's preload helper would add later (absolute href, anonymous CORS), which it then skips.
 */
function routeChunkPreload(): Plugin {
  return {
    name: 'itg-route-chunk-preload',
    transformIndexHtml: {
      order: 'post',
      handler(_html, { bundle, chunk: entry }) {
        if (!bundle || !entry) return
        const entryFiles = new Set<string>()
        chunkFiles(bundle, entry, entryFiles)
        const table = PRELOADED_ROUTES.flatMap(([pattern, module]) => {
          const route = Object.values(bundle).find(
            (output): output is Rollup.OutputChunk =>
              output.type === 'chunk' && Boolean(output.facadeModuleId?.endsWith(module)),
          )
          return route ? [[pattern, chunkFiles(bundle, route, new Set(entryFiles)).map((file) => `/${file}`)]] : []
        })
        if (table.length === 0) return
        const script =
          `(function(r,p){for(var i=0;i<r.length;i++){if(!new RegExp(r[i][0]).test(p))continue;` +
          `r[i][1].forEach(function(f){var l=document.createElement('link');` +
          `if(/\\.css$/.test(f)){l.rel='preload';l.as='style'}else{l.rel='modulepreload'}` +
          `l.crossOrigin='';l.href=f;document.head.appendChild(l)});return}})(${JSON.stringify(table)},location.pathname)`
        return [{ tag: 'script', children: script, injectTo: 'head' }]
      },
    },
  }
}
// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Load env file based on `mode` in the current working directory.
  const env = loadEnv(mode, process.cwd(), '')

  // Backend API URL - defaults to localhost:8000 for development
  const backendUrl = env.VITE_BACKEND_URL || 'http://127.0.0.1:8000'

  return {
    plugins: [react(), apiPreconnect(env.VITE_API_BASE_URL), routeChunkPreload()],
    resolve: {
      alias: {
        '@': resolve(configDir, 'src'),
      },
    },
    build: {
      // The CSS needs cascade layers, so its floor is the first browsers with @layer. Vite's default
      // target is newer: its minifier then rewrites (max-width: 768px) as (width<=768px), which Safari
      // before 16.4 and Chrome before 104 ignore, dropping every phone layout rule.
      cssTarget: ['chrome99', 'edge99', 'firefox97', 'safari15.4', 'ios15.4'],
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
