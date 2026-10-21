// Size and complexity limits for pages/src (policy: docs/architecture/code-quality.md).
//
// Each limit is a pair: `advisory` values are only reported by
// `npm run quality:report`; `hard` values are ESLint errors in `npm run lint`.
// Keeping the advisory level out of the lint config means `--max-warnings=0`
// never turns a report-only finding into a blocking one.
//
// Line counts skip blank and comment-only lines. `max-lines-per-function`
// counts a function's whole body, nested callbacks included, so component and
// hook bodies get a larger allowance than plain functions.

const lines = (max) => ({ max, skipBlankLines: true, skipComments: true })

// Profiles apply in order; a later matching profile overrides an earlier one.
export const QUALITY_PROFILES = [
  {
    name: 'ordinary',
    files: ['src/**/*.{ts,tsx}', '*.config.ts', 'e2e/**/*.ts'],
    limits: {
      'max-lines': { advisory: 300, hard: 500, option: lines },
      'max-lines-per-function': { advisory: 50, hard: 100, option: lines },
      complexity: { advisory: 10, hard: 15 },
      'max-depth': { advisory: 3, hard: 4 },
    },
  },
  {
    // Custom hooks orchestrate several callbacks inside one function body.
    name: 'hook',
    files: ['src/**/use*.ts', 'src/**/use*.tsx'],
    limits: {
      'max-lines-per-function': { advisory: 100, hard: 200, option: lines },
    },
  },
  {
    // React components: JSX markup is declarative and each conditional render
    // (`cond && <X/>`, ternary, `?.`) counts toward complexity.
    name: 'component',
    files: ['src/**/*.tsx'],
    limits: {
      'max-lines-per-function': { advisory: 100, hard: 200, option: lines },
      complexity: { advisory: 15, hard: 25 },
    },
  },
  {
    // Tests are flat arrange/act/assert sequences inside describe() callbacks.
    name: 'test',
    files: ['src/__tests__/**', 'src/**/*.test.{ts,tsx}', 'e2e/**'],
    limits: {
      'max-lines': { advisory: 600, hard: 1200, option: lines },
      'max-lines-per-function': null,
      complexity: null,
      'max-depth': { advisory: 4, hard: 6 },
    },
  },
]

export const QUALITY_RULES = ['max-lines', 'max-lines-per-function', 'complexity', 'max-depth']

function ruleEntry(level, limit, severity) {
  if (!limit) return 'off'
  const value = limit[level]
  return [severity, limit.option ? limit.option(value) : value]
}

/** Flat-config objects that apply one threshold level (`advisory` | `hard`). */
export function qualityConfigs(level, severity = level === 'hard' ? 'error' : 'warn') {
  return QUALITY_PROFILES.map(({ name, files, limits }) => ({
    name: `quality/${name}/${level}`,
    files,
    rules: Object.fromEntries(
      Object.entries(limits).map(([rule, limit]) => [rule, ruleEntry(level, limit, severity)]),
    ),
  }))
}
