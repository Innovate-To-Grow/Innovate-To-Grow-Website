import {afterEach, describe, expect, it, vi} from 'vitest';
import {
  captureAuthCallbackParams,
  clearAuthCallbackParams,
  readAuthCallbackParams,
} from '@/features/auth/api/callbackParams';

describe('auth callback parameter handoff', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
    delete (
      window as Window &
        typeof globalThis & {
          __i2gCallbackHandoff?: unknown;
        }
    ).__i2gCallbackHandoff;
    window.history.replaceState({}, '', '/');
  });

  it('captures and immediately scrubs legacy query credentials', () => {
    window.history.replaceState(
      {},
      '',
      '/impersonate-login?token=query-secret&campaign=spring#section',
    );

    captureAuthCallbackParams();

    expect(window.location.href).not.toContain('query-secret');
    expect(window.location.search).toBe('?campaign=spring');
    expect(window.location.hash).toBe('#section');
    expect(
      readAuthCallbackParams(
        'impersonate-login',
        new URLSearchParams(),
      ).get('token'),
    ).toBe('query-secret');
  });

  it('captures fragment credentials without leaving them in the URL', () => {
    window.history.replaceState(
      {},
      '',
      '/login-link#token=fragment-secret&campaign=spring',
    );

    captureAuthCallbackParams();

    expect(window.location.hash).toBe('#campaign=spring');
    expect(
      readAuthCallbackParams('login-link', new URLSearchParams()).get('token'),
    ).toBe('fragment-secret');
  });

  it('uses the non-enumerable memory handoff when sessionStorage is denied', () => {
    const originalStorage = window.sessionStorage;
    Object.defineProperty(window, 'sessionStorage', {
      configurable: true,
      value: {
        setItem: () => {
          throw new DOMException('denied');
        },
      },
    });
    window.history.replaceState({}, '', '/unsubscribe-login#token=private');

    try {
      captureAuthCallbackParams();
    } finally {
      Object.defineProperty(window, 'sessionStorage', {
        configurable: true,
        value: originalStorage,
      });
    }

    const descriptor = Object.getOwnPropertyDescriptor(
      window,
      '__i2gCallbackHandoff',
    );
    expect(descriptor?.enumerable).toBe(false);
    expect(
      readAuthCallbackParams(
        'unsubscribe-login',
        new URLSearchParams(),
      ).get('token'),
    ).toBe('private');
    expect(window.location.hash).toBe('');
  });

  it('reads an early-captured route-specific sessionStorage record', () => {
    sessionStorage.setItem(
      'i2g_callback_params:impersonate-login',
      JSON.stringify({
        capturedAt: Date.now(),
        params: {token: 'stored-secret'},
      }),
    );

    const params = readAuthCallbackParams(
      'impersonate-login',
      new URLSearchParams(),
    );
    expect(params.get('token')).toBe('stored-secret');

    clearAuthCallbackParams('impersonate-login');
    expect(
      sessionStorage.getItem('i2g_callback_params:impersonate-login'),
    ).toBeNull();
  });

  it('accepts fragment callback parameters when no stored handoff exists', () => {
    window.history.replaceState(
      {},
      '',
      '/email-auth-link#flow=auth&source=login&email=member%40example.com&code=123456',
    );

    const params = readAuthCallbackParams(
      'email-auth-link',
      new URLSearchParams(),
    );
    expect(params.get('flow')).toBe('auth');
    expect(params.get('source')).toBe('login');
    expect(params.get('email')).toBe('member@example.com');
    expect(params.get('code')).toBe('123456');
  });

  it('reads and clears the memory handoff used when storage is denied', () => {
    (
      window as Window &
        typeof globalThis & {
          __i2gCallbackHandoff?: Record<string, unknown>;
        }
    ).__i2gCallbackHandoff = {
      'login-link': {
        capturedAt: Date.now(),
        params: {token: 'memory-token'},
      },
    };

    expect(
      readAuthCallbackParams(
        'login-link',
        new URLSearchParams(),
      ).get('token'),
    ).toBe('memory-token');

    clearAuthCallbackParams('login-link');
    expect(
      (
        window as Window &
          typeof globalThis & {
            __i2gCallbackHandoff?: unknown;
          }
      ).__i2gCallbackHandoff,
    ).toBeUndefined();
  });

  it('rejects stale callback records', () => {
    sessionStorage.setItem(
      'i2g_callback_params:login-link',
      JSON.stringify({
        capturedAt: Date.now() - 16 * 60 * 1000,
        params: {token: 'expired-secret'},
      }),
    );

    expect(
      readAuthCallbackParams('login-link', new URLSearchParams()).get(
        'token',
      ),
    ).toBeNull();
  });
});
