#!/usr/bin/env node
// Enforce dependency directions between pages/src layers, forbid new import
// cycles, and keep directories small (policy: docs/architecture/code-quality.md).
//
// Layers, lowest first. A module may import its own layer and anything below
// it, never upward:
//
//   types, assets  <  lib  <  hooks, components  <  features  <  routes  <  app, main.tsx
//
// A feature imports another feature only through that feature's public entry
// points: `features/<name>/index.ts` or its data layer `features/<name>/api/**`.
// `routes/` and `app/` are composition layers: they may deep-import feature
// modules (that is how lazy routes keep their own chunks — a barrel import
// would pull every component and its CSS into the route chunk).
//
// Cycles are computed over static value imports (`import type` and dynamic
// `import()` are excluded because they do not run at module-evaluation time).
// Known cycles are listed in KNOWN_CYCLES; new ones and stale entries fail.
//
// Directory size: `.ts`/`.tsx` files directly inside one directory of src/ or
// e2e/ (tests included), `index.ts` excluded. Above DIRECTORY_ADVISORY it is reported; above
// DIRECTORY_HARD it fails unless the directory is in DIRECTORY_EXCEPTIONS with
// a reason.

import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import ts from 'typescript'

const pagesDir = resolve(fileURLToPath(import.meta.url), '../..')
const srcDir = join(pagesDir, 'src')
const EXTENSIONS = ['.ts', '.tsx', '/index.ts', '/index.tsx']

const LAYER_RANK = { types: 0, assets: 0, lib: 1, hooks: 2, components: 2, features: 3, routes: 4, app: 5 }

// Each entry: sorted module paths (relative to src/) and why it is tolerated.
const KNOWN_CYCLES = []

const DIRECTORY_ADVISORY = 15
const DIRECTORY_HARD = 25
// Directory (relative to pages/) -> why it may hold more than DIRECTORY_HARD files.
const DIRECTORY_EXCEPTIONS = {}

function listSources(dir) {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name)
    if (name === '__tests__') return []
    if (statSync(full).isDirectory()) return listSources(full)
    return /\.(ts|tsx)$/.test(name) && !/\.test\.tsx?$/.test(name) ? [full] : []
  })
}

function resolveSpecifier(fromFile, specifier) {
  let base
  if (specifier.startsWith('@/')) base = join(srcDir, specifier.slice(2))
  else if (specifier.startsWith('.')) base = resolve(dirname(fromFile), specifier)
  else return null
  if (/\.(ts|tsx)$/.test(base) && existsSync(base)) return base
  for (const extension of EXTENSIONS) {
    if (existsSync(base + extension)) return base + extension
  }
  return null // assets, CSS, JSON
}

function collectImports(file) {
  const source = ts.createSourceFile(file, readFileSync(file, 'utf8'), ts.ScriptTarget.Latest, true)
  const imports = []
  const visit = (node) => {
    if ((ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) && node.moduleSpecifier) {
      const typeOnly = ts.isImportDeclaration(node) ? node.importClause?.isTypeOnly : node.isTypeOnly
      imports.push({ specifier: node.moduleSpecifier.text, runtime: !typeOnly })
    } else if (ts.isCallExpression(node) && node.expression.kind === ts.SyntaxKind.ImportKeyword) {
      const [argument] = node.arguments
      if (argument && ts.isStringLiteral(argument)) imports.push({ specifier: argument.text, runtime: false })
    }
    ts.forEachChild(node, visit)
  }
  visit(source)
  return imports
}

function layerOf(rel) {
  const [top] = rel.split('/')
  if (!rel.includes('/')) return { layer: 'app', rank: LAYER_RANK.app } // main.tsx, index.css
  return { layer: top, rank: LAYER_RANK[top] ?? LAYER_RANK.app }
}

function featureOf(rel) {
  const parts = rel.split('/')
  return parts[0] === 'features' ? parts[1] : null
}

function isFeatureEntry(rel) {
  return /^features\/[^/]+\/(index\.tsx?|api\/.+)$/.test(rel)
}

