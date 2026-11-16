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
});
