import {afterEach, describe, expect, it, vi} from 'vitest';

import {
  AUTH_STATE_CHANGE_EVENT,
  defaultContextValue,
  dispatchAuthStateChange,
  getAuthErrorMessage,
  isSafeMessage,
} from '@/features/auth/components/context/shared';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('AUTH_STATE_CHANGE_EVENT', () => {
  it('uses the cross-root event name', () => {
    expect(AUTH_STATE_CHANGE_EVENT).toBe('i2g-auth-state-change');
  });
});

describe('dispatchAuthStateChange', () => {
  it('dispatches a CustomEvent with the auth state change name', () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
    dispatchAuthStateChange();

    expect(dispatchSpy).toHaveBeenCalledTimes(1);
    const event = dispatchSpy.mock.calls[0][0] as CustomEvent;
    expect(event).toBeInstanceOf(CustomEvent);
    expect(event.type).toBe(AUTH_STATE_CHANGE_EVENT);
  });
});

describe('defaultContextValue', () => {
  it('starts anonymous and initializing', () => {
    expect(defaultContextValue.user).toBeNull();
    expect(defaultContextValue.isAuthenticated).toBe(false);
    expect(defaultContextValue.isInitializing).toBe(true);
    expect(defaultContextValue.isLoading).toBe(true);
    expect(defaultContextValue.error).toBeNull();
  });

  it('provides no-op logout, refreshProfile, clearError, and completion helpers', async () => {
    expect(() => defaultContextValue.logout()).not.toThrow();
    await expect(defaultContextValue.refreshProfile()).resolves.toBeUndefined();
    expect(() => defaultContextValue.clearError()).not.toThrow();
    expect(defaultContextValue.clearProfileCompletionRequirement()).toBe(false);
  });

  it('makes the async auth actions reject as not implemented', async () => {
    await expect(defaultContextValue.login('a@b.c', 'password')).rejects.toThrow(
      'Not implemented',
    );
    await expect(
      defaultContextValue.register('a@b.c', 'x', 'x', 'A', 'B', 'Org'),
    ).rejects.toThrow('Not implemented');
  });
});

describe('isSafeMessage', () => {
  it('accepts short, HTML-free messages', () => {
    expect(isSafeMessage('hello')).toBe(true);
    expect(isSafeMessage('a'.repeat(300))).toBe(true);
  });

  it('rejects messages longer than 300 characters', () => {
    expect(isSafeMessage('a'.repeat(301))).toBe(false);
  });

  it('rejects HTML payloads', () => {
    expect(isSafeMessage('<div>hi</div>')).toBe(false);
    expect(isSafeMessage('<!DOCTYPE html>')).toBe(false);
    expect(isSafeMessage('<!doctype html>')).toBe(false);
  });
});

