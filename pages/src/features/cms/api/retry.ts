import { api } from '@/lib/api';
import {rateLimitRetryDelay} from '@/lib/api/rateLimit';
import type {AxiosRequestConfig} from 'axios';

const RETRYABLE_GET_STATUSES = new Set([408, 429, 502, 503, 504]);
/** The cap on a 408/5xx retry's wait. A 429 waits as long as the server asks, up to the shared client's limit. */
const MAX_RETRY_DELAY_MS = 2000;

/** Retry-After (seconds or an HTTP date) in milliseconds, capped; null when absent or unusable. */
function retryAfterDelay(retryAfter: string | undefined): number | null {
  if (!retryAfter) return null;
  const seconds = Number(retryAfter);
  if (Number.isFinite(seconds) && seconds >= 0) {
    return Math.min(seconds * 1000, MAX_RETRY_DELAY_MS);
  }
  const dateDelay = Date.parse(retryAfter) - Date.now();
  if (Number.isFinite(dateDelay) && dateDelay >= 0) {
    return Math.min(dateDelay, MAX_RETRY_DELAY_MS);
  }
  return null;
}

function retryDelay(error: unknown): number | null {
  const candidate = error as {
    code?: string;
    response?: {status?: number; headers?: Record<string, string | undefined>};
  };
  if (candidate.code === 'ERR_CANCELED') return null;
  const status = candidate.response?.status;
  if (status !== undefined && !RETRYABLE_GET_STATUSES.has(status)) return null;
  // Retrying a 429 before its Retry-After only earns another 429. The shared client has normally spent the one
  // retry already (null then), and a wait longer than it allows fails the page at once rather than early.
  if (status === 429) return rateLimitRetryDelay(error);

  const requested = retryAfterDelay(candidate.response?.headers?.['retry-after']);
  return requested ?? 150 + Math.floor(Math.random() * 151);
}

export async function getWithOneRetry<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
  try {
    return (await api.get<T>(url, config)).data;
  } catch (error) {
    const delay = retryDelay(error);
    if (delay === null || config?.signal?.aborted) throw error;
    await new Promise<void>((resolve, reject) => {
      const timeout = window.setTimeout(resolve, delay);
      config?.signal?.addEventListener?.('abort', () => {
        window.clearTimeout(timeout);
        reject(new DOMException('The request was aborted.', 'AbortError'));
      }, {once: true});
    });
    return (await api.get<T>(url, config)).data;
  }
}
