// What the browser does when the API answers 429 Too Many Requests: an idempotent read (GET/HEAD/OPTIONS) waits as
// long as the server asks (Retry-After, or the body's `retry_after`), plus a little jitter so many tabs refused at
// once do not all come back in the same instant, then retries once. A wait longer than RATE_LIMIT_MAX_WAIT_MS is not
// worth holding the screen for: the request fails at once instead. Any 429 that is finally passed on carries a
// message a visitor can read in place of axios' "Request failed with status code 429".
import type {AxiosError, AxiosInstance, InternalAxiosRequestConfig} from 'axios';

declare module 'axios' {
  // The type parameter must match axios' own declaration to merge.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any, @typescript-eslint/no-unused-vars
  interface AxiosRequestConfig<D = any> {
    /** Set false to pass a 429 straight to the caller (its own retry or polling loop handles it). */
    rateLimitRetry?: boolean;
  }
}

/** The longest Retry-After a read waits for before its one retry; a longer one fails the request at once. */
export const RATE_LIMIT_MAX_WAIT_MS = 10_000;
/** The wait before the retry when a 429 names none (an older proxy, or a header the browser cannot read). */
export const RATE_LIMIT_FALLBACK_WAIT_MS = 1_000;
/** Jitter added to the wait: a fifth of it, at least this much, at most RATE_LIMIT_MAX_JITTER_MS. */
const RATE_LIMIT_MIN_JITTER_MS = 250;
const RATE_LIMIT_MAX_JITTER_MS = 2_000;
const IDEMPOTENT_METHODS = new Set(['get', 'head', 'options']);
const RETRIED_MARKER = '_i2gRateLimitRetried';

type MarkedConfig = InternalAxiosRequestConfig & {[RETRIED_MARKER]?: boolean};

interface ErrorShape {
  config?: MarkedConfig;
  response?: {status?: unknown; headers?: unknown; data?: unknown};
}

const shape = (error: unknown): ErrorShape =>
  error && typeof error === 'object' ? (error as ErrorShape) : {};

/** True when `error` is an HTTP 429 answer. */
export const isRateLimited = (error: unknown): boolean => shape(error).response?.status === 429;

/** True when the shared client already spent its one rate-limit retry on this request. */
export const wasRateLimitRetried = (error: unknown): boolean => Boolean(shape(error).config?.[RETRIED_MARKER]);

const headerValue = (headers: unknown): string | undefined => {
  if (!headers || typeof headers !== 'object') return undefined;
  const getter = (headers as {get?: unknown}).get;
  const value = typeof getter === 'function'
    ? (getter as (name: string) => unknown).call(headers, 'retry-after')
    : (headers as Record<string, unknown>)['retry-after'] ?? (headers as Record<string, unknown>)['Retry-After'];
  if (typeof value === 'number') return String(value);
  return typeof value === 'string' ? value : undefined;
};

/** A Retry-After value (delta-seconds or an HTTP date) in milliseconds; null when absent, unusable or past. */
export const parseRetryAfter = (value: string | undefined, now: number = Date.now()): number | null => {
  const text = value?.trim();
  if (!text) return null;
  if (/^\d+(\.\d+)?$/.test(text)) return Number(text) * 1000;
  const delay = Date.parse(text) - now;
  return Number.isFinite(delay) && delay >= 0 ? delay : null;
};

/** How long the server asked a refused request to wait, in milliseconds: the header, else the body; null if neither. */
export const retryAfterMs = (error: unknown): number | null => {
  const response = shape(error).response;
  const fromHeader = parseRetryAfter(headerValue(response?.headers));
  if (fromHeader !== null) return fromHeader;
  const body = response?.data;
  const seconds = body && typeof body === 'object' ? (body as {retry_after?: unknown}).retry_after : undefined;
  return typeof seconds === 'number' && Number.isFinite(seconds) && seconds >= 0 ? seconds * 1000 : null;
};

/** The visitor-facing text for a 429. */
export const rateLimitMessage = (error: unknown): string => {
  const wait = retryAfterMs(error);
  if (wait === null) return 'The site is busy right now. Please try again in a moment.';
  const seconds = Math.max(1, Math.ceil(wait / 1000));
  return `The site is busy right now. Please try again in ${seconds} ${seconds === 1 ? 'second' : 'seconds'}.`;
};

/**
 * The wait before a 429'd request's one retry, jitter included; null when it must not be retried: it already was,
 * or the server asks for longer than RATE_LIMIT_MAX_WAIT_MS.
 */
export const rateLimitRetryDelay = (error: unknown, random: () => number = Math.random): number | null => {
  if (!isRateLimited(error) || wasRateLimitRetried(error)) return null;
  const wait = retryAfterMs(error) ?? RATE_LIMIT_FALLBACK_WAIT_MS;
  if (wait > RATE_LIMIT_MAX_WAIT_MS) return null;
  const spread = Math.min(RATE_LIMIT_MAX_JITTER_MS, Math.max(RATE_LIMIT_MIN_JITTER_MS, wait / 5));
  return Math.round(wait + random() * spread);
};

/**
 * The error a request aborted during its wait rejects with: what axios rejects an aborted request with (its
 * `axios.isCancel` reads `__CANCEL__`; callers also read `code` / `name`). Built here rather than imported, so the
 * many unit tests that replace the axios module need not provide it.
 */
export const canceledError = (): Error =>
  Object.assign(new Error('The request was aborted.'), {name: 'CanceledError', code: 'ERR_CANCELED', __CANCEL__: true});

/** Resolve after `ms`, or reject with `canceledError()` as soon as `signal` aborts. */
export const waitUnlessAborted = (ms: number, signal?: AbortSignal | null): Promise<void> =>
  new Promise<void>((resolve, reject) => {
    const cancel = () => reject(canceledError());
    if (signal?.aborted) {
      cancel();
      return;
    }
    const onAbort = () => {
      window.clearTimeout(timer);
      cancel();
    };
    const timer = window.setTimeout(() => {
      signal?.removeEventListener?.('abort', onAbort);
      resolve();
    }, ms);
    signal?.addEventListener?.('abort', onAbort, {once: true});
  });

/** Give a final 429 the visitor-facing message (the server's body and headers stay as they were). */
const withFriendlyMessage = (error: unknown) => {
  if (isRateLimited(error) && error && typeof error === 'object') {
    (error as AxiosError).message = rateLimitMessage(error);
  }
  return error;
};

const retriable = (config: MarkedConfig | undefined): config is MarkedConfig =>
  Boolean(config)
  && config?.rateLimitRetry !== false
  && IDEMPOTENT_METHODS.has((config?.method ?? 'get').toLowerCase());

/**
 * After a 429: wait and send the request again through `instance` once, or reject with the visitor-facing message.
 * Any other error is rethrown untouched. The auth client calls it from its own response handler.
 */
export const handleRateLimitError = async (instance: AxiosInstance, error: unknown): Promise<unknown> => {
  if (!isRateLimited(error)) throw error;
  const config = shape(error).config;
  const delay = retriable(config) ? rateLimitRetryDelay(error) : null;
  if (delay === null || !config) throw withFriendlyMessage(error);
  config[RETRIED_MARKER] = true;
  await waitUnlessAborted(delay, config.signal as AbortSignal | undefined);
  try {
    return await instance(config);
  } catch (retryError) {
    throw withFriendlyMessage(retryError);
  }
};

/** Retry an idempotent request once after a 429 (see the module comment). Register it after other error handlers. */
export const installRateLimitRetry = (instance: AxiosInstance): void => {
  instance.interceptors.response.use(undefined, (error: unknown) => handleRateLimitError(instance, error));
};
