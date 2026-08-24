import {afterEach, describe, expect, it, vi} from 'vitest'

import {fetchStatusSnapshot, isSnapshotStale, StatusRequestError} from './api'
import {makeSnapshot} from './test/fixture'

afterEach(() => {
  vi.useRealTimers()
})

describe('status API client', () => {
  it('fetches and validates the same-origin public endpoint', async () => {
    const snapshot = makeSnapshot()
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify(snapshot), {status: 200, headers: {'Content-Type': 'application/json'}}),
    )

    await expect(fetchStatusSnapshot(fetcher)).resolves.toEqual(snapshot)
    expect(fetcher).toHaveBeenCalledWith(
      '/api/status',
      expect.objectContaining({credentials: 'omit', redirect: 'error', referrerPolicy: 'no-referrer'}),
    )
  })

  it('does not expose response bodies when the service fails', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response('sensitive upstream detail', {status: 503}))
    const request = fetchStatusSnapshot(fetcher)
    await expect(request).rejects.toBeInstanceOf(StatusRequestError)
    await expect(request).rejects.not.toThrow('sensitive upstream detail')
  })

  it('rejects unsupported successful responses', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({...makeSnapshot(), schemaVersion: 2}), {status: 200}),
    )
    await expect(fetchStatusSnapshot(fetcher)).rejects.toThrow('unsupported response')
  })

  it('aborts a request at the configured timeout', async () => {
    vi.useFakeTimers()
    const fetcher = vi.fn<typeof fetch>().mockImplementation((_input, init) =>
      new Promise((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
      }),
    )
    const request = expect(fetchStatusSnapshot(fetcher, 50)).rejects.toThrow('timed out')
    await vi.advanceTimersByTimeAsync(51)
    await request
  })

  it('treats explicit, old, and implausibly future snapshots as stale', () => {
    const now = Date.parse('2026-08-20T12:00:00Z')
    expect(isSnapshotStale(makeSnapshot(), now)).toBe(false)
    expect(isSnapshotStale(makeSnapshot({stale: true}), now)).toBe(true)
    expect(isSnapshotStale(makeSnapshot({generatedAt: '2026-08-20T11:49:59Z'}), now)).toBe(true)
    expect(isSnapshotStale(makeSnapshot({generatedAt: '2026-08-20T12:05:01Z'}), now)).toBe(true)
  })
})
