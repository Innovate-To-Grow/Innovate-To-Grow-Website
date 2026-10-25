#!/usr/bin/env node
// Fail when the built CSS uses media-query range syntax such as `(width<=768px)`.
//
// Safari before 16.4 and Chrome before 104 ignore an @media rule written that way, so every
// phone and tablet rule inside it is lost there. The minifier only writes it when the build
// target allows it: vite.config.ts sets build.cssTarget to the first browsers with cascade
// layers, which keeps `(max-width: 768px)`. This check catches a target change or a Vite
// upgrade that undoes it. Run it after `npm run build`.

import { readdirSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const assets = join(dirname(fileURLToPath(import.meta.url)), '..', 'dist', 'assets')
// A feature compared with <, >, <= or >= on either side: (width<=768px), (768px>=width), (400px<width<=700px).
const RANGE = /\(\s*(?:[\d.]+[a-z%]*\s*[<>]=?\s*)?(?:min-|max-)?(?:width|height|aspect-ratio|resolution)\s*[<>]=?|\(\s*[\d.]+[a-z%]*\s*[<>]=?\s*(?:width|height|aspect-ratio|resolution)/i

let files
try {
  files = readdirSync(assets).filter((name) => name.endsWith('.css'))
} catch {
  console.error(`No build output at ${assets}: run npm run build first.`)
  process.exit(1)
}

const failures = []
for (const name of files) {
  const css = readFileSync(join(assets, name), 'utf8')
  for (const match of css.matchAll(/@media([^{]*)\{/g)) {
    if (RANGE.test(match[1])) failures.push(`${name}: @media${match[1].trim()}`)
  }
}

if (failures.length > 0) {
  console.error('Media queries in range syntax (ignored by Safari < 16.4 and Chrome < 104):')
  for (const failure of failures) console.error(`  ${failure}`)
  process.exit(1)
}
console.log(`Built CSS: ${files.length} files, no range-syntax media queries.`)
