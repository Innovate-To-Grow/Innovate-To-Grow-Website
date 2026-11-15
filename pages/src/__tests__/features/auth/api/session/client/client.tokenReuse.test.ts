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

// The auth client's refresh-session guards: reusing a token refreshed elsewhere; refreshing with nothing to refresh.
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

  it('reuses a token rotated by another tab while refresh is in flight', async () => {
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
    const retry = responseRejectedHandler({
      config: request,
      response: {status: 401},
    });

    storedSession = {
      ...accountA(),
      access: 'other-tab-access',
      refresh: 'other-tab-refresh',
    };
    resolveRefresh({
      data: {access: 'stale-access', refresh: 'stale-refresh'},
    });

    await expect(retry).resolves.toEqual(
      expect.objectContaining({data: {ok: true}}),
    );
    expect(request.headers.Authorization).toBe('Bearer other-tab-access');
    expect(clearTokens).not.toHaveBeenCalled();
  });

  it('reuses a token refreshed by a parallel request before the retry', async () => {
    const request = prepareRequest({headers: {}});
    if (!responseRejectedHandler) {
      throw new Error('Response interceptor was not registered');
    }
    storedSession = {...accountA(), access: 'parallel-access'};
    const error = {config: request, response: {status: 401}};

    await expect(responseRejectedHandler(error)).resolves.toEqual(
      expect.objectContaining({data: {ok: true}}),
    );
    expect(request.headers.Authorization).toBe('Bearer parallel-access');
    expect(axiosPost).not.toHaveBeenCalled();
  });

  it('reuses the previous refresh token when the refresh response omits it', async () => {
    axiosPost.mockResolvedValue({data: {access: 'new-access'}});
    const {refreshAccessToken} = await import('@/features/auth/api/session/client');

    await expect(refreshAccessToken('generation-a')).resolves.toMatchObject({
      access: 'new-access',
    });
    expect(updateSessionTokens).toHaveBeenCalledWith(
      {generation: 'generation-a', refresh: 'refresh-a'},
      {access: 'new-access', refresh: 'refresh-a'},
    );
  });

  it('returns null when refreshing without a stored session', async () => {
    storedSession = null;
    const {refreshAccessToken} = await import('@/features/auth/api/session/client');

    await expect(refreshAccessToken('generation-a')).resolves.toBeNull();
    expect(axiosPost).not.toHaveBeenCalled();
  });

  it('returns null when refreshing a different generation', async () => {
    const {refreshAccessToken} = await import('@/features/auth/api/session/client');

    await expect(refreshAccessToken('generation-other')).resolves.toBeNull();
    expect(axiosPost).not.toHaveBeenCalled();
  });
});
