import {beforeEach, describe, expect, it, vi} from 'vitest';

import {
  accessWithExpiry,
  accountA,
  axiosMocks,
  mockAxiosModule,
  storageMocks,
  type RequestFulfilledHandler,
  type TestRequest,
  type TestSession,
} from './clientFixtures';

// The auth client's refresh-session guards: member-aware public requests.
// The fake axios and storage live in clientFixtures.ts; this file keeps what the client registered on its
// axios instance and the stored session.
let requestFulfilledHandler: RequestFulfilledHandler | null = null;
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
    response: () => {},
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
    retryRequest.mockClear();
    axiosPost.mockReset();
    clearTokens.mockClear();
    getStoredSession.mockClear();
    updateSessionTokens.mockClear();
    storedSession = accountA();

    await import('@/features/auth/api/session/client');
  });

  describe('member-aware public requests', () => {
    it('refreshes an expired token before the request can read as anonymous', async () => {
      storedSession = {...accountA(), access: accessWithExpiry(Date.now() / 1000 - 60)};
      axiosPost.mockResolvedValue({data: {access: 'fresh-access', refresh: 'fresh-refresh'}});

      const request = await prepareRequest({headers: {}, requireFreshIdentity: true});

      expect(axiosPost).toHaveBeenCalledTimes(1);
      expect(request.headers.Authorization).toBe('Bearer fresh-access');
    });

    it('uses a still-valid token without a refresh request', async () => {
      storedSession = {...accountA(), access: accessWithExpiry(Date.now() / 1000 + 3600)};

      const request = await prepareRequest({headers: {}, requireFreshIdentity: true});

      expect(axiosPost).not.toHaveBeenCalled();
      expect(request.headers.Authorization).toBe(`Bearer ${storedSession?.access}`);
    });

    it('refreshes before an almost-expired token can reach the server', async () => {
      storedSession = {...accountA(), access: accessWithExpiry(Date.now() / 1000 + 10)};
      axiosPost.mockResolvedValue({data: {access: 'fresh-access'}});

      const request = await prepareRequest({headers: {}, requireFreshIdentity: true});

      expect(axiosPost).toHaveBeenCalledTimes(1);
      expect(request.headers.Authorization).toBe('Bearer fresh-access');
    });

    it('does not silently return anonymous data after a transient refresh failure', async () => {
      storedSession = {...accountA(), access: accessWithExpiry(Date.now() / 1000 - 60)};
      axiosPost.mockRejectedValue({response: {status: 503}});

      await expect(prepareRequest({headers: {}, requireFreshIdentity: true})).rejects.toThrow(
        'could not be refreshed',
      );
      expect(storedSession?.generation).toBe('generation-a');
    });

    it('can continue anonymously after the refresh credential is rejected', async () => {
      storedSession = {...accountA(), access: accessWithExpiry(Date.now() / 1000 - 60)};
      axiosPost.mockRejectedValue({response: {status: 401}});

      const request = await prepareRequest({headers: {}, requireFreshIdentity: true});

      expect(request.headers.Authorization).toBeUndefined();
      expect(storedSession).toBeNull();
    });

    it('does not send an account-A request under account B after a switch', async () => {
      storedSession = {...accountA(), access: accessWithExpiry(Date.now() / 1000 - 60)};
      let resolveRefresh!: (value: {data: {access: string}}) => void;
      axiosPost.mockReturnValue(new Promise((resolve) => { resolveRefresh = resolve; }));

      const pending = prepareRequest({headers: {}, requireFreshIdentity: true});
      storedSession = {...accountA(), generation: 'generation-b', access: 'access-b'};
      resolveRefresh({data: {access: 'new-access'}});

      await expect(pending).rejects.toThrow('session changed');
      expect(storedSession?.generation).toBe('generation-b');
    });

    it('keeps one-time credential requests anonymous even with the flag', async () => {
      storedSession = {...accountA(), access: accessWithExpiry(Date.now() / 1000 - 60)};

      const request = await prepareRequest({headers: {}, requireFreshIdentity: true, skipAuth: true});

      expect(request.headers.Authorization).toBeUndefined();
      expect(axiosPost).not.toHaveBeenCalled();
    });
  });
});
