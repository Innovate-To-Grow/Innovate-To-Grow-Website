import {act, renderHook} from '@testing-library/react';
import {useState} from 'react';
import {beforeEach, describe, expect, it, vi} from 'vitest';

const apiMock = vi.hoisted(() => ({
  clearProfileCompletionRequired: vi.fn(),
  confirmPasswordChange: vi.fn(),
  confirmPasswordReset: vi.fn(),
  getProfile: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
  register: vi.fn(),
  requestEmailAuthCode: vi.fn(),
  requestLoginCode: vi.fn(),
  requestPasswordChangeCode: vi.fn(),
  requestPasswordReset: vi.fn(),
  resendRegistrationCode: vi.fn(),
  verifyEmailAuthCode: vi.fn(),
  verifyLoginCode: vi.fn(),
  verifyPasswordChangeCode: vi.fn(),
  verifyPasswordResetCode: vi.fn(),
  verifyRegistrationCode: vi.fn(),
  isAuthenticated: vi.fn(),
  updateStoredUser: vi.fn(),
}));

vi.mock('@/features/auth/api', () => apiMock);

import {useAuthActions} from '@/features/auth/components/context/useAuthActions';
import {AUTH_STATE_CHANGE_EVENT} from '@/features/auth/components/context/shared';
import type {User} from '@/features/auth/api';

const user: User = {
  id: 'user-1',
  email: 'member@example.com',
  first_name: 'Ada',
  last_name: 'Lovelace',
  profile_image: '',
  email_verified: true,
};

function useHarness(initialUser: User | null = null) {
  const [currentUser, setUser] = useState<User | null>(initialUser);
  const [requiresProfileCompletion, setRequiresProfileCompletion] = useState(false);
  const [error, setError] = useState<string | null>('existing');
  const [isLoading, setIsLoading] = useState(false);
  const actions = useAuthActions({
    setUser,
    setRequiresProfileCompletion,
    setError,
    setIsLoading,
  });
  return {actions, currentUser, error, isLoading, requiresProfileCompletion};
}

