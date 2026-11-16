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

// The auth client's refresh-session guards: refresh de-duplication and account switches.
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

  it('deduplicates concurrent refreshes for one generation', async () => {
    let resolveRefresh!: (value: {
      data: {access: string; refresh: string};
    }) => void;
    const refreshPromise = new Promise<{
      data: {access: string; refresh: string};
    }>((resolve) => {
      resolveRefresh = resolve;
    });
    axiosPost.mockReturnValue(refreshPromise);

    const firstRequest = prepareRequest({headers: {}});
    const secondRequest = prepareRequest({headers: {}});
    if (!responseRejectedHandler) {
      throw new Error('Response interceptor was not registered');
    }

    const firstRetry = responseRejectedHandler({
      config: firstRequest,
      response: {status: 401},
    });
    const secondRetry = responseRejectedHandler({
      config: secondRequest,
      response: {status: 401},
    });

    expect(axiosPost).toHaveBeenCalledTimes(1);
    resolveRefresh({
      data: {access: 'new-access', refresh: 'new-refresh'},
    });
    await Promise.all([firstRetry, secondRetry]);

    expect(updateSessionTokens).toHaveBeenCalledTimes(1);
    expect(retryRequest).toHaveBeenCalledTimes(2);
    expect(firstRequest.headers).toEqual({
      Authorization: 'Bearer new-access',
    });
    expect(secondRequest.headers).toEqual({
      Authorization: 'Bearer new-access',
    });
    expect(clearTokens).not.toHaveBeenCalled();
  });

  it('does not retry an account-A request after account B replaces storage', async () => {
    const request = prepareRequest({headers: {}});
    storedSession = {
      ...accountA(),
      generation: 'generation-b',
      access: 'access-b',
      refresh: 'refresh-b',
      user: {member_uuid: 'b', email: 'b@example.com'},
    };
    if (!responseRejectedHandler) {
      throw new Error('Response interceptor was not registered');
    }
    const error = {config: request, response: {status: 401}};

    await expect(responseRejectedHandler(error)).rejects.toBe(error);
    expect(axiosPost).not.toHaveBeenCalled();
    expect(retryRequest).not.toHaveBeenCalled();
    expect(storedSession?.generation).toBe('generation-b');
  });

  it('discards a refresh response after logout', async () => {
    let resolveRefresh!: (value: {
      data: {access: string; refresh: string};
    }) => void;
    axiosPost.mockReturnValue(
      new Promise((resolve) => {
        resolveRefresh = resolve;
      }),
    );
    const request = prepareRequest({headers: {}});
    if (!responseRejectedHandler) {
      throw new Error('Response interceptor was not registered');
    }
    const error = {config: request, response: {status: 401}};
    const retry = responseRejectedHandler(error);

    storedSession = null;
    resolveRefresh({
      data: {access: 'stale-access', refresh: 'stale-refresh'},
    });

    await expect(retry).rejects.toBe(error);
    expect(retryRequest).not.toHaveBeenCalled();
    expect(storedSession).toBeNull();
  });

  it('clears only the retried generation when a fresh token is still rejected', async () => {
    axiosPost.mockResolvedValue({
      data: {access: 'new-access', refresh: 'new-refresh'},
    });
    const request = prepareRequest({headers: {}});
    if (!responseRejectedHandler) {
      throw new Error('Response interceptor was not registered');
    }

    await responseRejectedHandler({
      config: request,
      response: {status: 401},
    });
    // Simulate Axios running the request interceptor again for the retried
    // config. This tags the exact refreshed access token used by the retry.
    prepareRequest(request);
    const finalError = {config: request, response: {status: 401}};

    await expect(responseRejectedHandler(finalError)).rejects.toBe(finalError);
    expect(clearTokens).toHaveBeenCalledWith({
      generation: 'generation-a',
      refresh: 'new-refresh',
    });
    expect(storedSession).toBeNull();
    expect(axiosPost).toHaveBeenCalledTimes(1);
  });

  it('reports a changed session when a definitive refresh fails after a guard mismatch', async () => {
    axiosPost.mockRejectedValue({response: {status: 401}});
    const {refreshAccessToken} = await import('@/features/auth/api/session/client');

    const pending = refreshAccessToken('generation-a');
    storedSession = {...accountA(), generation: 'generation-b'};

    await expect(pending).resolves.toBeNull();
    expect(clearTokens).toHaveBeenCalled();
  });
});
