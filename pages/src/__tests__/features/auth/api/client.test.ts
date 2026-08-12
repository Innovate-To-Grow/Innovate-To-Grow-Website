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
        use: vi.fn((_fulfilled, rejected) => {
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
});