describe('useAuthActions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('applies successful auth responses and dispatches auth changes', async () => {
    const listener = vi.fn();
    window.addEventListener(AUTH_STATE_CHANGE_EVENT, listener);
    apiMock.login.mockResolvedValue({user, requires_profile_completion: true});

    const {result} = renderHook(() => useHarness());

    await act(async () => {
      await result.current.actions.login('member@example.com', 'password');
    });

    expect(result.current.currentUser).toEqual(user);
    expect(result.current.requiresProfileCompletion).toBe(true);
    expect(result.current.error).toBeNull();
    expect(result.current.isLoading).toBe(false);
    expect(listener).toHaveBeenCalledTimes(1);
    window.removeEventListener(AUTH_STATE_CHANGE_EVENT, listener);
  });

  it('sets a safe error message and resets loading when an action fails', async () => {
    apiMock.requestPasswordReset.mockRejectedValue({
      response: {status: 400, data: {email: ['Unknown email.']}},
    });

    const {result} = renderHook(() => useHarness());

    await act(async () => {
      await expect(result.current.actions.requestPasswordReset('bad@example.com')).rejects.toBeDefined();
    });

    expect(result.current.error).toBe('Unknown email.');
    expect(result.current.isLoading).toBe(false);

    act(() => result.current.actions.clearError());
    expect(result.current.error).toBeNull();
  });

  it('delegates register, code, and password actions to API helpers', async () => {
    apiMock.register.mockResolvedValue({message: 'registered'});
    apiMock.requestEmailAuthCode.mockResolvedValue({message: 'sent'});
    apiMock.requestLoginCode.mockResolvedValue({message: 'sent'});
    apiMock.resendRegistrationCode.mockResolvedValue({message: 'sent'});
    apiMock.verifyPasswordResetCode.mockResolvedValue({verification_token: 'reset-token'});
    apiMock.confirmPasswordReset.mockResolvedValue({message: 'reset'});
    apiMock.requestPasswordChangeCode.mockResolvedValue({message: 'sent'});
    apiMock.verifyPasswordChangeCode.mockResolvedValue({verification_token: 'change-token'});
    apiMock.confirmPasswordChange.mockResolvedValue({message: 'changed'});

    const {result} = renderHook(() => useHarness());

    await act(async () => {
      await result.current.actions.register('e', 'p', 'p', 'Ada', 'Lovelace', 'Org', 'CEO');
      await result.current.actions.requestEmailAuthCode('e', 'subscribe');
      await result.current.actions.requestLoginCode('e');
      await result.current.actions.resendRegistrationCode('e');
      await result.current.actions.verifyPasswordResetCode('e', '123456');
      await result.current.actions.confirmPasswordReset('e', 'token', 'new', 'new');
      await result.current.actions.requestPasswordChangeCode('e');
      await result.current.actions.verifyPasswordChangeCode('e', '654321');
      await result.current.actions.confirmPasswordChange('token', 'new', 'new');
    });

    expect(apiMock.register).toHaveBeenCalledWith('e', 'p', 'p', 'Ada', 'Lovelace', 'Org', 'CEO');
    expect(apiMock.requestEmailAuthCode).toHaveBeenCalledWith('e', 'subscribe');
    expect(apiMock.requestLoginCode).toHaveBeenCalledWith('e');
    expect(apiMock.resendRegistrationCode).toHaveBeenCalledWith('e');
    expect(apiMock.verifyPasswordResetCode).toHaveBeenCalledWith('e', '123456');
    expect(apiMock.confirmPasswordReset).toHaveBeenCalledWith('e', 'token', 'new', 'new');
    expect(apiMock.requestPasswordChangeCode).toHaveBeenCalledWith('e');
    expect(apiMock.verifyPasswordChangeCode).toHaveBeenCalledWith('e', '654321');
    expect(apiMock.confirmPasswordChange).toHaveBeenCalledWith('token', 'new', 'new');
  });

  it('applies verification auth responses', async () => {
    apiMock.verifyEmailAuthCode.mockResolvedValue({user, requires_profile_completion: false});
    apiMock.verifyLoginCode.mockResolvedValue({user, requires_profile_completion: false});
    apiMock.verifyRegistrationCode.mockResolvedValue({user, requires_profile_completion: false});

    const {result} = renderHook(() => useHarness());

    await act(async () => {
      await result.current.actions.verifyEmailAuthCode('e', '111111');
      await result.current.actions.verifyLoginCode('e', '222222');
      await result.current.actions.verifyRegistrationCode('e', '333333');
    });

    expect(apiMock.verifyEmailAuthCode).toHaveBeenCalledWith('e', '111111');
    expect(apiMock.verifyLoginCode).toHaveBeenCalledWith('e', '222222');
    expect(apiMock.verifyRegistrationCode).toHaveBeenCalledWith('e', '333333');
    expect(result.current.currentUser).toEqual(user);
  });

  it('clears local auth state on logout and profile-completion reset', () => {
    const listener = vi.fn();
    window.addEventListener(AUTH_STATE_CHANGE_EVENT, listener);
    const {result} = renderHook(() => useHarness(user));

    act(() => {
      result.current.actions.logout();
    });

    expect(apiMock.logout).toHaveBeenCalled();
    expect(result.current.currentUser).toBeNull();
    expect(result.current.requiresProfileCompletion).toBe(false);

    act(() => {
      result.current.actions.clearProfileCompletionRequirement();
    });

    expect(apiMock.clearProfileCompletionRequired).toHaveBeenCalled();
    expect(listener).toHaveBeenCalledTimes(2);
    window.removeEventListener(AUTH_STATE_CHANGE_EVENT, listener);
  });

  it('refreshes stored profile images only when authenticated and a user exists', async () => {
    apiMock.isAuthenticated.mockReturnValueOnce(false).mockReturnValueOnce(true).mockReturnValueOnce(true);
    apiMock.getProfile.mockResolvedValueOnce({profile_image: '/media/new.png'}).mockRejectedValueOnce(new Error('ignored'));

    const unauthenticated = renderHook(() => useHarness(user));
    await act(async () => {
      await unauthenticated.result.current.actions.refreshProfile();
    });
    expect(apiMock.getProfile).not.toHaveBeenCalled();

    const authenticated = renderHook(() => useHarness(user));
    await act(async () => {
      await authenticated.result.current.actions.refreshProfile();
    });
    expect(authenticated.result.current.currentUser?.profile_image).toBe('/media/new.png');
    expect(apiMock.updateStoredUser).toHaveBeenCalled();

    await act(async () => {
      await authenticated.result.current.actions.refreshProfile();
    });
    expect(authenticated.result.current.currentUser?.profile_image).toBe('/media/new.png');
  });
});
