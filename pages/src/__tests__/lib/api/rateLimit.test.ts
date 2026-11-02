import axios, {AxiosError, AxiosHeaders, type AxiosAdapter, type AxiosResponse, type InternalAxiosRequestConfig} from 'axios';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {
  RATE_LIMIT_FALLBACK_WAIT_MS,
  RATE_LIMIT_MAX_WAIT_MS,
  canceledError,
  handleRateLimitError,
  installRateLimitRetry,
  isRateLimited,
  parseRetryAfter,
  rateLimitMessage,
  rateLimitRetryDelay,
  retryAfterMs,
  waitUnlessAborted,
  wasRateLimitRetried,
} from '@/lib/api/rateLimit';

type Answer = {status: number; data?: unknown; headers?: Record<string, string>};

/** An axios instance with the retry installed, answering each request with the next scripted answer. */
function clientAnswering(...answers: Answer[]) {
  const seen: InternalAxiosRequestConfig[] = [];
  const adapter: AxiosAdapter = async (config) => {
    seen.push(config);
    const answer = answers.shift() ?? {status: 200, data: {ok: true}};
    const response: AxiosResponse = {
      status: answer.status,
      statusText: String(answer.status),
      data: answer.data ?? {},
      headers: new AxiosHeaders(answer.headers ?? {}),
      config,
    };
    if (answer.status >= 400) {
      throw new AxiosError(`Request failed with status code ${answer.status}`, 'ERR_BAD_REQUEST', config, {}, response);
    }
    return response;
  };
  const client = axios.create({adapter});
  installRateLimitRetry(client);
  return {client, seen};
}

const refused = (retryAfter?: string, data: unknown = {detail: 'Too many requests.'}): Answer => ({
  status: 429,
  data,
  headers: retryAfter === undefined ? {} : {'Retry-After': retryAfter},
});

describe('parseRetryAfter', () => {
  it('reads delta-seconds, including a fraction', () => {
    expect(parseRetryAfter('3')).toBe(3000);
    expect(parseRetryAfter(' 1.5 ')).toBe(1500);
    expect(parseRetryAfter('0')).toBe(0);
  });

  it('reads an HTTP date relative to now', () => {
    const now = Date.parse('2026-01-01T00:00:00Z');
    expect(parseRetryAfter('Thu, 01 Jan 2026 00:00:04 GMT', now)).toBe(4000);
  });

  it('is null for a missing, blank, unparseable, negative or past value', () => {
    const now = Date.parse('2026-01-01T00:00:00Z');
    expect(parseRetryAfter(undefined)).toBeNull();
    expect(parseRetryAfter('  ')).toBeNull();
    expect(parseRetryAfter('soon')).toBeNull();
    expect(parseRetryAfter('-5')).toBeNull();
    expect(parseRetryAfter('Wed, 31 Dec 2025 23:59:00 GMT', now)).toBeNull();
  });
});

describe('retryAfterMs', () => {
  it('prefers the header, read case-insensitively from AxiosHeaders', () => {
    const error = {response: {status: 429, headers: new AxiosHeaders({'Retry-After': '7'}), data: {retry_after: 2}}};
    expect(retryAfterMs(error)).toBe(7000);
  });

  it('reads a plain headers object in either spelling, and a numeric value', () => {
    expect(retryAfterMs({response: {headers: {'retry-after': '2'}}})).toBe(2000);
    expect(retryAfterMs({response: {headers: {'Retry-After': 3}}})).toBe(3000);
  });

  it('falls back to the body retry_after when the header is absent or unreadable (cross-origin)', () => {
    expect(retryAfterMs({response: {status: 429, headers: {}, data: {retry_after: 4}}})).toBe(4000);
    expect(retryAfterMs({response: {status: 429, headers: {'retry-after': 'x'}, data: {retry_after: 1}}})).toBe(1000);
  });

  it('is null when neither names a usable wait', () => {
    expect(retryAfterMs({response: {status: 429, headers: null, data: {retry_after: 'soon'}}})).toBeNull();
    expect(retryAfterMs({response: {status: 429, data: {retry_after: -1}}})).toBeNull();
    expect(retryAfterMs({response: {status: 429, data: 'Too Many Requests'}})).toBeNull();
    expect(retryAfterMs({response: {status: 429, headers: {'retry-after': {}}}})).toBeNull();
    expect(retryAfterMs(null)).toBeNull();
    expect(retryAfterMs('boom')).toBeNull();
  });
});