export function boundaryError(fromRel, toRel) {
  const from = layerOf(fromRel)
  const to = layerOf(toRel)
  if (to.rank > from.rank) return `${from.layer}/ must not import ${to.layer}/`
  const fromFeature = featureOf(fromRel)
  const toFeature = featureOf(toRel)
  if (toFeature && fromFeature && toFeature !== fromFeature && !isFeatureEntry(toRel)) {
    return `import features/${toFeature} through its index.ts or api/, not ${toRel}`
  }
  return null
}

function stronglyConnected(graph) {
  let counter = 0
  const index = new Map()
  const low = new Map()
  const stack = []
  const onStack = new Set()
  const components = []
  const connect = (node) => {
    index.set(node, counter)
    low.set(node, counter)
    counter += 1
    stack.push(node)
    onStack.add(node)
    for (const next of graph.get(node) ?? []) {
      if (!index.has(next)) {
        connect(next)
        low.set(node, Math.min(low.get(node), low.get(next)))
      } else if (onStack.has(next)) {
        low.set(node, Math.min(low.get(node), index.get(next)))
      }
    }
    if (low.get(node) === index.get(node)) {
      const component = []
      let member
      do {
        member = stack.pop()
        onStack.delete(member)
        component.push(member)
      } while (member !== node)
      if (component.length > 1) components.push(component.sort())
    }
  }
  for (const node of [...graph.keys()].sort()) if (!index.has(node)) connect(node)
  return components
}

function listAllTypeScript(dir) {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) return listAllTypeScript(full)
    return /\.(ts|tsx)$/.test(name) ? [full] : []
  })
}

/** Direct `.ts`/`.tsx` files per directory of src/ and e2e/ (tests included), keyed relative to pages/. */
function directorySizes() {
  const counts = new Map()
  for (const file of [...listAllTypeScript(srcDir), ...listAllTypeScript(join(pagesDir, 'e2e'))]) {
    const rel = relative(pagesDir, file)
    if (/(^|\/)index\.tsx?$/.test(rel)) continue
    const dir = dirname(rel)
    counts.set(dir, (counts.get(dir) ?? 0) + 1)
  }
  return counts
}

function main() {
  const errors = []
  const sources = listSources(srcDir)
  const sizes = directorySizes()
  for (const [dir, count] of [...sizes].sort()) {
    if (count > DIRECTORY_HARD && !DIRECTORY_EXCEPTIONS[dir]) {
      errors.push(`directory: ${dir} holds ${count} TypeScript files (limit ${DIRECTORY_HARD}); split it by responsibility`)
    } else if (count > DIRECTORY_ADVISORY) {
      console.log(`advisory: ${dir} holds ${count} TypeScript files (advisory limit ${DIRECTORY_ADVISORY})`)
    }
  }
  for (const dir of Object.keys(DIRECTORY_EXCEPTIONS)) {
    if ((sizes.get(dir) ?? 0) <= DIRECTORY_HARD) errors.push(`stale DIRECTORY_EXCEPTIONS entry: ${dir}`)
  }
  const graph = new Map()
  let edgeCount = 0
  for (const file of sources) {
    const fromRel = relative(srcDir, file)
    graph.set(fromRel, graph.get(fromRel) ?? new Set())
    for (const { specifier, runtime } of collectImports(file)) {
      const target = resolveSpecifier(file, specifier)
      if (!target) continue
      const toRel = relative(srcDir, target)
      edgeCount += 1
      const error = boundaryError(fromRel, toRel)
      if (error) errors.push(`boundary: ${fromRel} imports ${toRel}: ${error}`)
      if (runtime && toRel !== fromRel) graph.get(fromRel).add(toRel)
    }
  }

  const known = new Set(KNOWN_CYCLES.map((entry) => entry.modules.join(' ')))
  const found = new Set(stronglyConnected(graph).map((component) => component.join(' ')))
  for (const cycle of found) if (!known.has(cycle)) errors.push(`new import cycle: ${cycle.split(' ').join(' -> ')}`)
  for (const cycle of known) if (!found.has(cycle)) errors.push(`stale KNOWN_CYCLES entry: ${cycle}`)

  console.log(`Frontend imports: ${graph.size} modules, ${edgeCount} internal imports, ${found.size} import cycles`)
  for (const error of errors) console.log(`ERROR: ${error}`)
  process.exitCode = errors.length ? 1 : 0
}

if (process.argv[1] === fileURLToPath(import.meta.url)) main()
