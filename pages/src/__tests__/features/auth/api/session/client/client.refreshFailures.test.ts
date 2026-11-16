import {beforeEach, describe, expect, it, vi} from 'vitest';

import {
  accountA,
  axiosMocks,
  mockAxiosModule,
  storageMocks,
  type RequestFulfilledHandler,
  type ResponseRejectedHandler,
  type TestRequest,
  type TestSession,
} from './clientFixtures';

// The auth client's refresh-session guards: failed refreshes: transient keeps the session, definitive clears it.
// The fake axios and storage live in clientFixtures.ts; this file keeps what the client registered on its
// axios instance and the stored session.
let requestFulfilledHandler: RequestFulfilledHandler | null = null;
let responseRejectedHandler: ResponseRejectedHandler | null = null;
let storedSession: TestSession | null;

const {retryRequest, axiosPost} = axiosMocks();
const {clearTokens, getStoredSession, updateSessionTokens} = storageMocks(() => storedSession, (session) => {
  storedSession = session;
});

vi.mock('axios', () =>
  mockAxiosModule({retryRequest, axiosPost}, {
    request: (handler) => {
      requestFulfilledHandler = handler;
    },
    response: (_fulfilled, rejected) => {
      responseRejectedHandler = rejected;
    },
  }),
);
vi.mock('@/features/auth/api/session/storage', () => ({clearTokens, getStoredSession, updateSessionTokens}));

const prepareRequest = (request: TestRequest) => {
  if (!requestFulfilledHandler) {
    throw new Error('Request interceptor was not registered');
  }
  return requestFulfilledHandler(request);
};

describe('auth refresh session guards', () => {
  beforeEach(async () => {
    vi.resetModules();
    requestFulfilledHandler = null;
    responseRejectedHandler = null;
    retryRequest.mockClear();
    axiosPost.mockReset();
    clearTokens.mockClear();
    getStoredSession.mockClear();
    updateSessionTokens.mockClear();
    storedSession = accountA();

    await import('@/features/auth/api/session/client');
  });

  it('retains the guarded generation when refresh returns a malformed success', async () => {
    axiosPost.mockResolvedValue({data: {}});
    const {refreshAccessToken} = await import('@/features/auth/api/session/client');

    await expect(refreshAccessToken('generation-a')).resolves.toBeNull();

    expect(clearTokens).not.toHaveBeenCalled();
    expect(storedSession).toEqual(accountA());
  });

  it('retains the guarded generation when refresh fails transiently', async () => {
    axiosPost.mockRejectedValue({response: {status: 503}});
    const {refreshAccessToken} = await import('@/features/auth/api/session/client');

    await expect(refreshAccessToken('generation-a')).resolves.toBeNull();

    expect(clearTokens).not.toHaveBeenCalled();
    expect(storedSession).toEqual(accountA());
  });

  it('does not mark the original 401 definitive after a refresh 5xx', async () => {
    axiosPost.mockRejectedValue({response: {status: 503}});
    const {isDefinitiveAuthFailure} = await import('@/features/auth/api/session/client');
    const request = prepareRequest({headers: {}});
    if (!responseRejectedHandler) {
      throw new Error('Response interceptor was not registered');
    }
    const error = {config: request, response: {status: 401}};

    await expect(responseRejectedHandler(error)).rejects.toBe(error);

    expect(isDefinitiveAuthFailure(error)).toBe(false);
    expect(clearTokens).not.toHaveBeenCalled();
    expect(storedSession).toEqual(accountA());
  });

  it('marks only a definitive refresh rejection for anonymous fallback', async () => {
    axiosPost.mockRejectedValue({response: {status: 401}});
    const {isDefinitiveAuthFailure} = await import('@/features/auth/api/session/client');
    const request = prepareRequest({headers: {}});
    if (!responseRejectedHandler) {
      throw new Error('Response interceptor was not registered');
    }
    const error = {config: request, response: {status: 401}};

    await expect(responseRejectedHandler(error)).rejects.toBe(error);

    expect(isDefinitiveAuthFailure(error)).toBe(true);
    expect(storedSession).toBeNull();
  });

  it('treats a non-object refresh failure as transient', async () => {
    axiosPost.mockRejectedValue(null);
    const {refreshAccessToken} = await import('@/features/auth/api/session/client');

    await expect(refreshAccessToken('generation-a')).resolves.toBeNull();
    expect(clearTokens).not.toHaveBeenCalled();
    expect(storedSession).toEqual(accountA());
  });

  it('treats a refresh failure without a response as transient', async () => {
    axiosPost.mockRejectedValue({});
    const {refreshAccessToken} = await import('@/features/auth/api/session/client');

    await expect(refreshAccessToken('generation-a')).resolves.toBeNull();
    expect(clearTokens).not.toHaveBeenCalled();
    expect(storedSession).toEqual(accountA());
  });

  it('treats a non-numeric refresh failure status as transient', async () => {
    axiosPost.mockRejectedValue({response: {status: 'oops'}});
    const {refreshAccessToken} = await import('@/features/auth/api/session/client');

    await expect(refreshAccessToken('generation-a')).resolves.toBeNull();
    expect(clearTokens).not.toHaveBeenCalled();
    expect(storedSession).toEqual(accountA());
  });
});