describe('rateLimitMessage and isRateLimited', () => {
  it('names the wait in whole seconds', () => {
    expect(rateLimitMessage({response: {status: 429, data: {retry_after: 30}}})).toBe(
      'The site is busy right now. Please try again in 30 seconds.',
    );
    expect(rateLimitMessage({response: {status: 429, headers: {'retry-after': '0.2'}}})).toBe(
      'The site is busy right now. Please try again in 1 second.',
    );
  });

  it('says "in a moment" when no wait is known', () => {
    expect(rateLimitMessage({response: {status: 429}})).toBe('The site is busy right now. Please try again in a moment.');
  });

  it('recognises only a 429', () => {
    expect(isRateLimited({response: {status: 429}})).toBe(true);
    expect(isRateLimited({response: {status: 503}})).toBe(false);
    expect(isRateLimited(undefined)).toBe(false);
  });
});

describe('rateLimitRetryDelay', () => {
  it('adds jitter of a fifth of the wait, at least 250 ms and at most 2 s', () => {
    const error = (seconds: string) => ({response: {status: 429, headers: {'retry-after': seconds}}});
    expect(rateLimitRetryDelay(error('0'), () => 0)).toBe(0);
    expect(rateLimitRetryDelay(error('0'), () => 1)).toBe(250);
    expect(rateLimitRetryDelay(error('5'), () => 1)).toBe(6000);
    expect(rateLimitRetryDelay(error('10'), () => 1)).toBe(12000);
  });

  it('waits the fallback when the server names no wait', () => {
    expect(rateLimitRetryDelay({response: {status: 429}}, () => 0)).toBe(RATE_LIMIT_FALLBACK_WAIT_MS);
  });

  it('is null for a wait longer than the maximum, an already-retried request, or another status', () => {
    const longer = String(RATE_LIMIT_MAX_WAIT_MS / 1000 + 1);
    expect(rateLimitRetryDelay({response: {status: 429, headers: {'retry-after': longer}}})).toBeNull();
    expect(rateLimitRetryDelay({config: {_i2gRateLimitRetried: true}, response: {status: 429}})).toBeNull();
    expect(rateLimitRetryDelay({response: {status: 503}})).toBeNull();
  });

  it('uses Math.random by default, staying inside the jitter bounds', () => {
    const delay = rateLimitRetryDelay({response: {status: 429, headers: {'retry-after': '1'}}});
    expect(delay).toBeGreaterThanOrEqual(1000);
    expect(delay).toBeLessThanOrEqual(1250);
  });
});

describe('waitUnlessAborted', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('resolves after the wait and stops listening to the signal', async () => {
    const controller = new AbortController();
    const remove = vi.spyOn(controller.signal, 'removeEventListener');
    const pending = waitUnlessAborted(500, controller.signal);
    await vi.advanceTimersByTimeAsync(500);
    await expect(pending).resolves.toBeUndefined();
    expect(remove).toHaveBeenCalledWith('abort', expect.any(Function));
  });

  it('resolves without a signal', async () => {
    const pending = waitUnlessAborted(10);
    await vi.advanceTimersByTimeAsync(10);
    await expect(pending).resolves.toBeUndefined();
  });

  it('rejects with a cancel error at once when the signal is already aborted', async () => {
    const controller = new AbortController();
    controller.abort();
    const failure = await waitUnlessAborted(5000, controller.signal).catch((error: unknown) => error);
    expect(axios.isCancel(failure)).toBe(true);
    expect(failure).toMatchObject({code: 'ERR_CANCELED', name: 'CanceledError'});
  });

  it('rejects and clears its timer when the signal aborts during the wait', async () => {
    const controller = new AbortController();
    const pending = waitUnlessAborted(5000, controller.signal);
    controller.abort();
    await expect(pending).rejects.toMatchObject({code: 'ERR_CANCELED'});
    expect(vi.getTimerCount()).toBe(0);
  });

  it('builds an error axios recognises as a cancellation', () => {
    expect(axios.isCancel(canceledError())).toBe(true);
  });
});

