import {parseStatusSnapshot, type StatusSnapshotV1} from './contract'

export const CACHE_KEY = 'i2g-status.snapshot.v1'
export const CACHE_MAX_AGE_MS = 24 * 60 * 60 * 1_000

interface StoredSnapshot {
  savedAt: number
  snapshot: StatusSnapshotV1
}

export function loadCachedSnapshot(
  storage: Pick<Storage, 'getItem' | 'removeItem'> = globalThis.localStorage,
  now = Date.now(),
): StatusSnapshotV1 | null {
  try {
    const raw = storage.getItem(CACHE_KEY)
    if (raw === null) return null
    const parsed: unknown = JSON.parse(raw)
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) throw new Error('invalid cache')
    const candidate = parsed as Record<string, unknown>
    if (
      typeof candidate.savedAt !== 'number' ||
      !Number.isFinite(candidate.savedAt) ||
      candidate.savedAt > now + 5 * 60 * 1_000 ||
      now - candidate.savedAt > CACHE_MAX_AGE_MS
    ) {
      throw new Error('expired cache')
    }
    return parseStatusSnapshot(candidate.snapshot)
  } catch {
    try {
      storage.removeItem(CACHE_KEY)
    } catch {
      // Storage can be unavailable in privacy modes. Treat it as an empty cache.
    }
    return null
  }
}

export function saveCachedSnapshot(
  snapshot: StatusSnapshotV1,
  storage: Pick<Storage, 'getItem' | 'setItem'> = globalThis.localStorage,
  now = Date.now(),
): void {
  try {
    const existing = storage.getItem(CACHE_KEY)
    if (existing !== null) {
      const parsed = JSON.parse(existing) as Partial<StoredSnapshot>
      if (parsed.snapshot && Date.parse(parsed.snapshot.generatedAt) > Date.parse(snapshot.generatedAt)) return
    }
    const value: StoredSnapshot = {savedAt: now, snapshot}
    storage.setItem(CACHE_KEY, JSON.stringify(value))
  } catch {
    // A valid live response must remain usable even when local storage is blocked.
  }
}
