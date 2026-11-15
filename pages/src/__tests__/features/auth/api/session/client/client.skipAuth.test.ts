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

// The auth client's refresh-session guards: skipAuth requests.
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

  describe('skipAuth requests', () => {
    it('sends no Authorization header even when a session is stored', () => {
      const request = prepareRequest({headers: {}, skipAuth: true});

      expect(request.headers.Authorization).toBeUndefined();
    });

    it('does not record a session for the request, so nothing can be refreshed or cleared on its behalf', async () => {
      const request = prepareRequest({headers: {}, skipAuth: true});
      if (!responseRejectedHandler) {
        throw new Error('Response interceptor was not registered');
      }
      const error = {config: request, response: {status: 401}};

      await expect(responseRejectedHandler(error)).rejects.toBe(error);

      expect(axiosPost).not.toHaveBeenCalled();
      expect(clearTokens).not.toHaveBeenCalled();
    });

    it('strips an Authorization header supplied by the caller', () => {
      const request = prepareRequest({
        headers: {Authorization: 'Bearer caller-supplied'},
        skipAuth: true,
      });

      expect(request.headers.Authorization).toBeUndefined();
    });

    it('strips the header whatever its casing on a plain headers object', () => {
      const request = prepareRequest({
        headers: {
          authorization: 'Bearer lower',
          AUTHORIZATION: 'Bearer upper',
          Accept: 'application/json',
        },
        skipAuth: true,
      });

      expect(request.headers).toEqual({Accept: 'application/json'});
    });

    it.each([
      ['a lowercase key', {authorization: 'Bearer lower', Accept: 'application/json'}],
      ['the canonical key', {Authorization: 'Bearer canonical', Accept: 'application/json'}],
      ['an upper-case key', {AUTHORIZATION: 'Bearer upper', Accept: 'application/json'}],
    ])('strips the header from an AxiosHeaders instance (%s)', async (_label, initial) => {
      const {AxiosHeaders} = await vi.importActual<typeof import('axios')>('axios');
      const headers = new AxiosHeaders(initial);

      const request = prepareRequest({
        headers: headers as unknown as Record<string, string>,
        skipAuth: true,
      });

      const result = request.headers as unknown as InstanceType<typeof AxiosHeaders>;
      expect(result.has('Authorization')).toBe(false);
      expect(result.get('authorization')).toBeUndefined();
      expect(result.get('Accept')).toBe('application/json');
    });

    it('still attaches the stored session to requests that do not opt out', () => {
      const request = prepareRequest({headers: {}});

      expect(request.headers.Authorization).toBe('Bearer old-access');
    });

    it('still clears the Content-Type header for FormData requests', () => {
      const request = prepareRequest({
        headers: {'Content-Type': 'application/json'},
        data: new FormData(),
        skipAuth: true,
      });

      expect(request.headers['Content-Type']).toBeUndefined();
    });

    it('rejects a 401 without refreshing, retrying, or touching the stored session', async () => {
      const request = prepareRequest({headers: {}, skipAuth: true});
      if (!responseRejectedHandler) {
        throw new Error('Response interceptor was not registered');
      }
      const {isDefinitiveAuthFailure} = await import('@/features/auth/api/session/client');
      const error = {config: request, response: {status: 401}};

      await expect(responseRejectedHandler(error)).rejects.toBe(error);

      expect(axiosPost).not.toHaveBeenCalled();
      expect(retryRequest).not.toHaveBeenCalled();
      expect(clearTokens).not.toHaveBeenCalled();
      expect(isDefinitiveAuthFailure(error)).toBe(false);
      expect(storedSession).toEqual(accountA());
    });

    it('never clears the stored session, even for a request that was already tagged and retried', async () => {
      // Defense in depth: the opt-out wins over any per-request session record.
      const request = prepareRequest({headers: {}});
      request.skipAuth = true;
      request._i2gAuthRetried = true;
      if (!responseRejectedHandler) {
        throw new Error('Response interceptor was not registered');
      }
      const {isDefinitiveAuthFailure} = await import('@/features/auth/api/session/client');
      const error = {config: request, response: {status: 401}};

      await expect(responseRejectedHandler(error)).rejects.toBe(error);

      expect(clearTokens).not.toHaveBeenCalled();
      expect(isDefinitiveAuthFailure(error)).toBe(false);
      expect(storedSession).toEqual(accountA());
    });

    it('does not refresh for a tagged request that opted out after the fact', async () => {
      const request = prepareRequest({headers: {}});
      request.skipAuth = true;
      if (!responseRejectedHandler) {
        throw new Error('Response interceptor was not registered');
      }
      const error = {config: request, response: {status: 401}};

      await expect(responseRejectedHandler(error)).rejects.toBe(error);

      expect(axiosPost).not.toHaveBeenCalled();
      expect(retryRequest).not.toHaveBeenCalled();
    });

    it('passes non-401 failures through untouched', async () => {
      const request = prepareRequest({headers: {}, skipAuth: true});
      if (!responseRejectedHandler) {
        throw new Error('Response interceptor was not registered');
      }
      const error = {config: request, response: {status: 400}};

      await expect(responseRejectedHandler(error)).rejects.toBe(error);
      expect(storedSession).toEqual(accountA());
    });
  });
});
