import {describe, expect, it, vi} from 'vitest';

import {
  AUTH_STATE_CHANGE_EVENT,
  defaultContextValue,
  dispatchAuthStateChange,
  getAuthErrorMessage,
  isSafeMessage,
} from '@/features/auth/components/context/shared';

describe('auth context shared helpers', () => {
  it('dispatches the shared auth state change event', () => {
    const listener = vi.fn();
    window.addEventListener(AUTH_STATE_CHANGE_EVENT, listener);

    dispatchAuthStateChange();

    expect(listener).toHaveBeenCalledTimes(1);
    window.removeEventListener(AUTH_STATE_CHANGE_EVENT, listener);
  });

  it('classifies user-displayable messages conservatively', () => {
    expect(isSafeMessage('Short message')).toBe(true);
    expect(isSafeMessage('<strong>Injected</strong>')).toBe(false);
    expect(isSafeMessage('<!DOCTYPE html><html></html>')).toBe(false);
    expect(isSafeMessage('x'.repeat(301))).toBe(false);
  });

  it('extracts safe backend validation messages', () => {
    expect(
      getAuthErrorMessage({
        response: {
          status: 400,
          data: {
            email: ['Enter a valid email.'],
            password: 'Password is too short.',
            ignored: ['<script>alert(1)</script>'],
          },
        },
      }),
    ).toBe('Enter a valid email. Password is too short.');
  });

  it('uses status-aware fallback messages', () => {
    expect(getAuthErrorMessage(null)).toBe('An unexpected error occurred. Please try again.');
    expect(getAuthErrorMessage({response: {status: 404, data: {}}})).toBe('Request failed. Please check your input and try again.');
    expect(getAuthErrorMessage({response: {status: 500, data: {}}})).toBe('A server error occurred. Please try again later.');
    expect(getAuthErrorMessage({response: {data: {detail: '<html>bad</html>'}}})).toBe('An unexpected error occurred. Please try again.');
  });

  it('default async context actions reject when called outside a provider', async () => {
    await expect(defaultContextValue.login('a', 'b')).rejects.toThrow('Not implemented');
    expect(defaultContextValue.logout()).toBeUndefined();
    await expect(defaultContextValue.refreshProfile()).resolves.toBeUndefined();
  });
});
