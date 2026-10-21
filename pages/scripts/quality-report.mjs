#!/usr/bin/env node
// Report advisory size/complexity findings (eslint.quality.js). Always exits 0:
// hard limits are enforced by `npm run lint`, this only shows where to look next.
//
//   npm run quality:report            # summary + every finding
//   npm run quality:report -- --json out.json

import { writeFileSync } from 'node:fs'
import { relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { ESLint } from 'eslint'

import { QUALITY_RULES, qualityConfigs } from '../eslint.quality.js'

const pagesDir = resolve(fileURLToPath(import.meta.url), '../..')
const jsonIndex = process.argv.indexOf('--json')
const jsonPath = jsonIndex === -1 ? null : process.argv[jsonIndex + 1]

const eslint = new ESLint({
  cwd: pagesDir,
  overrideConfig: qualityConfigs('advisory'),
  ruleFilter: ({ ruleId }) => QUALITY_RULES.includes(ruleId),
})

const results = await eslint.lintFiles(['src', 'e2e', '*.config.ts'])
const findings = results.flatMap((result) =>
  result.messages
    .filter((message) => QUALITY_RULES.includes(message.ruleId))
    .map((message) => ({
      rule: message.ruleId,
      path: relative(pagesDir, result.filePath),
      line: message.line,
      test: /(^|\/)(__tests__|e2e)\//.test(relative(pagesDir, result.filePath)),
      message: message.message,
      hard: message.severity === 2,
    })),
)

for (const finding of findings) {
  console.log(`${finding.rule.padEnd(24)} ${finding.path}:${finding.line}  ${finding.message}`)
}

for (const [label, subset] of [
  ['TypeScript application code', findings.filter((finding) => !finding.test)],
  ['TypeScript tests', findings.filter((finding) => finding.test)],
]) {
  console.log(`\n${label} (advisory findings):`)
  for (const rule of QUALITY_RULES) {
    console.log(`  ${rule.padEnd(24)} ${subset.filter((finding) => finding.rule === rule).length}`)
  }
}

if (jsonPath) writeFileSync(jsonPath, `${JSON.stringify(findings, null, 2)}\n`)
