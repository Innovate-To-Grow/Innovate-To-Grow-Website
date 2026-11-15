import {act, cleanup, renderHook} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

const authApi = vi.hoisted(() => ({
  clearProfileCompletionRequired: vi.fn(),
  confirmPasswordChange: vi.fn(),
  confirmPasswordReset: vi.fn(),
  getProfile: vi.fn(),
  getStoredSession: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
  register: vi.fn(),
  requestEmailAuthCode: vi.fn(),
  requestLoginCode: vi.fn(),
  requestPasswordChangeCode: vi.fn(),
  requestPasswordReset: vi.fn(),
  requestPhoneAuthCode: vi.fn(),
  resendRegistrationCode: vi.fn(),
  updateStoredUser: vi.fn(),
  verifyEmailAuthCode: vi.fn(),
  verifyLoginCode: vi.fn(),
  verifyPasswordChangeCode: vi.fn(),
  verifyPasswordResetCode: vi.fn(),
  verifyPhoneAuthCode: vi.fn(),
  verifyRegistrationCode: vi.fn(),
}));

vi.mock('@/features/auth/api', () => authApi);

import {useAuthActions} from '@/features/auth/components/context/useAuthActions';

const user = {
  id: '2dc36239-e6e4-4630-b341-a90442358aa7',
  email: 'member@example.com',
};

const makeSetters = () => ({
  setUser: vi.fn(),
  setRequiresProfileCompletion: vi.fn(),
  setError: vi.fn(),
  setIsLoading: vi.fn(),
});

describe('useAuthActions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it('requests a password reset code', async () => {
    authApi.requestPasswordReset.mockResolvedValue({message: 'sent', challenge_id: 'c'});
    const setters = makeSetters();
    const {result} = renderHook(() => useAuthActions(setters));

    await act(async () => {
      await result.current.requestPasswordReset('a@b.com');
    });

    expect(authApi.requestPasswordReset).toHaveBeenCalledWith('a@b.com');
  });

  it('verifies a password reset code', async () => {
    authApi.verifyPasswordResetCode.mockResolvedValue({verification_token: 't'});
    const setters = makeSetters();
    const {result} = renderHook(() => useAuthActions(setters));

    await act(async () => {
      await result.current.verifyPasswordResetCode('a@b.com', '123456', 'c');
    });

    expect(authApi.verifyPasswordResetCode).toHaveBeenCalledWith('a@b.com', '123456', 'c');
  });

  it('confirms a password reset', async () => {
    authApi.confirmPasswordReset.mockResolvedValue({message: 'done'});
    const setters = makeSetters();
    const {result} = renderHook(() => useAuthActions(setters));

    await act(async () => {
      await result.current.confirmPasswordReset('a@b.com', 'token', 'newpw', 'newpw');
    });

    expect(authApi.confirmPasswordReset).toHaveBeenCalledWith('a@b.com', 'token', 'newpw', 'newpw');
  });

  it('requests a password change code', async () => {
    authApi.requestPasswordChangeCode.mockResolvedValue({message: 'sent'});
    const setters = makeSetters();
    const {result} = renderHook(() => useAuthActions(setters));

    await act(async () => {
      await result.current.requestPasswordChangeCode('a@b.com');
    });

    expect(authApi.requestPasswordChangeCode).toHaveBeenCalledWith('a@b.com');
  });

  it('confirms a password change', async () => {
    authApi.confirmPasswordChange.mockResolvedValue({message: 'done'});
    const setters = makeSetters();
    const {result} = renderHook(() => useAuthActions(setters));

    await act(async () => {
      await result.current.confirmPasswordChange('token', 'newpw', 'newpw');
    });

    expect(authApi.confirmPasswordChange).toHaveBeenCalledWith('token', 'newpw', 'newpw');
  });

  it('exposes the password flows by name and keeps the actions object stable across renders', () => {
    const setters = makeSetters();
    const {result, rerender} = renderHook(() => useAuthActions(setters));
    const first = result.current;

    for (const name of [
      'requestPasswordReset',
      'verifyPasswordResetCode',
      'confirmPasswordReset',
      'requestPasswordChangeCode',
      'verifyPasswordChangeCode',
      'confirmPasswordChange',
    ] as const) {
      expect(first[name]).toBeTypeOf('function');
    }
    rerender();
    expect(result.current).toBe(first);
  });

  it('does not set the user when the profile refresh fails to persist', async () => {
    authApi.getStoredSession.mockReturnValue({user, generation: 'generation-1'});
    authApi.getProfile.mockResolvedValue({profile_image: '/media/new.png'});
    authApi.updateStoredUser.mockReturnValue(null);
    const setters = makeSetters();
    const {result} = renderHook(() => useAuthActions(setters));

    await act(async () => result.current.refreshProfile());

    expect(setters.setUser).not.toHaveBeenCalled();
  });
});
