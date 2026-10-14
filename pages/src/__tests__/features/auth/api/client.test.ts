import {beforeEach, describe, expect, it, vi} from 'vitest';

interface TestSession {
  version: 1;
  generation: string;
  access: string;
  refresh: string;
  user: {member_uuid: string; email: string};
  requires_profile_completion: boolean;
}

interface TestRequest {
  headers: Record<string, string>;
  data?: unknown;
  [key: string]: unknown;
}

let requestFulfilledHandler:
  | ((config: TestRequest) => TestRequest)
  | null = null;
let responseFulfilledHandler: ((response: unknown) => unknown) | null = null;
let responseRejectedHandler:
  | ((error: {
      config: TestRequest;
      response?: {status?: number};
    }) => Promise<unknown>)
  | null = null;

const retryRequest = vi.fn(async (request) => ({
  data: {ok: true},
  config: request,
}));
const axiosPost = vi.fn();

vi.mock('axios', () => {
  const create = vi.fn(() => {
    const instance = retryRequest as typeof retryRequest & {
      interceptors: {
        request: {use: (handler: typeof requestFulfilledHandler) => void};
        response: {
          use: (
            fulfilled: unknown,
            rejected: typeof responseRejectedHandler,
          ) => void;
        };
      };
    };

    instance.interceptors = {
      request: {
        use: vi.fn((handler) => {
          requestFulfilledHandler = handler;
        }),
      },
      response: {
        use: vi.fn((fulfilled, rejected) => {
          responseFulfilledHandler = fulfilled;
          responseRejectedHandler = rejected;
        }),
      },
    };

    return instance;
  });

  return {
    default: {
      create,
      post: axiosPost,
    },
  };
});

let storedSession: TestSession | null;
const clearTokens = vi.fn((guard?: {generation: string; refresh?: string}) => {
  if (
    guard &&
    (!storedSession ||
      storedSession.generation !== guard.generation ||
      (guard.refresh !== undefined &&
        storedSession.refresh !== guard.refresh))
  ) {
    return false;
  }
  storedSession = null;
  return true;
});
const getStoredSession = vi.fn(() => storedSession);
const updateSessionTokens = vi.fn(
  (
    guard: {generation: string; refresh?: string},
    tokens: {access: string; refresh: string},
  ) => {
    if (
      !storedSession ||
      storedSession.generation !== guard.generation ||
      (guard.refresh !== undefined &&
        storedSession.refresh !== guard.refresh)
    ) {
      return null;
    }
    storedSession = {...storedSession, ...tokens};
    return storedSession;
  },
);

vi.mock('@/features/auth/api/storage', () => ({
  clearTokens,
  getStoredSession,
  updateSessionTokens,
}));

