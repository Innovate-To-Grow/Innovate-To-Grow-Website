import {beforeEach, describe, expect, it} from 'vitest'

import {CACHE_KEY, CACHE_MAX_AGE_MS, loadCachedSnapshot, saveCachedSnapshot} from './storage'
import {makeSnapshot, MemoryStorage} from './test/fixture'

describe('last-known snapshot cache', () => {
  let storage: MemoryStorage

  beforeEach(() => {
    storage = new MemoryStorage()
  })

  it('round-trips a validated snapshot', () => {
    const snapshot = makeSnapshot()
    saveCachedSnapshot(snapshot, storage, 1_000)
    expect(loadCachedSnapshot(storage, 1_500)).toEqual(snapshot)
  })

  it('removes expired and invalid cached data', () => {
    const removeCalls: string[] = []
    const expiredStorage = {
      getItem: () => JSON.stringify({savedAt: 1, snapshot: makeSnapshot()}),
      removeItem: (key: string) => removeCalls.push(key),
    }
    expect(loadCachedSnapshot(expiredStorage, CACHE_MAX_AGE_MS + 2)).toBeNull()
    expect(removeCalls).toEqual([CACHE_KEY])

    storage.setItem(CACHE_KEY, '{bad json')
    expect(loadCachedSnapshot(storage, 100)).toBeNull()
    expect(storage.getItem(CACHE_KEY)).toBeNull()
  })

  it('does not replace a newer verified snapshot with an older response', () => {
    const newer = makeSnapshot({generatedAt: '2026-08-20T12:05:00Z'})
    const older = makeSnapshot({generatedAt: '2026-08-20T12:00:00Z'})
    saveCachedSnapshot(newer, storage, 1_000)
    saveCachedSnapshot(older, storage, 2_000)
    expect(loadCachedSnapshot(storage, 3_000)?.generatedAt).toBe(newer.generatedAt)
  })

  it('continues safely when storage access throws', () => {
    const blockedStorage = {
      getItem: () => {
        throw new Error('blocked')
      },
      removeItem: () => {
        throw new Error('blocked')
      },
    }
    expect(loadCachedSnapshot(blockedStorage)).toBeNull()
  })
})