describe('getAuthErrorMessage', () => {
  it.each(['a plain string', 42, null, undefined])(
    'returns the default message for a non-object error (%s)',
    (err) => {
      expect(getAuthErrorMessage(err)).toBe(
        'An unexpected error occurred. Please try again.',
      );
    },
  );

  it('returns the default message when there is no response data', () => {
    expect(getAuthErrorMessage({})).toBe(
      'An unexpected error occurred. Please try again.',
    );
    expect(getAuthErrorMessage({response: {status: 400}})).toBe(
      'An unexpected error occurred. Please try again.',
    );
    expect(getAuthErrorMessage({response: {data: null}})).toBe(
      'An unexpected error occurred. Please try again.',
    );
  });

  it('joins safe array and string values from response data', () => {
    expect(
      getAuthErrorMessage({
        response: {
          data: {email: ['Already taken'], password: 'Too short'},
        },
      }),
    ).toBe('Already taken Too short');
  });

  it('skips non-string, HTML, and over-long values', () => {
    expect(
      getAuthErrorMessage({
        response: {
          data: {
            detail: ['<b>unsafe</b>', 42, {nested: true}, 'ok'],
          },
        },
      }),
    ).toBe('ok');
  });

  it('ignores a non-array string value that contains HTML', () => {
    expect(
      getAuthErrorMessage({response: {data: {detail: '<b>unsafe</b>'}}}),
    ).toBe('An unexpected error occurred. Please try again.');
  });

  it('returns the 4xx message when the status is a client error', () => {
    expect(
      getAuthErrorMessage({response: {status: 400, data: {detail: ['<b>x</b>']}}}),
    ).toBe('Request failed. Please check your input and try again.');
  });

  it('returns the 5xx message when the status is a server error', () => {
    expect(getAuthErrorMessage({response: {status: 500, data: {}}})).toBe(
      'A server error occurred. Please try again later.',
    );
  });

  it('returns the default message for a non-error status with no messages', () => {
    expect(getAuthErrorMessage({response: {status: 200, data: {}}})).toBe(
      'An unexpected error occurred. Please try again.',
    );
  });

  describe('a body that is not JSON (an edge, proxy or WAF answer)', () => {
    it('never spells a plain-text body out one character at a time', () => {
      const message = getAuthErrorMessage({response: {status: 429, data: 'Too Many Requests'}});

      expect(message).toBe('Request failed. Please check your input and try again.');
      expect(message).not.toMatch(/T o o/);
    });

    it('does not print an HTML error page', () => {
      expect(
        getAuthErrorMessage({response: {status: 502, data: '<html><body>Bad Gateway</body></html>'}}),
      ).toBe('A server error occurred. Please try again later.');
    });

    it('uses the default sentence for a text body that comes with no usable status', () => {
      expect(getAuthErrorMessage({response: {data: 'Blocked'}})).toBe(
        'An unexpected error occurred. Please try again.',
      );
    });

    it('still reads a JSON array body the way it always did', () => {
      expect(getAuthErrorMessage({response: {status: 400, data: ['Invalid code.']}})).toBe('Invalid code.');
    });
  });

  describe('a locked-out password sign-in (429, login_locked)', () => {
    const SERVER_DETAIL =
      'Too many failed sign-in attempts. Please try again later or sign in with an email code.';
    const locked = (data: Record<string, unknown>, status = 429) => ({response: {status, data}});

    it("shows the server's detail, which already points to the email code", () => {
      expect(getAuthErrorMessage(locked({detail: SERVER_DETAIL, code: 'login_locked'}))).toBe(SERVER_DETAIL);
    });

    it('shows whatever safe detail the server sent, not a copy of it', () => {
      expect(getAuthErrorMessage(locked({detail: 'Locked for now.', code: 'login_locked'}))).toBe(
        'Locked for now.',
      );
    });

    it.each<[string, Record<string, unknown>]>([
      ['no detail', {code: 'login_locked'}],
      ['a detail that is not text', {detail: 42, code: 'login_locked'}],
      ['an HTML detail', {detail: '<b>blocked</b>', code: 'login_locked'}],
      ['an over-long detail', {detail: 'x'.repeat(301), code: 'login_locked'}],
    ])('keeps the way out in view when the server sent %s', (_label, data) => {
      const message = getAuthErrorMessage(locked(data));

      expect(message).toBe(SERVER_DETAIL);
      expect(message).toMatch(/email code/);
    });

    it('is decided by the code only on a 429', () => {
      // Anything else that merely carries the word keeps the generic mapping.
      expect(getAuthErrorMessage(locked({code: 'login_locked'}, 400))).toBe(
        'Request failed. Please check your input and try again.',
      );
      expect(getAuthErrorMessage(locked({detail: 'Nope.', code: 'login_locked'}, 401))).toBe('Nope.');
    });
  });

  describe('every other 429 keeps its generic mapping', () => {
    const throttled = (data: Record<string, unknown>) => ({response: {status: 429, data}});

    it('shows a throttle detail as it came', () => {
      expect(
        getAuthErrorMessage(throttled({detail: 'Request was throttled. Expected available in 30 seconds.'})),
      ).toBe('Request was throttled. Expected available in 30 seconds.');
    });

    it('shows the detail of a destination cooldown or an SMS throttle, ignoring its machine fields', () => {
      expect(
        getAuthErrorMessage(
          throttled({detail: 'Please wait before requesting another code.', code: 'send_throttled', retry_after: 42}),
        ),
      ).toBe('Please wait before requesting another code.');
    });

    it('does not turn another code into the locked-out wording', () => {
      const message = getAuthErrorMessage(throttled({detail: 'Slow down.', code: 'verification_rate_limited'}));

      expect(message).toBe('Slow down.');
      expect(message).not.toMatch(/failed sign-in/i);
    });

    it('falls back to the client-error message when a 429 has nothing to show', () => {
      expect(getAuthErrorMessage(throttled({code: 'verification_rate_limited', retry_after: 5}))).toBe(
        'Request failed. Please check your input and try again.',
      );
    });
  });
});
