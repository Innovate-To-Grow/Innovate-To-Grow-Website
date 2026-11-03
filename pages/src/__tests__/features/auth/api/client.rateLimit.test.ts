// The auth client under 429 Too Many Requests, through real axios with scripted adapters: a refused read waits and
// retries once; a refused token refresh is resent once and otherwise stays transient, so the member is never logged
// out (and the three React roots are not told the session ended) because the server was busy.
import axios, {AxiosError, AxiosHeaders, type AxiosAdapter, type AxiosResponse, type InternalAxiosRequestConfig} from 'axios';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {authApi, refreshAccessToken} from '@/features/auth/api/client';
import {clearTokens, getStoredSession, setTokens} from '@/features/auth/api/storage';

type Answer = {status: number; data?: unknown; headers?: Record<string, string>};

function scripted(answers: Answer[], seen: InternalAxiosRequestConfig[]): AxiosAdapter {
  return async (config) => {
    seen.push(config);
    const answer = answers.shift() ?? {status: 200, data: {}};
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
}

const refused = (seconds: string): Answer => ({status: 429, data: {code: 'rate_limited'}, headers: {'Retry-After': seconds}});
const user = {member_uuid: 'a', email: 'a@example.com'} as never;
const originalAdapter = axios.defaults.adapter;
const originalAuthAdapter = authApi.defaults.adapter;
const authChanges = vi.fn();

let refreshes: InternalAxiosRequestConfig[];
let reads: InternalAxiosRequestConfig[];

const useRefreshAnswers = (...answers: Answer[]) => {
  axios.defaults.adapter = scripted(answers, refreshes);
};
const useReadAnswers = (...answers: Answer[]) => {
  authApi.defaults.adapter = scripted(answers, reads);
};

beforeEach(() => {
  vi.useFakeTimers();
  vi.spyOn(Math, 'random').mockReturnValue(0);
  localStorage.clear();
  refreshes = [];
  reads = [];
  setTokens({access: 'old-access', refresh: 'refresh-a'}, user);
  window.addEventListener('i2g-auth-state-change', authChanges);
  authChanges.mockClear();
});

afterEach(() => {
  window.removeEventListener('i2g-auth-state-change', authChanges);
  axios.defaults.adapter = originalAdapter;
  authApi.defaults.adapter = originalAuthAdapter;
  clearTokens();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe('token refresh under 429', () => {
  it('resends a refused refresh once after Retry-After and stores the new tokens', async () => {
    const generation = getStoredSession()!.generation;
    useRefreshAnswers(refused('2'), {status: 200, data: {access: 'new-access', refresh: 'refresh-b'}});

    const pending = refreshAccessToken(generation);
    await vi.advanceTimersByTimeAsync(1999);
    expect(refreshes).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(1);

    await expect(pending).resolves.toEqual({access: 'new-access', generation});
    expect(refreshes).toHaveLength(2);
    expect(JSON.parse(refreshes[1].data as string)).toEqual({refresh: 'refresh-a'});
    expect(getStoredSession()).toMatchObject({access: 'new-access', refresh: 'refresh-b'});
    expect(authChanges).toHaveBeenCalledTimes(1);
  });

  it('keeps the member signed in when the refresh is still refused', async () => {
    useRefreshAnswers(refused('1'), refused('1'));

    const pending = refreshAccessToken();
    await vi.advanceTimersByTimeAsync(1500);

    await expect(pending).resolves.toBeNull();
    expect(refreshes).toHaveLength(2);
    expect(getStoredSession()).toMatchObject({access: 'old-access', refresh: 'refresh-a'});
    expect(authChanges).not.toHaveBeenCalled();
  });

  it('does not wait out a long Retry-After, and still keeps the session', async () => {
    useRefreshAnswers(refused('120'));

    await expect(refreshAccessToken()).resolves.toBeNull();

    expect(refreshes).toHaveLength(1);
    expect(getStoredSession()).toMatchObject({access: 'old-access'});
    expect(authChanges).not.toHaveBeenCalled();
  });

  it('still ends the session on a definitive rejection after the resend', async () => {
    useRefreshAnswers(refused('0'), {status: 401, data: {detail: 'Token is invalid'}});

    const pending = refreshAccessToken();
    await vi.advanceTimersByTimeAsync(300);

    await expect(pending).resolves.toBeNull();
    expect(getStoredSession()).toBeNull();
    expect(authChanges).toHaveBeenCalledTimes(1);
  });
});

describe('authApi reads under 429', () => {
  it('retries a refused member read once, still under the stored session', async () => {
    useReadAnswers(refused('1'), {status: 200, data: {authenticated: true}});

    const pending = authApi.get('/authn/session/');
    await vi.advanceTimersByTimeAsync(1000);

    await expect(pending).resolves.toMatchObject({data: {authenticated: true}});
    expect(reads).toHaveLength(2);
    expect(reads.map((config) => config.headers.Authorization)).toEqual(['Bearer old-access', 'Bearer old-access']);
    expect(getStoredSession()).toMatchObject({access: 'old-access'});
  });

  it('passes a remaining 429 on with the friendly message and leaves the session alone', async () => {
    useReadAnswers(refused('0'), refused('3'));

    const pending = authApi.get('/authn/session/').catch((error: unknown) => error);
    await vi.advanceTimersByTimeAsync(300);
    const failure = (await pending) as AxiosError;

    expect(failure.message).toBe('The site is busy right now. Please try again in 3 seconds.');
    expect(failure.response?.status).toBe(429);
    expect(getStoredSession()).toMatchObject({access: 'old-access'});
    expect(authChanges).not.toHaveBeenCalled();
  });

  it('does not resend a refused POST', async () => {
    useReadAnswers(refused('0'));

    await expect(authApi.post('/authn/change-password/', {})).rejects.toMatchObject({response: {status: 429}});
    expect(reads).toHaveLength(1);
  });

  it('passes a skipAuth 429 through untouched (one-time credentials are never resent)', async () => {
    useReadAnswers(refused('0'));

    await expect(authApi.get('/authn/email-link/', {skipAuth: true})).rejects.toMatchObject({
      message: 'Request failed with status code 429',
    });
    expect(reads).toHaveLength(1);
  });
});
