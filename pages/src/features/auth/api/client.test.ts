import {beforeEach, describe, expect, it, vi} from 'vitest';

let responseRejectedHandler: ((error: {config: Record<string, unknown>; response?: {status?: number}}) => Promise<unknown>) | null = null;

const retryRequest = vi.fn(async (request) => ({data: {ok: true}, config: request}));
const axiosPost = vi.fn();

vi.mock('axios', () => {
  const create = vi.fn(() => {
    const instance = retryRequest as typeof retryRequest & {
      interceptors: {
        request: {use: (handler: unknown) => void};
        response: {use: (fulfilled: unknown, rejected: typeof responseRejectedHandler) => void};
      };
    };

    instance.interceptors = {
      request: {
        use: vi.fn(),
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

const clearTokens = vi.fn();
const getAccessToken = vi.fn(() => 'old-access');
const getRefreshToken = vi.fn(() => 'refresh-token');
const getStoredUser = vi.fn(() => ({email: 'member@example.com'}));
const setTokens = vi.fn();

vi.mock('./storage', () => ({
  clearTokens,
  getAccessToken,
  getRefreshToken,
  getStoredUser,
  setTokens,
}));

describe('auth refresh dedupe', () => {
  beforeEach(async () => {
    vi.resetModules();
    responseRejectedHandler = null;
    retryRequest.mockClear();
    axiosPost.mockReset();
    clearTokens.mockReset();
    getAccessToken.mockClear();
    getRefreshToken.mockClear();
    getStoredUser.mockClear();
    setTokens.mockReset();

    await import('./client');
  });

  it('deduplicates concurrent refresh requests across parallel 401 responses', async () => {
    let resolveRefresh!: (value: {data: {access: string; refresh: string}}) => void;
    const refreshPromise = new Promise<{data: {access: string; refresh: string}}>((resolve) => {
      resolveRefresh = resolve;
    });
    axiosPost.mockReturnValue(refreshPromise);

    const firstRequest = {headers: {}, _retry: false};
    const secondRequest = {headers: {}, _retry: false};

    if (!responseRejectedHandler) {
      throw new Error('Response interceptor was not registered');
    }

    const firstRetry = responseRejectedHandler({config: firstRequest, response: {status: 401}});
    const secondRetry = responseRejectedHandler({config: secondRequest, response: {status: 401}});

    expect(axiosPost).toHaveBeenCalledTimes(1);

    resolveRefresh({data: {access: 'new-access', refresh: 'new-refresh'}});

    await Promise.all([firstRetry, secondRetry]);

    expect(setTokens).toHaveBeenCalledTimes(1);
    expect(retryRequest).toHaveBeenCalledTimes(2);
    expect(firstRequest.headers).toEqual({Authorization: 'Bearer new-access'});
    expect(secondRequest.headers).toEqual({Authorization: 'Bearer new-access'});
    expect(clearTokens).not.toHaveBeenCalled();
  });
});
