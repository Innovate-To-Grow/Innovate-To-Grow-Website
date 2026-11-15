import axios, {AxiosError, AxiosHeaders, type AxiosAdapter, type AxiosResponse, type InternalAxiosRequestConfig} from 'axios';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {
  handleRateLimitError,
  installRateLimitRetry,
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
