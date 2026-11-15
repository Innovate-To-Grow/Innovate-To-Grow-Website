import {vi} from 'vitest';

// Shared setup of the client.*.test.ts files. The auth client is driven through a fake axios instance whose
// interceptors the tests call directly, over a fake session storage. Each test file keeps its own captured
// interceptors and stored session (it reassigns them) and hands these factories the accessors.

export interface TestSession {
  version: 1;
  generation: string;
  access: string;
  refresh: string;
  user: {member_uuid: string; email: string};
  requires_profile_completion: boolean;
}

export interface TestRequest {
  headers: Record<string, string>;
  data?: unknown;
  [key: string]: unknown;
}

export type RequestFulfilledHandler = (config: TestRequest) => TestRequest;
export type ResponseFulfilledHandler = (response: unknown) => unknown;
export type ResponseRejectedHandler = (error: {
  config: TestRequest;
  response?: {status?: number};
}) => Promise<unknown>;

/** The axios instance call (a retried request) and `axios.post` (the token refresh). */
export function axiosMocks() {
  const retryRequest = vi.fn(async (request) => ({
    data: {ok: true},
    config: request,
  }));
  const axiosPost = vi.fn();
  return {retryRequest, axiosPost};
}

/** The fake axios module: `create()` returns `retryRequest`, whose interceptors hand their handlers to `capture`. */
export function mockAxiosModule(
  {retryRequest, axiosPost}: ReturnType<typeof axiosMocks>,
  capture: {
    request: (handler: RequestFulfilledHandler) => void;
    response: (fulfilled: ResponseFulfilledHandler, rejected: ResponseRejectedHandler) => void;
  },
) {
  const create = vi.fn(() => {
    const instance = retryRequest as typeof retryRequest & {
      interceptors: {
        request: {use: (handler: RequestFulfilledHandler) => void};
        response: {
          use: (
            fulfilled: ResponseFulfilledHandler,
            rejected: ResponseRejectedHandler,
          ) => void;
        };
      };
    };

    instance.interceptors = {
      request: {
        use: vi.fn((handler) => {
          capture.request(handler);
        }),
      },
      response: {
        use: vi.fn((fulfilled, rejected) => {
          capture.response(fulfilled, rejected);
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
}

/** The stored-session API, reading and writing the test file's stored session through `get` and `set`. */
export function storageMocks(get: () => TestSession | null, set: (session: TestSession | null) => void) {
  const clearTokens = vi.fn((guard?: {generation: string; refresh?: string}) => {
    const storedSession = get();
    if (
      guard &&
      (!storedSession ||
        storedSession.generation !== guard.generation ||
        (guard.refresh !== undefined &&
          storedSession.refresh !== guard.refresh))
    ) {
      return false;
    }
    set(null);
    return true;
  });
  const getStoredSession = vi.fn(() => get());
  const updateSessionTokens = vi.fn(
    (
      guard: {generation: string; refresh?: string},
      tokens: {access: string; refresh: string},
    ) => {
      const storedSession = get();
      if (
        !storedSession ||
        storedSession.generation !== guard.generation ||
        (guard.refresh !== undefined &&
          storedSession.refresh !== guard.refresh)
      ) {
        return null;
      }
      set({...storedSession, ...tokens});
      return get();
    },
  );
  return {clearTokens, getStoredSession, updateSessionTokens};
}

export const accountA = (): TestSession => ({
  version: 1,
  generation: 'generation-a',
  access: 'old-access',
  refresh: 'refresh-a',
  user: {member_uuid: 'a', email: 'a@example.com'},
  requires_profile_completion: false,
});

export const accessWithExpiry = (exp: number) =>
  `header.${btoa(JSON.stringify({exp}))}.signature`;