const accountA = (): TestSession => ({
  version: 1,
  generation: 'generation-a',
  access: 'old-access',
  refresh: 'refresh-a',
  user: {member_uuid: 'a', email: 'a@example.com'},
  requires_profile_completion: false,
});

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

    await import('@/features/auth/api/client');
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

  it('retains the guarded generation when refresh returns a malformed success', async () => {
    axiosPost.mockResolvedValue({data: {}});
    const {refreshAccessToken} = await import('@/features/auth/api/client');

    await expect(refreshAccessToken('generation-a')).resolves.toBeNull();

    expect(clearTokens).not.toHaveBeenCalled();
    expect(storedSession).toEqual(accountA());
  });

  it('retains the guarded generation when refresh fails transiently', async () => {
    axiosPost.mockRejectedValue({response: {status: 503}});
    const {refreshAccessToken} = await import('@/features/auth/api/client');

    await expect(refreshAccessToken('generation-a')).resolves.toBeNull();

    expect(clearTokens).not.toHaveBeenCalled();
    expect(storedSession).toEqual(accountA());
  });

  it('does not mark the original 401 definitive after a refresh 5xx', async () => {
    axiosPost.mockRejectedValue({response: {status: 503}});
    const {isDefinitiveAuthFailure} = await import('@/features/auth/api/client');
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
    const {isDefinitiveAuthFailure} = await import('@/features/auth/api/client');
    const request = prepareRequest({headers: {}});
    if (!responseRejectedHandler) {
      throw new Error('Response interceptor was not registered');
    }
    const error = {config: request, response: {status: 401}};

    await expect(responseRejectedHandler(error)).rejects.toBe(error);

    expect(isDefinitiveAuthFailure(error)).toBe(true);
    expect(storedSession).toBeNull();
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

  it('passes fulfilled responses through the response interceptor untouched', async () => {
    if (!responseFulfilledHandler) {
      throw new Error('Response interceptor was not registered');
    }
    const response = {data: {ok: true}};
    expect(responseFulfilledHandler(response)).toBe(response);
  });

  it('returns null when refreshing without a stored session', async () => {
    storedSession = null;
    const {refreshAccessToken} = await import('@/features/auth/api/client');

    await expect(refreshAccessToken('generation-a')).resolves.toBeNull();
    expect(axiosPost).not.toHaveBeenCalled();
  });

  it('returns null when refreshing a different generation', async () => {
    const {refreshAccessToken} = await import('@/features/auth/api/client');

    await expect(refreshAccessToken('generation-other')).resolves.toBeNull();
    expect(axiosPost).not.toHaveBeenCalled();
  });

  it('treats a non-object refresh failure as transient', async () => {
    axiosPost.mockRejectedValue(null);
    const {refreshAccessToken} = await import('@/features/auth/api/client');

    await expect(refreshAccessToken('generation-a')).resolves.toBeNull();
    expect(clearTokens).not.toHaveBeenCalled();
    expect(storedSession).toEqual(accountA());
  });

  it('treats a refresh failure without a response as transient', async () => {
    axiosPost.mockRejectedValue({});
    const {refreshAccessToken} = await import('@/features/auth/api/client');

    await expect(refreshAccessToken('generation-a')).resolves.toBeNull();
    expect(clearTokens).not.toHaveBeenCalled();
    expect(storedSession).toEqual(accountA());
  });

  it('reports a changed session when a definitive refresh fails after a guard mismatch', async () => {
    axiosPost.mockRejectedValue({response: {status: 401}});
    const {refreshAccessToken} = await import('@/features/auth/api/client');

    const pending = refreshAccessToken('generation-a');
    storedSession = {...accountA(), generation: 'generation-b'};

    await expect(pending).resolves.toBeNull();
    expect(clearTokens).toHaveBeenCalled();
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

  it('treats a non-numeric refresh failure status as transient', async () => {
    axiosPost.mockRejectedValue({response: {status: 'oops'}});
    const {refreshAccessToken} = await import('@/features/auth/api/client');

    await expect(refreshAccessToken('generation-a')).resolves.toBeNull();
    expect(clearTokens).not.toHaveBeenCalled();
    expect(storedSession).toEqual(accountA());
  });

  it('reuses the previous refresh token when the refresh response omits it', async () => {
    axiosPost.mockResolvedValue({data: {access: 'new-access'}});
    const {refreshAccessToken} = await import('@/features/auth/api/client');

    await expect(refreshAccessToken('generation-a')).resolves.toMatchObject({
      access: 'new-access',
    });
    expect(updateSessionTokens).toHaveBeenCalledWith(
      {generation: 'generation-a', refresh: 'refresh-a'},
      {access: 'new-access', refresh: 'refresh-a'},
    );
  });

  it('does not touch headers when there is no session and no headers object', async () => {
    storedSession = null;
    const request = prepareRequest({} as TestRequest);
    expect(request).toEqual({});
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
      const {isDefinitiveAuthFailure} = await import('@/features/auth/api/client');
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
      const {isDefinitiveAuthFailure} = await import('@/features/auth/api/client');
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
