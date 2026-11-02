#!/usr/bin/env node
// Fail when the built index.html no longer carries what vite.config.ts's HTML plugins promise.
//
// itg-route-chunk-preload walks the bundle graph that Vite/Rolldown hand it (chunk.imports,
// viteMetadata.importedCss, facadeModuleId) and inlines a table of the files each preloaded
// route needs. A bundler upgrade that changes that graph only fails the build when a route's
// chunk disappears; anything else (a dropped stylesheet, a file the entry already loads, a
// missing shared chunk) would ship silently. So this check rebuilds the expectation from the
// output itself: for each route, the files Vite's own preload helper lists for that route's
// dynamic import (__vite__mapDeps), minus what index.html already loads, must be exactly the
// table's files. It also checks the table sits before the first stylesheet and that
// itg-api-preconnect emitted the API origin. Run it after `npm run build`; pass the build's
// VITE_API_BASE_URL to check the preconnect.

import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const dist = join(root, 'dist')
const failures = []

let html
try {
  html = readFileSync(join(dist, 'index.html'), 'utf8')
} catch {
  console.error(`No build output at ${dist}: run npm run build first.`)
  process.exit(1)
}

// PRELOADED_ROUTES in vite.config.ts: ['<path pattern>', 'src/routes/<Page>/index.ts'] pairs.
const configSource = readFileSync(join(root, 'vite.config.ts'), 'utf8')
const routesBlock = configSource.match(/const PRELOADED_ROUTES[^=]*=\s*\[([\s\S]*?)\n\]/)
const configured = routesBlock
  ? [...routesBlock[1].matchAll(/\[\s*'([^']+)'\s*,\s*'([^']+)'\s*\]/g)].map(([, pattern, module]) => ({ pattern, module }))
  : []
if (configured.length === 0) failures.push('could not read PRELOADED_ROUTES from vite.config.ts')

// The inline script ends with `})(<table>,location.pathname)`.
const inlineScripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].filter(([, body]) => body.includes('location.pathname'))
let table = []
if (inlineScripts.length !== 1) {
  failures.push(`expected one inline route-preload script, found ${inlineScripts.length}`)
} else {
  const tableMatch = inlineScripts[0][1].match(/\}\)\((\[[\s\S]*\]),location\.pathname\)$/)
  if (!tableMatch) failures.push('the route-preload script does not end with its route table')
  else table = JSON.parse(tableMatch[1])
  const firstStylesheet = html.search(/<link\b[^>]*\brel=["']?stylesheet\b/i)
  if (firstStylesheet !== -1 && inlineScripts[0].index > firstStylesheet) {
    failures.push('the route-preload script comes after a stylesheet, so it waits for every stylesheet to load')
  }
}

const tablePatterns = table.map(([pattern]) => pattern)
const configuredPatterns = configured.map(({ pattern }) => pattern)
if (JSON.stringify(tablePatterns) !== JSON.stringify(configuredPatterns)) {
  failures.push(`route table patterns ${JSON.stringify(tablePatterns)} differ from PRELOADED_ROUTES ${JSON.stringify(configuredPatterns)}`)
}

// Files index.html already loads: the entry script, its modulepreloads and its stylesheets.
const entryLoaded = new Set(
  [...html.matchAll(/<(?:script|link)\b[^>]*\b(?:src|href)="\/(assets\/[^"]+)"/g)].map(([, file]) => file),
)

// Vite's preload helper deps: `__vite__mapDeps` holds every dep file once (m.f=[...]) and each
// wrapped dynamic import passes the indices of the files it needs.
const assets = join(dist, 'assets')
const jsFiles = readdirSync(assets).filter((name) => name.endsWith('.js'))
const viteDeps = new Map()
for (const name of jsFiles) {
  const js = readFileSync(join(assets, name), 'utf8')
  const fileList = js.match(/__vite__mapDeps=\([^)]*m\.f=(\[[^\]]*\])/)
  if (!fileList) continue
  const files = JSON.parse(fileList[1])
  for (const call of js.matchAll(/import\([`'"]\.\/([^`'"]+\.js)[`'"]\)[\s\S]{0,200}?__vite__mapDeps\(\[([\d,]*)\]\)/g)) {
    const deps = call[2] ? call[2].split(',').map((index) => files[Number(index)]) : []
    const previous = viteDeps.get(`assets/${call[1]}`)
    const current = JSON.stringify([...new Set(deps)].sort())
    if (previous && previous !== current) failures.push(`Vite lists two different dep sets for assets/${call[1]}`)
    viteDeps.set(`assets/${call[1]}`, current)
  }
}

for (const [pattern, files] of table) {
  const label = `route ${pattern}`
  if (!Array.isArray(files) || files.length === 0) {
    failures.push(`${label}: no files to preload`)
    continue
  }
  const relative = files.map((file) => file.replace(/^\//, ''))
  for (const file of relative) {
    if (!existsSync(join(dist, file))) failures.push(`${label}: ${file} is not in dist`)
    if (entryLoaded.has(file)) failures.push(`${label}: ${file} is already loaded by index.html`)
  }
  if (new Set(relative).size !== relative.length) failures.push(`${label}: lists a file twice`)
  const routeChunk = relative[0]
  if (!routeChunk.endsWith('.js')) {
    failures.push(`${label}: the first file ${routeChunk} is not the route chunk`)
    continue
  }
  const expected = viteDeps.get(routeChunk)
  if (!expected) {
    failures.push(`${label}: no __vite__mapDeps call imports ${routeChunk}; recheck the preload table against Vite's preload helper`)
    continue
  }
  const wanted = JSON.parse(expected).filter((file) => !entryLoaded.has(file))
  if (!wanted.includes(routeChunk)) wanted.push(routeChunk)
  const missing = wanted.filter((file) => !relative.includes(file))
  const extra = relative.filter((file) => !wanted.includes(file))
  if (missing.length > 0) failures.push(`${label}: Vite preloads ${missing.join(', ')} but the table does not`)
  if (extra.length > 0) failures.push(`${label}: the table preloads ${extra.join(', ')} that Vite does not`)
}

const apiBaseUrl = process.env.VITE_API_BASE_URL
if (apiBaseUrl && /^https?:\/\//.test(apiBaseUrl)) {
  const origin = new URL(apiBaseUrl).origin
  if (!html.includes(`<link rel="preconnect" href="${origin}" crossorigin>`)) {
    failures.push(`no anonymous preconnect to the API origin ${origin}`)
  }
}

if (failures.length > 0) {
  console.error('Built index.html does not match vite.config.ts:')
  for (const failure of failures) console.error(`  ${failure}`)
  process.exit(1)
}
console.log(`Built HTML: ${table.length} preloaded routes match Vite's preload deps${apiBaseUrl ? ', API preconnect present' : ''}.`)
