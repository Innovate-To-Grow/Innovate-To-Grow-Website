import {act, renderHook} from '@testing-library/react';
import {beforeEach, describe, expect, it, vi} from 'vitest';

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
});
