import {beforeEach, describe, expect, it, vi} from 'vitest';

import {
  accountA,
  axiosMocks,
  mockAxiosModule,
  storageMocks,
  type RequestFulfilledHandler,
  type ResponseFulfilledHandler,
  type ResponseRejectedHandler,
  type TestRequest,
  type TestSession,
} from './clientFixtures';

// The auth client's refresh-session guards: what the interceptors do to a request's headers and to a response.
// The fake axios and storage live in clientFixtures.ts; this file keeps what the client registered on its
// axios instance and the stored session.
let requestFulfilledHandler: RequestFulfilledHandler | null = null;
let responseFulfilledHandler: ResponseFulfilledHandler | null = null;
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
    response: (fulfilled, rejected) => {
      responseFulfilledHandler = fulfilled;
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
    responseFulfilledHandler = null;
    responseRejectedHandler = null;
    retryRequest.mockClear();
    axiosPost.mockReset();
    clearTokens.mockClear();
    getStoredSession.mockClear();
    updateSessionTokens.mockClear();
    storedSession = accountA();

    await import('@/features/auth/api/session/client');
  });

  it('passes fulfilled responses through the response interceptor untouched', async () => {
    if (!responseFulfilledHandler) {
      throw new Error('Response interceptor was not registered');
    }
    const response = {data: {ok: true}};
    expect(responseFulfilledHandler(response)).toBe(response);
  });

  it('removes an inherited Authorization header when no session is stored', async () => {
    storedSession = null;
    const request = prepareRequest({headers: {Authorization: 'Bearer stale'}});
    expect(request.headers.Authorization).toBeUndefined();
  });

  it('clears the Content-Type header for FormData requests', async () => {
    const request = prepareRequest({
      headers: {'Content-Type': 'application/json'},
      data: new FormData(),
    });
    expect(request.headers['Content-Type']).toBeUndefined();
  });

  it('does not touch headers when there is no session and no headers object', async () => {
    storedSession = null;
    const request = prepareRequest({} as TestRequest);
    expect(request).toEqual({});
  });

  it('rejects a non-401 response error without retrying', async () => {
    const request = prepareRequest({headers: {}});
    if (!responseRejectedHandler) {
      throw new Error('Response interceptor was not registered');
    }
    const error = {config: request, response: {status: 500}};

    await expect(responseRejectedHandler(error)).rejects.toBe(error);
    expect(axiosPost).not.toHaveBeenCalled();
    expect(retryRequest).not.toHaveBeenCalled();
  });
});
