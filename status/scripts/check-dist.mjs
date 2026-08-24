import {readdir, readFile} from 'node:fs/promises'
import {extname, join, relative} from 'node:path'
import {fileURLToPath} from 'node:url'

const root = fileURLToPath(new URL('../dist/', import.meta.url))
const textExtensions = new Set(['.css', '.html', '.js', '.json', '.map', '.svg', '.txt', '.xml'])
const forbidden = [
  {label: 'remote HTTP resource', pattern: /https?:\/\//i},
  {
    label: 'protocol-relative remote resource',
    pattern: /(?:["'`]\s*\/\/[A-Za-z0-9]|\b(?:src|href|xlink:href)\s*=\s*\/\/[A-Za-z0-9]|url\s*\(\s*\/\/[A-Za-z0-9])/i,
  },
  {label: 'CSS import', pattern: /@import\s/i},
  {label: 'main-site layout API', pattern: /\/api\/layout/i},
  {label: 'direct monitored API request', pattern: /(?:api|demo-api|archive)\.i2g\.ucmerced\.edu/i},
]

function normalizeSource(source) {
  return source
    .replaceAll('http://www.w3.org/2000/svg', '')
    .replaceAll('http://www.w3.org/1999/xlink', '')
}

// Keep the production guard honest against the resource forms this release
// explicitly forbids. These assertions execute in every CI and deployment
// build before the generated directory is inspected.
for (const unsafe of [
  '<script src="https://third-party.invalid/app.js"></script>',
  '<link href="https://third-party.invalid/font.css" rel="stylesheet">',
  'fetch("https://third-party.invalid/status")',
  '<svg xmlns="http://www.w3.org/2000/svg"><image href="https://third-party.invalid/image.png"/></svg>',
  '<script src="//third-party.invalid/app.js"></script>',
  '@font-face { src: url(//third-party.invalid/font.woff2); }',
  'fetch("//third-party.invalid/status")',
  'fetch(`//third-party.invalid/status`)',
]) {
  if (!forbidden.some((rule) => rule.pattern.test(normalizeSource(unsafe)))) {
    throw new Error('Status self-containment guard failed its remote-resource regression check.')
  }
}

async function files(directory) {
  const entries = await readdir(directory, {withFileTypes: true})
  const results = []
  for (const entry of entries) {
    const path = join(directory, entry.name)
    if (entry.isDirectory()) results.push(...(await files(path)))
    else results.push(path)
  }
  return results
}

const failures = []
for (const file of await files(root)) {
  if (!textExtensions.has(extname(file))) continue
  // XML namespace identifiers are not network requests and Vite may inline
  // an SVG data URI into HTML. Remove only the two standard namespace values
  // before rejecting every other embedded HTTP(S) URL in every text asset.
  const source = normalizeSource(await readFile(file, 'utf8'))
  for (const rule of forbidden) {
    if (rule.pattern.test(source)) failures.push(`${relative(root, file)}: ${rule.label}`)
  }
}

if (failures.length) {
  throw new Error(`Status build is not self-contained:\n${failures.join('\n')}`)
}

console.log('Status build is self-contained.')
