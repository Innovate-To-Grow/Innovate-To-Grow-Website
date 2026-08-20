import {parseStatusSnapshot, type StatusSnapshotV1} from './contract'

export const STATUS_ENDPOINT = '/api/status'
export const REQUEST_TIMEOUT_MS = 5_000
export const STALE_AFTER_MS = 10 * 60 * 1_000

export class StatusRequestError extends Error {
  constructor(message: string, readonly status: number | null = null) {
    super(message)
    this.name = 'StatusRequestError'
  }
}

export async function fetchStatusSnapshot(
  fetcher: typeof fetch = globalThis.fetch,
  timeoutMs = REQUEST_TIMEOUT_MS,
): Promise<StatusSnapshotV1> {
  const controller = new AbortController()
  const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetcher(STATUS_ENDPOINT, {
      method: 'GET',
      headers: {Accept: 'application/json'},
      credentials: 'omit',
      redirect: 'error',
      referrerPolicy: 'no-referrer',
      signal: controller.signal,
    })
    if (!response.ok) throw new StatusRequestError('Status service is temporarily unavailable.', response.status)
    let payload: unknown
    try {
      payload = await response.json()
    } catch {
      throw new StatusRequestError('Status service returned an unreadable response.', response.status)
    }
    try {
      return parseStatusSnapshot(payload)
    } catch {
      throw new StatusRequestError('Status service returned an unsupported response.', response.status)
    }
  } catch (error) {
    if (error instanceof StatusRequestError) throw error
    if (controller.signal.aborted) throw new StatusRequestError('Status request timed out.')
    throw new StatusRequestError('Could not connect to the status service.')
  } finally {
    globalThis.clearTimeout(timeout)
  }
}

export function isSnapshotStale(snapshot: StatusSnapshotV1, now = Date.now()): boolean {
  const generatedAt = Date.parse(snapshot.generatedAt)
  const age = now - generatedAt
  return snapshot.stale || !Number.isFinite(generatedAt) || age > STALE_AFTER_MS || age < -5 * 60 * 1_000
}
