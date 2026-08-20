import {fetchStatusSnapshot, isSnapshotStale} from './api'
import type {StatusSnapshotV1} from './contract'
import {renderError, renderSnapshot, type SnapshotSource} from './render'
import {loadCachedSnapshot, saveCachedSnapshot} from './storage'

export const POLL_INTERVAL_MS = 60_000

export interface StatusAppOptions {
  fetchSnapshot?: () => Promise<StatusSnapshotV1>
  storage?: Storage
  now?: () => number
  pollIntervalMs?: number
}

export class StatusApp {
  private readonly fetchSnapshot: () => Promise<StatusSnapshotV1>
  private readonly storage: Storage
  private readonly now: () => number
  private readonly pollIntervalMs: number
  private pollTimer: number | null = null
  private refreshPromise: Promise<void> | null = null
  private started = false

  constructor(
    private readonly root: HTMLElement,
    private readonly announcer: HTMLElement,
    options: StatusAppOptions = {},
  ) {
    this.fetchSnapshot = options.fetchSnapshot ?? (() => fetchStatusSnapshot())
    this.storage = options.storage ?? globalThis.localStorage
    this.now = options.now ?? Date.now
    this.pollIntervalMs = options.pollIntervalMs ?? POLL_INTERVAL_MS
  }

  start(): void {
    if (this.started) return
    this.started = true
    document.addEventListener('visibilitychange', this.onVisibilityChange)
    this.schedulePolling()
    void this.refresh()
  }

  stop(): void {
    if (!this.started) return
    this.started = false
    document.removeEventListener('visibilitychange', this.onVisibilityChange)
    this.clearPolling()
  }

  async refresh(): Promise<void> {
    if (this.refreshPromise !== null) return this.refreshPromise
    const operation = this.performRefresh()
    this.refreshPromise = operation
    try {
      await operation
    } finally {
      if (this.refreshPromise === operation) this.refreshPromise = null
    }
  }

  private readonly onVisibilityChange = (): void => {
    if (document.visibilityState === 'hidden') {
      this.clearPolling()
      return
    }
    this.schedulePolling()
    void this.refresh()
  }

  private schedulePolling(): void {
    this.clearPolling()
    if (!this.started || document.visibilityState === 'hidden') return
    this.pollTimer = globalThis.setInterval(() => void this.refresh(), this.pollIntervalMs)
  }

  private clearPolling(): void {
    if (this.pollTimer === null) return
    globalThis.clearInterval(this.pollTimer)
    this.pollTimer = null
  }

  private async performRefresh(): Promise<void> {
    this.root.setAttribute('aria-busy', 'true')
    const refreshButton = this.root.querySelector<HTMLButtonElement>('[data-refresh]')
    if (refreshButton) refreshButton.disabled = true
    try {
      const snapshot = await this.fetchSnapshot()
      if (isSnapshotStale(snapshot, this.now())) {
        const cached = loadCachedSnapshot(this.storage, this.now())
        const newest =
          cached !== null && Date.parse(cached.generatedAt) > Date.parse(snapshot.generatedAt) ? cached : snapshot
        this.present(newest, 'stale')
        return
      }
      saveCachedSnapshot(snapshot, this.storage, this.now())
      this.present(snapshot, 'live')
    } catch {
      const cached = loadCachedSnapshot(this.storage, this.now())
      if (cached !== null) {
        this.present(cached, 'cache')
      } else {
        renderError(this.root, () => void this.refresh())
        this.announcer.textContent = 'Current status could not be loaded.'
        document.title = 'Status unavailable | Innovate to Grow'
      }
    }
  }

  private present(snapshot: StatusSnapshotV1, source: SnapshotSource): void {
    renderSnapshot(this.root, snapshot, source, () => void this.refresh())
    if (source === 'live') {
      this.announcer.textContent = `Status updated. Overall status: ${snapshot.overallStatus.replaceAll('_', ' ')}.`
      document.title = `${snapshot.overallStatus === 'operational' ? 'All systems operational' : 'Service status update'} | Innovate to Grow`
    } else {
      this.announcer.textContent = 'Live status is delayed. Last verified information is displayed.'
      document.title = 'Status data delayed | Innovate to Grow'
    }
  }
}
