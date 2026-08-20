import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest'

import {StatusApp} from './app'
import {CACHE_KEY, saveCachedSnapshot} from './storage'
import {makeSnapshot, MemoryStorage} from './test/fixture'

describe('StatusApp lifecycle', () => {
  let root: HTMLElement
  let announcer: HTMLElement
  let storage: MemoryStorage

  beforeEach(() => {
    vi.useFakeTimers()
    storage = new MemoryStorage()
    document.body.replaceChildren()
    root = document.createElement('main')
    announcer = document.createElement('p')
    document.body.append(root, announcer)
    Object.defineProperty(document, 'visibilityState', {configurable: true, value: 'visible'})
  })

  afterEach(() => vi.useRealTimers())

  it('loads live data, saves it, and polls once per interval', async () => {
    const snapshot = makeSnapshot()
    const fetchSnapshot = vi.fn().mockResolvedValue(snapshot)
    const app = new StatusApp(root, announcer, {
      fetchSnapshot,
      storage,
      now: () => Date.parse(snapshot.generatedAt),
      pollIntervalMs: 60_000,
    })
    app.start()
    await vi.waitFor(() => expect(fetchSnapshot).toHaveBeenCalledTimes(1))
    expect(root.textContent).toContain('All systems operational')
    expect(storage.getItem(CACHE_KEY)).not.toBeNull()

    await vi.advanceTimersByTimeAsync(60_000)
    expect(fetchSnapshot).toHaveBeenCalledTimes(2)
    app.stop()
  })

  it('pauses polling while hidden and refreshes immediately when visible', async () => {
    const snapshot = makeSnapshot()
    const fetchSnapshot = vi.fn().mockResolvedValue(snapshot)
    const app = new StatusApp(root, announcer, {
      fetchSnapshot,
      storage,
      now: () => Date.parse(snapshot.generatedAt),
      pollIntervalMs: 100,
    })
    app.start()
    await vi.waitFor(() => expect(fetchSnapshot).toHaveBeenCalledTimes(1))

    Object.defineProperty(document, 'visibilityState', {configurable: true, value: 'hidden'})
    document.dispatchEvent(new Event('visibilitychange'))
    await vi.advanceTimersByTimeAsync(300)
    expect(fetchSnapshot).toHaveBeenCalledTimes(1)

    Object.defineProperty(document, 'visibilityState', {configurable: true, value: 'visible'})
    document.dispatchEvent(new Event('visibilitychange'))
    await vi.waitFor(() => expect(fetchSnapshot).toHaveBeenCalledTimes(2))
    app.stop()
  })

  it('shows a cached snapshot as last known after a request failure', async () => {
    const snapshot = makeSnapshot()
    const now = Date.parse(snapshot.generatedAt)
    saveCachedSnapshot(snapshot, storage, now)
    const app = new StatusApp(root, announcer, {
      fetchSnapshot: vi.fn().mockRejectedValue(new Error('offline')),
      storage,
      now: () => now + 1_000,
    })
    await app.refresh()
    expect(root.textContent).toContain('Status data is delayed')
    expect(root.textContent).toContain('Last known status')
    expect(document.title).toContain('delayed')
  })

  it('does not start overlapping requests', async () => {
    let resolveRequest: ((value: ReturnType<typeof makeSnapshot>) => void) | undefined
    const fetchSnapshot = vi.fn(
      () =>
        new Promise<ReturnType<typeof makeSnapshot>>((resolve) => {
          resolveRequest = resolve
        }),
    )
    const snapshot = makeSnapshot()
    const app = new StatusApp(root, announcer, {
      fetchSnapshot,
      storage,
      now: () => Date.parse(snapshot.generatedAt),
    })
    const first = app.refresh()
    const second = app.refresh()
    expect(fetchSnapshot).toHaveBeenCalledOnce()
    resolveRequest?.(snapshot)
    await Promise.all([first, second])
    expect(fetchSnapshot).toHaveBeenCalledOnce()
  })

  it('renders an honest unavailable state without a usable cache', async () => {
    const app = new StatusApp(root, announcer, {
      fetchSnapshot: vi.fn().mockRejectedValue(new Error('offline')),
      storage,
    })
    await app.refresh()
    expect(root.textContent).toContain('Current status could not be loaded')
    expect(root.textContent).not.toContain('All systems operational')
  })
})
