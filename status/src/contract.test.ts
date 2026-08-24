import {describe, expect, it} from 'vitest'

import {parseStatusSnapshot, validateStatusSnapshot} from './contract'
import {makeIncident, makeSnapshot} from './test/fixture'

interface FixtureMutation {
  op: 'add' | 'replace' | 'remove'
  path: string
  value?: unknown
}

interface InvalidFixtureSpec {
  description: string
  base: string
  mutations: FixtureMutation[]
  expectedIssue: string
}

const validFixtureModules = import.meta.glob<unknown>('../contracts/fixtures/valid/*.json', {
  eager: true,
  import: 'default',
})
const invalidFixtureModules = import.meta.glob<unknown>('../contracts/fixtures/invalid/*.json', {
  eager: true,
  import: 'default',
})

function fixtureName(path: string): string {
  return path.split('/').at(-1) ?? path
}

function invalidFixtureSpec(value: unknown, path: string): InvalidFixtureSpec {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new Error(`${path} must be an object`)
  }
  const item = value as Record<string, unknown>
  if (
    typeof item.description !== 'string' ||
    typeof item.base !== 'string' ||
    typeof item.expectedIssue !== 'string' ||
    !Array.isArray(item.mutations)
  ) {
    throw new Error(`${path} has an invalid fixture specification`)
  }
  const mutations = item.mutations.map((mutation, index): FixtureMutation => {
    if (typeof mutation !== 'object' || mutation === null || Array.isArray(mutation)) {
      throw new Error(`${path} mutation ${index} must be an object`)
    }
    const candidate = mutation as Record<string, unknown>
    if (
      (candidate.op !== 'add' && candidate.op !== 'replace' && candidate.op !== 'remove') ||
      typeof candidate.path !== 'string'
    ) {
      throw new Error(`${path} mutation ${index} is invalid`)
    }
    if (candidate.op !== 'remove' && !Object.hasOwn(candidate, 'value')) {
      throw new Error(`${path} mutation ${index} requires a value`)
    }
    return {
      op: candidate.op,
      path: candidate.path,
      ...(Object.hasOwn(candidate, 'value') ? {value: candidate.value} : {}),
    }
  })
  return {
    description: item.description,
    base: item.base,
    mutations,
    expectedIssue: item.expectedIssue,
  }
}

function pointerSegments(pointer: string): string[] {
  if (!pointer.startsWith('/') || pointer === '/') throw new Error(`Unsupported JSON Pointer: ${pointer}`)
  return pointer
    .slice(1)
    .split('/')
    .map((segment) => segment.replaceAll('~1', '/').replaceAll('~0', '~'))
}

function applyMutation(document: unknown, mutation: FixtureMutation): void {
  const segments = pointerSegments(mutation.path)
  const finalSegment = segments.pop()
  if (finalSegment === undefined) throw new Error(`Mutation path has no target: ${mutation.path}`)
  let parent = document
  for (const segment of segments) {
    if (Array.isArray(parent)) {
      parent = parent[Number(segment)]
    } else if (typeof parent === 'object' && parent !== null) {
      parent = (parent as Record<string, unknown>)[segment]
    } else {
      throw new Error(`Mutation path does not exist: ${mutation.path}`)
    }
  }
  if (Array.isArray(parent)) {
    const index = Number(finalSegment)
    if (!Number.isSafeInteger(index) || index < 0 || index >= parent.length) {
      throw new Error(`Mutation array index does not exist: ${mutation.path}`)
    }
    if (mutation.op === 'remove') parent.splice(index, 1)
    else parent[index] = mutation.value
    return
  }
  if (typeof parent !== 'object' || parent === null) {
    throw new Error(`Mutation parent is not an object: ${mutation.path}`)
  }
  if (mutation.op === 'remove') delete (parent as Record<string, unknown>)[finalSegment]
  else (parent as Record<string, unknown>)[finalSegment] = mutation.value
}

const validFixtureCases = Object.entries(validFixtureModules)
  .sort(([left], [right]) => left.localeCompare(right))
  .map(([path, document]) => ({name: fixtureName(path), document}))

const invalidFixtureCases = Object.entries(invalidFixtureModules)
  .sort(([left], [right]) => left.localeCompare(right))
  .map(([path, value]) => {
    const spec = invalidFixtureSpec(value, path)
    const baseName = fixtureName(spec.base)
    const baseEntry = Object.entries(validFixtureModules).find(([validPath]) => fixtureName(validPath) === baseName)
    if (baseEntry === undefined) throw new Error(`${path} references missing base fixture ${spec.base}`)
    const document: unknown = structuredClone(baseEntry[1])
    for (const mutation of spec.mutations) applyMutation(document, mutation)
    return {name: fixtureName(path), document, expectedIssue: spec.expectedIssue}
  })

describe('StatusSnapshotV1 validation', () => {
  it.each(validFixtureCases)('accepts shared valid fixture $name', ({document}) => {
    expect(validateStatusSnapshot(document)).toMatchObject({ok: true})
  })

  it.each(invalidFixtureCases)(
    'rejects shared invalid fixture $name',
    ({document, expectedIssue}) => {
      const result = validateStatusSnapshot(document)
      expect(result.ok).toBe(false)
      if (!result.ok) expect(result.issues.join('; ')).toContain(expectedIssue)
    },
  )

  it('accepts the complete public contract', () => {
    const snapshot = makeSnapshot({incidents: [makeIncident()]})
    expect(validateStatusSnapshot(snapshot)).toEqual({ok: true, value: snapshot})
  })

  it('rejects missing and additional public fields', () => {
    const missing = structuredClone(makeSnapshot()) as unknown as Record<string, unknown>
    delete missing.generatedAt
    expect(validateStatusSnapshot(missing)).toMatchObject({ok: false})

    const additional = {...makeSnapshot(), internalError: 'database host'}
    const result = validateStatusSnapshot(additional)
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.issues[0]).toContain('unexpected property internalError')
  })

  it('requires every fixed component exactly once', () => {
    const snapshot = makeSnapshot()
    snapshot.components[4] = structuredClone(snapshot.components[0]!)
    expect(() => parseStatusSnapshot(snapshot)).toThrow('each public component exactly once')
  })

  it('requires exactly 90 consecutive, valid UTC history dates', () => {
    const short = makeSnapshot()
    short.components[0]!.history.pop()
    expect(() => parseStatusSnapshot(short)).toThrow('exactly 90 days')

    const gap = makeSnapshot()
    gap.components[0]!.history[20]!.date = '2026-02-31'
    expect(() => parseStatusSnapshot(gap)).toThrow('real calendar date')
  })

  it('rejects impossible summary and maintenance counts', () => {
    const summary = makeSnapshot()
    summary.summary.availability24h.availableChecks = 1_500
    expect(() => parseStatusSnapshot(summary)).toThrow('cannot exceed eligibleChecks')

    const history = makeSnapshot()
    history.components[0]!.history[0]!.maintenanceSampleCount = 289
    expect(() => parseStatusSnapshot(history)).toThrow('cannot exceed sampleCount')
  })

  it('requires incident updates to be chronological and match the current state', () => {
    const mismatch = makeSnapshot({incidents: [makeIncident()]})
    mismatch.incidents[0]!.updates[1]!.state = 'resolved'
    expect(() => parseStatusSnapshot(mismatch)).toThrow('last update state')

    const invalidResolution = makeSnapshot({
      incidents: [makeIncident({state: 'resolved', resolvedAt: null})],
    })
    expect(() => parseStatusSnapshot(invalidResolution)).toThrow('required for a resolved incident')
  })
})
