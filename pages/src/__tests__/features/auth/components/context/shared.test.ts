import {afterEach, describe, expect, it, vi} from 'vitest';

import {
  AUTH_STATE_CHANGE_EVENT,
  defaultContextValue,
  dispatchAuthStateChange,
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
