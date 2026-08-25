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

  it('applies login state, loading state, and cross-root synchronization', async () => {
    authApi.login.mockResolvedValue({
      user,
      access: 'access-token',
      refresh: 'refresh-token',
      requires_profile_completion: true,
    });
    const setters = makeSetters();
    const eventListener = vi.fn();
    window.addEventListener('i2g-auth-state-change', eventListener);
    const {result} = renderHook(() => useAuthActions(setters));

    await act(async () => {
      await result.current.login('member@example.com', 'password');
    });

    expect(authApi.login).toHaveBeenCalledWith('member@example.com', 'password');
    expect(setters.setError).toHaveBeenCalledWith(null);
    expect(setters.setIsLoading.mock.calls).toEqual([[true], [false]]);
    expect(setters.setUser).toHaveBeenCalledWith(user);
    expect(setters.setRequiresProfileCompletion).toHaveBeenCalledWith(true);
    expect(eventListener).toHaveBeenCalledOnce();
    window.removeEventListener('i2g-auth-state-change', eventListener);
  });

  it('records API errors and always clears loading state', async () => {
    const error = new Error('Login unavailable');
    authApi.login.mockRejectedValue(error);
    const setters = makeSetters();
    const {result} = renderHook(() => useAuthActions(setters));

    await act(async () => {
      await expect(
        result.current.login('member@example.com', 'password'),
      ).rejects.toBe(error);
    });

    expect(setters.setError).toHaveBeenCalledWith(
      'An unexpected error occurred. Please try again.',
    );
    expect(setters.setIsLoading.mock.calls).toEqual([[true], [false]]);
    expect(setters.setUser).not.toHaveBeenCalled();
  });

  it('adapts the context email/code order to the code/email API order', async () => {
    authApi.verifyPasswordChangeCode.mockResolvedValue({
      message: 'ok',
      verification_token: 'verification-token',
    });
    const setters = makeSetters();
    const {result} = renderHook(() => useAuthActions(setters));

    await act(async () => {
      await result.current.verifyPasswordChangeCode(
        'member@example.com',
        '123456',
        'c742ef5b-e34f-491d-91f2-8ead9bc10401',
      );
    });

    expect(authApi.verifyPasswordChangeCode).toHaveBeenCalledWith(
      '123456',
      'member@example.com',
      'c742ef5b-e34f-491d-91f2-8ead9bc10401',
    );
  });

  it('logs out locally and clears profile completion state', () => {
    const setters = makeSetters();
    const eventListener = vi.fn();
    window.addEventListener('i2g-auth-state-change', eventListener);
    const {result} = renderHook(() => useAuthActions(setters));

    act(() => result.current.logout());

    expect(authApi.logout).toHaveBeenCalledOnce();
    expect(setters.setUser).toHaveBeenCalledWith(null);
    expect(setters.setRequiresProfileCompletion).toHaveBeenCalledWith(false);
    expect(eventListener).toHaveBeenCalledOnce();
    window.removeEventListener('i2g-auth-state-change', eventListener);
  });

  it('only clears profile completion when the persisted generation matches', () => {
    authApi.clearProfileCompletionRequired
      .mockReturnValueOnce(false)
      .mockReturnValueOnce(true);
    const setters = makeSetters();
    const {result} = renderHook(() => useAuthActions(setters));
    const guard = {generation: 'generation-1'};

    expect(result.current.clearProfileCompletionRequirement(guard)).toBe(false);
    expect(result.current.clearProfileCompletionRequirement(guard)).toBe(true);
    expect(setters.setRequiresProfileCompletion).toHaveBeenCalledOnce();
    expect(setters.setRequiresProfileCompletion).toHaveBeenCalledWith(false);
  });

  it('refreshes only the profile image for the captured session generation', async () => {
    authApi.getStoredSession.mockReturnValue({
      user,
      generation: 'generation-1',
    });
    authApi.getProfile.mockResolvedValue({profile_image: '/media/new.png'});
    authApi.updateStoredUser.mockImplementation((updater, generation) => {
      expect(generation).toBe('generation-1');
      return updater({...user, profile_image: '/media/old.png'});
    });
    const setters = makeSetters();
    const {result} = renderHook(() => useAuthActions(setters));

    await act(async () => result.current.refreshProfile());

    expect(setters.setUser).toHaveBeenCalledWith({
      ...user,
      profile_image: '/media/new.png',
    });
  });

  it('does not fetch a profile without a stored session', async () => {
    authApi.getStoredSession.mockReturnValue(null);
    const setters = makeSetters();
    const {result} = renderHook(() => useAuthActions(setters));

    await act(async () => result.current.refreshProfile());

    expect(authApi.getProfile).not.toHaveBeenCalled();
  });

  it('clears the error message', () => {
    const setters = makeSetters();
    const {result} = renderHook(() => useAuthActions(setters));

    act(() => result.current.clearError());

    expect(setters.setError).toHaveBeenCalledWith(null);
  });

  it('registers a new account with the supplied fields', async () => {
    authApi.register.mockResolvedValue({access: 'a', refresh: 'r', user});
    const setters = makeSetters();
    const {result} = renderHook(() => useAuthActions(setters));

    await act(async () => {
      await result.current.register('a@b.com', 'pw', 'pw', 'First', 'Last', 'Org', 'Title');
    });

    expect(authApi.register).toHaveBeenCalledWith('a@b.com', 'pw', 'pw', 'First', 'Last', 'Org', 'Title');
    expect(setters.setIsLoading.mock.calls).toEqual([[true], [false]]);
  });

  it('defaults the register title to an empty string', async () => {
    authApi.register.mockResolvedValue({access: 'a', refresh: 'r', user});
    const setters = makeSetters();
    const {result} = renderHook(() => useAuthActions(setters));

    await act(async () => {
      await result.current.register('a@b.com', 'pw', 'pw', 'First', 'Last', 'Org');
    });

    expect(authApi.register).toHaveBeenCalledWith('a@b.com', 'pw', 'pw', 'First', 'Last', 'Org', '');
  });

  it('requests an email code with the default login source', async () => {
    authApi.requestEmailAuthCode.mockResolvedValue({message: 'sent'});
    const setters = makeSetters();
    const {result} = renderHook(() => useAuthActions(setters));

    await act(async () => {
      await result.current.requestEmailAuthCode('a@b.com');
    });

    expect(authApi.requestEmailAuthCode).toHaveBeenCalledWith('a@b.com', 'login', undefined);
  });

  it('verifies an email auth code and applies the session', async () => {
    authApi.verifyEmailAuthCode.mockResolvedValue({
      access: 'a',
      refresh: 'r',
      user,
      requires_profile_completion: false,
    });
    const setters = makeSetters();
    const {result} = renderHook(() => useAuthActions(setters));

    await act(async () => {
      await result.current.verifyEmailAuthCode('a@b.com', '123456');
    });

    expect(authApi.verifyEmailAuthCode).toHaveBeenCalledWith('a@b.com', '123456');
    expect(setters.setUser).toHaveBeenCalledWith(user);
    expect(setters.setRequiresProfileCompletion).toHaveBeenCalledWith(false);
  });

  it('requests a phone code with default region and source', async () => {
    authApi.requestPhoneAuthCode.mockResolvedValue({message: 'sent'});
    const setters = makeSetters();
    const {result} = renderHook(() => useAuthActions(setters));

    await act(async () => {
      await result.current.requestPhoneAuthCode('2025550123');
    });

    expect(authApi.requestPhoneAuthCode).toHaveBeenCalledWith('2025550123', '1-US', 'login');
  });

  it('verifies a phone code and applies the session', async () => {
    authApi.verifyPhoneAuthCode.mockResolvedValue({
      access: 'a',
      refresh: 'r',
      user,
      requires_profile_completion: true,
    });
    const setters = makeSetters();
    const {result} = renderHook(() => useAuthActions(setters));

    await act(async () => {
      await result.current.verifyPhoneAuthCode('2025550123', '123456', '1-US', 'challenge');
    });

    expect(authApi.verifyPhoneAuthCode).toHaveBeenCalledWith('2025550123', '123456', '1-US', 'challenge');
    expect(setters.setRequiresProfileCompletion).toHaveBeenCalledWith(true);
  });

  it('requests a login code', async () => {
    authApi.requestLoginCode.mockResolvedValue({message: 'sent'});
    const setters = makeSetters();
    const {result} = renderHook(() => useAuthActions(setters));

    await act(async () => {
      await result.current.requestLoginCode('a@b.com');
    });

    expect(authApi.requestLoginCode).toHaveBeenCalledWith('a@b.com');
  });

  it('verifies a login code and applies the session', async () => {
    authApi.verifyLoginCode.mockResolvedValue({access: 'a', refresh: 'r', user});
    const setters = makeSetters();
    const {result} = renderHook(() => useAuthActions(setters));

    await act(async () => {
      await result.current.verifyLoginCode('a@b.com', '123456');
    });

    expect(authApi.verifyLoginCode).toHaveBeenCalledWith('a@b.com', '123456');
    expect(setters.setUser).toHaveBeenCalledWith(user);
  });

  it('verifies a registration code and applies the session', async () => {
    authApi.verifyRegistrationCode.mockResolvedValue({access: 'a', refresh: 'r', user});
    const setters = makeSetters();
    const {result} = renderHook(() => useAuthActions(setters));

    await act(async () => {
      await result.current.verifyRegistrationCode('a@b.com', '123456');
    });

    expect(authApi.verifyRegistrationCode).toHaveBeenCalledWith('a@b.com', '123456');
    expect(setters.setUser).toHaveBeenCalledWith(user);
  });

  it('resends a registration code', async () => {
    authApi.resendRegistrationCode.mockResolvedValue({message: 'resent'});
    const setters = makeSetters();
    const {result} = renderHook(() => useAuthActions(setters));

    await act(async () => {
      await result.current.resendRegistrationCode('a@b.com');
    });

    expect(authApi.resendRegistrationCode).toHaveBeenCalledWith('a@b.com');
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