describe('installRateLimitRetry', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('retries a refused GET once after Retry-After plus jitter', async () => {
    vi.spyOn(Math, 'random').mockReturnValue(0);
    const {client, seen} = clientAnswering(refused('2'), {status: 200, data: {menus: []}});

    const pending = client.get('/layout/');
    await vi.advanceTimersByTimeAsync(1999);
    expect(seen).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(1);

    await expect(pending).resolves.toMatchObject({data: {menus: []}});
    expect(seen).toHaveLength(2);
    vi.restoreAllMocks();
  });

  it('reads the wait from the body when the header is not exposed', async () => {
    vi.spyOn(Math, 'random').mockReturnValue(0);
    const {client, seen} = clientAnswering(refused(undefined, {retry_after: 3}), {status: 200});

    const pending = client.get('/news/');
    await vi.advanceTimersByTimeAsync(2999);
    expect(seen).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(1);
    await expect(pending).resolves.toMatchObject({status: 200});
    vi.restoreAllMocks();
  });

  it('retries HEAD and OPTIONS too', async () => {
    const {client, seen} = clientAnswering(refused('0'), {status: 200}, refused('0'), {status: 200});
    const head = client.head('/x/');
    await vi.advanceTimersByTimeAsync(300);
    await expect(head).resolves.toMatchObject({status: 200});
    const options = client.options('/x/');
    await vi.advanceTimersByTimeAsync(300);
    await expect(options).resolves.toMatchObject({status: 200});
    expect(seen.map((config) => config.method)).toEqual(['head', 'head', 'options', 'options']);
  });

  it('gives up after the one retry, with a visitor-facing message and the server body intact', async () => {
    const {client, seen} = clientAnswering(refused('1'), refused('4', {detail: 'Slow down.', retry_after: 4}));

    const pending = client.get('/projects/all/').catch((error: unknown) => error);
    await vi.advanceTimersByTimeAsync(1500);
    const failure = (await pending) as AxiosError;

    expect(seen).toHaveLength(2);
    expect(failure.message).toBe('The site is busy right now. Please try again in 4 seconds.');
    expect(failure.response?.data).toEqual({detail: 'Slow down.', retry_after: 4});
    expect(wasRateLimitRetried(failure)).toBe(true);
  });

  it('fails at once when the server asks for longer than the maximum wait', async () => {
    const {client, seen} = clientAnswering(refused('60'));

    const failure = (await client.get('/cms/pages/').catch((error: unknown) => error)) as AxiosError;

    expect(seen).toHaveLength(1);
    expect(failure.message).toBe('The site is busy right now. Please try again in 60 seconds.');
  });

  it('never retries a POST, but still gives it the friendly message', async () => {
    const {client, seen} = clientAnswering(refused('1'));

    const failure = (await client.post('/event/registrations/', {}).catch((error: unknown) => error)) as AxiosError;

    expect(seen).toHaveLength(1);
    expect(failure.message).toBe('The site is busy right now. Please try again in 1 second.');
  });

  it('passes a 429 straight through when the request opts out', async () => {
    const {client, seen} = clientAnswering(refused('1'));

    await expect(client.get('/health/', {rateLimitRetry: false})).rejects.toMatchObject({response: {status: 429}});
    expect(seen).toHaveLength(1);
  });

  it('leaves other failures untouched', async () => {
    const {client, seen} = clientAnswering({status: 503});

    await expect(client.get('/layout/')).rejects.toMatchObject({message: 'Request failed with status code 503'});
    expect(seen).toHaveLength(1);
  });

  it('passes a non-429 failure of the retry through unchanged', async () => {
    const {client} = clientAnswering(refused('0'), {status: 500});
    const pending = client.get('/layout/').catch((error: unknown) => error);
    await vi.advanceTimersByTimeAsync(300);
    expect(await pending).toMatchObject({message: 'Request failed with status code 500', response: {status: 500}});
  });

  it('cancels the wait when the caller aborts', async () => {
    const {client, seen} = clientAnswering(refused('5'));
    const controller = new AbortController();

    const pending = client.get('/projects/archive/', {signal: controller.signal}).catch((error: unknown) => error);
    await vi.advanceTimersByTimeAsync(10);
    controller.abort();

    expect(axios.isCancel(await pending)).toBe(true);
    expect(seen).toHaveLength(1);
  });
});

describe('handleRateLimitError', () => {
  it('rethrows a 429 that has no request config to resend', async () => {
    const error = {response: {status: 429, headers: {'retry-after': '0'}}};
    const instance = vi.fn();

    await expect(handleRateLimitError(instance as never, error)).rejects.toBe(error);
    expect(instance).not.toHaveBeenCalled();
  });

  it('treats a config without a method as a GET and resends it through the instance', async () => {
    vi.useFakeTimers();
    try {
      const config = {headers: {}};
      const instance = vi.fn().mockResolvedValue({status: 200});
      const pending = handleRateLimitError(instance as never, {config, response: {status: 429, headers: {'retry-after': '0'}}});
      await vi.advanceTimersByTimeAsync(300);
      await expect(pending).resolves.toEqual({status: 200});
      expect(instance).toHaveBeenCalledWith(config);
    } finally {
      vi.useRealTimers();
    }
  });

  it('rethrows a non-object rejection unchanged', async () => {
    await expect(handleRateLimitError(vi.fn() as never, 'offline')).rejects.toBe('offline');
  });
});
